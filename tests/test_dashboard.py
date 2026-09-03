from pathlib import Path

from typer.testing import CliRunner

from voltran.cli import app
from voltran.dashboard import DashboardView
from voltran.hcom_client import HcomAgentInfo, HcomEvent
from voltran.lock import LockInfo
from voltran.models import HistoryRecord

runner = CliRunner()


def test_dashboard_render_once() -> None:
    view = DashboardView()
    rendered = view.render_once()
    assert rendered is not None


def test_dashboard_build_layout_with_data(tmp_path: Path) -> None:
    view = DashboardView()
    agents = [
        HcomAgentInfo(name="mimar-1", status="idle", tag="mimar", model="claude-3"),
        HcomAgentInfo(name="kodcu-2", status="busy", tag="kodcu", model="o3-mini"),
    ]
    locks = [LockInfo(file_path=str(tmp_path / "app.py"), holder="kodcu-2", acquired_at=100.0)]
    records = [
        HistoryRecord(
            run_id="run-12345678",
            created_at="2026-09-03T18:00:00",
            mode="council",
            status="success",
            duration_ms=1200,
            prompt_preview="Mimari analiz yap",
            providers_used=["claude", "codex"],
        )
    ]

    events = [
        HcomEvent(
            event_id="e1",
            timestamp="18:00:05",
            event_type="message",
            agent="mimar-1",
            target="kodcu-2",
            content="Görüşüm hazır.",
        )
    ]

    layout = view.build_layout(agents, locks, records, events)
    assert layout is not None
    assert layout["header"] is not None
    assert layout["body"] is not None
    assert layout["footer"] is not None


def test_cli_dashboard_once() -> None:
    result = runner.invoke(app, ["dashboard", "--once"])
    assert result.exit_code == 0
    assert "VOLTRAN MULTI-AGENT DASHBOARD" in result.stdout
