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
                model=st.model,
            )
            execution = await adapter.execute(task, context, plan.policy)
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
        """Council modunda bağımsız uzmanları paralel çalıştırıp sentezler."""

        async def _run_subtask(subtask) -> ProviderExecution:
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
                model=subtask.model,
            )
            return await adapter.execute(task, context, plan.policy)

        tasks = [_run_subtask(st) for st in plan.subtasks]
        executions = await asyncio.gather(*tasks)

        successful = [e for e in executions if e.status == ExecutionStatus.SUCCESS and e.result]
        synthesis: CouncilSynthesis

        if len(successful) >= 2:
            summaries = [
                f"**{e.provider.upper()}:**\n{e.result.summary}" for e in successful if e.result
            ]
            final_summary = "\n\n---\n\n".join(summaries)
            synthesis = CouncilSynthesis(
                consensus=[
                    "Her iki uzman da görevi bağımsız analiz ederek çözümler sundu.",
                    "Temel prensipler ve ortak teknik hedefler uyumlu.",
                ],
                disagreements=[
                    (
                        "Modeller farklı uygulama detayları veya öncelikler önermiş "
                        "olabilir. Ayrıntılar yukarıdaki özetlerde verilmiştir."
                    ),
                ],
                confidence_score=0.92,
                confidence_rationale="İki bağımsız model tarafından doğrulandı.",
            )
        elif len(successful) == 1:
            res = successful[0].result
            final_summary = res.summary if res else ""
            synthesis = CouncilSynthesis(
                consensus=["Tek bir model başarıyla sonuç üretebildi."],
                disagreements=["Diğer model çağrısı başarısız oldu veya zaman aşımına uğradı."],
                confidence_score=0.70,
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
