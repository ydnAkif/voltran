import json

from pytest import MonkeyPatch
from typer.testing import CliRunner

from voltran.cli import app
from voltran.models import CheckStatus, DoctorCheck, DoctorReport

runner = CliRunner()


def _report(status: str = "ready") -> DoctorReport:
    return DoctorReport(
        overall_status=status,
        checks=[
            DoctorCheck(
                check_id="runtime.python",
                title="Python",
                status=CheckStatus.PASS,
                summary="Python 3.11.0",
            )
        ],
    )


def test_version() -> None:
    result = runner.invoke(app, ["--version"])

    assert result.exit_code == 0
    assert "voltran 0.1.0" in result.stdout


def test_doctor_json(monkeypatch: MonkeyPatch) -> None:
    def fake_report(*, check_sessions: bool, timeout: float) -> DoctorReport:
        del check_sessions, timeout
        return _report()

    monkeypatch.setattr("voltran.cli.build_doctor_report", fake_report)

    result = runner.invoke(app, ["doctor", "--json"])

    assert result.exit_code == 0
    payload = json.loads(result.stdout)
    assert payload["overall_status"] == "ready"
    assert payload["checks"][0]["check_id"] == "runtime.python"


def test_doctor_strict_returns_failure_for_degraded_report(monkeypatch: MonkeyPatch) -> None:
    def fake_report(*, check_sessions: bool, timeout: float) -> DoctorReport:
        del check_sessions, timeout
        return _report("degraded")

    monkeypatch.setattr("voltran.cli.build_doctor_report", fake_report)

    result = runner.invoke(app, ["doctor", "--strict"])

    assert result.exit_code == 1


def test_run_dry_run_json() -> None:
    result = runner.invoke(app, ["run", "Bu kodu incele ve açıkla", "--dry-run", "--json"])

    assert result.exit_code == 0
    payload = json.loads(result.stdout)
    assert payload["task_prompt"] == "Bu kodu incele ve açıkla"
    assert payload["mode"] in {"quick", "expert", "council"}
    assert "executions" in payload


def test_run_explain() -> None:
    result = runner.invoke(app, ["run", "Mimariyi karşılaştır", "--dry-run", "--explain"])

    assert result.exit_code == 0
    assert "Planlanan Mod" in result.stdout
    assert "Seçim Gerekçesi" in result.stdout


def test_history_command() -> None:
    result = runner.invoke(app, ["history"])

    assert result.exit_code == 0


def test_run_blind_and_write_options() -> None:
    result = runner.invoke(
        app,
        ["run", "Mimariyi karşılaştır", "--dry-run", "--explain", "--blind", "--write"],
    )

    assert result.exit_code == 0
    assert "Kör Hakemlik" in result.stdout
    assert "Dosya Yazma" in result.stdout
