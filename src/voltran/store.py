"""VOLTRAN Yerel Kayıt Deposu (Store) — SQLite geçmiş ve denetim kayıtları."""

from __future__ import annotations

import json
import os
import sqlite3
import sys
from contextlib import closing
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, cast

from voltran.models import ExecutionPolicy, ExecutionReport, HistoryRecord, StoredRun, TaskPlan
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
            with closing(sqlite3.connect(self.db_path)) as conn, conn:
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
                        summary TEXT NOT NULL,
                        plan_json TEXT,
                        policy_json TEXT
                    )
                    """
                )
                # Geriye dönük uyumluluk: Mevcut tablolarda plan_json ve policy_json yoksa ekle
                cursor = conn.cursor()
                cursor.execute("PRAGMA table_info(runs)")
                columns = {str(row[1]) for row in cursor.fetchall()}
                if "plan_json" not in columns:
                    conn.execute("ALTER TABLE runs ADD COLUMN plan_json TEXT")
                if "policy_json" not in columns:
                    conn.execute("ALTER TABLE runs ADD COLUMN policy_json TEXT")

                # FR-15: Aktif çalışan süreçleri ve PID'leri takip eden geçici tablo
                conn.execute(
                    """
                    CREATE TABLE IF NOT EXISTS active_runs (
                        run_id TEXT PRIMARY KEY,
                        started_at TEXT NOT NULL,
                        pid INTEGER NOT NULL,
                        mode TEXT NOT NULL,
                        prompt TEXT NOT NULL
                    )
                    """
                )
                conn.commit()
        except sqlite3.Error:
            pass

    def save_report(self, report: ExecutionReport) -> None:
        """Raporu gizli değer içermeyen özet meta veriler ve plan ile veritabanına kaydeder."""

        providers = [e.provider for e in report.executions]
        overall_status = (
            "success"
            if report.executions and all(e.status == "success" for e in report.executions)
            else "failed"
        )

        clean_prompt = sanitize_text(report.task_prompt)
        clean_summary = sanitize_text(report.final_summary[:500])
        plan_json = report.plan.model_dump_json()
        policy_json = report.plan.policy.model_dump_json()

        try:
            with closing(sqlite3.connect(self.db_path)) as conn, conn:
                conn.execute(
                    """
                    INSERT OR REPLACE INTO runs (
                        run_id, created_at, mode, prompt, providers,
                        duration_ms, status, summary, plan_json, policy_json
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
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
                        plan_json,
                        policy_json,
                    ),
                )
                conn.commit()
        except sqlite3.Error:
            # Kayıt hatası ana iş akışını engellememeli
            pass

    def get_run(self, run_id: str) -> StoredRun | None:
        """Belirtilen çalıştırma kaydını plan ve politikasıyla birlikte döndürür."""

        try:
            with closing(sqlite3.connect(self.db_path)) as conn, conn:
                cursor = conn.cursor()
                cursor.execute(
                    """
                    SELECT run_id, created_at, mode, prompt, providers,
                           duration_ms, status, summary, plan_json, policy_json
                    FROM runs
                    WHERE run_id = ?
                    """,
                    (run_id,),
                )
                row = cursor.fetchone()
                if row is None:
                    return None

                (
                    r_id,
                    created_at,
                    mode,
                    prompt,
                    providers_json,
                    duration_ms,
                    status,
                    summary,
                    plan_json,
                    policy_json,
                ) = row
                providers: list[str] = []
                try:
                    raw_providers: object = json.loads(str(providers_json))
                    if isinstance(raw_providers, list):
                        obj_list = cast(list[object], raw_providers)
                        for item in obj_list:
                            providers.append(str(item))
                except (json.JSONDecodeError, TypeError):
                    pass

                plan: TaskPlan | None = None
                if plan_json:
                    try:
                        plan = TaskPlan.model_validate_json(str(plan_json))
                    except Exception:
                        plan = None

                policy: ExecutionPolicy | None = None
                if policy_json:
                    try:
                        policy = ExecutionPolicy.model_validate_json(str(policy_json))
                    except Exception:
                        policy = None

                return StoredRun(
                    run_id=str(r_id),
                    created_at=str(created_at),
                    mode=str(mode),
                    prompt=str(prompt),
                    providers=providers,
                    duration_ms=int(duration_ms),
                    status=str(status),
                    summary=str(summary),
                    plan=plan,
                    policy=policy,
                )
        except sqlite3.Error:
            return None

    def register_active_run(self, run_id: str, pid: int, mode: str, prompt: str) -> None:
        """Devam eden bir çalıştırmayı iptal yönetimi için kaydeder."""

        try:
            with closing(sqlite3.connect(self.db_path)) as conn, conn:
                conn.execute(
                    """
                    INSERT OR REPLACE INTO active_runs (run_id, started_at, pid, mode, prompt)
                    VALUES (?, ?, ?, ?, ?)
                    """,
                    (run_id, datetime.now(UTC).isoformat(), pid, mode, sanitize_text(prompt[:300])),
                )
                conn.commit()
        except sqlite3.Error:
            pass

    def unregister_active_run(self, run_id: str) -> None:
        """Tamamlanan veya iptal edilen çalıştırmayı aktif tablodan siler."""

        try:
            with closing(sqlite3.connect(self.db_path)) as conn, conn:
                conn.execute("DELETE FROM active_runs WHERE run_id = ?", (run_id,))
                conn.commit()
        except sqlite3.Error:
            pass

    def get_active_run(self, run_id: str) -> dict[str, Any] | None:
        """Belirtilen aktif çalıştırmanın PID ve meta verilerini döndürür."""

        try:
            with closing(sqlite3.connect(self.db_path)) as conn, conn:
                cursor = conn.cursor()
                cursor.execute(
                    """
                    SELECT run_id, started_at, pid, mode, prompt
                    FROM active_runs WHERE run_id = ?
                    """,
                    (run_id,),
                )
                row = cursor.fetchone()
                if row:
                    return {
                        "run_id": str(row[0]),
                        "started_at": str(row[1]),
                        "pid": int(row[2]),
                        "mode": str(row[3]),
                        "prompt": str(row[4]),
                    }
                return None
        except sqlite3.Error:
            return None

    def list_active_runs(self) -> list[dict[str, Any]]:
        """Mevcut tüm aktif çalıştırmaları döndürür."""

        try:
            with closing(sqlite3.connect(self.db_path)) as conn, conn:
                cursor = conn.cursor()
                cursor.execute("SELECT run_id, started_at, pid, mode, prompt FROM active_runs")
                return [
                    {
                        "run_id": str(r[0]),
                        "started_at": str(r[1]),
                        "pid": int(r[2]),
                        "mode": str(r[3]),
                        "prompt": str(r[4]),
                    }
                    for r in cursor.fetchall()
                ]
        except sqlite3.Error:
            return []

    def mark_run_cancelled(self, run_id: str) -> bool:
        """Çalıştırmayı veritabanında 'cancelled' durumuna çeker."""

        try:
            with closing(sqlite3.connect(self.db_path)) as conn, conn:
                cursor = conn.cursor()
                cursor.execute(
                    "UPDATE runs SET status = 'cancelled' WHERE run_id = ?",
                    (run_id,),
                )
                conn.commit()
                return cursor.rowcount > 0
        except sqlite3.Error:
            return False

    def list_recent(self, limit: int = 15) -> list[HistoryRecord]:
        """En son çalıştırılan görevleri döndürür."""

        try:
            with closing(sqlite3.connect(self.db_path)) as conn, conn:
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
                            prompt_preview=str(prompt)[:300],
                            providers_used=providers,
                            duration_ms=int(duration_ms),
                            status=str(status),
                        )
                    )
                return records

        except sqlite3.Error:
            return []
