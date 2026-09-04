"""VOLTRAN hcom İstemcisi — hcom CLI için alt seviye asenkron sarmalayıcı."""

from __future__ import annotations

import asyncio
import json
import os
import shutil
import signal
from collections.abc import Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, cast


@dataclass
class HcomAgentInfo:
    """Aktif bir hcom ajanı hakkında durum bilgisi."""

    name: str
    status: str  # "idle", "busy", "waiting", "dead"
    tag: str | None = None
    session_id: str | None = None
    model: str | None = None
    raw_data: dict[str, Any] = field(default_factory=lambda: dict[str, Any]())


@dataclass
class HcomEvent:
    """hcom olay günlüğündeki tek bir olay."""

    event_id: str
    timestamp: str
    event_type: str  # "message", "file_edit", "status_change", "tool_call"
    agent: str | None = None
    target: str | None = None
    content: str = ""
    reply_to: str | None = None


class HcomClientError(RuntimeError):
    """hcom istemcisi çalıştırma veya iletişim hatası."""


class HcomNotFoundError(HcomClientError):
    """hcom ikilisi sistemde bulunamadığında fırlatılır."""


class HcomClient:
    """hcom CLI (Rust binary) komutlarını yöneten asenkron istemci."""

    def __init__(self, executable: str = "hcom") -> None:
        self.executable = executable

    def is_available(self) -> bool:
        """hcom aracının sistemde kurulu ve PATH üzerinde olup olmadığını denetler."""
        return shutil.which(self.executable) is not None

    def _ensure_available(self) -> None:
        if not self.is_available():
            raise HcomNotFoundError(
                f"'{self.executable}' bulunamadı. Lütfen hcom aracını kurun "
                "(ör. 'brew install aannoo/hcom/hcom' veya 'uv tool install hcom')."
            )

    async def _run_command(
        self,
        args: Sequence[str],
        *,
        cwd: Path | None = None,
        timeout: float = 15.0,
    ) -> tuple[int, str, str]:
        """hcom alt komutunu güvenli biçimde çalıştırır."""
        self._ensure_available()
        cmd = [self.executable, *args]
        process: asyncio.subprocess.Process | None = None

        try:
            process = await asyncio.create_subprocess_exec(
                *cmd,
                cwd=str(cwd) if cwd else None,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                start_new_session=True,
            )
            stdout_bytes, stderr_bytes = await asyncio.wait_for(
                process.communicate(),
                timeout=timeout,
            )
            return (
                process.returncode or 0,
                stdout_bytes.decode("utf-8", errors="replace"),
                stderr_bytes.decode("utf-8", errors="replace"),
            )
        except TimeoutError as exc:
            if process is not None:
                await self._terminate_process(process)
            raise HcomClientError(
                f"hcom komutu ({' '.join(args)}) {timeout} saniye içinde zaman aşımına uğradı."
            ) from exc
        except Exception as exc:
            raise HcomClientError(f"hcom komutu çalıştırılırken hata: {exc}") from exc

    async def spawn_agent(
        self,
        provider: str,
        *,
        tag: str | None = None,
        prompt: str | None = None,
        system_prompt: str | None = None,
        working_dir: Path | None = None,
        headless: bool = True,
        extra_args: Sequence[str] = (),
    ) -> asyncio.subprocess.Process:
        """Yeni bir ajanı arka planda (headless) veya terminalde başlatır."""
        self._ensure_available()

        # hcom sağlayıcı eşlemesi (claude, codex, agy / gemini)
        provider_cmd = "agy" if provider in ("google", "agy", "antigravity") else provider
        # hcom launch sözleşmesi: hcom <provider> [hcom flags...]
        cmd: list[str] = [self.executable, provider_cmd]

        if headless:
            cmd.append("--headless")
        if tag:
            cmd.extend(("--tag", tag))
        if working_dir:
            cmd.extend(("--dir", str(working_dir)))
        if prompt:
            cmd.extend(("--hcom-prompt", prompt))
        if system_prompt:
            cmd.extend(("--hcom-system-prompt", system_prompt))
        cmd.extend(extra_args)
        process: asyncio.subprocess.Process | None = None

        try:
            # --headless ajanı hcom'un PTY yöneticisine devreder. Launcher,
            # hazır/başarısız durumunu bildirdikten sonra sonlanır.
            child_env = os.environ.copy()
            if child_env.get("TERM", "").lower() in {"", "dumb", "unknown"}:
                child_env["TERM"] = "xterm-256color"
            process = await asyncio.create_subprocess_exec(
                *cmd,
                cwd=str(working_dir) if working_dir else None,
                env=child_env,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                start_new_session=True,
            )
            stdout_bytes, stderr_bytes = await asyncio.wait_for(process.communicate(), timeout=45.0)
            if process.returncode != 0:
                detail = (
                    (stdout_bytes + b"\n" + stderr_bytes).decode("utf-8", errors="replace").strip()
                )
                # hcom, ajanı PTY yöneticisine başarıyla devrettiği halde 10 saniyelik
                # hazır olma penceresi aşılırsa sıfırdan farklı çıkabilir. start_session
                # hemen ardından gerçek instance kaydını doğrular.
                if "Started the launch process" not in detail:
                    raise HcomClientError(f"Ajan '{provider}' başlatılamadı: {detail}")
            return process
        except TimeoutError as exc:
            if process is not None:
                await self._terminate_process(process)
            raise HcomClientError(f"Ajan '{provider}' 45 saniye içinde başlatılamadı.") from exc
        except HcomClientError:
            raise
        except Exception as exc:
            raise HcomClientError(f"Ajan '{provider}' başlatılamadı: {exc}") from exc

    @staticmethod
    async def _terminate_process(process: asyncio.subprocess.Process) -> None:
        """Zaman aşımına uğrayan hcom sürecini ve alt süreç grubunu temizle."""
        if process.returncode is not None:
            return
        try:
            if process.pid and os.name == "posix":
                os.killpg(process.pid, signal.SIGTERM)
            else:
                process.terminate()
        except ProcessLookupError:
            return
        try:
            await asyncio.wait_for(process.wait(), timeout=1.0)
            return
        except TimeoutError:
            pass
        try:
            if process.pid and os.name == "posix":
                os.killpg(process.pid, signal.SIGKILL)
            else:
                process.kill()
        except ProcessLookupError:
            return
        await process.wait()

    async def send_message(
        self,
        message: str,
        *,
        target: str | None = None,
        reply_to: str | None = None,
        broadcast: bool = False,
        cwd: Path | None = None,
    ) -> bool:
        """Belirli bir ajana (@agent) veya herkese (broadcast) mesaj gönderir."""
        args: list[str] = ["send", "--from", "voltran"]

        if broadcast or target == "all" or target == "@all":
            # Hedefsiz gönderim broadcast'tir; --go güvenlik önizlemesini onaylar.
            args.append("--go")
        elif target:
            target_tag = target if target.startswith("@") else f"@{target}"
            args.append(target_tag)

        if reply_to:
            args.extend(("--reply-to", reply_to))

        args.append("--")
        args.append(message)

        code, stdout, stderr = await self._run_command(args, cwd=cwd)
        if code != 0:
            raise HcomClientError(f"Mesaj gönderilemedi: {stderr or stdout}")
        return True

    async def list_agents(self, *, cwd: Path | None = None) -> list[HcomAgentInfo]:
        """Çalışmakta olan aktif ajanları ve durumlarını listeler."""
        code, stdout, _ = await self._run_command(["list", "--json"], cwd=cwd)
        if code != 0 or not stdout.strip():
            return []

        try:
            parsed = json.loads(stdout)
            if not isinstance(parsed, list):
                return []

            raw_list = cast(list[object], parsed)
            agents: list[HcomAgentInfo] = []
            for entry in raw_list:
                if isinstance(entry, dict):
                    item = cast(dict[str, object], entry)
                    tag_v = item.get("tag")
                    sess_v = item.get("session_id")
                    mod_v = item.get("model")
                    raw_dict: dict[str, Any] = {str(k): v for k, v in item.items()}
                    agents.append(
                        HcomAgentInfo(
                            name=str(item.get("name") or "unknown"),
                            status=str(item.get("status") or "idle"),
                            tag=str(tag_v) if tag_v is not None else None,
                            session_id=str(sess_v) if sess_v is not None else None,
                            model=str(mod_v) if mod_v is not None else None,
                            raw_data=raw_dict,
                        )
                    )
            return agents
        except json.JSONDecodeError:
            return []

    async def get_events(
        self,
        *,
        limit: int = 50,
        cwd: Path | None = None,
    ) -> list[HcomEvent]:
        """hcom olay günlüğünü JSON olarak okur."""
        code, stdout, _ = await self._run_command(
            ["events", "--last", str(limit), "--full"],
            cwd=cwd,
        )
        if code != 0 or not stdout.strip():
            return []

        events: list[HcomEvent] = []
        for line in stdout.splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                data: object = json.loads(line)
                if isinstance(data, dict):
                    ev = cast(dict[str, object], data)
                    payload_v = ev.get("data")
                    payload = (
                        cast(dict[str, object], payload_v) if isinstance(payload_v, dict) else {}
                    )
                    event_type = str(ev.get("type") or "message")
                    agent_v = payload.get("from") if event_type == "message" else ev.get("instance")
                    delivered_v = payload.get("delivered_to")
                    delivered = (
                        cast(list[object], delivered_v) if isinstance(delivered_v, list) else []
                    )
                    target_v = ",".join(str(item) for item in delivered) or None
                    reply_v = payload.get("reply_to")
                    events.append(
                        HcomEvent(
                            event_id=str(ev.get("id") or ""),
                            timestamp=str(ev.get("ts") or ev.get("timestamp") or ""),
                            event_type=event_type,
                            agent=str(agent_v) if agent_v is not None else None,
                            target=str(target_v) if target_v is not None else None,
                            content=str(payload.get("text") or payload.get("status") or ""),
                            reply_to=str(reply_v) if reply_v is not None else None,
                        )
                    )
            except json.JSONDecodeError:
                continue
        return events

    async def get_terminal_output(self, agent_name: str, *, cwd: Path | None = None) -> str:
        """Ajanın mevcut terminal / ekran çıktısını alır."""
        code, stdout, stderr = await self._run_command(["term", agent_name, "--clean"], cwd=cwd)
        return stdout if code == 0 else stderr

    async def kill_agent(self, target: str = "all", *, cwd: Path | None = None) -> bool:
        """Ajanı veya tüm ajanları sonlandırır."""
        target_name = "all" if target in ("all", "@all") else target
        code, _, _ = await self._run_command(["kill", target_name], cwd=cwd)
        return code == 0
