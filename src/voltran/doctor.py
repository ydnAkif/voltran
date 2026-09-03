"""Yerel ortam için değişiklik yapmayan teşhis kontrolleri."""

from __future__ import annotations

import importlib.util
import os
import platform
import re
import shutil
import subprocess
import sys
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from pathlib import Path

from voltran.models import CheckStatus, DoctorCheck, DoctorReport

CommandRunner = Callable[[str, Sequence[str], float], "CommandResult"]
ExecutableFinder = Callable[[str], str | None]


@dataclass(frozen=True, slots=True)
class CommandResult:
    """Alt süreç çıktısının küçük ve test edilebilir temsili."""

    returncode: int
    stdout: str = ""
    stderr: str = ""
    timed_out: bool = False


@dataclass(frozen=True, slots=True)
class ProviderProbe:
    """Bir sağlayıcı CLI'ı için salt okunur kontrol tanımı."""

    key: str
    name: str
    executable: str
    fallback_executables: tuple[str, ...] = ()
    version_args: tuple[str, ...] = ("--version",)
    session_args: tuple[str, ...] | None = None


PROVIDERS = (
    ProviderProbe("codex", "Codex", "codex", session_args=("login", "status")),
    ProviderProbe("claude", "Claude", "claude", session_args=("auth", "status")),
    ProviderProbe(
        "google",
        "Google Antigravity",
        "agy",
        fallback_executables=("gemini",),
    ),
)

HCOM_INSTALL_COMMAND = "brew install aannoo/hcom/hcom"

_EMAIL_PATTERN = re.compile(r"\b[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}\b", re.IGNORECASE)
_SECRET_PATTERN = re.compile(r"(?i)\b(?:bearer\s+)?(?:sk-[A-Za-z0-9_-]{12,}|[A-Za-z0-9_-]{32,})\b")


def _safe_output(value: str, *, limit: int = 160) -> str:
    """Komut çıktısından olası kişisel/gizli değerleri ayıklar."""

    first_line = next((line.strip() for line in value.splitlines() if line.strip()), "")
    redacted = _EMAIL_PATTERN.sub("[e-posta maskelendi]", first_line)
    redacted = _SECRET_PATTERN.sub("[gizli değer maskelendi]", redacted)
    return redacted[:limit]


def run_command(executable: str, args: Sequence[str], timeout: float) -> CommandResult:
    """Bir salt okunur teşhis komutunu süre sınırıyla çalıştırır."""

    try:
        completed = subprocess.run(
            [executable, *args],
            capture_output=True,
            check=False,
            text=True,
            timeout=timeout,
        )
    except subprocess.TimeoutExpired:
        return CommandResult(returncode=124, timed_out=True)
    except OSError as exc:
        return CommandResult(returncode=126, stderr=type(exc).__name__)
    return CommandResult(completed.returncode, completed.stdout, completed.stderr)


def _platform_check() -> DoctorCheck:
    system = platform.system()
    machine = platform.machine().lower()
    supported = system == "Darwin" and machine in {"arm64", "aarch64"}
    return DoctorCheck(
        check_id="system.platform",
        title="Platform",
        status=CheckStatus.PASS if supported else CheckStatus.WARNING,
        summary=f"{system} / {machine}",
        details={"supported_target": "macOS Apple Silicon"},
        remediation=None if supported else "MVP için macOS Apple Silicon kullanın.",
    )


def _python_check() -> DoctorCheck:
    current = sys.version_info[:3]
    supported = current >= (3, 11)
    version = ".".join(str(part) for part in current)
    return DoctorCheck(
        check_id="runtime.python",
        title="Python",
        status=CheckStatus.PASS if supported else CheckStatus.FAIL,
        summary=f"Python {version}",
        details={"minimum": "3.11", "executable": sys.executable},
        remediation=None if supported else "Python 3.11 veya daha yeni bir sürüm kurun.",
    )


def _sqlite_check() -> DoctorCheck:
    available = importlib.util.find_spec("sqlite3") is not None
    return DoctorCheck(
        check_id="runtime.sqlite",
        title="SQLite",
        status=CheckStatus.PASS if available else CheckStatus.FAIL,
        summary="Python SQLite desteği mevcut" if available else "Python SQLite desteği yok",
        remediation=None if available else "SQLite desteği olan bir Python dağıtımı kurun.",
    )


def _nearest_existing_parent(path: Path) -> Path:
    candidate = path.expanduser()
    while not candidate.exists() and candidate != candidate.parent:
        candidate = candidate.parent
    return candidate


def _directory_check(name: str, path: Path, check_id: str) -> DoctorCheck:
    parent = _nearest_existing_parent(path)
    writable = parent.is_dir() and os.access(parent, os.W_OK | os.X_OK)
    return DoctorCheck(
        check_id=check_id,
        title=name,
        status=CheckStatus.PASS if writable else CheckStatus.FAIL,
        summary="Kullanılabilir" if writable else "Yazılabilir değil",
        details={"path": str(path.expanduser()), "checked_parent": str(parent)},
        remediation=None if writable else f"{parent} için yazma iznini kontrol edin.",
    )


def _configured_directories() -> tuple[tuple[str, Path, str], ...]:
    config_root = Path(os.environ.get("XDG_CONFIG_HOME", Path.home() / ".config"))
    if sys.platform == "darwin":
        default_data_root = Path.home() / "Library" / "Application Support"
    else:
        default_data_root = Path.home() / ".local" / "share"
    data_root = Path(os.environ.get("XDG_DATA_HOME", default_data_root))
    config_dir = Path(os.environ.get("VOLTRAN_CONFIG_DIR", config_root / "voltran"))
    data_dir = Path(os.environ.get("VOLTRAN_DATA_DIR", data_root / "voltran"))
    return (
        ("Yapılandırma dizini", config_dir, "filesystem.config"),
        ("Veri dizini", data_dir, "filesystem.data"),
    )


def _hcom_check(
    *,
    finder: ExecutableFinder,
    runner: CommandRunner,
    timeout: float,
) -> DoctorCheck:
    """Canlı council modu için gereken hcom çalışma motorunu denetle."""

    executable = finder("hcom")
    if executable is None:
        return DoctorCheck(
            check_id="runtime.hcom",
            title="hcom işbirliği motoru",
            status=CheckStatus.WARNING,
            summary="Bulunamadı; council modu kullanılamaz",
            details={"required_for": "council"},
            remediation=f"hcom'u kurun: {HCOM_INSTALL_COMMAND}",
        )

    version_result = runner(executable, ("--version",), timeout)
    if version_result.timed_out:
        status = CheckStatus.WARNING
        summary = "Sürüm kontrolü zaman aşımına uğradı"
        remediation = "hcom kurulumunu ve PATH ayarını kontrol edin."
    elif version_result.returncode == 0:
        status = CheckStatus.PASS
        summary = _safe_output(version_result.stdout) or "Kurulu"
        remediation = None
    else:
        status = CheckStatus.WARNING
        summary = "Çalıştırılamadı"
        remediation = f"hcom'u yeniden kurun: {HCOM_INSTALL_COMMAND}"

    return DoctorCheck(
        check_id="runtime.hcom",
        title="hcom işbirliği motoru",
        status=status,
        summary=summary,
        details={"executable": executable, "required_for": "council"},
        remediation=remediation,
    )


def _provider_checks(
    probe: ProviderProbe,
    *,
    finder: ExecutableFinder,
    runner: CommandRunner,
    check_sessions: bool,
    timeout: float,
) -> list[DoctorCheck]:
    command = probe.executable
    executable = finder(command)
    using_legacy_fallback = False
    if executable is None:
        for fallback in probe.fallback_executables:
            executable = finder(fallback)
            if executable is not None:
                command = fallback
                using_legacy_fallback = True
                break

    if executable is None:
        return [
            DoctorCheck(
                check_id=f"provider.{probe.key}",
                title=f"{probe.name} CLI",
                status=CheckStatus.WARNING,
                summary="Bulunamadı",
                remediation=f"Resmî {probe.name} CLI aracını kurup PATH'e ekleyin.",
            )
        ]

    version_result = runner(executable, probe.version_args, timeout)
    if version_result.timed_out:
        version_status = CheckStatus.WARNING
        version_summary = "Sürüm kontrolü zaman aşımına uğradı"
    elif version_result.returncode == 0:
        version_status = CheckStatus.WARNING if using_legacy_fallback else CheckStatus.PASS
        version_summary = _safe_output(version_result.stdout) or "Kurulu"
        if using_legacy_fallback:
            version_summary = f"{version_summary} (eski istemci)"
    else:
        version_status = CheckStatus.WARNING
        version_summary = "Sürüm bilgisi alınamadı"

    checks = [
        DoctorCheck(
            check_id=f"provider.{probe.key}",
            title=f"{probe.name} CLI",
            status=version_status,
            summary=version_summary,
            details={"command": command, "executable": executable},
            remediation=(
                f"{probe.name} CLI'ye geçin: brew install --cask antigravity-cli"
                if using_legacy_fallback
                else None
            ),
        )
    ]

    if not check_sessions:
        return checks
    if probe.session_args is None:
        checks.append(
            DoctorCheck(
                check_id=f"session.{probe.executable}",
                title=f"{probe.name} oturumu",
                status=CheckStatus.INFO,
                summary="Güvenli yerel oturum kontrolü tanımlı değil",
            )
        )
        return checks

    session_result = runner(executable, probe.session_args, timeout)
    if session_result.timed_out:
        status = CheckStatus.WARNING
        summary = "Oturum kontrolü zaman aşımına uğradı"
    elif session_result.returncode == 0:
        status = CheckStatus.PASS
        summary = "Oturum açık"
    else:
        status = CheckStatus.WARNING
        summary = "Oturum doğrulanamadı"
    checks.append(
        DoctorCheck(
            check_id=f"session.{probe.executable}",
            title=f"{probe.name} oturumu",
            status=status,
            summary=summary,
            remediation=(
                None
                if status is CheckStatus.PASS
                else f"Resmî {probe.name} CLI aracında yeniden oturum açın."
            ),
        )
    )
    return checks


def build_doctor_report(
    *,
    check_sessions: bool = True,
    timeout: float = 3.0,
    finder: ExecutableFinder = shutil.which,
    runner: CommandRunner = run_command,
) -> DoctorReport:
    """Tüm yerel kontrolleri çalıştırır; kurulum veya dosya değişikliği yapmaz."""

    checks = [_platform_check(), _python_check(), _sqlite_check()]
    checks.extend(
        _directory_check(name, path, check_id) for name, path, check_id in _configured_directories()
    )
    checks.append(_hcom_check(finder=finder, runner=runner, timeout=timeout))
    for provider in PROVIDERS:
        checks.extend(
            _provider_checks(
                provider,
                finder=finder,
                runner=runner,
                check_sessions=check_sessions,
                timeout=timeout,
            )
        )

    statuses = {check.status for check in checks}
    if CheckStatus.FAIL in statuses:
        overall = "failed"
    elif CheckStatus.WARNING in statuses:
        overall = "degraded"
    else:
        overall = "ready"
    return DoctorReport(overall_status=overall, checks=checks)
