from __future__ import annotations

import asyncio

from voltran.engine import ExecutionEngine
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


class _DummyAdapter:
    def __init__(self, key: str, output: str, fail: bool = False) -> None:
        self.key = key
        self.output = output
        self.fail = fail

    def availability(self) -> bool:
        return True

    def capabilities(self) -> ProviderCapabilities:
        return ProviderCapabilities()

    async def health_check(self) -> ProviderHealth:
        return ProviderHealth(provider=self.key, available=True, message="ok")

    async def execute(
        self, task: ProviderTask, context: str | None, policy: ExecutionPolicy
    ) -> ProviderExecution:
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


def test_engine_executes_single_mode() -> None:
    async def scenario() -> None:
        registry: dict[str, ProviderAdapter] = {
            "claude": _DummyAdapter("claude", "Claude cevabı"),
        }
        engine = ExecutionEngine(registry)
        plan = TaskPlan(
            mode=ExecutionMode.QUICK,
            reasoning="hızlı test",
            subtasks=[SubTask(role="hızlı", purpose="p", assigned_provider="claude")],
        )

        report = await engine.execute_plan("Özetle", plan)

        assert report.mode == ExecutionMode.QUICK
        assert "Claude cevabı" in report.final_summary
        assert len(report.executions) == 1
        assert report.executions[0].status == ExecutionStatus.SUCCESS

    asyncio.run(scenario())


def test_engine_executes_council_with_synthesis() -> None:
    async def scenario() -> None:
        registry: dict[str, ProviderAdapter] = {
            "claude": _DummyAdapter("claude", "Claude mimari analizi"),
            "codex": _DummyAdapter("codex", "Codex mimari analizi"),
        }
        engine = ExecutionEngine(registry)
        plan = TaskPlan(
            mode=ExecutionMode.COUNCIL,
            reasoning="konsey testi",
            subtasks=[
                SubTask(role="uzman_1", purpose="p1", assigned_provider="claude"),
                SubTask(role="uzman_2", purpose="p2", assigned_provider="codex"),
            ],
        )

        report = await engine.execute_plan("Mimariyi karşılaştır", plan)

        assert report.mode == ExecutionMode.COUNCIL
        assert "Claude mimari analizi" in report.final_summary
        assert "Codex mimari analizi" in report.final_summary
        assert report.synthesis is not None
        assert report.synthesis.confidence_score > 0.8
        assert len(report.executions) == 2

    asyncio.run(scenario())


def test_engine_handles_partial_failure_in_council() -> None:
    async def scenario() -> None:
        registry: dict[str, ProviderAdapter] = {
            "claude": _DummyAdapter("claude", "Başarılı Claude çıktısı"),
            "codex": _DummyAdapter("codex", "", fail=True),
        }
        engine = ExecutionEngine(registry)
        plan = TaskPlan(
            mode=ExecutionMode.COUNCIL,
            reasoning="kısmi hata testi",
            subtasks=[
                SubTask(role="uzman_1", purpose="p1", assigned_provider="claude"),
                SubTask(role="uzman_2", purpose="p2", assigned_provider="codex"),
            ],
        )

        report = await engine.execute_plan("Test", plan)

        # Sistem çökmemeli, kısmi başarıyı raporlamalı
        assert "Başarılı Claude çıktısı" in report.final_summary
        assert report.synthesis is not None
        assert report.synthesis.confidence_score < 0.8
        assert any(e.status == ExecutionStatus.FAILED for e in report.executions)

    asyncio.run(scenario())


def test_engine_dry_run_does_not_execute_providers() -> None:
    async def scenario() -> None:
        # Boş registry ile bile dry run çalışabilmeli
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
