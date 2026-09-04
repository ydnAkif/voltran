# pyright: reportPrivateUsage=false
from __future__ import annotations

import asyncio
from pathlib import Path
from typing import cast
from unittest.mock import AsyncMock, MagicMock

import pytest

from voltran.hcom_client import HcomClient, HcomClientError, HcomEvent


def _make_fake_process(
    *,
    returncode: int | None = 0,
    stdout: bytes = b"",
    stderr: bytes = b"",
    pid: int = 12345,
) -> asyncio.subprocess.Process:
    proc = MagicMock()
    proc.returncode = returncode
    proc.pid = pid
    proc.communicate = AsyncMock(return_value=(stdout, stderr))
    proc.wait = AsyncMock(return_value=returncode or 0)
    proc.terminate = MagicMock()
    proc.kill = MagicMock()
    return cast(asyncio.subprocess.Process, proc)


def test_spawn_agent_success(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    client = HcomClient("python3")
    monkeypatch.setattr(client, "_ensure_available", lambda: None)

    fake_proc = _make_fake_process(returncode=0, stdout=b"agent launched")

    async def fake_create(*args: object, **kwargs: object) -> asyncio.subprocess.Process:
        del args, kwargs
        return fake_proc

    monkeypatch.setattr(asyncio, "create_subprocess_exec", fake_create)

    async def scenario() -> None:
        proc = await client.spawn_agent(
            "codex",
            tag="mimar",
            prompt="Plan yap",
            system_prompt="Sen bir mimarsın",
            working_dir=tmp_path,
            headless=True,
            extra_args=["--extra", "arg"],
        )
        assert proc is fake_proc

    asyncio.run(scenario())


def test_spawn_agent_tolerates_started_launch_process_marker(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    client = HcomClient("python3")
    monkeypatch.setattr(client, "_ensure_available", lambda: None)

    fake_proc = _make_fake_process(
        returncode=1,
        stdout=b"Started the launch process in background PTY",
    )

    async def fake_create(*args: object, **kwargs: object) -> asyncio.subprocess.Process:
        del args, kwargs
        return fake_proc

    monkeypatch.setattr(asyncio, "create_subprocess_exec", fake_create)

    async def scenario() -> None:
        proc = await client.spawn_agent("claude", headless=True)
        assert proc is fake_proc

    asyncio.run(scenario())


def test_spawn_agent_failure_raises_hcom_client_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    client = HcomClient("python3")
    monkeypatch.setattr(client, "_ensure_available", lambda: None)

    fake_proc = _make_fake_process(returncode=1, stderr=b"permission denied")

    async def fake_create(*args: object, **kwargs: object) -> asyncio.subprocess.Process:
        del args, kwargs
        return fake_proc

    monkeypatch.setattr(asyncio, "create_subprocess_exec", fake_create)

    async def scenario() -> None:
        with pytest.raises(HcomClientError, match="başlatılamadı"):
            await client.spawn_agent("codex")

    asyncio.run(scenario())


def test_spawn_agent_timeout_cleans_up_process(monkeypatch: pytest.MonkeyPatch) -> None:
    client = HcomClient("python3")
    monkeypatch.setattr(client, "_ensure_available", lambda: None)

    fake_proc = _make_fake_process(returncode=0)

    async def fake_wait_for(fut: object, timeout: float) -> tuple[bytes, bytes]:
        del timeout
        if asyncio.iscoroutine(fut):
            fut.close()
        raise TimeoutError()

    terminated = False

    async def fake_terminate(proc: asyncio.subprocess.Process) -> None:
        nonlocal terminated
        del proc
        terminated = True

    monkeypatch.setattr(asyncio, "create_subprocess_exec", AsyncMock(return_value=fake_proc))
    monkeypatch.setattr(asyncio, "wait_for", fake_wait_for)
    monkeypatch.setattr(client, "_terminate_process", fake_terminate)

    async def scenario() -> None:
        with pytest.raises(HcomClientError, match="başlatılamadı"):
            await client.spawn_agent("google")
        assert terminated is True

    asyncio.run(scenario())


def test_spawn_agent_generic_exception(monkeypatch: pytest.MonkeyPatch) -> None:
    client = HcomClient("python3")
    monkeypatch.setattr(client, "_ensure_available", lambda: None)

    async def fake_create(*args: object, **kwargs: object) -> asyncio.subprocess.Process:
        del args, kwargs
        raise OSError("Process failed")

    monkeypatch.setattr(asyncio, "create_subprocess_exec", fake_create)

    async def scenario() -> None:
        with pytest.raises(HcomClientError, match="Process failed"):
            await client.spawn_agent("codex")

    asyncio.run(scenario())


def test_terminate_process_handles_already_finished_and_lookup_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def scenario() -> None:
        # 1. Zaten bitmiş süreç
        finished = _make_fake_process(returncode=0)
        await HcomClient._terminate_process(finished)

        # 2. ProcessLookupError fırlatan süreç
        live = _make_fake_process(returncode=None, pid=88888)

        def raise_lookup(pid: int, sig: int) -> None:
            del pid, sig
            raise ProcessLookupError()

        import os

        if hasattr(os, "killpg"):
            monkeypatch.setattr(os, "killpg", raise_lookup)
        await HcomClient._terminate_process(live)

    asyncio.run(scenario())


def test_terminate_process_escalates_to_sigkill_on_timeout(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def scenario() -> None:
        live = _make_fake_process(returncode=None, pid=77777)

        first_wait = True

        async def fake_wait_for(fut: object, timeout: float) -> int:
            nonlocal first_wait
            del timeout
            if first_wait:
                first_wait = False
                if asyncio.iscoroutine(fut):
                    fut.close()
                raise TimeoutError()
            return 0

        signals_sent: list[int] = []

        import os

        def fake_killpg(pid: int, sig: int) -> None:
            del pid
            signals_sent.append(sig)

        if hasattr(os, "killpg"):
            monkeypatch.setattr(os, "killpg", fake_killpg)
        monkeypatch.setattr(asyncio, "wait_for", fake_wait_for)

        await HcomClient._terminate_process(live)

        import signal

        assert signal.SIGTERM in signals_sent
        assert signal.SIGKILL in signals_sent

    asyncio.run(scenario())


def test_get_terminal_output_and_kill_agent(monkeypatch: pytest.MonkeyPatch) -> None:
    client = HcomClient("python3")

    async def fake_run_ok(args: list[str], **kwargs: object) -> tuple[int, str, str]:
        del kwargs
        if args[0] == "term":
            return 0, "terminal text", ""
        if args[0] == "kill":
            return 0, "killed", ""
        return 0, "", ""

    client._run_command = fake_run_ok  # type: ignore[assignment]

    async def scenario() -> None:
        out = await client.get_terminal_output("agent-1")
        assert out == "terminal text"

        assert await client.kill_agent("@all") is True
        assert await client.kill_agent("agent-2") is True

    asyncio.run(scenario())

    async def fake_run_err(args: list[str], **kwargs: object) -> tuple[int, str, str]:
        del args, kwargs
        return 1, "", "failed term"

    client._run_command = fake_run_err  # type: ignore[assignment]

    async def err_scenario() -> None:
        out = await client.get_terminal_output("agent-1")
        assert out == "failed term"

    asyncio.run(err_scenario())


def test_get_events_parses_json_and_ignores_malformed() -> None:
    client = HcomClient("python3")

    raw_output = (
        '{"id": "evt-1", "ts": "2026-09-04T10:00:00", "type": "message", '
        '"data": {"text": "Merhaba", "from": "mimar"}}\n'
        "invalid non-json line\n"
        '{"id": "evt-2", "timestamp": "2026-09-04T10:00:05", "type": "status", '
        '"instance": "elestirmen", "data": {"status": "hazir", "reply_to": "evt-1"}}\n'
    )

    async def fake_run(args: list[str], **kwargs: object) -> tuple[int, str, str]:
        del args, kwargs
        return 0, raw_output, ""

    client._run_command = fake_run  # type: ignore[assignment]

    async def scenario() -> None:
        events = await client.get_events(limit=10)
        assert len(events) == 2
        assert isinstance(events[0], HcomEvent)
        assert events[0].event_id == "evt-1"
        assert events[0].content == "Merhaba"
        assert events[1].event_id == "evt-2"
        assert events[1].reply_to == "evt-1"

    asyncio.run(scenario())
