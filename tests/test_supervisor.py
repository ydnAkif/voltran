from __future__ import annotations

import asyncio
from dataclasses import dataclass

from voltran.supervisor import (
    CollaborationSupervisor,
    SupervisionStatus,
    SupervisorPolicy,
)


@dataclass
class _Event:
    event_id: str
    event_type: str
    agent: str | None
    content: str


@dataclass
class _State:
    name: str
    status: str


def test_supervisor_completes_on_explicit_consensus() -> None:
    async def scenario() -> None:
        supervisor = CollaborationSupervisor(
            SupervisorPolicy(timeout_seconds=1, poll_interval_seconds=0.001, max_rounds=1)
        )

        async def events() -> list[_Event]:
            return [
                _Event("1", "message", "claude", "Bir önerim var"),
                _Event("2", "message", "codex", "Katılıyorum VOLTRAN_CONSENSUS"),
            ]

        async def states() -> list[_State]:
            return [_State("claude", "active"), _State("codex", "active")]

        outcome = await supervisor.monitor(
            expected_agents=["claude", "codex"], poll_events=events, poll_states=states
        )
        assert outcome.status is SupervisionStatus.COMPLETED
        assert outcome.consensus_reached is True
        assert outcome.participants == {"claude", "codex"}

    asyncio.run(scenario())


def test_supervisor_deduplicates_events_and_waits_for_all_done() -> None:
    async def scenario() -> None:
        calls = 0
        supervisor = CollaborationSupervisor(
            SupervisorPolicy(timeout_seconds=1, poll_interval_seconds=0.001)
        )

        async def events() -> list[_Event]:
            nonlocal calls
            calls += 1
            rows = [_Event("1", "message", "claude", "Bitti VOLTRAN_DONE")]
            if calls > 1:
                rows.append(_Event("2", "message", "codex", "Bitti VOLTRAN_DONE"))
            return rows

        async def states() -> list[_State]:
            return [_State("claude", "listening"), _State("codex", "active")]

        outcome = await supervisor.monitor(
            expected_agents=["claude", "codex"], poll_events=events, poll_states=states
        )
        assert outcome.status is SupervisionStatus.COMPLETED
        assert outcome.completed_agents == {"claude", "codex"}
        assert len(outcome.events) == 2

    asyncio.run(scenario())


def test_supervisor_fails_when_agent_crashes() -> None:
    async def scenario() -> None:
        supervisor = CollaborationSupervisor(
            SupervisorPolicy(timeout_seconds=1, poll_interval_seconds=0.001)
        )

        async def events() -> list[_Event]:
            return []

        async def states() -> list[_State]:
            return [_State("claude", "crashed"), _State("codex", "idle")]

        outcome = await supervisor.monitor(
            expected_agents=["claude", "codex"], poll_events=events, poll_states=states
        )
        assert outcome.status is SupervisionStatus.FAILED
        assert "claude" in outcome.reason

    asyncio.run(scenario())


def test_supervisor_times_out_without_progress() -> None:
    async def scenario() -> None:
        supervisor = CollaborationSupervisor(
            SupervisorPolicy(timeout_seconds=0.01, poll_interval_seconds=0.001)
        )

        async def events() -> list[_Event]:
            return []

        async def states() -> list[_State]:
            return [_State("claude", "idle"), _State("codex", "idle")]

        outcome = await supervisor.monitor(
            expected_agents=["claude", "codex"], poll_events=events, poll_states=states
        )
        assert outcome.status is SupervisionStatus.TIMED_OUT

    asyncio.run(scenario())


def test_supervisor_stops_at_round_limit_without_claiming_consensus() -> None:
    async def scenario() -> None:
        calls = 0
        supervisor = CollaborationSupervisor(
            SupervisorPolicy(
                timeout_seconds=1,
                poll_interval_seconds=0.001,
                max_rounds=2,
            )
        )

        async def events() -> list[_Event]:
            nonlocal calls
            calls += 1
            rows = [
                _Event("a1", "message", "agent-a", "İlk görüş A"),
                _Event("b1", "message", "agent-b", "İlk görüş B"),
            ]
            if calls > 1:
                rows.extend(
                    [
                        _Event("a2", "message", "agent-a", "İkinci görüş A"),
                        _Event("b2", "message", "agent-b", "İkinci görüş B"),
                    ]
                )
            return rows

        async def states() -> list[_State]:
            return [_State("agent-a", "active"), _State("agent-b", "active")]

        outcome = await supervisor.monitor(
            expected_agents=["agent-a", "agent-b"], poll_events=events, poll_states=states
        )

        assert outcome.status is SupervisionStatus.COMPLETED
        assert outcome.rounds_completed == 2
        assert outcome.consensus_reached is False
        assert "azami" in outcome.reason

    asyncio.run(scenario())


def test_supervisor_stops_when_context_budget_is_exhausted() -> None:
    async def scenario() -> None:
        supervisor = CollaborationSupervisor(
            SupervisorPolicy(
                timeout_seconds=1,
                poll_interval_seconds=0.001,
                max_context_chars=5,
            )
        )

        async def events() -> list[_Event]:
            return [
                _Event("1", "message", "agent-a", "1234"),
                _Event("2", "message", "agent-b", "5678"),
            ]

        async def states() -> list[_State]:
            return []

        outcome = await supervisor.monitor(
            expected_agents=["agent-a", "agent-b"], poll_events=events, poll_states=states
        )

        assert outcome.context_truncated is True
        assert outcome.context_chars == 4
        assert len(outcome.events) == 1
        assert outcome.consensus_reached is False

    asyncio.run(scenario())
