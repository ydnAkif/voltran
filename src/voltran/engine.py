"""VOLTRAN Yürütme Motoru (Execution Engine) — Mod orkestrasyonu ve alt süreç yönetimi."""

from __future__ import annotations

import asyncio
import json
import os
import time
from collections.abc import Sequence
from pathlib import Path
from typing import cast
from uuid import uuid4

from voltran.collaboration import (
    AgentRole,
    CollaborationRuntime,
    CollaborationSession,
)
from voltran.context import ContextError, load_context
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
from voltran.sanitizer import sanitize_for_provider
from voltran.supervisor import (
    CollaborationSupervisor,
    EventLike,
    SupervisorPolicy,
)


def _json_object(value: str) -> dict[str, object] | None:
    decoder = json.JSONDecoder()
    for index, character in enumerate(value):
        if character != "{":
            continue
        try:
            payload: object
            payload, _ = decoder.raw_decode(value[index:])
        except json.JSONDecodeError:
            continue
        if isinstance(payload, dict):
            dict_obj = cast(dict[object, object], payload)
            return {str(key): item for key, item in dict_obj.items()}
    return None


def _string_list(value: object) -> list[str]:
    if not isinstance(value, list):
        return []
    list_obj = cast(list[object], value)
    return [str(item).strip() for item in list_obj if str(item).strip()]


def _deduplicate(values: list[str]) -> list[str]:
    return list(dict.fromkeys(values))


def _extract_council_decision(
    events: Sequence[EventLike], participants: set[str]
) -> tuple[list[str], list[str], str | None]:
    """Açık karar kayıtlarını çıkar; serbest metinden çoğunluk/uzlaşma tahmin etme."""

    consensus: list[str] = []
    disagreements: list[str] = []
    final_summary: str | None = None
    disagreement_marker = "VOLTRAN_DISAGREEMENT:"

    for event in events:
        if event.agent not in participants:
            continue
        content = event.content.strip()
        if disagreement_marker in content:
            objection = content.split(disagreement_marker, 1)[1].strip()
            payload = _json_object(objection)
            if payload is not None:
                disagreements.extend(_string_list(payload.get("disagreements")))
            elif objection:
                disagreements.append(objection)
        if "VOLTRAN_CONSENSUS" not in content:
            continue
        decision = content.split("VOLTRAN_CONSENSUS", 1)[1].strip()
        payload = _json_object(decision)
        if payload is not None:
            consensus.extend(_string_list(payload.get("consensus")))
            disagreements.extend(_string_list(payload.get("disagreements")))
            summary = payload.get("summary")
            if isinstance(summary, str) and summary.strip():
                final_summary = summary.strip()
        elif decision:
            consensus.append(decision)
            final_summary = decision

    return _deduplicate(consensus), _deduplicate(disagreements), final_summary


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
        self._current_run_id: str | None = None
        self._current_session: CollaborationSession | None = None
        self._running_tasks: set[str] = set()

    async def cancel_run(self, run_id: str | None = None) -> bool:
        """Etkin çalışmayı, adaptör alt süreçlerini ve hcom oturumunu sonlandırır."""

        cancelled = False
        if self._current_session is not None:
            try:
                await self.collaboration_runtime.terminate_session(self._current_session)
                cancelled = True
            except Exception:
                pass
            self._current_session = None

        for subtask_id in list(self._running_tasks):
            for adapter in self.registry.values():
                try:
                    if await adapter.cancel(subtask_id):
                        cancelled = True
                except Exception:
                    pass
        self._running_tasks.clear()
        return cancelled

    async def execute_plan(
        self,
        prompt: str,
        plan: TaskPlan,
        *,
        dry_run: bool = False,
    ) -> ExecutionReport:
        started = time.monotonic()
        run_id = uuid4().hex[:12]

        # Bağlam dosyasını SEC-04 bütçesiyle oku (varsa). CLI aynı kontrolü önceden
        # yapar; buradaki yakalama, kütüphane olarak kullanımda çökmeyi önler.
        context: str | None = None
        if plan.context_file is not None:
            try:
                scope = load_context(
                    plan.context_file,
                    max_chars=plan.policy.max_context_chars,
                    line_range=plan.policy.context_line_range,
                )
                context = scope.text
            except ContextError as exc:
                context = f"[Bağlam dosyası kullanılamadı: {exc}]"

        # Gizli değerler sağlayıcı süreçlerine ulaşmadan önce maskelenir.
        provider_prompt = sanitize_for_provider(prompt)
        if context is not None:
            context = sanitize_for_provider(context)

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

        self._current_run_id = run_id
        from voltran.store import RunStore

        store = RunStore()
        store.register_active_run(run_id, os.getpid(), plan.mode.value, prompt)
        try:
            match plan.mode:
                case ExecutionMode.COUNCIL:
                    report = await self._execute_council(
                        run_id, prompt, provider_prompt, plan, context, started
                    )
                case _:
                    report = await self._execute_single_or_expert(
                        run_id, prompt, provider_prompt, plan, context, started
                    )
            return report
        except asyncio.CancelledError:
            await self.cancel_run(run_id)
            raise
        finally:
            self._current_run_id = None
            store.unregister_active_run(run_id)

    async def _execute_single_or_expert(
        self,
        run_id: str,
        prompt: str,
        provider_prompt: str,
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
                prompt=provider_prompt,
                role=st.role,
                purpose=st.purpose,
                model=st.model,
            )
            self._running_tasks.add(st.subtask_id)
            try:
                execution = await adapter.execute(task, context, plan.policy)
            finally:
                self._running_tasks.discard(st.subtask_id)

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
        provider_prompt: str,
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
        session_prompt = provider_prompt
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
            self._current_session = session

            if len(session.event_names) != len(roles):
                raise HcomClientError("Başlatılan hcom ajan kimlikleri doğrulanamadı.")

            addresses = ", ".join(f"@{role.name}-" for role in roles)
            # Global broadcast kullanma: aynı makinedeki başka hcom oturumlarını uyandırabilir.
            for role_index, role in enumerate(roles):
                role_can_write = plan.policy.allow_writes and role_index == len(roles) - 1
                permission_note = (
                    "Tek yazım sorumlusu sensin; görev kapsamındaki dosyaları değiştirebilirsin."
                    if role_can_write
                    else "Dosyalarda değişiklik yapma; yalnızca analiz et ve öneri sun."
                )
                mission = (
                    f"VOLTRAN ortak görevi başladı. Ekip: {addresses}. {permission_note} "
                    "En fazla iki ortak tur çalışın; her turda her ajan en az bir anlamlı "
                    "mesaj üretsin. Birbirinizin görüşünü isteyin ve itirazları doğrudan "
                    "tartışın. Çözülmeyen her itirazı `VOLTRAN_DISAGREEMENT: açıklama` "
                    "biçiminde kaydet. Kendi katkın bittiğinde VOLTRAN_DONE yaz. En az iki "
                    "ajan ortak karara vardığında nihai mesajı "
                    '`VOLTRAN_CONSENSUS {"summary":"...","consensus":["..."],'
                    '"disagreements":["..."]}` biçiminde yaz.'
                )
                await self.collaboration_runtime.send_to_role(session, role.name, mission)

            supervisor = self.supervisor or CollaborationSupervisor(
                SupervisorPolicy(
                    timeout_seconds=plan.policy.timeout_seconds,
                    max_context_chars=plan.policy.max_output_chars,
                )
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
                event_name = session.event_names[role.name]
                messages = [
                    event.content
                    for event in outcome.events
                    if event.agent == event_name and event.content.strip()
                ]
                summary = "\n".join(messages).strip()
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

            consensus, disagreements, decision_summary = _extract_council_decision(
                outcome.events, outcome.participants
            )
            if not outcome.consensus_reached:
                disagreements.append("Açık ve doğrulanmış konsey uzlaşması oluşmadı.")
            disagreements = _deduplicate(disagreements)
            final_summary = decision_summary or "\n\n".join(transcript_parts) or outcome.reason
            successful_count = sum(
                execution.status is ExecutionStatus.SUCCESS for execution in executions
            )
            synthesis = CouncilSynthesis(
                consensus=consensus if outcome.consensus_reached else [],
                disagreements=disagreements,
                confidence_score=(
                    0.9
                    if outcome.consensus_reached and successful_count >= 3 and not disagreements
                    else 0.75
                    if outcome.consensus_reached
                    else 0.4
                ),
                confidence_rationale=(
                    f"{successful_count} ajan, {outcome.rounds_completed} tamamlanmış tur ve "
                    f"{outcome.context_chars} karakter olay bağlamı üzerinden izlendi."
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
            self._current_session = None
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
