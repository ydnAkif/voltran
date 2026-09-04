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


def test_store_redacts_secrets_and_pii_in_sqlite(tmp_path: Path) -> None:
    db_path = tmp_path / "test_privacy_voltran.db"
    store = RunStore(db_path)

    plan = TaskPlan(mode=ExecutionMode.QUICK, reasoning="test")
    report = ExecutionReport(
        task_prompt="API çağrısı: sk-1234567890abcdef1234567890 ve user@example.com",
        mode=ExecutionMode.QUICK,
        plan=plan,
        executions=[],
        final_summary="Gizli çıktı: password=supersecret1234567890",
        total_duration_ms=50,
    )

    store.save_report(report)
    history = store.list_recent()

    assert len(history) == 1
    assert "sk-1234567890" not in history[0].prompt_preview
    assert "user@example.com" not in history[0].prompt_preview
    assert "[REDACTED_API_KEY]" in history[0].prompt_preview
    assert "[REDACTED_EMAIL]" in history[0].prompt_preview


def test_store_marks_partial_failure_as_failed(tmp_path: Path) -> None:
    store = RunStore(tmp_path / "partial.db")
    plan = TaskPlan(mode=ExecutionMode.COUNCIL, reasoning="test")
    report = ExecutionReport(
        task_prompt="Konsey görevi",
        mode=ExecutionMode.COUNCIL,
        plan=plan,
        executions=[
            ProviderExecution(
                run_id="ok",
                provider="claude",
                status=ExecutionStatus.SUCCESS,
                duration_ms=1,
                result=TaskResult(summary="ok", status="success"),
            ),
            ProviderExecution(
                run_id="failed",
                provider="codex",
                status=ExecutionStatus.FAILED,
                duration_ms=1,
                error="boom",
            ),
        ],
        final_summary="Kısmi sonuç",
    )

    store.save_report(report)

    assert store.list_recent()[0].status == "failed"
