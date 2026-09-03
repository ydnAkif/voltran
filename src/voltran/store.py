"""VOLTRAN Yerel Kayıt Deposu (Store) — SQLite geçmiş ve denetim kayıtları."""

from __future__ import annotations

import json
import os
import sqlite3
import sys
from pathlib import Path
from typing import cast

from voltran.models import ExecutionReport, HistoryRecord
from voltran.sanitizer import sanitize_text


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

        clean_prompt = sanitize_text(report.task_prompt[:300])
        clean_summary = sanitize_text(report.final_summary[:500])

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
                        clean_prompt,
                        json.dumps(providers),
                        report.total_duration_ms,
                        overall_status,
                        clean_summary,
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
                    providers: list[str] = []
                    try:
                        raw_providers: object = json.loads(str(providers_json))
                        if isinstance(raw_providers, list):
                            obj_list = cast(list[object], raw_providers)
                            for item in obj_list:
                                providers.append(str(item))
                    except (json.JSONDecodeError, TypeError):
                        pass

                    records.append(
                        HistoryRecord(
                            run_id=str(run_id),
                            created_at=str(created_at),
                            mode=str(mode),
                            prompt_preview=str(prompt),
                            providers_used=providers,
                            duration_ms=int(duration_ms),
                            status=str(status),
                        )
                    )
                return records

        except sqlite3.Error:
            return []
