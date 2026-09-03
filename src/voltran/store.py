"""VOLTRAN Yerel Kayıt Deposu (Store) — SQLite geçmiş ve denetim kayıtları."""

from __future__ import annotations

import json
import os
import sqlite3
import sys
from pathlib import Path

from voltran.models import ExecutionReport, HistoryRecord


def get_default_db_path() -> Path:
    """İşletim sistemine uygun yerel veri tabanı yolunu belirler."""

    candidates: list[Path] = []
    if "VOLTRAN_DATA_DIR" in os.environ:
        candidates.append(Path(os.environ["VOLTRAN_DATA_DIR"]))

    if sys.platform == "darwin":
        candidates.append(Path.home() / "Library" / "Application Support" / "voltran")
    else:
        candidates.append(Path.home() / ".local" / "share" / "voltran")

    candidates.append(Path.home() / ".voltran")
    candidates.append(Path.cwd() / ".voltran")

    for candidate in candidates:
        try:
            candidate.mkdir(parents=True, exist_ok=True)
            test_file = candidate / ".write_test"
            test_file.touch()
            test_file.unlink()
            return candidate / "voltran.db"
        except (OSError, PermissionError):
            continue

    return Path(":memory:")


class RunStore:
    """Çalıştırma kayıtlarını güvenli ve sorgulanabilir şekilde saklar."""

    def __init__(self, db_path: Path | None = None) -> None:
        self.db_path = db_path or get_default_db_path()
        self._init_db()

    def _init_db(self) -> None:
        try:
            with sqlite3.connect(self.db_path) as conn:
                conn.execute(
                    """
                    CREATE TABLE IF NOT EXISTS runs (
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
                conn.commit()
        except sqlite3.Error:
            pass

    def save_report(self, report: ExecutionReport) -> None:
        """Raporu gizli değer içermeyen özet meta verilerle veritabanına kaydeder."""

        providers = [e.provider for e in report.executions]
        overall_status = (
            "success" if any(e.status == "success" for e in report.executions) else "failed"
        )

        try:
            with sqlite3.connect(self.db_path) as conn:
                conn.execute(
                    """
                    INSERT OR REPLACE INTO runs (
                        run_id, created_at, mode, prompt, providers, duration_ms, status, summary
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        report.run_id,
                        report.created_at.isoformat(),
                        report.mode.value,
                        report.task_prompt[:300],
                        json.dumps(providers),
                        report.total_duration_ms,
                        overall_status,
                        report.final_summary[:500],
                    ),
                )
                conn.commit()
        except sqlite3.Error:
            # Kayıt hatası ana iş akışını engellememeli
            pass

    def list_recent(self, limit: int = 15) -> list[HistoryRecord]:
        """En son çalıştırılan görevleri döndürür."""

        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                cursor.execute(
                    """
                    SELECT run_id, created_at, mode, prompt, providers, duration_ms, status
                    FROM runs
                    ORDER BY created_at DESC
                    LIMIT ?
                    """,
                    (limit,),
                )
                rows = cursor.fetchall()
                records: list[HistoryRecord] = []
                for row in rows:
                    run_id, created_at, mode, prompt, providers_json, duration_ms, status = row
                    try:
                        providers = json.loads(providers_json)
                    except json.JSONDecodeError:
                        providers = []
                    records.append(
                        HistoryRecord(
                            run_id=run_id,
                            created_at=created_at,
                            mode=mode,
                            prompt_preview=prompt,
                            providers_used=providers,
                            duration_ms=duration_ms,
                            status=status,
                        )
                    )
                return records
        except sqlite3.Error:
            return []
