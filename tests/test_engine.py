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


def test_engine_executes_council_with_judge_synthesis() -> None:
    async def scenario() -> None:
        claude = _DummyAdapter("claude", "Ortak Hakem Sentezi")
        codex = _DummyAdapter("codex", "Codex mimari analizi")
        registry: dict[str, ProviderAdapter] = {"claude": claude, "codex": codex}
        engine = ExecutionEngine(registry)
        plan = TaskPlan(
            mode=ExecutionMode.COUNCIL,
            reasoning="konsey testi",
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
            ],
        )

        report = await engine.execute_plan("Mimariyi karşılaştır", plan)

        assert report.mode == ExecutionMode.COUNCIL
        assert report.synthesis is not None
        assert report.synthesis.confidence_score >= 0.8
        # Claude hem uzman hem hakem olarak çalıştırıldı
        assert len(report.executions) == 3
        assert "Ortak Hakem Sentezi" in report.final_summary

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
        assert report.synthesis.confidence_score <= 0.75
        assert any(e.status == ExecutionStatus.FAILED for e in report.executions)

    asyncio.run(scenario())


def test_engine_handles_unexpected_exception_in_gather() -> None:
    async def scenario() -> None:
        registry: dict[str, ProviderAdapter] = {
            "claude": _DummyAdapter("claude", "Claude sağlam"),
            "codex": _DummyAdapter("codex", "", raise_exc=True),
        }
        engine = ExecutionEngine(registry)
        plan = TaskPlan(
            mode=ExecutionMode.COUNCIL,
            reasoning="çökme izolasyonu",
            subtasks=[
                SubTask(role="uzman_1", purpose="p1", assigned_provider="claude"),
                SubTask(role="uzman_2", purpose="p2", assigned_provider="codex"),
            ],
        )

        # Beklenmeyen Exception fırlatan adaptör tüm council'ı düşürmemeli
        report = await engine.execute_plan("Test", plan)

        assert report.mode == ExecutionMode.COUNCIL
        assert "Claude sağlam" in report.final_summary
        failed_exec = next(e for e in report.executions if e.status == ExecutionStatus.FAILED)
        assert "Beklenmeyen adaptör hatası" in str(failed_exec.error)

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
