# pyright: reportPrivateUsage=false
from __future__ import annotations

import asyncio
import json
import sys
from collections.abc import Callable, Sequence
from pathlib import Path
from typing import cast
from unittest.mock import AsyncMock, MagicMock

import pytest
from pytest import MonkeyPatch

from voltran.models import ExecutionPolicy, ProviderCapabilities, ProviderTask
from voltran.providers import AntigravityAdapter, ClaudeAdapter, CodexAdapter, default_registry
from voltran.providers.cli import CliProviderAdapter


def _finder(command: str) -> str | None:
    return f"/opt/tools/{command}"


def test_default_registry_contains_all_supported_providers() -> None:
    assert set(default_registry()) == {"codex", "claude", "google"}


def test_provider_commands_keep_prompt_out_of_process_arguments(tmp_path: Path) -> None:
    task = ProviderTask(prompt="çok gizli görev", working_directory=tmp_path)
    policy = ExecutionPolicy()

    commands = (
        CodexAdapter(finder=_finder).command_for(task, policy),
        ClaudeAdapter(finder=_finder).command_for(task, policy),
        AntigravityAdapter(finder=_finder).command_for(task, policy),
    )

    assert all("çok gizli görev" not in " ".join(command) for command in commands)
    assert "read-only" in commands[0]
    assert "plan" in commands[1]
    assert "plan" in commands[2]
    assert "--safe-mode" in commands[1]
    assert "--new-project" in commands[2]
    assert "stream-json" in commands[2]
    assert "--print" not in commands[2]
    assert all("dangerously" not in " ".join(command) for command in commands)


def test_antigravity_normalizes_stream_json_result() -> None:
    adapter = AntigravityAdapter(finder=_finder)
    raw = "\n".join(
        [
            '{"event":"init","conversation_id":"test"}',
            '{"event":"result","result":{"status":"SUCCESS","response":"Ortak cevap"}}',
        ]
    )

    result = adapter.normalize_result(raw)

    assert result.status == "success"
    assert result.summary == "Ortak cevap"


def test_provider_prompt_requests_complete_json_contract() -> None:
    adapter = _PythonAdapter("pass")
    prompt = adapter.compose_input(ProviderTask(prompt="test"), None)

    for field in (
        "summary",
        "claims",
        "evidence",
        "uncertainties",
        "risks",
        "artifacts",
        "status",
    ):
        assert field in prompt
    assert 'status="success" (hata durumunda "error")' in prompt
    assert "Başka status değeri kullanma" in prompt


def test_provider_normalizes_fenced_structured_result() -> None:
    raw = """Yanıt:\n```json
{"summary":"sonuç","claims":["iddia"],"evidence":["pytest geçti"],
"uncertainties":["sürüm"],"risks":["timeout"],"artifacts":["report.md"],
"status":"success"}
```"""

    result = _PythonAdapter("pass").normalize_result(raw)

    assert result.summary == "sonuç"
    assert result.claims == ["iddia"]
    assert result.evidence == ["pytest geçti"]
    assert result.uncertainties == ["sürüm"]
    assert result.risks == ["timeout"]
    assert result.artifacts == ["report.md"]


def test_provider_normalizes_known_status_aliases() -> None:
    adapter = _PythonAdapter("pass")

    for status in ("SUCCESS", "ok", "completed", "done", "başarılı"):
        result = adapter.normalize_result(json.dumps({"summary": "sonuç", "status": status}))
        assert result.status == "success"

    for status in ("ERROR", "failed", "failure", "başarısız"):
        result = adapter.normalize_result(json.dumps({"summary": "hata", "status": status}))
        assert result.status == "error"


def test_provider_preserves_unknown_status_as_contract_failure() -> None:
    result = _PythonAdapter("pass").normalize_result(
        json.dumps({"summary": "belirsiz", "status": "maybe"})
    )

    assert result.status == "maybe"


def test_antigravity_normalizes_structured_response_contract() -> None:
    response = {
        "summary": "sonuç",
        "claims": ["iddia"],
        "evidence": ["kanıt"],
        "uncertainties": [],
        "risks": [],
        "artifacts": [],
        "status": "success",
    }
    raw = json.dumps({"event": "result", "result": {"response": json.dumps(response)}})

    result = AntigravityAdapter(finder=_finder).normalize_result(raw)

    assert result.summary == "sonuç"
    assert result.claims == ["iddia"]


class _PythonAdapter(CliProviderAdapter):
    key = "fake"
    display_name = "Fake"
    executable = sys.executable

    def __init__(self, script: str, finder: Callable[[str], str | None] | None = None) -> None:
        if finder is not None:
            super().__init__(finder=finder)
        else:
            super().__init__()
        self._script = script

    def capabilities(self) -> ProviderCapabilities:
        return ProviderCapabilities()

    def compose_input(self, task: ProviderTask, context: str | None) -> str:
        return self._compose_input(task, context)

    def _build_command(
        self,
        executable: str,
        task: ProviderTask,
        policy: ExecutionPolicy,
    ) -> Sequence[str]:
        del task, policy
        return (executable, "-c", self._script)


def test_execute_normalizes_plain_text_without_real_model_call(tmp_path: Path) -> None:
    async def scenario() -> None:
        adapter = _PythonAdapter("import sys; print(sys.stdin.read())")
        task = ProviderTask(prompt="Ana görev", working_directory=tmp_path)

        execution = await adapter.execute(task, "Güvenilmeyen bağlam", ExecutionPolicy())

        assert execution.status == "success"
        assert execution.result is not None
        assert "Ana görev" in execution.result.summary
        assert "<context>" in execution.result.summary
        assert execution.result.metadata["provider"] == "fake"

    asyncio.run(scenario())


def test_execute_enforces_timeout_and_stops_process(tmp_path: Path) -> None:
    async def scenario() -> None:
        adapter = _PythonAdapter("import time; time.sleep(5)")
        task = ProviderTask(prompt="Bekle", working_directory=tmp_path)

        execution = await adapter.execute(
            task,
            None,
            ExecutionPolicy(timeout_seconds=0.1),
        )

        assert execution.status == "timed_out"

    asyncio.run(scenario())


def test_active_execution_can_be_cancelled(tmp_path: Path) -> None:
    async def scenario() -> None:
        adapter = _PythonAdapter("import time; time.sleep(5)")
        task = ProviderTask(prompt="Bekle", working_directory=tmp_path)
        pending = asyncio.create_task(adapter.execute(task, None, ExecutionPolicy()))
        await asyncio.sleep(0.1)

        cancelled = await adapter.cancel(task.task_id)
        execution = await pending

        assert cancelled is True
        assert execution.status == "cancelled"

    asyncio.run(scenario())


def test_health_check_starts_isolated_process_group(monkeypatch: MonkeyPatch) -> None:
    async def scenario() -> None:
        captured: dict[str, object] = {}
        process = MagicMock(spec=asyncio.subprocess.Process)
        process.returncode = 0
        process.communicate = AsyncMock(return_value=(b"1.0\n", b""))

        async def fake_create(*args: str, **kwargs: object) -> asyncio.subprocess.Process:
            del args
            captured.update(kwargs)
            return cast(asyncio.subprocess.Process, process)

        monkeypatch.setattr(asyncio, "create_subprocess_exec", fake_create)

        health = await _PythonAdapter("pass").health_check()

        assert health.available is True
        assert captured["start_new_session"] is True

    asyncio.run(scenario())


def test_health_check_failures(monkeypatch: MonkeyPatch) -> None:
    async def scenario() -> None:
        # 1. CLI bulunamadı
        adapter_missing = _PythonAdapter("pass", finder=lambda _: None)
        h1 = await adapter_missing.health_check()
        assert h1.available is False
        assert "bulunamadı" in h1.message

        # 2. OSError ile başlatılamadı
        async def fake_create_err(*args: str, **kwargs: object) -> asyncio.subprocess.Process:
            del args, kwargs
            raise OSError("Access denied")

        monkeypatch.setattr(asyncio, "create_subprocess_exec", fake_create_err)
        adapter = _PythonAdapter("pass")
        h2 = await adapter.health_check()
        assert h2.available is False
        assert "başlatılamadı" in h2.message

        # 3. Sürüm kontrolü zaman aşımı
        process = MagicMock(spec=asyncio.subprocess.Process)
        process.returncode = None
        process.pid = 43210
        process.wait = AsyncMock(return_value=0)

        async def fake_create_proc(*args: str, **kwargs: object) -> asyncio.subprocess.Process:
            del args, kwargs
            return cast(asyncio.subprocess.Process, process)

        async def fake_wait_for(fut: object, timeout: float) -> tuple[bytes, bytes]:
            del timeout
            if asyncio.iscoroutine(fut):
                fut.close()
            raise TimeoutError()

        monkeypatch.setattr(asyncio, "create_subprocess_exec", fake_create_proc)
        monkeypatch.setattr(asyncio, "wait_for", fake_wait_for)
        monkeypatch.setattr(adapter, "_terminate_process", AsyncMock())

        h3 = await adapter.health_check()
        assert h3.available is False
        assert "zaman aşımına" in h3.message

    asyncio.run(scenario())


def test_execute_edge_cases_and_errors(monkeypatch: MonkeyPatch, tmp_path: Path) -> None:
    async def scenario() -> None:
        # 1. CLI bulunamadı
        adapter_missing = _PythonAdapter("pass", finder=lambda _: None)
        task = ProviderTask(prompt="Test", working_directory=tmp_path)
        e1 = await adapter_missing.execute(task, None, ExecutionPolicy())
        assert e1.status == "failed"
        assert "CLI bulunamadı" in (e1.error or "")

        # 2. Çalışma dizini geçersiz
        adapter = _PythonAdapter("pass")
        invalid_task = ProviderTask(
            prompt="Test", working_directory=tmp_path / "non_existent_folder_xyz"
        )
        e2 = await adapter.execute(invalid_task, None, ExecutionPolicy())
        assert e2.status == "failed"
        assert "Çalışma dizini bulunamadı" in (e2.error or "")

        # 3. Alt süreç başlatılırken OSError
        async def fake_create_fail(*args: str, **kwargs: object) -> asyncio.subprocess.Process:
            del args, kwargs
            raise OSError("Spawn failure")

        monkeypatch.setattr(asyncio, "create_subprocess_exec", fake_create_fail)
        e3 = await adapter.execute(task, None, ExecutionPolicy())
        assert e3.status == "failed"
        assert "CLI başlatılamadı" in (e3.error or "")

    asyncio.run(scenario())


def test_execute_cancelled_error(monkeypatch: MonkeyPatch, tmp_path: Path) -> None:
    async def scenario() -> None:
        adapter = _PythonAdapter("pass")
        task = ProviderTask(prompt="Test", working_directory=tmp_path)

        proc = MagicMock(spec=asyncio.subprocess.Process)
        proc.returncode = None
        proc.pid = 55555

        async def fake_create(*args: str, **kwargs: object) -> asyncio.subprocess.Process:
            del args, kwargs
            return cast(asyncio.subprocess.Process, proc)

        async def fake_wait_for(fut: object, timeout: float) -> tuple[bytes, bytes]:
            del timeout
            if asyncio.iscoroutine(fut):
                fut.close()
            raise asyncio.CancelledError()

        monkeypatch.setattr(asyncio, "create_subprocess_exec", fake_create)
        monkeypatch.setattr(asyncio, "wait_for", fake_wait_for)
        monkeypatch.setattr(adapter, "_terminate_process", AsyncMock())

        with pytest.raises(asyncio.CancelledError):
            await adapter.execute(task, None, ExecutionPolicy())

    asyncio.run(scenario())


def test_execute_non_zero_exit_and_empty_output(tmp_path: Path) -> None:
    async def scenario() -> None:
        # 1. Hatalı çıkış
        adapter_err = _PythonAdapter("import sys; sys.stderr.write('kritik hata'); sys.exit(2)")
        task1 = ProviderTask(prompt="Hata testi", working_directory=tmp_path)
        e1 = await adapter_err.execute(task1, None, ExecutionPolicy())
        assert e1.status == "failed"
        assert "kritik hata" in (e1.error or "")

        # 2. Boş çıktı
        adapter_empty = _PythonAdapter("pass")
        task2 = ProviderTask(prompt="Boş çıktı testi", working_directory=tmp_path)
        e2 = await adapter_empty.execute(task2, None, ExecutionPolicy())
        assert e2.status == "failed"
        assert "boş çıktı" in (e2.error or "")

        # 3. Rol, odak ve bağlam ile başarılı çalıştırma
        adapter_ok = _PythonAdapter(
            "import json; print(json.dumps({'summary': 'tamam', 'status': 'success'}))"
        )
        task3 = ProviderTask(
            prompt="Detaylı test",
            role="Mimar",
            purpose="Analiz",
            instructions="Kurallara uy",
            working_directory=tmp_path,
        )
        e3 = await adapter_ok.execute(task3, "Bağlam metni", ExecutionPolicy())
        assert e3.status == "success"
        assert e3.result is not None
        assert e3.result.summary == "tamam"

    asyncio.run(scenario())


def test_cancel_edge_cases() -> None:
    async def scenario() -> None:
        adapter = _PythonAdapter("pass")
        # 1. Olmayan run_id
        assert await adapter.cancel("non_existent") is False

        # 2. Zaten bitmiş süreç
        proc = MagicMock(spec=asyncio.subprocess.Process)
        proc.returncode = 0
        adapter._active["finished"] = cast(asyncio.subprocess.Process, proc)
        assert await adapter.cancel("finished") is False

    asyncio.run(scenario())


def test_terminate_process_variants(monkeypatch: MonkeyPatch) -> None:
    async def scenario() -> None:
        adapter = _PythonAdapter("pass")

        # 1. returncode is not None -> erken dönüş
        proc_done = MagicMock(spec=asyncio.subprocess.Process)
        proc_done.returncode = 0
        await adapter._terminate_process(cast(asyncio.subprocess.Process, proc_done))

        # 2. ProcessLookupError on killpg
        proc_live = MagicMock(spec=asyncio.subprocess.Process)
        proc_live.returncode = None
        proc_live.pid = 66666

        import os

        def raise_lookup(pid: int, sig: int) -> None:
            del pid, sig
            raise ProcessLookupError()

        if hasattr(os, "killpg"):
            monkeypatch.setattr(os, "killpg", raise_lookup)
        await adapter._terminate_process(cast(asyncio.subprocess.Process, proc_live))

        # 3. Zaman aşımı sonrası SIGKILL
        signals_sent: list[int] = []

        def track_killpg(pid: int, sig: int) -> None:
            del pid
            signals_sent.append(sig)

        first = True

        async def fake_wait_for(fut: object, timeout: float) -> int:
            nonlocal first
            del timeout
            if first:
                first = False
                if asyncio.iscoroutine(fut):
                    fut.close()
                raise TimeoutError()
            return 0

        if hasattr(os, "killpg"):
            monkeypatch.setattr(os, "killpg", track_killpg)
        monkeypatch.setattr(asyncio, "wait_for", fake_wait_for)

        proc_stubborn = MagicMock(spec=asyncio.subprocess.Process)
        proc_stubborn.returncode = None
        proc_stubborn.pid = 77777
        proc_stubborn.wait = AsyncMock(return_value=0)

        await adapter._terminate_process(cast(asyncio.subprocess.Process, proc_stubborn))

        import signal

        assert signal.SIGTERM in signals_sent
        assert signal.SIGKILL in signals_sent

    asyncio.run(scenario())
