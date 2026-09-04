from __future__ import annotations

import asyncio
import json
import sys
from collections.abc import Sequence
from pathlib import Path
from typing import cast
from unittest.mock import AsyncMock, MagicMock

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

    def __init__(self, script: str) -> None:
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
