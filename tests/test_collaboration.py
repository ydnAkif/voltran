from __future__ import annotations

import asyncio
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest

from voltran.collaboration import (
    AgentRole,
    CollaborationRuntime,
)
from voltran.hcom_client import (
    HcomAgentInfo,
    HcomClient,
    HcomClientError,
    HcomNotFoundError,
)


def test_hcom_client_availability() -> None:
    client_found = HcomClient("python3")
    assert client_found.is_available() is True

    client_missing = HcomClient("non_existent_hcom_binary_xyz")
    assert client_missing.is_available() is False

    with pytest.raises(HcomNotFoundError, match="bulunamadı"):
        asyncio.run(client_missing.list_agents())


def test_hcom_client_send_message_args() -> None:
    async def scenario() -> None:
        client = HcomClient("python3")
        executed_args: list[list[str]] = []

        async def fake_run_command(args: list[str], **kwargs: object) -> tuple[int, str, str]:
            executed_args.append(args)
            return 0, "ok", ""

        client._run_command = fake_run_command  # type: ignore[assignment]

        # 1. Hedefli mesaj
        await client.send_message("Merhaba", target="mimar")
        assert executed_args[0] == ["send", "--from", "voltran", "@mimar", "--", "Merhaba"]

        # 2. Yanıt zinciri ile hedefli mesaj
        await client.send_message("İtirazım var", target="@elestirmen", reply_to="evt-123")
        assert executed_args[1] == [
            "send",
            "--from",
            "voltran",
            "@elestirmen",
            "--reply-to",
            "evt-123",
            "--",
            "İtirazım var",
        ]

        # 3. Broadcast
        await client.send_message("Genel brifing", broadcast=True)
        assert executed_args[2] == [
            "send",
            "--from",
            "voltran",
            "--go",
            "--",
            "Genel brifing",
        ]

    asyncio.run(scenario())


def test_hcom_client_list_agents_parsing() -> None:
    async def scenario() -> None:
        client = HcomClient("python3")
        mock_output = """
        [
            {"name": "mimar", "status": "idle", "tag": "mimar", "model": "claude-3-5"},
            {"name": "kodlayici", "status": "busy", "tag": "kodlayici", "model": "o3-mini"}
        ]
        """

        async def fake_run(args: list[str], **kwargs: object) -> tuple[int, str, str]:
            return 0, mock_output, ""

        client._run_command = fake_run  # type: ignore[assignment]

        agents = await client.list_agents()
        assert len(agents) == 2
        assert agents[0].name == "mimar"
        assert agents[0].status == "idle"
        assert agents[1].name == "kodlayici"
        assert agents[1].status == "busy"

    asyncio.run(scenario())


def test_hcom_client_get_events_parsing() -> None:
    async def scenario() -> None:
        client = HcomClient("python3")
        mock_ndjson = (
            '{"id": 1, "ts": "2026-09-03T18:00:00", "type": "message", '
            '"instance": "kodlayici", "data": {"from": "mimar", '
            '"text": "Mimari hazır", "delivered_to": ["kodlayici"]}}\n'
            '{"id": 2, "ts": "2026-09-03T18:00:05", "type": "message", '
            '"instance": "mimar", "data": {"from": "elestirmen", '
            '"text": "Onaylandı", "reply_to": "1", "delivered_to": ["mimar"]}}\n'
        )

        async def fake_run(args: list[str], **kwargs: object) -> tuple[int, str, str]:
            return 0, mock_ndjson, ""

        client._run_command = fake_run  # type: ignore[assignment]

        events = await client.get_events()
        assert len(events) == 2
        assert events[0].event_id == "1"
        assert events[0].agent == "mimar"
        assert events[0].target == "kodlayici"
        assert events[1].reply_to == "1"

    asyncio.run(scenario())


def test_collaboration_runtime_session_lifecycle(tmp_path: Path) -> None:
    async def scenario() -> None:
        mock_client = MagicMock(spec=HcomClient)
        mock_client.is_available.return_value = True

        fake_process = MagicMock(spec=asyncio.subprocess.Process)
        fake_process.returncode = None
        fake_process.terminate = MagicMock()
        fake_process.wait = AsyncMock(return_value=0)

        mock_client.spawn_agent = AsyncMock(return_value=fake_process)
        mock_client.send_message = AsyncMock(return_value=True)
        mock_client.kill_agent = AsyncMock(return_value=True)
        mock_client.list_agents = AsyncMock(
            side_effect=[
                [],
                [HcomAgentInfo(name="mimar-luna", status="idle", tag="mimar")],
                [
                    HcomAgentInfo(name="mimar-luna", status="idle", tag="mimar"),
                    HcomAgentInfo(name="elestirmen-nova", status="idle", tag="elestirmen"),
                ],
                [
                    HcomAgentInfo(name="mimar-luna", status="idle", tag="mimar"),
                    HcomAgentInfo(name="elestirmen-nova", status="idle", tag="elestirmen"),
                ],
            ]
        )

        runtime = CollaborationRuntime(mock_client)
        roles = [
            AgentRole(
                name="mimar",
                provider="claude",
                role="Yazılım Mimarı",
                purpose="Tasarım analizi",
            ),
            AgentRole(
                name="elestirmen",
                provider="codex",
                role="Güvenlik Uzmanı",
                purpose="Açık taraması",
            ),
        ]

        # 1. Oturum Başlatma
        session = await runtime.start_session(
            task_prompt="Sistem mimarisini incele",
            roles=roles,
            working_dir=tmp_path,
        )

        assert session.is_active is True
        assert len(session.roles) == 2
        assert session.agent_names == {
            "mimar": "mimar-luna",
            "elestirmen": "elestirmen-nova",
        }
        assert session.event_names == {"mimar": "luna", "elestirmen": "nova"}
        assert mock_client.spawn_agent.call_count == 2

        # İlk ajana rol ve amacın aktarıldığını doğrula
        call_kwargs = mock_client.spawn_agent.call_args_list[0].kwargs
        assert call_kwargs["provider"] == "claude"
        assert call_kwargs["tag"] == "mimar"
        assert "Yazılım Mimarı" in call_kwargs["system_prompt"]
        assert "Tasarım analizi" in call_kwargs["system_prompt"]

        # 2. Görev İletişimi
        await runtime.broadcast_mission(session, "Başlayın")
        mock_client.send_message.assert_called_with(
            message="Başlayın",
            broadcast=True,
            cwd=tmp_path,
        )

        await runtime.send_to_role(session, "mimar", "Lütfen şemayı sun")
        mock_client.send_message.assert_called_with(
            message="Lütfen şemayı sun",
            target="mimar-",
            reply_to=None,
            cwd=tmp_path,
        )

        # 3. Durum ve Boşta Kalma (Idle) Denetimi
        is_idle = await runtime.wait_for_idle(session, timeout=5.0)
        assert is_idle is True

        # 4. Oturumu Kapatma
        await runtime.terminate_session(session)
        assert session.is_active is False
        assert mock_client.kill_agent.call_count == 2
        mock_client.kill_agent.assert_any_call("mimar-luna", cwd=tmp_path)
        mock_client.kill_agent.assert_any_call("elestirmen-nova", cwd=tmp_path)
        fake_process.terminate.assert_called()

    asyncio.run(scenario())


def test_collaboration_runtime_not_available_raises() -> None:
    async def scenario() -> None:
        mock_client = MagicMock(spec=HcomClient)
        mock_client.is_available.return_value = False

        runtime = CollaborationRuntime(mock_client)
        with pytest.raises(HcomClientError, match="hcom çalışma motoru bulunamadı"):
            await runtime.start_session(
                task_prompt="test",
                roles=[AgentRole("a", "claude", "r", "p")],
            )

    asyncio.run(scenario())
