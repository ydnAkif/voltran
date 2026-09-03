"""VOLTRAN Yürütme Motoru (Execution Engine) — Mod orkestrasyonu ve alt süreç yönetimi."""

from __future__ import annotations

import time
from pathlib import Path
from uuid import uuid4

from voltran.collaboration import AgentRole, CollaborationRuntime
from voltran.hcom_client import HcomClientError
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
from voltran.supervisor import (
    CollaborationSupervisor,
    SupervisionStatus,
    SupervisorPolicy,
)


class ExecutionEngine:
    """Alt görevleri planlanan modlara göre koordine eder ve yürütür."""

    def __init__(
        self,
        registry: dict[str, ProviderAdapter] | None = None,
        collaboration_runtime: CollaborationRuntime | None = None,
        supervisor: CollaborationSupervisor | None = None,
    ) -> None:
        self.registry = registry if registry is not None else default_registry()
        self.collaboration_runtime = collaboration_runtime or CollaborationRuntime()
        self.supervisor = supervisor

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
        """Sağlayıcıları kalıcı hcom oturumlarında canlı olarak birlikte çalıştırır."""

        if not self.collaboration_runtime.is_available():
            return self._council_failure_report(
                run_id=run_id,
                prompt=prompt,
                plan=plan,
                started=started,
                error=(
                    "hcom işbirliği motoru bulunamadı. Council modu için kurun: "
                    "brew install aannoo/hcom/hcom"
                ),
            )

        roles = [
            AgentRole(
                name=f"vt-{run_id[:6]}-{index}",
                provider=subtask.assigned_provider or "codex",
                role=subtask.role,
                purpose=subtask.purpose,
                model=subtask.model,
            )
            for index, subtask in enumerate(plan.subtasks, start=1)
        ]
        working_dir = plan.context_file.parent if plan.context_file else Path.cwd()
        permission_note = (
            "Dosyalarda değişiklik yapma; yalnızca analiz et."
            if not plan.policy.allow_writes
            else "Yalnızca verilen görev kapsamındaki dosyalarda değişiklik yap."
        )
        session_prompt = prompt
        if context:
            session_prompt += f"\n\nBAĞLAM:\n{context[: plan.policy.max_output_chars]}"

        session = None
        try:
            session = await self.collaboration_runtime.start_session(
                session_prompt,
                roles,
                working_dir=working_dir,
                headless=True,
                allow_writes=plan.policy.allow_writes,
                blind_mode=plan.policy.blind_mode,
            )

            if len(session.event_names) != len(roles):
                raise HcomClientError("Başlatılan hcom ajan kimlikleri doğrulanamadı.")

            addresses = ", ".join(f"@{role.name}-" for role in roles)
            mission = (
                f"VOLTRAN ortak görevi başladı. Ekip: {addresses}. {permission_note} "
                "Birbirinizin görüşünü isteyin, itirazları doğrudan tartışın ve görev "
                "devredin. Kendi katkınız bittiğinde VOLTRAN_DONE yazın. En az iki ajan "
                "ortak karara vardığında nihai mesajda VOLTRAN_CONSENSUS kullanın."
            )
            # Global broadcast kullanma: aynı makinedeki başka hcom oturumlarını uyandırabilir.
            for role in roles:
                await self.collaboration_runtime.send_to_role(session, role.name, mission)

            supervisor = self.supervisor or CollaborationSupervisor(
                SupervisorPolicy(timeout_seconds=plan.policy.timeout_seconds)
            )
            outcome = await supervisor.monitor(
                expected_agents=list(session.event_names.values()),
                poll_events=lambda: self.collaboration_runtime.poll_events(session),
                poll_states=lambda: self.collaboration_runtime.get_agent_states(session),
            )

            executions: list[ProviderExecution] = []
            transcript_parts: list[str] = []
            for index, (role, subtask) in enumerate(
                zip(roles, plan.subtasks, strict=True), start=1
            ):
                transcript = await self.collaboration_runtime.get_transcript(session, role.name)

                event_name = session.event_names[role.name]
                messages = [
                    event.content
                    for event in outcome.events
                    if event.agent == event_name and event.content.strip()
                ]
                summary = transcript.strip() or "\n".join(messages).strip()
                participated = event_name in outcome.participants
                status = ExecutionStatus.SUCCESS if participated else ExecutionStatus.FAILED
                executions.append(
                    ProviderExecution(
                        run_id=subtask.subtask_id,
                        provider=subtask.assigned_provider or "codex",
                        status=status,
                        duration_ms=max(0, round((time.monotonic() - started) * 1000)),
                        result=(
                            TaskResult(
                                summary=summary or "Ajan geçerli çıktı üretmedi.",
                                status="success",
                                metadata={
                                    "role": subtask.role,
                                    "purpose": subtask.purpose,
                                    "hcom_agent": event_name,
                                },
                            )
                            if participated
                            else None
                        ),
                        error=None if participated else "Ajan geçerli çıktı üretmedi.",
                    )
                )
                if participated and summary:
                    header = (
                        f"### {subtask.role} [Kör Hakem #{index}]\n{summary}"
                        if plan.policy.blind_mode
                        else f"### {subtask.role} ({subtask.assigned_provider})\n{summary}"
                    )
                    transcript_parts.append(header)

            consensus_messages = [
                event.content.replace("VOLTRAN_CONSENSUS", "").strip()
                for event in outcome.events
                if event.agent in outcome.participants and "VOLTRAN_CONSENSUS" in event.content
            ]
            final_summary = next(
                (message for message in reversed(consensus_messages) if message),
                "\n\n".join(transcript_parts) or outcome.reason,
            )
            successful_count = sum(
                execution.status is ExecutionStatus.SUCCESS for execution in executions
            )
            synthesis = CouncilSynthesis(
                consensus=[outcome.reason] if outcome.status is SupervisionStatus.COMPLETED else [],
                disagreements=(
                    []
                    if outcome.consensus_reached
                    else ["Açık VOLTRAN_CONSENSUS işareti oluşmadı."]
                ),
                confidence_score=(
                    0.9
                    if outcome.consensus_reached and successful_count >= 3
                    else 0.75
                    if outcome.status is SupervisionStatus.COMPLETED
                    else 0.4
                ),
                confidence_rationale=(
                    f"{successful_count} ajan canlı hcom oturumunda mesaj ve durum "
                    "olayları üzerinden izlendi."
                ),
            )
            return ExecutionReport(
                run_id=run_id,
                task_prompt=prompt,
                mode=plan.mode,
                plan=plan,
                executions=executions,
                final_summary=final_summary,
                synthesis=synthesis,
                next_step_recommendation=(
                    "Canlı konsey kararını doğrulayın ve önerilen eylemleri uygulayın."
                ),
                total_duration_ms=max(0, round((time.monotonic() - started) * 1000)),
            )
        except (HcomClientError, OSError, RuntimeError, ValueError) as exc:
            return self._council_failure_report(
                run_id=run_id,
                prompt=prompt,
                plan=plan,
                started=started,
                error=f"Canlı konsey başlatılamadı: {exc}",
            )
        finally:
            if session is not None:
                await self.collaboration_runtime.terminate_session(session)

    @staticmethod
    def _council_failure_report(
        *,
        run_id: str,
        prompt: str,
        plan: TaskPlan,
        started: float,
        error: str,
    ) -> ExecutionReport:
        execution = ProviderExecution(
            run_id=run_id,
            provider="hcom",
            status=ExecutionStatus.FAILED,
            duration_ms=max(0, round((time.monotonic() - started) * 1000)),
            error=error,
        )
        return ExecutionReport(
            run_id=run_id,
            task_prompt=prompt,
            mode=plan.mode,
            plan=plan,
            executions=[execution],
            final_summary=error,
            synthesis=CouncilSynthesis(
                confidence_score=0.0,
                confidence_rationale="Canlı hcom işbirliği oturumu kurulamadı.",
            ),
            next_step_recommendation="hcom kurulumunu ve sağlayıcı oturumlarını kontrol edin.",
            total_duration_ms=execution.duration_ms,
        )
