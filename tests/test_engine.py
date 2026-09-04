from __future__ import annotations

import asyncio
from pathlib import Path
from typing import cast

from voltran.collaboration import AgentRole, CollaborationRuntime, CollaborationSession
from voltran.engine import ExecutionEngine
from voltran.hcom_client import HcomAgentInfo, HcomClient, HcomClientError, HcomEvent
from voltran.models import (
    ExecutionMode,
    ExecutionPolicy,
    ExecutionStatus,
    ProviderCapabilities,
    ProviderExecution,
    ProviderHealth,
    ProviderTask,
    SubTask,
    TaskPlan,
    TaskResult,
)
from voltran.providers import ProviderAdapter
from voltran.supervisor import (
    CollaborationSupervisor,
    SupervisionOutcome,
    SupervisionStatus,
)


class _DummyAdapter:
    def __init__(
        self,
        key: str,
        output: str,
        fail: bool = False,
        raise_exc: bool = False,
    ) -> None:
        self.key = key
        self.output = output
        self.fail = fail
        self.raise_exc = raise_exc
        self.received_tasks: list[ProviderTask] = []
        self.received_contexts: list[str | None] = []

    def availability(self) -> bool:
        return True

    def capabilities(self) -> ProviderCapabilities:
        return ProviderCapabilities()

    async def health_check(self) -> ProviderHealth:
        return ProviderHealth(provider=self.key, available=True, message="ok")

    async def execute(
        self,
        task: ProviderTask,
        context: str | None,
        policy: ExecutionPolicy,
    ) -> ProviderExecution:
        self.received_tasks.append(task)
        self.received_contexts.append(context)
        if self.raise_exc:
            raise RuntimeError("Beklenmeyen adaptör çökmesi")
        if self.fail:
            return ProviderExecution(
                run_id=task.task_id,
                provider=self.key,
                status=ExecutionStatus.FAILED,
                duration_ms=10,
                error="Zorunlu hata",
            )
        return ProviderExecution(
            run_id=task.task_id,
            provider=self.key,
            status=ExecutionStatus.SUCCESS,
            duration_ms=50,
            result=TaskResult(summary=self.output, status="success"),
        )

    async def cancel(self, run_id: str) -> bool:
        return True

    def normalize_result(self, raw_output: str) -> TaskResult:
        return TaskResult(summary=raw_output, status="success")


def test_engine_executes_single_mode_forwarding_subtask_role() -> None:
    async def scenario() -> None:
        claude = _DummyAdapter("claude", "Claude uzman cevabı")
        registry: dict[str, ProviderAdapter] = {"claude": claude}
        engine = ExecutionEngine(registry)
        plan = TaskPlan(
            mode=ExecutionMode.EXPERT,
            reasoning="uzman testi",
            subtasks=[
                SubTask(
                    role="Güvenlik Denetçisi",
                    purpose="Kod açıklarını tara",
                    assigned_provider="claude",
                )
            ],
        )

        report = await engine.execute_plan("Güvenlik incelemesi yap", plan)

        assert report.mode == ExecutionMode.EXPERT
        assert "Claude uzman cevabı" in report.final_summary
        assert len(claude.received_tasks) == 1
        assert claude.received_tasks[0].role == "Güvenlik Denetçisi"
        assert claude.received_tasks[0].purpose == "Kod açıklarını tara"

    asyncio.run(scenario())


def test_engine_sanitizes_prompt_and_context_before_provider_call(tmp_path: Path) -> None:
    async def scenario() -> None:
        adapter = _DummyAdapter("claude", "ok")
        context_file = tmp_path / "context.txt"
        context_file.write_text("email=user@example.com", encoding="utf-8")
        plan = TaskPlan(
            mode=ExecutionMode.EXPERT,
            reasoning="test",
            context_file=context_file,
            subtasks=[SubTask(role="uzman", purpose="test", assigned_provider="claude")],
        )

        report = await ExecutionEngine({"claude": adapter}).execute_plan(
            "token sk-1234567890abcdef1234567890", plan
        )

        assert "sk-1234567890abcdef1234567890" not in adapter.received_tasks[0].prompt
        assert "[REDACTED_API_KEY]" in adapter.received_tasks[0].prompt
        assert adapter.received_contexts == ["email=[REDACTED_EMAIL]"]
        # Yerel rapor özgün kullanıcı görevini korur; kalıcı store ayrıca maskeler.
        assert "sk-1234567890abcdef1234567890" in report.task_prompt

    asyncio.run(scenario())


class _FakeCollaborationRuntime:
    def __init__(self, *, available: bool = True, fail_start: bool = False) -> None:
        self.available = available
        self.fail_start = fail_start
        self.sent_roles: list[str] = []
        self.sent_messages: list[tuple[str, str]] = []
        self.terminated = False
        self.session: CollaborationSession | None = None

    def is_available(self) -> bool:
        return self.available

    async def start_session(
        self,
        task_prompt: str,
        roles: list[AgentRole],
        *,
        working_dir: Path | None = None,
        headless: bool = True,
        allow_writes: bool = False,
        blind_mode: bool = False,
    ) -> CollaborationSession:
        del headless, allow_writes, blind_mode

        if self.fail_start:
            raise HcomClientError("başlatma hatası")
        session = CollaborationSession(
            session_id="test-session",
            task_prompt=task_prompt,
            roles=roles,
            working_dir=working_dir or Path.cwd(),
            client=HcomClient("fake-hcom"),
            agent_names={
                role.name: f"{role.name}-agent{index}" for index, role in enumerate(roles)
            },
            event_names={role.name: f"agent{index}" for index, role in enumerate(roles)},
        )
        self.session = session
        return session

    async def send_to_role(
        self,
        session: CollaborationSession,
        target_role: str,
        message: str,
        *,
        reply_to: str | None = None,
    ) -> bool:
        del session, reply_to
        self.sent_roles.append(target_role)
        self.sent_messages.append((target_role, message))
        return True

    async def poll_events(
        self, session: CollaborationSession, *, limit: int = 50
    ) -> list[HcomEvent]:
        del session, limit
        return []

    async def get_agent_states(self, session: CollaborationSession) -> list[HcomAgentInfo]:
        return [
            HcomAgentInfo(name=name, status="listening") for name in session.event_names.values()
        ]

    async def get_transcript(self, session: CollaborationSession, agent_name: str) -> str:
        del session
        return f"{agent_name} canlı katkısı"

    async def terminate_session(self, session: CollaborationSession) -> None:
        session.is_active = False
        self.terminated = True


class _FakeSupervisor:
    async def monitor(self, **_: object) -> SupervisionOutcome:
        return SupervisionOutcome(
            status=SupervisionStatus.COMPLETED,
            reason="Ajanlar açık uzlaşma işareti üretti.",
            events=[
                HcomEvent("1", "", "message", "agent0", content="İlk görüş"),
                HcomEvent(
                    "2",
                    "",
                    "message",
                    "agent1",
                    content="Ortak nihai karar VOLTRAN_CONSENSUS",
                ),
                HcomEvent("3", "", "message", "agent2", content="VOLTRAN_DONE"),
            ],
            participants={"agent0", "agent1", "agent2"},
            consensus_reached=True,
        )


class _CompletedWithoutConsensusSupervisor:
    async def monitor(self, **_: object) -> SupervisionOutcome:
        return SupervisionOutcome(
            status=SupervisionStatus.COMPLETED,
            reason="Konsey sakin duruma geçti.",
            events=[
                HcomEvent("1", "", "message", "agent0", content="İlk görüş"),
                HcomEvent("2", "", "message", "agent1", content="İkinci görüş"),
            ],
            participants={"agent0", "agent1"},
            consensus_reached=False,
        )


def test_engine_executes_council_through_live_collaboration_runtime() -> None:
    async def scenario() -> None:
        runtime = _FakeCollaborationRuntime()
        engine = ExecutionEngine(
            {},
            collaboration_runtime=cast(CollaborationRuntime, runtime),
            supervisor=cast(CollaborationSupervisor, _FakeSupervisor()),
        )
        plan = TaskPlan(
            mode=ExecutionMode.COUNCIL,
            reasoning="konsey testi",
            policy=ExecutionPolicy(allow_writes=True),
            subtasks=[
                SubTask(
                    role="Mimar A",
                    purpose="Mikroservis odaklı plan",
                    assigned_provider="claude",
                ),
                SubTask(
                    role="Mimar B",
                    purpose="Monolit odaklı plan",
                    assigned_provider="codex",
                ),
                SubTask(
                    role="Mimar C",
                    purpose="Ortak çözümü geliştir",
                    assigned_provider="google",
                ),
            ],
        )

        report = await engine.execute_plan("Mimariyi karşılaştır", plan)

        assert report.mode == ExecutionMode.COUNCIL
        assert report.synthesis is not None
        assert report.synthesis.confidence_score >= 0.8
        assert len(report.executions) == 3
        assert report.final_summary == "Ortak nihai karar"
        assert len(runtime.sent_roles) == 3
        assert "değişiklik yapma" in runtime.sent_messages[0][1]
        assert "değişiklik yapma" in runtime.sent_messages[1][1]
        assert "Tek yazım sorumlusu" in runtime.sent_messages[2][1]
        assert runtime.terminated is True

    asyncio.run(scenario())


def test_engine_does_not_claim_consensus_for_idle_completion() -> None:
    async def scenario() -> None:
        runtime = _FakeCollaborationRuntime()
        engine = ExecutionEngine(
            {},
            collaboration_runtime=cast(CollaborationRuntime, runtime),
            supervisor=cast(CollaborationSupervisor, _CompletedWithoutConsensusSupervisor()),
        )
        plan = TaskPlan(
            mode=ExecutionMode.COUNCIL,
            reasoning="konsey testi",
            subtasks=[
                SubTask(role="A", purpose="p1", assigned_provider="claude"),
                SubTask(role="B", purpose="p2", assigned_provider="codex"),
            ],
        )

        report = await engine.execute_plan("Karşılaştır", plan)

        assert report.synthesis is not None
        assert report.synthesis.consensus == []
        assert report.synthesis.disagreements

    asyncio.run(scenario())


def test_engine_requires_hcom_for_council_without_static_fallback() -> None:
    async def scenario() -> None:
        runtime = _FakeCollaborationRuntime(available=False)
        engine = ExecutionEngine({}, collaboration_runtime=cast(CollaborationRuntime, runtime))
        plan = TaskPlan(
            mode=ExecutionMode.COUNCIL,
            reasoning="kısmi hata testi",
            subtasks=[
                SubTask(role="uzman_1", purpose="p1", assigned_provider="claude"),
                SubTask(role="uzman_2", purpose="p2", assigned_provider="codex"),
            ],
        )

        report = await engine.execute_plan("Test", plan)

        assert "hcom işbirliği motoru bulunamadı" in report.final_summary
        assert report.synthesis is not None
        assert report.synthesis.confidence_score == 0.0
        assert report.executions[0].provider == "hcom"

    asyncio.run(scenario())


def test_engine_terminates_partial_session_when_collaboration_fails() -> None:
    async def scenario() -> None:
        runtime = _FakeCollaborationRuntime(fail_start=True)
        engine = ExecutionEngine({}, collaboration_runtime=cast(CollaborationRuntime, runtime))
        plan = TaskPlan(
            mode=ExecutionMode.COUNCIL,
            reasoning="çökme izolasyonu",
            subtasks=[
                SubTask(role="uzman_1", purpose="p1", assigned_provider="claude"),
                SubTask(role="uzman_2", purpose="p2", assigned_provider="codex"),
            ],
        )

        report = await engine.execute_plan("Test", plan)

        assert report.mode == ExecutionMode.COUNCIL
        assert "başlatma hatası" in report.final_summary
        assert report.executions[0].status is ExecutionStatus.FAILED

    asyncio.run(scenario())


def test_engine_dry_run_does_not_execute_providers() -> None:
    async def scenario() -> None:
        engine = ExecutionEngine({})
        plan = TaskPlan(
            mode=ExecutionMode.EXPERT,
            reasoning="kuru çalışma",
            subtasks=[SubTask(role="uzman", purpose="kod analizi", assigned_provider="claude")],
        )

        report = await engine.execute_plan("Görev", plan, dry_run=True)

        assert "[Kuru Çalışma / Dry Run]" in report.final_summary
        assert report.total_duration_ms == 0
        assert report.executions[0].result is not None
        assert "Dry Run" in report.executions[0].result.summary

    asyncio.run(scenario())


def test_engine_applies_context_budget_before_reaching_provider(tmp_path: Path) -> None:
    """SEC-04: sağlayıcıya giden bağlam politikadaki bütçeyi aşmamalıdır."""

    seen: dict[str, str | None] = {}

    class _BudgetSpyAdapter:
        key = "codex"

        def availability(self) -> bool:
            return True

        def capabilities(self) -> ProviderCapabilities:
            return ProviderCapabilities(file_access=True)

        async def health_check(self) -> ProviderHealth:
            return ProviderHealth(provider=self.key, available=True, message="ok")

        async def cancel(self, run_id: str) -> bool:
            return True

        def normalize_result(self, raw_output: str) -> TaskResult:
            return TaskResult(summary=raw_output, status="success")

        async def execute(
            self,
            task: ProviderTask,
            context: str | None,
            policy: ExecutionPolicy,
        ) -> ProviderExecution:
            seen["context"] = context
            return ProviderExecution(
                run_id=task.task_id,
                provider=self.key,
                status=ExecutionStatus.SUCCESS,
                duration_ms=1,
                result=TaskResult(summary="ok", status="success"),
            )

    context_file = tmp_path / "buyuk.py"
    context_file.write_text("A" * 50_000, encoding="utf-8")
    plan = TaskPlan(
        mode=ExecutionMode.EXPERT,
        reasoning="test",
        subtasks=[SubTask(role="uzman", purpose="", assigned_provider="codex")],
        context_file=context_file,
        policy=ExecutionPolicy(max_context_chars=2_000),
    )
    registry: dict[str, ProviderAdapter] = {"codex": _BudgetSpyAdapter()}

    asyncio.run(ExecutionEngine(registry=registry).execute_plan("incele", plan))

    sent = seen["context"]
    assert sent is not None
    assert len(sent) <= 2_000
    assert "gönderilmedi" in sent
