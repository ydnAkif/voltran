from __future__ import annotations

from voltran.models import (
    ExecutionMode,
    ExecutionPolicy,
    ProviderCapabilities,
    ProviderExecution,
    ProviderHealth,
    ProviderTask,
    SubTask,
    TaskPlan,
    TaskResult,
)
from voltran.providers import ProviderAdapter
from voltran.router import Router


class _MockAdapter:
    def __init__(self, key: str, available: bool = True, file_access: bool = True) -> None:
        self.key = key
        self._available = available
        self._file_access = file_access

    def availability(self) -> bool:
        return self._available

    def capabilities(self) -> ProviderCapabilities:
        return ProviderCapabilities(file_access=self._file_access)

    async def health_check(self) -> ProviderHealth:
        return ProviderHealth(provider=self.key, available=self._available, message="ok")

    async def execute(
        self, task: ProviderTask, context: str | None, policy: ExecutionPolicy
    ) -> ProviderExecution:
        raise NotImplementedError

    async def cancel(self, run_id: str) -> bool:
        return True

    def normalize_result(self, raw_output: str) -> TaskResult:
        return TaskResult(summary=raw_output, status="success")


def test_router_assigns_distinct_providers_for_council() -> None:
    registry: dict[str, ProviderAdapter] = {
        "claude": _MockAdapter("claude"),
        "codex": _MockAdapter("codex"),
        "google": _MockAdapter("google"),
    }
    router = Router(registry)
    plan = TaskPlan(
        mode=ExecutionMode.COUNCIL,
        reasoning="Test",
        subtasks=[
            SubTask(role="uzman_1", purpose="p1"),
            SubTask(role="uzman_2", purpose="p2"),
            SubTask(role="uzman_3", purpose="p3"),
        ],
    )

    assigned_plan = router.assign_providers(plan)

    assigned = [st.assigned_provider for st in assigned_plan.subtasks]
    assert len(set(assigned)) == 3
    assert all(p in registry for p in assigned)


def test_router_respects_allowed_providers_filter() -> None:
    registry: dict[str, ProviderAdapter] = {
        "claude": _MockAdapter("claude"),
        "codex": _MockAdapter("codex"),
    }
    router = Router(registry)
    plan = TaskPlan(
        mode=ExecutionMode.EXPERT,
        reasoning="Test",
        subtasks=[SubTask(role="uzman", purpose="p")],
    )

    assigned_plan = router.assign_providers(plan, allowed_providers=["codex"])
    assert assigned_plan.subtasks[0].assigned_provider == "codex"


def test_router_drops_unfillable_council_roles_instead_of_reusing_provider() -> None:
    registry: dict[str, ProviderAdapter] = {
        "codex": _MockAdapter("codex"),
        "google": _MockAdapter("google"),
    }
    plan = TaskPlan(
        mode=ExecutionMode.COUNCIL,
        reasoning="Test",
        subtasks=[
            SubTask(role="analist", purpose="p1"),
            SubTask(role="uygulayıcı", purpose="p2"),
            SubTask(role="hakem", purpose="p3"),
        ],
    )

    assigned = Router(registry).assign_providers(plan)

    assert len(assigned.subtasks) == 2
    assert len({subtask.assigned_provider for subtask in assigned.subtasks}) == 2
