"""VOLTRAN Yürütme Motoru (Execution Engine) — Mod orkestrasyonu ve alt süreç yönetimi."""

from __future__ import annotations

import asyncio
import time
from uuid import uuid4

from voltran.models import (
    CouncilSynthesis,
    ExecutionMode,
    ExecutionReport,
    ExecutionStatus,
    ProviderExecution,
    ProviderTask,
    SubTask,
    TaskPlan,
    TaskResult,
)
from voltran.providers import ProviderAdapter, default_registry


class ExecutionEngine:
    """Alt görevleri planlanan modlara göre koordine eder ve yürütür."""

    def __init__(self, registry: dict[str, ProviderAdapter] | None = None) -> None:
        self.registry = registry if registry is not None else default_registry()

    async def execute_plan(
        self,
        prompt: str,
        plan: TaskPlan,
        *,
        dry_run: bool = False,
    ) -> ExecutionReport:
        started = time.monotonic()
        run_id = uuid4().hex[:12]

        # Bağlam dosyasını oku (varsa)
        context: str | None = None
        if plan.context_file is not None and plan.context_file.is_file():
            try:
                context = plan.context_file.read_text(encoding="utf-8", errors="replace")
            except OSError as exc:
                context = f"[Bağlam dosyası okunamadı: {exc}]"

        if dry_run:
            executions: list[ProviderExecution] = []
            for st in plan.subtasks:
                provider_key = st.assigned_provider or "bilinmeyen"
                executions.append(
                    ProviderExecution(
                        run_id=f"dry-{st.subtask_id}",
                        provider=provider_key,
                        status=ExecutionStatus.SUCCESS,
                        duration_ms=0,
                        result=TaskResult(
                            summary=(
                                f"[Dry Run] Görev '{st.purpose}' {provider_key} "
                                "modeline yönlendirildi."
                            ),
                            status="simulated",
                            metadata={"role": st.role},
                        ),
                    )
                )
            dry_summary = (
                "[Kuru Çalışma / Dry Run] Görev gerçek modellere gönderilmedi.\n"
                f"Seçilen mod: {plan.mode.value}\n"
                f"Gerekçe: {plan.reasoning}"
            )
            return ExecutionReport(
                run_id=run_id,
                task_prompt=prompt,
                mode=plan.mode,
                plan=plan,
                executions=executions,
                final_summary=dry_summary,
                total_duration_ms=0,
            )

        match plan.mode:
            case ExecutionMode.COUNCIL:
                report = await self._execute_council(run_id, prompt, plan, context, started)
            case _:
                report = await self._execute_single_or_expert(
                    run_id, prompt, plan, context, started
                )

        return report

    async def _execute_single_or_expert(
        self,
        run_id: str,
        prompt: str,
        plan: TaskPlan,
        context: str | None,
        started: float,
    ) -> ExecutionReport:
        executions: list[ProviderExecution] = []
        final_summary = ""
        next_step: str | None = None

        for st in plan.subtasks:
            provider_key = st.assigned_provider or "codex"
            adapter = self.registry.get(provider_key)
            if adapter is None:
                executions.append(
                    ProviderExecution(
                        run_id=st.subtask_id,
                        provider=provider_key,
                        status=ExecutionStatus.FAILED,
                        duration_ms=0,
                        error=f"Sağlayıcı adaptörü '{provider_key}' bulunamadı.",
                    )
                )
                continue

            task = ProviderTask(
                task_id=st.subtask_id,
                prompt=prompt,
                role=st.role,
                purpose=st.purpose,
                model=st.model,
            )
            execution = await adapter.execute(task, context, plan.policy)
            if execution.result:
                execution.result.metadata["role"] = st.role
                execution.result.metadata["purpose"] = st.purpose
            executions.append(execution)

            if execution.status == ExecutionStatus.SUCCESS and execution.result:
                final_summary = execution.result.summary
                if execution.result.risks:
                    next_step = f"Riskleri gözden geçirin: {', '.join(execution.result.risks)}"
            else:
                final_summary = f"Çalıştırma başarısız oldu: {execution.error}"

        total_duration = max(0, round((time.monotonic() - started) * 1000))
        return ExecutionReport(
            run_id=run_id,
            task_prompt=prompt,
            mode=plan.mode,
            plan=plan,
            executions=executions,
            final_summary=final_summary or "Herhangi bir sonuç üretilemedi.",
            next_step_recommendation=next_step or "Çıktıyı doğrulayın ve sonraki göreve geçin.",
            total_duration_ms=total_duration,
        )

    async def _execute_council(
        self,
        run_id: str,
        prompt: str,
        plan: TaskPlan,
        context: str | None,
        started: float,
    ) -> ExecutionReport:
        """Council modunda bağımsız uzmanları paralel çalıştırıp hakem turuyla sentezler."""

        async def _run_subtask(subtask: SubTask) -> ProviderExecution:
            provider_key = subtask.assigned_provider or "codex"
            adapter = self.registry.get(provider_key)
            if adapter is None:
                return ProviderExecution(
                    run_id=subtask.subtask_id,
                    provider=provider_key,
                    status=ExecutionStatus.FAILED,
                    duration_ms=0,
                    error=f"Sağlayıcı adaptörü '{provider_key}' bulunamadı.",
                )
            task = ProviderTask(
                task_id=subtask.subtask_id,
                prompt=prompt,
                role=subtask.role,
                purpose=subtask.purpose,
                model=subtask.model,
            )
            res = await adapter.execute(task, context, plan.policy)
            if res.result:
                res.result.metadata["role"] = subtask.role
                res.result.metadata["purpose"] = subtask.purpose
            return res

        tasks = [_run_subtask(st) for st in plan.subtasks]
        raw_results = await asyncio.gather(*tasks, return_exceptions=True)

        executions: list[ProviderExecution] = []
        for idx, res in enumerate(raw_results):
            if isinstance(res, BaseException):
                st = plan.subtasks[idx]
                executions.append(
                    ProviderExecution(
                        run_id=st.subtask_id,
                        provider=st.assigned_provider or "unknown",
                        status=ExecutionStatus.FAILED,
                        duration_ms=0,
                        error=f"Beklenmeyen adaptör hatası: {type(res).__name__}: {res}",
                    )
                )
            else:
                executions.append(res)

        successful = [e for e in executions if e.status == ExecutionStatus.SUCCESS and e.result]
        synthesis: CouncilSynthesis

        if len(successful) >= 2:
            # 2. Tur: Hakem (Judge) çağrısı ile gerçek eleştiri ve sentez
            judge_key = next(
                (k for k in ("claude", "codex", "google") if k in self.registry),
                successful[0].provider,
            )
            judge_adapter = self.registry.get(judge_key)

            candidate_sections: list[str] = []
            for i, e in enumerate(successful, 1):
                role_name = (
                    e.result.metadata.get("role", f"Uzman {i}") if e.result else f"Uzman {i}"
                )
                sol = e.result.summary if e.result else ""
                candidate_sections.append(f"### {role_name} ({e.provider.upper()}) ÇÖZÜMÜ:\n{sol}")

            judge_input = (
                f"GÖREV:\n{prompt}\n\n"
                "Aşağıda bağımsız uzmanların bu göreve sundukları aday çözümler yer almaktadır:\n\n"
                + "\n\n---\n\n".join(candidate_sections)
                + "\n\n"
                "Lütfen konsey hakemi olarak bu çözümleri tarafsızca değerlendir:\n"
                "1. Uzmanların ortak uzlaştığı noktaları belirt.\n"
                "2. Çelişen veya farklılaşan önerileri ve riskleri tespit et.\n"
                "3. İki çözümün güçlü yönlerini birleştirerek tek, "
                "eksiksiz bir sentez nihai sonuç oluştur."
            )

            judge_task = ProviderTask(
                prompt=judge_input,
                role="Konsey Hakemi ve Sentezci",
                purpose=(
                    "Bağımsız uzman çözümlerini eleştirerek ortak konsensüs ve "
                    "nihai sentezi oluştur."
                ),
            )

            judge_execution: ProviderExecution | None = None
            if judge_adapter is not None:
                try:
                    judge_execution = await judge_adapter.execute(judge_task, context, plan.policy)
                except Exception:
                    judge_execution = None

            if (
                judge_execution is not None
                and judge_execution.status == ExecutionStatus.SUCCESS
                and judge_execution.result
            ):
                executions.append(judge_execution)
                final_summary = judge_execution.result.summary
                synthesis = CouncilSynthesis(
                    consensus=[
                        "Bağımsız uzman çözümleri incelendi ve ortak doğrular sentezlendi.",
                        f"Hakem incelemesi: {judge_key.capitalize()}",
                    ],
                    disagreements=[
                        (
                            "Uzmanlar arasındaki alternatif yaklaşım ve yöntem "
                            "farkları hakem tarafından çözümlendi."
                        ),
                    ],
                    confidence_score=0.90,
                    confidence_rationale=(
                        f"Çözümler {len(successful)} bağımsız model tarafından üretildi ve "
                        f"{judge_key.capitalize()} hakemi tarafından sentezlendi."
                    ),
                )
            else:
                # Hakem modeli yoksa şeffaf karşılaştırma ve dürüst güven skoru
                final_summary = "\n\n---\n\n".join(candidate_sections)
                synthesis = CouncilSynthesis(
                    consensus=["İki bağımsız uzman aday çözümü başarıyla toplandı."],
                    disagreements=[
                        "Uzman aday çözümleri doğrudan karşılaştırmanız için yukarıda sunulmuştur.",
                    ],
                    confidence_score=0.75,
                    confidence_rationale=(
                        "İki bağımsız çözüm üretildi, ek hakem turu çalıştırılmadan ham sunuldu."
                    ),
                )
        elif len(successful) == 1:
            res = successful[0].result
            final_summary = res.summary if res else ""
            synthesis = CouncilSynthesis(
                consensus=["Tek bir model başarıyla sonuç üretebildi."],
                disagreements=["Diğer model çağrısı başarısız oldu veya zaman aşımına uğradı."],
                confidence_score=0.60,
                confidence_rationale="Yalnızca tek model çıktısı mevcut (kısmi başarı).",
            )
        else:
            errors = [e.error or "Bilinmeyen hata" for e in executions]
            final_summary = (
                "Konsey modellerinin hiçbiri geçerli bir yanıt üretemedi:\n" + "\n".join(errors)
            )
            synthesis = CouncilSynthesis(
                confidence_score=0.0,
                confidence_rationale="Tüm sağlayıcı çağrıları başarısız oldu.",
            )

        total_duration = max(0, round((time.monotonic() - started) * 1000))
        return ExecutionReport(
            run_id=run_id,
            task_prompt=prompt,
            mode=plan.mode,
            plan=plan,
            executions=list(executions),
            final_summary=final_summary,
            synthesis=synthesis,
            next_step_recommendation=(
                "Modeller arasındaki olası farklılıkları karşılaştırarak en uygun çözümü seçin."
            ),
            total_duration_ms=total_duration,
        )
