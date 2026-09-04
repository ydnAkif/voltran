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


def test_router_ignores_extra_adapters_beyond_council_role_count() -> None:
    registry: dict[str, ProviderAdapter] = {
        key: _MockAdapter(key) for key in ("claude", "codex", "google", "fourth")
    }
    plan = TaskPlan(
        mode=ExecutionMode.COUNCIL,
        reasoning="Test",
        subtasks=[SubTask(role=f"role-{index}", purpose="p") for index in range(3)],
    )

    assigned = Router(registry).assign_providers(plan)

    assert len(assigned.subtasks) == 3
    assert len({subtask.assigned_provider for subtask in assigned.subtasks}) == 3


def _plan(mode: ExecutionMode, subtask_count: int) -> TaskPlan:
    return TaskPlan(
        mode=mode,
        reasoning="test",
        subtasks=[SubTask(role=f"rol-{index}", purpose="") for index in range(subtask_count)],
    )


def _registry(*adapters: _MockAdapter) -> dict[str, ProviderAdapter]:
    return {adapter.key: adapter for adapter in adapters}


def test_validate_provider_keys_rejects_unknown_and_deduplicates() -> None:
    router = Router(_registry(_MockAdapter("claude"), _MockAdapter("codex")))

    assert router.known_providers() == ("claude", "codex")
    assert router.validate_provider_keys(["codex", "claude", "codex"]) == ["codex", "claude"]

    try:
        router.validate_provider_keys(["gpt5"])
    except ValueError as exc:
        assert "gpt5" in str(exc)
        assert "claude, codex" in str(exc)
    else:  # pragma: no cover - beklenen hata atılmadı
        raise AssertionError("Bilinmeyen sağlayıcı için ValueError bekleniyordu.")


def test_allow_list_restricts_assignment() -> None:
    router = Router(
        _registry(_MockAdapter("claude"), _MockAdapter("codex"), _MockAdapter("google"))
    )
    plan = router.assign_providers(
        _plan(ExecutionMode.COUNCIL, 3), allowed_providers=["codex", "google"]
    )

    assert {subtask.assigned_provider for subtask in plan.subtasks} == {"codex", "google"}
    assert len(plan.subtasks) == 2


def test_dry_run_honours_allow_list_when_nothing_is_installed() -> None:
    # Hiçbir CLI kurulu değil: kuru çalışma yine de izin listesine uymalı, aksi
    # hâlde önizleme gerçek çalışmadan farklı sağlayıcılar gösterir.
    router = Router(
        _registry(
            _MockAdapter("claude", available=False),
            _MockAdapter("codex", available=False),
            _MockAdapter("google", available=False),
        )
    )
    plan = router.assign_providers(
        _plan(ExecutionMode.EXPERT, 1), allowed_providers=["google"], dry_run=True
    )

    assert plan.subtasks[0].assigned_provider == "google"


def test_empty_allow_list_means_no_restriction() -> None:
    router = Router(_registry(_MockAdapter("claude")))
    plan = router.assign_providers(_plan(ExecutionMode.EXPERT, 1), allowed_providers=[])

    assert plan.subtasks[0].assigned_provider == "claude"


def test_allow_list_with_no_available_provider_reports_the_allow_list() -> None:
    router = Router(_registry(_MockAdapter("claude"), _MockAdapter("codex", available=False)))

    try:
        router.assign_providers(_plan(ExecutionMode.EXPERT, 1), allowed_providers=["codex"])
    except RuntimeError as exc:
        assert "codex" in str(exc)
        assert "İzin listesini genişletin" in str(exc)
    else:  # pragma: no cover - beklenen hata atılmadı
        raise AssertionError("Kullanılamayan izin listesi için RuntimeError bekleniyordu.")


def test_council_requires_at_least_two_providers() -> None:
    router = Router(_registry(_MockAdapter("claude"), _MockAdapter("codex", available=False)))

    try:
        router.assign_providers(_plan(ExecutionMode.COUNCIL, 3))
    except RuntimeError as exc:
        assert "en az iki farklı sağlayıcı" in str(exc)
        assert "claude" in str(exc)
    else:  # pragma: no cover - beklenen hata atılmadı
        raise AssertionError("Tek sağlayıcılı konsey için RuntimeError bekleniyordu.")


def test_council_single_provider_is_allowed_in_dry_run() -> None:
    router = Router(_registry(_MockAdapter("claude")))
    plan = router.assign_providers(_plan(ExecutionMode.COUNCIL, 3), dry_run=True)

    assert len(plan.subtasks) == 1
    assert plan.subtasks[0].assigned_provider == "claude"
