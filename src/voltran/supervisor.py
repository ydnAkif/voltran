"""Canlı hcom konseylerinin bitiş, uzlaşma ve zaman aşımı denetimi."""

from __future__ import annotations

import asyncio
import time
from collections.abc import Awaitable, Callable, Sequence
from dataclasses import dataclass, field
from enum import StrEnum
from typing import Protocol


class EventLike(Protocol):
    """Supervisor'ın hcom istemcisinden ihtiyaç duyduğu olay alanları."""

    event_id: str
    event_type: str
    agent: str | None
    content: str


class AgentStateLike(Protocol):
    """Supervisor'ın ajan durumundan ihtiyaç duyduğu alanlar."""

    name: str
    status: str


class SupervisionStatus(StrEnum):
    COMPLETED = "completed"
    TIMED_OUT = "timed_out"
    FAILED = "failed"


@dataclass(frozen=True, slots=True)
class SupervisorPolicy:
    """Bir canlı konseyin kaynak ve bitiş sınırları."""

    timeout_seconds: float = 300.0
    poll_interval_seconds: float = 1.0
    idle_grace_seconds: float = 3.0
    minimum_participants: int = 2
    max_rounds: int = 2
    max_context_chars: int = 120_000
    done_marker: str = "VOLTRAN_DONE"
    consensus_marker: str = "VOLTRAN_CONSENSUS"

    def __post_init__(self) -> None:
        if self.max_rounds < 1:
            raise ValueError("max_rounds en az 1 olmalıdır.")
        if self.max_context_chars < 1:
            raise ValueError("max_context_chars en az 1 olmalıdır.")


@dataclass(slots=True)
class SupervisionOutcome:
    """Canlı işbirliği akışından üretilen denetlenebilir sonuç."""

    status: SupervisionStatus
    reason: str
    events: list[EventLike] = field(default_factory=lambda: list[EventLike]())
    participants: set[str] = field(default_factory=lambda: set[str]())
    completed_agents: set[str] = field(default_factory=lambda: set[str]())
    consensus_reached: bool = False
    rounds_completed: int = 0
    context_chars: int = 0
    context_truncated: bool = False


PollEvents = Callable[[], Awaitable[Sequence[EventLike]]]
PollStates = Callable[[], Awaitable[Sequence[AgentStateLike]]]


class CollaborationSupervisor:
    """Mesaj akışını izler; sabit tur sayısı kullanmadan oturumu sonuçlandırır."""

    _QUIESCENT_STATES = frozenset({"idle", "listening", "waiting"})
    _FAILED_STATES = frozenset({"dead", "error", "failed", "crashed"})
    _SUBSTANTIVE_EVENT_TYPES = frozenset({"message", "assistant", "response"})

    def __init__(self, policy: SupervisorPolicy | None = None) -> None:
        self.policy = policy or SupervisorPolicy()

    async def monitor(
        self,
        *,
        expected_agents: Sequence[str],
        poll_events: PollEvents,
        poll_states: PollStates,
    ) -> SupervisionOutcome:
        """Ajanlar uzlaşana, işi bitirene, hata verene veya süre dolana kadar izle."""

        expected = {name for name in expected_agents if name}
        if not expected:
            raise ValueError("En az bir beklenen ajan adı gereklidir.")

        started = time.monotonic()
        idle_since: float | None = None
        events_by_id: dict[str, EventLike] = {}
        participants: set[str] = set()
        completed_agents: set[str] = set()
        message_counts = {name: 0 for name in expected}
        consensus_seen = False
        context_chars = 0

        while True:
            now = time.monotonic()
            if now - started >= self.policy.timeout_seconds:
                return self._outcome(
                    SupervisionStatus.TIMED_OUT,
                    "Canlı konsey zaman sınırına ulaştı.",
                    events_by_id,
                    participants,
                    completed_agents,
                    rounds_completed=self._rounds_completed(message_counts),
                    context_chars=context_chars,
                )

            for event in await poll_events():
                event_key = event.event_id or (
                    f"anonymous-{hash((event.agent, event.event_type, event.content))}"
                )
                if event_key in events_by_id:
                    continue
                content = event.content.strip()
                event_chars = len(content)
                if context_chars + event_chars > self.policy.max_context_chars:
                    return self._outcome(
                        SupervisionStatus.COMPLETED,
                        "Konsey bağlam bütçesine ulaştı; açık uzlaşma oluşmadı.",
                        events_by_id,
                        participants,
                        completed_agents,
                        rounds_completed=self._rounds_completed(message_counts),
                        context_chars=context_chars,
                        context_truncated=True,
                    )
                events_by_id[event_key] = event
                context_chars += event_chars
                if (
                    event.agent
                    and event.agent in expected
                    and event.event_type.lower() in self._SUBSTANTIVE_EVENT_TYPES
                    and content
                ):
                    participants.add(event.agent)
                    message_counts[event.agent] += 1
                if event.agent in expected and self.policy.done_marker in content:
                    completed_agents.add(event.agent)
                if event.agent in expected and self.policy.consensus_marker in content:
                    consensus_seen = True

            rounds_completed = self._rounds_completed(message_counts)
            if rounds_completed >= self.policy.max_rounds:
                consensus_reached = consensus_seen and self._quorum_met(participants, expected)
                reason = (
                    "Ajanlar tur sınırında açık uzlaşma işareti üretti."
                    if consensus_reached
                    else "Konsey azami ortak çalışma turuna ulaştı."
                )
                return self._outcome(
                    SupervisionStatus.COMPLETED,
                    reason,
                    events_by_id,
                    participants,
                    completed_agents,
                    consensus=consensus_reached,
                    rounds_completed=rounds_completed,
                    context_chars=context_chars,
                )

            if expected.issubset(completed_agents):
                return self._outcome(
                    SupervisionStatus.COMPLETED,
                    "Tüm ajanlar işi tamamladığını bildirdi.",
                    events_by_id,
                    participants,
                    completed_agents,
                    rounds_completed=rounds_completed,
                    context_chars=context_chars,
                )

            states = {state.name: state.status.lower() for state in await poll_states()}
            failed = sorted(
                name for name in expected if states.get(name, "") in self._FAILED_STATES
            )
            if failed:
                return self._outcome(
                    SupervisionStatus.FAILED,
                    f"Ajan çalışma zamanı hatası: {', '.join(failed)}.",
                    events_by_id,
                    participants,
                    completed_agents,
                    rounds_completed=rounds_completed,
                    context_chars=context_chars,
                )

            all_quiescent = expected.issubset(states) and all(
                states[name] in self._QUIESCENT_STATES for name in expected
            )
            if all_quiescent and self._quorum_met(participants, expected):
                idle_since = idle_since or now
                if now - idle_since >= self.policy.idle_grace_seconds:
                    return self._outcome(
                        SupervisionStatus.COMPLETED,
                        "Katılımcılar çıktı ürettikten sonra konsey sakin duruma geçti.",
                        events_by_id,
                        participants,
                        completed_agents,
                        rounds_completed=rounds_completed,
                        context_chars=context_chars,
                    )
            else:
                idle_since = None

            await asyncio.sleep(self.policy.poll_interval_seconds)

    def _quorum_met(self, participants: set[str], expected: set[str]) -> bool:
        required = min(max(1, self.policy.minimum_participants), len(expected))
        return len(participants & expected) >= required

    @staticmethod
    def _rounds_completed(message_counts: dict[str, int]) -> int:
        return min(message_counts.values(), default=0)

    @staticmethod
    def _outcome(
        status: SupervisionStatus,
        reason: str,
        events_by_id: dict[str, EventLike],
        participants: set[str],
        completed_agents: set[str],
        *,
        consensus: bool = False,
        rounds_completed: int = 0,
        context_chars: int = 0,
        context_truncated: bool = False,
    ) -> SupervisionOutcome:
        return SupervisionOutcome(
            status=status,
            reason=reason,
            events=list(events_by_id.values()),
            participants=set(participants),
            completed_agents=set(completed_agents),
            consensus_reached=consensus,
            rounds_completed=rounds_completed,
            context_chars=context_chars,
            context_truncated=context_truncated,
        )
