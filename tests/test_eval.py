import asyncio
import json
from unittest.mock import AsyncMock, MagicMock

from typer.testing import CliRunner

from voltran.cli import app
from voltran.eval import DEFAULT_BENCHMARK_SUITE, BenchmarkRunner
from voltran.models import (
    CouncilSynthesis,
    ExecutionMode,
    ExecutionReport,
    ExecutionStatus,
    ProviderExecution,
    TaskPlan,
)

runner = CliRunner()


def test_benchmark_runner_dry_run() -> None:
    bench_runner = BenchmarkRunner()
    results = asyncio.run(bench_runner.run_all(dry_run=True))

    assert len(results) == len(DEFAULT_BENCHMARK_SUITE)
    for res in results:
        assert res.status == ExecutionStatus.SUCCESS
        assert res.duration_ms == 0
        assert res.confidence_score > 0.0


def test_cli_bench_dry_run() -> None:
    result = runner.invoke(app, ["bench", "--dry-run"])

    assert result.exit_code == 0
    assert "VOLTRAN Görev Bazlı Kıyaslama Raporu" in result.stdout
    assert "bench-arch-01" in result.stdout
    assert "bench-sec-02" in result.stdout
    assert "bench-code-03" in result.stdout


def test_cli_bench_dry_run_json() -> None:
    from typing import cast

    result = runner.invoke(app, ["bench", "--dry-run", "--json"])

    assert result.exit_code == 0
    raw: object = json.loads(result.stdout)
    assert isinstance(raw, list)
    payload = cast(list[dict[str, object]], raw)
    assert len(payload) == len(DEFAULT_BENCHMARK_SUITE)
    assert payload[0]["task_id"] == "bench-arch-01"
    assert payload[0]["status"] == "success"


def test_benchmark_propagates_failed_execution_status() -> None:
    task = DEFAULT_BENCHMARK_SUITE[0]
    report = ExecutionReport(
        task_prompt=task.prompt,
        mode=ExecutionMode.COUNCIL,
        plan=TaskPlan(mode=ExecutionMode.COUNCIL, reasoning="test"),
        executions=[
            ProviderExecution(
                run_id="failed",
                provider="hcom",
                status=ExecutionStatus.FAILED,
                duration_ms=5,
                error="council failed",
            )
        ],
        final_summary="council failed",
    )
    engine = MagicMock()
    engine.execute_plan = AsyncMock(return_value=report)
    router = MagicMock()
    bench_runner = BenchmarkRunner(tasks=[task], router=router, engine=engine)

    result = asyncio.run(bench_runner.run_task(task))

    assert result.status is ExecutionStatus.FAILED


def test_benchmark_does_not_report_consensus_when_disagreements_remain() -> None:
    task = DEFAULT_BENCHMARK_SUITE[0]
    report = ExecutionReport(
        task_prompt=task.prompt,
        mode=ExecutionMode.COUNCIL,
        plan=TaskPlan(mode=ExecutionMode.COUNCIL, reasoning="test"),
        executions=[
            ProviderExecution(
                run_id="ok",
                provider="claude",
                status=ExecutionStatus.SUCCESS,
                duration_ms=5,
            )
        ],
        final_summary="done",
        synthesis=CouncilSynthesis(
            consensus=["session completed"],
            disagreements=["explicit consensus was not reached"],
        ),
    )
    engine = MagicMock()
    engine.execute_plan = AsyncMock(return_value=report)
    bench_runner = BenchmarkRunner(tasks=[task], router=MagicMock(), engine=engine)

    result = asyncio.run(bench_runner.run_task(task))

    assert result.consensus_reached is False
