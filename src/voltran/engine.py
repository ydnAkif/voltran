"""VOLTRAN Yürütme Motoru (Execution Engine) — Mod orkestrasyonu ve alt süreç yönetimi."""

from __future__ import annotations

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
        """Sağlayıcıları ortak transkript üzerinden, tur bazlı olarak birlikte çalıştırır."""

        async def _run_subtask(
            subtask: SubTask,
            *,
            round_number: int,
            transcript: str,
        ) -> ProviderExecution:
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
                instructions=(
                    "ORTAK ÇALIŞMA PROTOKOLÜ:\n"
                    f"Bu, konsey görüşmesinin {round_number}. turudur. "
                    "Aşağıdaki ortak konuşmayı dikkatle oku; diğer çalışma ortaklarının "
                    "fikirlerine doğrudan yanıt ver, katıldığın ve itiraz ettiğin noktaları "
                    "belirt, eksikleri tamamla ve ekibi uygulanabilir tek bir sonuca yaklaştır. "
                    "Önceki cevapları yalnızca tekrar etme.\n\n"
                    f"ORTAK KONUŞMA:\n{transcript or '[Henüz mesaj yok]'}"
                ),
            )
            res = await adapter.execute(task, context, plan.policy)
            if res.result:
                res.result.metadata["role"] = subtask.role
                res.result.metadata["purpose"] = subtask.purpose
                res.result.metadata["round"] = round_number
            return res

        # İki tur kullanılır: ilk turda görüşler oluşur; ikinci turda her sağlayıcı,
        # diğerlerinin mesajlarını da görerek ortak çözümü geliştirir.
        executions: list[ProviderExecution] = []
        transcript_parts: list[str] = []
        for round_number in (1, 2):
            for st in plan.subtasks:
                try:
                    execution = await _run_subtask(
                        st,
                        round_number=round_number,
                        transcript="\n\n".join(transcript_parts),
                    )
                except Exception as exc:
                    execution = ProviderExecution(
                        run_id=st.subtask_id,
                        provider=st.assigned_provider or "unknown",
                        status=ExecutionStatus.FAILED,
                        duration_ms=0,
                        error=f"Beklenmeyen adaptör hatası: {type(exc).__name__}: {exc}",
                    )
                executions.append(execution)
                if execution.status == ExecutionStatus.SUCCESS and execution.result:
                    # Ortak bağlamın kontrolsüz büyümesini engelle; tam çıktı raporda kalır.
                    excerpt = execution.result.summary[:20_000]
                    transcript_parts.append(
                        f"### Tur {round_number} — {st.role} "
                        f"({execution.provider.upper()})\n{excerpt}"
                    )

        successful = [e for e in executions if e.status == ExecutionStatus.SUCCESS and e.result]
        successful_providers = {e.provider for e in successful}
        synthesis: CouncilSynthesis

        if len(successful_providers) >= 2:
            # Son konuşmacı, tüm ortak transkripti görmüş durumdadır ve ekip adına
            # karar kaydı üretir. Bu bir bağımsız hakem değil, ortak çalışmanın son adımıdır.
            finalizer_execution: ProviderExecution | None = None
            finalizer_key = successful[-1].provider
            finalizer = self.registry.get(finalizer_key)
            if finalizer is not None:
                finalizer_task = ProviderTask(
                    prompt=prompt,
                    role="Konsey kolaylaştırıcısı",
                    purpose="Ortak çalışmadan tek ve uygulanabilir nihai sonuç üret.",
                    instructions=(
                        "Aşağıdaki ortak görüşme Claude, Codex ve Antigravity'nin birbirlerinin "
                        "fikirlerine yanıt verdiği çalışma kaydıdır. Ekibin vardığı uzlaşıyı, "
                        "çözülemeyen görüş ayrılıklarını, riskleri ve önerilen eylemleri tek bir "
                        "nihai cevapta sentezle. Yeni ve bağlantısız bir çözüm üretme.\n\n"
                        "ORTAK KONUŞMA:\n" + "\n\n".join(transcript_parts)
                    ),
                )
                try:
                    finalizer_execution = await finalizer.execute(
                        finalizer_task, context, plan.policy
                    )
                except Exception:
                    finalizer_execution = None

            if (
                finalizer_execution is not None
                and finalizer_execution.status == ExecutionStatus.SUCCESS
                and finalizer_execution.result
            ):
                executions.append(finalizer_execution)
                final_summary = finalizer_execution.result.summary
            else:
                last_result = successful[-1].result
                assert last_result is not None
                final_summary = last_result.summary

            provider_count = len(successful_providers)
            synthesis = CouncilSynthesis(
                consensus=[
                    f"{provider_count} sağlayıcı ortak transkript üzerinde iki tur çalıştı."
                ],
                disagreements=[
                    "Nihai metinde belirtilen açık görüş ayrılıkları kullanıcı "
                    "değerlendirmesine sunuldu."
                ],
                confidence_score=0.90 if provider_count >= 3 else 0.75,
                confidence_rationale=(
                    f"{provider_count} farklı sağlayıcı birbirlerinin mesajlarını görerek "
                    "ortak çözümü geliştirdi."
                ),
            )
        elif len(successful) >= 1:
            res = successful[0].result
            final_summary = res.summary if res else ""
            synthesis = CouncilSynthesis(
                consensus=["Tek bir model başarıyla sonuç üretebildi."],
                disagreements=["Diğer çalışma ortakları başarısız oldu veya zaman aşımına uğradı."],
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
                "Konseyin ortak kararını doğrulayın ve önerilen eylemleri uygulayın."
            ),
            total_duration_ms=total_duration,
        )
