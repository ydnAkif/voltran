import json
import os
import signal
from pathlib import Path

from pytest import MonkeyPatch
from typer.testing import CliRunner

from voltran.cli import app
from voltran.models import CheckStatus, DoctorCheck, DoctorReport

runner = CliRunner()


def _voltran_command(pid: int) -> str:
    del pid
    return "/usr/local/bin/voltran run görev"


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


def test_run_stops_when_write_lock_cannot_be_acquired(
    monkeypatch: MonkeyPatch, tmp_path: Path
) -> None:
    def deny_lock(lock_manager: object, target_file: Path, holder: str) -> bool:
        del lock_manager, target_file, holder
        return False

    def existing_holder(lock_manager: object, target_file: Path) -> str:
        del lock_manager, target_file
        return "another-voltran-run"

    context_file = tmp_path / "context.py"
    context_file.write_text("print('hello')", encoding="utf-8")
    monkeypatch.setattr("voltran.lock.FileLockManager.acquire", deny_lock)
    monkeypatch.setattr("voltran.lock.FileLockManager.get_holder", existing_holder)

    result = runner.invoke(
        app,
        ["run", "Dosyayı düzelt", "--file", str(context_file), "--write", "--dry-run"],
    )

    assert result.exit_code == 1
    assert "Dosya kilidi alınamadı" in result.stdout
    assert "another-voltran-run" in result.stdout


def test_unlock_file_and_all(monkeypatch: MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.chdir(tmp_path)
    from voltran.lock import FileLockManager

    first = tmp_path / "first.py"
    second = tmp_path / "second.py"
    lock_mgr = FileLockManager()
    assert lock_mgr.acquire(first, "crashed-1") is True
    assert lock_mgr.acquire(second, "crashed-2") is True

    result = runner.invoke(app, ["unlock", str(first)])
    assert result.exit_code == 0
    assert lock_mgr.get_holder(first) is None
    assert lock_mgr.get_holder(second) == "crashed-2"

    result = runner.invoke(app, ["unlock", "--all"])
    assert result.exit_code == 0
    assert lock_mgr.list_active_locks() == []


def test_unlock_reports_when_no_lock_exists(monkeypatch: MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.chdir(tmp_path)
    target = tmp_path / "never-locked.py"

    result = runner.invoke(app, ["unlock", str(target)])

    assert result.exit_code == 0
    assert "Kilit bulunmuyor" in result.stdout
    assert "Kilit kaldırıldı" not in result.stdout


def test_run_rejects_unknown_provider(monkeypatch: MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.chdir(tmp_path)

    result = runner.invoke(app, ["run", "test görevi", "--provider", "gpt5", "--dry-run"])

    assert result.exit_code == 2
    assert "Bilinmeyen sağlayıcı" in result.stdout
    assert "claude" in result.stdout


def test_run_warns_on_sensitive_input_and_skips_council(
    monkeypatch: MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.chdir(tmp_path)
    context = tmp_path / "bordro.txt"
    context.write_text("TC: 12345678901\nMaaş: 45000", encoding="utf-8")

    result = runner.invoke(
        app,
        ["run", "Bu bordroyu karşılaştır", "--file", str(context), "--dry-run", "--explain"],
    )

    assert result.exit_code == 0
    assert "Hassas veri uyarısı" in result.stdout
    assert "Konsey moduna otomatik genişletme yapılmadı" in result.stdout
    assert "EXPERT" in result.stdout
    # Uyarı bulgunun türünü söyler, değerini değil.
    assert "12345678901" not in result.stdout


def test_dry_run_shows_data_sharing_preview(monkeypatch: MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.chdir(tmp_path)
    context = tmp_path / "notlar.txt"
    context.write_text("merhaba dünya", encoding="utf-8")

    result = runner.invoke(
        app,
        [
            "run",
            "Bu dosyayı incele",
            "--file",
            str(context),
            "--provider",
            "codex",
            "--dry-run",
        ],
    )

    assert result.exit_code == 0
    assert "Veri Paylaşım Önizlemesi" in result.stdout
    assert "notlar.txt" in result.stdout
    assert "Tahmini model çağrısı: 1" in result.stdout
    assert "codex" in result.stdout


def test_run_rejects_binary_context_file(monkeypatch: MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.chdir(tmp_path)
    binary = tmp_path / "resim.png"
    binary.write_bytes(b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR")

    result = runner.invoke(app, ["run", "incele", "--file", str(binary), "--dry-run"])

    assert result.exit_code == 2
    assert "Bağlam dosyası hatası" in result.stdout
    assert "ikili" in result.stdout


def test_run_rejects_invalid_line_range(monkeypatch: MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.chdir(tmp_path)
    target = tmp_path / "app.py"
    target.write_text("bir\niki\n", encoding="utf-8")

    result = runner.invoke(
        app, ["run", "incele", "--file", str(target), "--lines", "40-10", "--dry-run"]
    )

    assert result.exit_code == 2
    assert "Satır aralığı ters" in result.stdout


def test_dry_run_reports_context_minimisation(monkeypatch: MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.chdir(tmp_path)
    target = tmp_path / "buyuk.py"
    target.write_text("x" * 10_000, encoding="utf-8")

    result = runner.invoke(
        app,
        [
            "run",
            "Bu dosyayı incele",
            "--file",
            str(target),
            "--max-context",
            "1000",
            "--provider",
            "codex",
            "--dry-run",
        ],
    )

    assert result.exit_code == 0
    assert "Veri minimizasyonu" in result.stdout
    assert "gönderilmeyecek" in result.stdout


def test_config_command_shows_defaults(monkeypatch: MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("VOLTRAN_CONFIG_DIR", str(tmp_path / "yok"))

    result = runner.invoke(app, ["config"])

    assert result.exit_code == 0
    assert "varsayılan" in result.stdout
    assert "Hiçbir yapılandırma dosyası bulunamadı" in result.stdout
    assert "yapılandırılamaz" in result.stdout


def test_config_command_reports_project_layer(monkeypatch: MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("VOLTRAN_CONFIG_DIR", str(tmp_path / "yok"))
    (tmp_path / "voltran.toml").write_text('mode = "quick"\ntimeout = 12\n', encoding="utf-8")

    result = runner.invoke(app, ["config", "--json"])

    assert result.exit_code == 0
    payload = json.loads(result.stdout)
    assert payload["settings"]["mode"] == "quick"
    assert payload["provenance"]["mode"] == "proje"
    assert payload["provenance"]["max_context"] == "varsayılan"
    assert payload["sources"] == [str(tmp_path / "voltran.toml")]


def test_run_uses_project_config_and_cli_wins(monkeypatch: MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("VOLTRAN_CONFIG_DIR", str(tmp_path / "yok"))
    (tmp_path / "voltran.toml").write_text(
        'mode = "council"\nproviders = ["codex", "google"]\nblind = true\n',
        encoding="utf-8",
    )

    result = runner.invoke(app, ["run", "bir görev", "--dry-run", "--explain"])
    assert result.exit_code == 0
    assert "COUNCIL" in result.stdout
    assert "codex, google" in result.stdout
    assert "Kör Hakemlik" in result.stdout

    # Komut satırı proje dosyasını ezer.
    overridden = runner.invoke(
        app, ["run", "bir görev", "--mode", "quick", "--no-blind", "--dry-run", "--explain"]
    )
    assert overridden.exit_code == 0
    assert "QUICK" in overridden.stdout
    assert "Kör Hakemlik" not in overridden.stdout


def test_run_rejects_invalid_mode_from_config(monkeypatch: MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("VOLTRAN_CONFIG_DIR", str(tmp_path / "yok"))
    (tmp_path / "voltran.toml").write_text('mode = "konsey"\n', encoding="utf-8")

    result = runner.invoke(app, ["run", "bir görev", "--dry-run"])

    assert result.exit_code == 2
    assert "Geçersiz mod" in result.stdout
    assert "proje" in result.stdout


def test_run_reports_broken_config_file(monkeypatch: MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("VOLTRAN_CONFIG_DIR", str(tmp_path / "yok"))
    (tmp_path / "voltran.toml").write_text("timeout = [bozuk\n", encoding="utf-8")

    result = runner.invoke(app, ["run", "bir görev", "--dry-run"])

    assert result.exit_code == 2
    assert "Yapılandırma hatası" in result.stdout


def test_replay_command_missing_and_legacy(monkeypatch: MonkeyPatch, tmp_path: Path) -> None:
    from voltran.models import ExecutionMode, ExecutionReport, TaskPlan
    from voltran.store import RunStore

    monkeypatch.chdir(tmp_path)
    db_path = tmp_path / "voltran.db"
    store = RunStore(db_path)
    monkeypatch.setattr("voltran.store.get_default_db_path", lambda: db_path)

    # 1. Olmayan çalıştırma
    result = runner.invoke(app, ["replay", "non-existent-id"])
    assert result.exit_code == 1
    assert "Çalıştırma bulunamadı" in result.stdout

    # 2. Plan bilgisi olmayan eski formatta kayıt
    plan = TaskPlan(mode=ExecutionMode.QUICK, reasoning="eski")
    report = ExecutionReport(
        run_id="legacy-run-123",
        task_prompt="Eski görev",
        mode=ExecutionMode.QUICK,
        plan=plan,
        executions=[],
        final_summary="Eski özet",
    )
    store.save_report(report)
    # plan_json alanını elle null yapalım (eski veri simülasyonu)
    import sqlite3
    from contextlib import closing

    with closing(sqlite3.connect(db_path)) as conn, conn:
        conn.execute("UPDATE runs SET plan_json = NULL WHERE run_id = 'legacy-run-123'")
        conn.commit()

    result = runner.invoke(app, ["replay", "legacy-run-123"])
    assert result.exit_code == 1
    assert "eski formatta" in result.stdout


def test_replay_command_success(monkeypatch: MonkeyPatch, tmp_path: Path) -> None:
    from voltran.models import ExecutionMode, ExecutionReport, TaskPlan
    from voltran.store import RunStore

    monkeypatch.chdir(tmp_path)
    db_path = tmp_path / "voltran.db"
    store = RunStore(db_path)
    monkeypatch.setattr("voltran.store.get_default_db_path", lambda: db_path)

    plan = TaskPlan(mode=ExecutionMode.QUICK, reasoning="hızlı test")
    report = ExecutionReport(
        run_id="replay-run-456",
        task_prompt="Test istemi",
        mode=ExecutionMode.QUICK,
        plan=plan,
        executions=[],
        final_summary="İlk çalıştırma özeti",
    )
    store.save_report(report)

    # Mock execute_plan
    async def fake_execute(
        self: object, prompt: str, plan_arg: TaskPlan, **kwargs: object
    ) -> ExecutionReport:
        del self, kwargs
        return ExecutionReport(
            run_id="replayed-789",
            task_prompt=prompt,
            mode=plan_arg.mode,
            plan=plan_arg,
            executions=[],
            final_summary="Yeniden oynatma başarılı",
        )

    monkeypatch.setattr("voltran.engine.ExecutionEngine.execute_plan", fake_execute)

    result = runner.invoke(app, ["replay", "replay-run-456", "--explain"])
    assert result.exit_code == 0
    assert "Yeniden Oynatılan Çalıştırma" in result.stdout
    assert "Yeniden oynatma başarılı" in result.stdout

    # JSON çıktısı ile
    json_result = runner.invoke(app, ["replay", "replay-run-456", "--json"])
    assert json_result.exit_code == 0
    payload = json.loads(json_result.stdout)
    assert payload["run_id"] == "replayed-789"


def test_cancel_command(monkeypatch: MonkeyPatch, tmp_path: Path) -> None:
    from voltran.models import ExecutionMode, ExecutionReport, TaskPlan
    from voltran.store import RunStore

    monkeypatch.chdir(tmp_path)
    db_path = tmp_path / "voltran.db"
    store = RunStore(db_path)
    monkeypatch.setattr("voltran.store.get_default_db_path", lambda: db_path)

    # 1. Olmayan çalıştırma
    result = runner.invoke(app, ["cancel", "missing-id"])
    assert result.exit_code == 1
    assert "Çalıştırma bulunamadı" in result.stdout

    # 2. Tamamlanmış (aktif olmayan) çalıştırma
    plan = TaskPlan(mode=ExecutionMode.QUICK, reasoning="bitti")
    report = ExecutionReport(
        run_id="completed-id",
        task_prompt="Tamamlandı",
        mode=ExecutionMode.QUICK,
        plan=plan,
        executions=[],
        final_summary="Bitti",
    )
    store.save_report(report)
    result = runner.invoke(app, ["cancel", "completed-id"])
    assert result.exit_code == 0
    assert "zaten aktif değil" in result.stdout

    # 3. Aktif çalıştırma (mock os.kill ile)
    store.register_active_run("active-id", pid=999999, mode="quick", prompt="aktif görev")

    # PID kimlik doğrulaması: hedefin gerçekten bir voltran süreci olduğunu bildir.
    monkeypatch.setattr("voltran.cli._process_command_line", _voltran_command)

    def fake_kill(pid: int, sig: int) -> None:
        del pid, sig

    monkeypatch.setattr("os.kill", fake_kill)
    if hasattr(os, "killpg"):

        def fake_killpg(pgid: int, sig: int) -> None:
            del pgid, sig

        monkeypatch.setattr("os.killpg", fake_killpg)

    result = runner.invoke(app, ["cancel", "active-id"])
    assert result.exit_code == 0
    assert "başarıyla iptal edildi" in result.stdout
    assert store.get_active_run("active-id") is None


def test_run_keyboard_interrupt(monkeypatch: MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.chdir(tmp_path)

    async def raise_interrupt(*args: object, **kwargs: object) -> None:
        raise KeyboardInterrupt()

    monkeypatch.setattr("voltran.engine.ExecutionEngine.execute_plan", raise_interrupt)

    result = runner.invoke(app, ["run", "kesilecek görev", "--dry-run"])
    assert result.exit_code == 130
    assert "kullanıcı tarafından iptal edildi" in result.stdout


def _register_active(run_id: str, pid: int) -> None:
    from voltran.store import RunStore

    RunStore().register_active_run(run_id, pid, "expert", "uzun görev")


def test_cancel_refuses_to_kill_a_recycled_pid(monkeypatch: MonkeyPatch, tmp_path: Path) -> None:
    """Çöken bir çalıştırmadan kalan PID başka bir uygulamaya verilmiş olabilir."""
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("VOLTRAN_DATA_DIR", str(tmp_path / "veri"))
    _register_active("hayalet", 4242)

    def _foreign_command(pid: int) -> str:
        del pid
        return "/usr/bin/postgres -D /var/lib/postgresql/data"

    signals: list[tuple[int, int]] = []

    def _record_kill(pid: int, sig: int) -> None:
        signals.append((pid, sig))

    monkeypatch.setattr("voltran.cli._process_command_line", _foreign_command)
    monkeypatch.setattr("os.kill", _record_kill)

    result = runner.invoke(app, ["cancel", "hayalet"])

    assert result.exit_code == 1
    assert "Güvenlik durdurması" in result.stdout
    assert signals == []  # hiçbir sinyal gönderilmemeli

    from voltran.store import RunStore

    assert RunStore().get_active_run("hayalet") is None


def test_cancel_cleans_up_when_the_process_is_gone(
    monkeypatch: MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("VOLTRAN_DATA_DIR", str(tmp_path / "veri"))
    _register_active("olu", 999_999)

    def _no_process(pid: int) -> str | None:
        del pid
        return None

    monkeypatch.setattr("voltran.cli._process_command_line", _no_process)

    result = runner.invoke(app, ["cancel", "olu"])

    assert result.exit_code == 0
    assert "Süreç zaten çalışmıyor" in result.stdout

    from voltran.store import RunStore

    assert RunStore().get_active_run("olu") is None


def test_cancel_signals_a_genuine_voltran_process(monkeypatch: MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("VOLTRAN_DATA_DIR", str(tmp_path / "veri"))
    _register_active("gercek", 4242)

    signalled: list[tuple[int, int]] = []
    killed_groups: list[tuple[int, int]] = []

    def _fake_kill(pid: int, sig: int) -> None:
        if sig == 0:
            raise ProcessLookupError  # yoklamada süreç kapanmış say
        signalled.append((pid, sig))

    def _own_group(pid: int) -> int:
        return pid

    def _record_killpg(pgid: int, sig: int) -> None:
        killed_groups.append((pgid, sig))

    monkeypatch.setattr("voltran.cli._process_command_line", _voltran_command)
    monkeypatch.setattr("os.kill", _fake_kill)
    monkeypatch.setattr("os.getpgid", _own_group)
    monkeypatch.setattr("os.killpg", _record_killpg)

    result = runner.invoke(app, ["cancel", "gercek"])

    assert result.exit_code == 0
    assert "başarıyla iptal edildi" in result.stdout
    assert (4242, int(signal.SIGTERM)) in signalled
    assert killed_groups == [(4242, int(signal.SIGTERM))]


def test_cancel_does_not_kill_the_group_when_not_group_leader(
    monkeypatch: MonkeyPatch, tmp_path: Path
) -> None:
    """Etkileşimsiz kabukta voltran çağıranın grubunu miras alır; grup öldürülmemeli."""
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("VOLTRAN_DATA_DIR", str(tmp_path / "veri"))
    _register_active("grup", 4242)

    killed_groups: list[tuple[int, int]] = []

    def _noop_kill(pid: int, sig: int) -> None:
        del pid, sig

    def _callers_group(pid: int) -> int:
        del pid
        return 1000  # çağıran betiğin süreç grubu

    def _record_killpg(pgid: int, sig: int) -> None:
        killed_groups.append((pgid, sig))

    monkeypatch.setattr("voltran.cli._process_command_line", _voltran_command)
    monkeypatch.setattr("os.kill", _noop_kill)
    monkeypatch.setattr("os.getpgid", _callers_group)
    monkeypatch.setattr("os.killpg", _record_killpg)

    runner.invoke(app, ["cancel", "grup"])

    assert killed_groups == []
