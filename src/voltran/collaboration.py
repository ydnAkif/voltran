"""VOLTRAN İşbirliği Motoru (Collaboration Runtime) — hcom tabanlı çoklu ajan oturumu."""

from __future__ import annotations

import asyncio
import contextlib
from dataclasses import dataclass, field
from pathlib import Path
from uuid import uuid4

from voltran.hcom_client import HcomAgentInfo, HcomClient, HcomClientError, HcomEvent


@dataclass
class AgentRole:
    """İşbirliği oturumunda yer alan bir ajanın tanımı ve rolü."""

    name: str  # hcom etiketi / adı (örn. 'mimar', 'elestirmen', 'kodlayici')
    provider: str  # 'claude', 'codex', 'agy'
    role: str  # Rol tanımı (örn. 'Yazılım Mimarı')
    purpose: str  # Odak noktası (örn. 'Güvenlik ve ölçeklenebilirlik analizi')
    model: str | None = None


@dataclass
class CollaborationSession:
    """Aktif bir hcom işbirliği oturumu."""

    session_id: str
    task_prompt: str
    roles: list[AgentRole]
    working_dir: Path
    client: HcomClient
    processes: list[asyncio.subprocess.Process] = field(
        default_factory=lambda: list[asyncio.subprocess.Process]()
    )
    agent_names: dict[str, str] = field(default_factory=lambda: dict[str, str]())
    event_names: dict[str, str] = field(default_factory=lambda: dict[str, str]())
    is_active: bool = True


class CollaborationRuntime:
    """hcom üzerinde çoklu ajan oturumlarını başlatan, mesajlaşmayı yöneten ve denetleyen motor."""

    def __init__(self, client: HcomClient | None = None) -> None:
        self.client = client if client is not None else HcomClient()

    def is_available(self) -> bool:
        """hcom motorunun sistemde kullanılabilir olup olmadığını döndürür."""
        return self.client.is_available()

    async def start_session(
        self,
        task_prompt: str,
        roles: list[AgentRole],
        *,
        working_dir: Path | None = None,
        headless: bool = True,
        allow_writes: bool = False,
    ) -> CollaborationSession:
        """Belirtilen roller için ajanları başlatır ve oturumu hazırlar."""
        if not self.is_available():
            raise HcomClientError(
                "hcom çalışma motoru bulunamadı. Lütfen 'hcom' aracını kurun: "
                "'brew install aannoo/hcom/hcom' veya 'uv tool install hcom'."
            )

        if not roles:
            raise ValueError("Oturum başlatmak için en az bir AgentRole tanımlanmalıdır.")

        work_path = working_dir or Path.cwd()
        session_id = f"voltran-{uuid4().hex[:8]}"
        session = CollaborationSession(
            session_id=session_id,
            task_prompt=task_prompt,
            roles=roles,
            working_dir=work_path,
            client=self.client,
        )

        try:
            known_names = {agent.name for agent in await self.client.list_agents(cwd=work_path)}
            for agent_role in roles:
                peer_addresses = ", ".join(f"@{role.name}-" for role in roles if role != agent_role)
                restriction = (
                    "Kabuk komutu veya araç çağırma; yalnızca verilen metni tartış.\n"
                    if not allow_writes
                    else "Yalnızca görev kapsamındaki araçları kullan.\n"
                )
                system_prompt = (
                    f"Sen VOLTRAN konseyinde bir uzmansın.\n"
                    f"Rolün: {agent_role.role}\n"
                    f"Amacın: {agent_role.purpose}\n"
                    "Diğer ajanlarla hcom üzerinden doğrudan işbirliği yap. "
                    f"Ekip adresleri: {peer_addresses or '[tek ajan]'}. "
                    "Rol grubuna mesaj gönderirken sondaki tireyi koru. "
                    "Son karar oluştuğunda VOLTRAN_CONSENSUS; kendi işin bittiğinde "
                    "VOLTRAN_DONE işaretini kullan.\n"
                    f"{restriction}"
                    f"Ortak Görev: {task_prompt}"
                )

                extra_args: list[str] = []
                if agent_role.model:
                    extra_args.extend(("--model", agent_role.model))
                if agent_role.provider == "codex":
                    extra_args.append("--no-alt-screen")
                    if not allow_writes:
                        extra_args.extend(("-s", "read-only", "-a", "never"))
                elif agent_role.provider in {"google", "agy", "antigravity"}:
                    if not allow_writes:
                        extra_args.extend(("--sandbox", "--mode", "plan"))

                proc = await self.client.spawn_agent(
                    provider=agent_role.provider,
                    tag=agent_role.name,
                    system_prompt=system_prompt,
                    working_dir=work_path,
                    headless=headless,
                    extra_args=extra_args,
                )
                session.processes.append(proc)
                agents = await self.client.list_agents(cwd=work_path)
                candidates = [
                    agent
                    for agent in agents
                    if agent.tag == agent_role.name and agent.name not in known_names
                ]
                if candidates:
                    candidate = candidates[-1]
                    actual_name = candidate.name
                    session.agent_names[agent_role.name] = actual_name
                    base_name = candidate.raw_data.get("base_name")
                    if not isinstance(base_name, str) or not base_name:
                        prefix = f"{agent_role.name}-"
                        base_name = (
                            actual_name.removeprefix(prefix)
                            if actual_name.startswith(prefix)
                            else actual_name
                        )
                    session.event_names[agent_role.name] = base_name
                    known_names.add(actual_name)
                    if candidate.status == "blocked":
                        detail = candidate.raw_data.get("status_detail")
                        raise HcomClientError(
                            f"{agent_role.provider} ajanı başlangıç onayında engellendi: "
                            f"{detail or actual_name}"
                        )

            return session
        except Exception:
            # Başlatma sırasında hata çıkarsa açılmış olan süreçleri temizle
            await self.terminate_session(session)
            raise

    async def broadcast_mission(self, session: CollaborationSession, message: str) -> bool:
        """Oturumdaki tüm ajanlara genel bir duyuru veya görev iletir."""
        if not session.is_active:
            raise RuntimeError("Sonlandırılmış bir oturuma mesaj gönderilemez.")
        return await self.client.send_message(
            message=message,
            broadcast=True,
            cwd=session.working_dir,
        )

    async def send_to_role(
        self,
        session: CollaborationSession,
        target_role: str,
        message: str,
        *,
        reply_to: str | None = None,
    ) -> bool:
        """Belirli bir role (@rol_adi) hedefli mesaj gönderir."""
        if not session.is_active:
            raise RuntimeError("Sonlandırılmış bir oturuma mesaj gönderilemez.")
        return await self.client.send_message(
            message=message,
            target=f"{target_role}-",
            reply_to=reply_to,
            cwd=session.working_dir,
        )

    async def poll_events(
        self,
        session: CollaborationSession,
        *,
        limit: int = 50,
    ) -> list[HcomEvent]:
        """Oturum süresince gerçekleşen olayları ve mesaj trafiğini getirir."""
        events = await self.client.get_events(limit=limit, cwd=session.working_dir)
        session_senders = set(session.event_names.values())
        session_targets = set(session.agent_names.values()) | session_senders
        return [
            event
            for event in events
            if event.agent in session_senders
            or bool(event.target and session_targets.intersection(event.target.split(",")))
        ]

    async def get_agent_states(
        self,
        session: CollaborationSession,
    ) -> list[HcomAgentInfo]:
        """Oturumdaki ajanların anlık çalışma/boşta durumlarını listeler."""
        agents = await self.client.list_agents(cwd=session.working_dir)
        by_actual_name = {agent.name: agent for agent in agents}
        states: list[HcomAgentInfo] = []
        for role_name, actual_name in session.agent_names.items():
            agent = by_actual_name.get(actual_name)
            if agent is None:
                continue
            states.append(
                HcomAgentInfo(
                    name=session.event_names.get(role_name, actual_name),
                    status=agent.status,
                    tag=agent.tag,
                    session_id=agent.session_id,
                    model=agent.model,
                    raw_data=agent.raw_data,
                )
            )
        return states

    async def wait_for_idle(
        self,
        session: CollaborationSession,
        *,
        timeout: float = 60.0,
        poll_interval: float = 1.0,
    ) -> bool:
        """Tüm ajanlar boşta (idle) durumuna geçene kadar bekler."""
        started = asyncio.get_event_loop().time()
        while asyncio.get_event_loop().time() - started < timeout:
            states = await self.get_agent_states(session)
            if states and all(a.status == "idle" for a in states):
                return True
            await asyncio.sleep(poll_interval)
        return False

    async def get_transcript(self, session: CollaborationSession, agent_name: str) -> str:
        """Belirli bir ajanın canlı terminal/ekran çıktısını okur."""
        resolved_name = session.agent_names.get(agent_name, agent_name)
        return await self.client.get_terminal_output(resolved_name, cwd=session.working_dir)

    async def terminate_session(self, session: CollaborationSession) -> None:
        """Oturumu ve tüm alt ajan süreçlerini güvenli biçimde kapatır."""
        session.is_active = False

        # 1. Yalnızca bu oturumun başlattığı ajanları kapat. Kullanıcının diğer
        # hcom oturumlarına dokunma.
        for name in session.agent_names.values():
            with contextlib.suppress(Exception):
                await self.client.kill_agent(name, cwd=session.working_dir)

        # 2. Arka plan süreç nesnelerini doğrula ve zorla kapat
        for proc in session.processes:
            with contextlib.suppress(ProcessLookupError, Exception):
                if proc.returncode is None:
                    proc.terminate()
                    with contextlib.suppress(TimeoutError, asyncio.TimeoutError):
                        await asyncio.wait_for(proc.wait(), timeout=2.0)
                    if proc.returncode is None:
                        proc.kill()
        session.processes.clear()
