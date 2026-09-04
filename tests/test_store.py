from __future__ import annotations

from pathlib import Path

from voltran.models import (
    ExecutionMode,
    ExecutionPolicy,
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


def test_store_saves_and_retrieves_plan_with_get_run(tmp_path: Path) -> None:
    db_path = tmp_path / "replay_test.db"
    store = RunStore(db_path)

    plan = TaskPlan(
        mode=ExecutionMode.EXPERT,
        reasoning="derin analiz",
    )
    report = ExecutionReport(
        task_prompt="Detaylı analiz görevi",
        mode=ExecutionMode.EXPERT,
        plan=plan,
        executions=[],
        final_summary="Analiz tamamlandı",
    )

    store.save_report(report)
    stored = store.get_run(report.run_id)

    assert stored is not None
    assert stored.run_id == report.run_id
    assert stored.mode == "expert"
    assert stored.prompt == "Detaylı analiz görevi"
    assert stored.plan is not None
    assert stored.plan.reasoning == "derin analiz"


def test_store_migrates_legacy_database_without_plan_columns(tmp_path: Path) -> None:
    import sqlite3
    from contextlib import closing

    legacy_db = tmp_path / "legacy.db"
    with closing(sqlite3.connect(legacy_db)) as conn:
        conn.execute(
            """
            CREATE TABLE runs (
                run_id TEXT PRIMARY KEY,
                created_at TEXT NOT NULL,
                mode TEXT NOT NULL,
                prompt TEXT NOT NULL,
                providers TEXT NOT NULL,
                duration_ms INTEGER NOT NULL,
                status TEXT NOT NULL,
                summary TEXT NOT NULL
            )
            """
        )
        conn.execute(
            """
            INSERT INTO runs VALUES (
                'old-run-123', '2026-09-01T10:00:00', 'quick',
                'Eski görev', '["claude"]', 50, 'success', 'Eski özet'
            )
            """
        )
        conn.commit()

    # RunStore başlatıldığında otomatik migrasyon çalışmalı
    store = RunStore(legacy_db)
    legacy_run = store.get_run("old-run-123")

    assert legacy_run is not None
    assert legacy_run.run_id == "old-run-123"
    assert legacy_run.plan is None  # Eski kayıtta plan yok

    new_policy = ExecutionPolicy(blind_mode=True)
    new_plan = TaskPlan(mode=ExecutionMode.QUICK, reasoning="yeni", policy=new_policy)
    new_report = ExecutionReport(
        task_prompt="Yeni görev",
        mode=ExecutionMode.QUICK,
        plan=new_plan,
        executions=[],
        final_summary="Yeni özet",
    )
    store.save_report(new_report)
    new_run = store.get_run(new_report.run_id)
    assert new_run is not None
    assert new_run.plan is not None
    assert new_run.policy is not None
    assert new_run.policy.blind_mode is True


def test_store_active_runs_lifecycle(tmp_path: Path) -> None:
    store = RunStore(tmp_path / "active.db")

    assert store.get_run("non-existent") is None
    assert store.get_active_run("run-xyz") is None
    assert store.list_active_runs() == []
    store.register_active_run(
        "run-xyz",
        pid=12345,
        mode="council",
        prompt="Gizli sk-1234567890abcdef1234567890",
    )
    active = store.get_active_run("run-xyz")
    assert active is not None
    assert active["pid"] == 12345
    assert active["mode"] == "council"
    assert "[REDACTED_API_KEY]" in active["prompt"]

    all_active = store.list_active_runs()
    assert len(all_active) == 1
    assert all_active[0]["run_id"] == "run-xyz"

    store.unregister_active_run("run-xyz")
    assert store.get_active_run("run-xyz") is None
    assert store.list_active_runs() == []
