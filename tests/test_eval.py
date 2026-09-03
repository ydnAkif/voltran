import asyncio
import json

from typer.testing import CliRunner

from voltran.cli import app
from voltran.eval import DEFAULT_BENCHMARK_SUITE, BenchmarkRunner
from voltran.models import ExecutionStatus

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
