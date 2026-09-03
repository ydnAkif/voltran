from __future__ import annotations

from pathlib import Path

from voltran.models import (
    ExecutionMode,
    ExecutionReport,
    ExecutionStatus,
    ProviderExecution,
    TaskPlan,
    TaskResult,
)
from voltran.store import RunStore


def test_store_saves_and_lists_reports(tmp_path: Path) -> None:
    db_path = tmp_path / "test_voltran.db"
    store = RunStore(db_path)

    plan = TaskPlan(mode=ExecutionMode.QUICK, reasoning="test")
    report = ExecutionReport(
        task_prompt="Kısa test görevi",
        mode=ExecutionMode.QUICK,
        plan=plan,
        executions=[
            ProviderExecution(
                run_id="r1",
                provider="claude",
                status=ExecutionStatus.SUCCESS,
                duration_ms=120,
                result=TaskResult(summary="Test özeti", status="success"),
            )
        ],
        final_summary="Test özeti",
        total_duration_ms=120,
    )

    store.save_report(report)
    history = store.list_recent()

    assert len(history) == 1
    assert history[0].mode == "quick"
    assert history[0].status == "success"
    assert "Kısa test görevi" in history[0].prompt_preview
    assert history[0].providers_used == ["claude"]
