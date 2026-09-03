from collections.abc import Sequence
from pathlib import Path

from pytest import MonkeyPatch

from voltran.doctor import CommandResult, build_doctor_report


def _finder(command: str) -> str | None:
    if command in {"agy", "gemini"}:
        return None
    return f"/usr/local/bin/{command}"


def _runner(executable: str, args: Sequence[str], timeout: float) -> CommandResult:
    del timeout
    if tuple(args) == ("--version",):
        return CommandResult(0, stdout=f"{executable} 1.2.3\n")
    return CommandResult(0, stdout="authenticated@example.com\n")


def test_report_uses_injected_provider_probes_without_real_calls(
    monkeypatch: MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setenv("VOLTRAN_CONFIG_DIR", str(tmp_path / "config"))
    monkeypatch.setenv("VOLTRAN_DATA_DIR", str(tmp_path / "data"))
    report = build_doctor_report(finder=_finder, runner=_runner)
    by_id = {check.check_id: check for check in report.checks}

    assert by_id["provider.codex"].status == "pass"
    assert by_id["runtime.hcom"].status == "pass"
    assert by_id["session.codex"].summary == "Oturum açık"
    assert by_id["provider.claude"].status == "pass"
    assert by_id["provider.google"].status == "warning"
    assert "session.agy" not in by_id
    assert report.overall_status == "degraded"


def test_session_probes_can_be_disabled() -> None:
    report = build_doctor_report(check_sessions=False, finder=_finder, runner=_runner)

    assert all(not check.check_id.startswith("session.") for check in report.checks)


def test_legacy_gemini_is_reported_as_a_fallback(monkeypatch: MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setenv("VOLTRAN_CONFIG_DIR", str(tmp_path / "config"))
    monkeypatch.setenv("VOLTRAN_DATA_DIR", str(tmp_path / "data"))

    def legacy_finder(command: str) -> str | None:
        if command == "agy":
            return None
        return f"/usr/local/bin/{command}"

    report = build_doctor_report(
        check_sessions=False,
        finder=legacy_finder,
        runner=_runner,
    )
    google = next(check for check in report.checks if check.check_id == "provider.google")

    assert google.status == "warning"
    assert google.details["command"] == "gemini"
    assert "eski istemci" in google.summary


def test_authentication_command_output_is_not_stored() -> None:
    report = build_doctor_report(finder=_finder, runner=_runner)
    serialized = report.model_dump_json()

    assert "authenticated@example.com" not in serialized


def test_hcom_is_reported_as_required_for_council_when_missing(
    monkeypatch: MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setenv("VOLTRAN_CONFIG_DIR", str(tmp_path / "config"))
    monkeypatch.setenv("VOLTRAN_DATA_DIR", str(tmp_path / "data"))

    def finder_without_hcom(command: str) -> str | None:
        if command in {"hcom", "agy", "gemini"}:
            return None
        return f"/usr/local/bin/{command}"

    report = build_doctor_report(
        check_sessions=False,
        finder=finder_without_hcom,
        runner=_runner,
    )
    hcom = next(check for check in report.checks if check.check_id == "runtime.hcom")

    assert hcom.status == "warning"
    assert hcom.details["required_for"] == "council"
    assert "brew install aannoo/hcom/hcom" in (hcom.remediation or "")
