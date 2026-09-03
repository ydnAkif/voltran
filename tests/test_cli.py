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
