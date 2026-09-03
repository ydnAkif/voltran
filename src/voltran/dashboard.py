"""VOLTRAN Canlı Terminal Gösterge Paneli (TUI / Dashboard).

Çoklu ajan oturumlarını, hcom mesajlaşma trafiğini, yerel dosya kilitlerini
ve çalışma geçmişini Rich Live panelleriyle canlı olarak görselleştirir.
"""

from __future__ import annotations

import asyncio
import time
from pathlib import Path

from rich.console import Console, RenderableType
from rich.layout import Layout
from rich.live import Live
from rich.panel import Panel
from rich.table import Table
from rich.text import Text

from voltran.hcom_client import HcomAgentInfo, HcomClient, HcomEvent
from voltran.lock import FileLockManager, LockInfo
from voltran.models import HistoryRecord
from voltran.store import RunStore


class DashboardView:
    """Canlı gösterge panelinin düzenini ve bileşenlerini yönetir."""

    def __init__(
        self,
        hcom_client: HcomClient | None = None,
        run_store: RunStore | None = None,
        lock_manager: FileLockManager | None = None,
    ) -> None:
        self.hcom = hcom_client or HcomClient()
        self.store = run_store or RunStore()
        self.locks = lock_manager or FileLockManager()

    def generate_header(self) -> Panel:
        """Üst başlık ve durum çubuğu."""
        title = Text("VOLTRAN MULTI-AGENT DASHBOARD", style="bold cyan")
        subtitle = Text(" • Canlı Ajan İşbirliği & Sistem İzleme", style="dim")
        clock = Text(f" {time.strftime('%H:%M:%S')} ", style="bold black on cyan")

        content = Text.assemble(title, subtitle, "\n", clock)
        return Panel(content, border_style="cyan", padding=(0, 1))

    def generate_agents_panel(self, agents: list[HcomAgentInfo]) -> Panel:
        """Aktif hcom ajanlarının durum tablosu."""
        table = Table(expand=True, show_lines=False, box=None)
        table.add_column("Ajan / Tag", style="bold")
        table.add_column("Durum")
        table.add_column("Model", style="dim")

        if not agents:
            table.add_row("[dim]Aktif ajan yok[/dim]", "-", "-")
        else:
            for agent in agents:
                status_color = "green" if agent.status == "idle" else "yellow"
                table.add_row(
                    f"{agent.name} [dim]({agent.tag or 'genel'})[/dim]",
                    f"[{status_color}]{agent.status}[/{status_color}]",
                    agent.model or "varsayılan",
                )

        return Panel(table, title="🤖 Aktif Ajanlar", border_style="blue")

    def generate_locks_panel(self, active_locks: list[LockInfo]) -> Panel:
        """Aktif dosya kilitleri tablosu."""
        table = Table(expand=True, show_lines=False, box=None)
        table.add_column("Dosya", style="bold")
        table.add_column("Kilit Sahibi", style="yellow")

        if not active_locks:
            table.add_row("[dim]Kilitli dosya yok[/dim]", "-")
        else:
            for lock in active_locks:
                file_name = Path(lock.file_path).name
                table.add_row(file_name, lock.holder)

        return Panel(table, title="🔒 Dosya Kilitleri (Safety)", border_style="yellow")

    def generate_history_panel(self, records: list[HistoryRecord]) -> Panel:
        """Son çalışma geçmişi tablosu."""
        table = Table(expand=True, show_lines=False, box=None)
        table.add_column("ID", style="bold cyan", no_wrap=True)
        table.add_column("Mod")
        table.add_column("Durum")
        table.add_column("Süre", justify="right", style="dim")

        if not records:
            table.add_row("[dim]Kayıt yok[/dim]", "-", "-", "-")
        else:
            for rec in records:
                status_color = "green" if rec.status == "success" else "red"
                table.add_row(
                    rec.run_id[:8],
                    rec.mode.upper(),
                    f"[{status_color}]{rec.status}[/{status_color}]",
                    f"{rec.duration_ms}ms",
                )

        return Panel(table, title="📜 Son Çalışmalar", border_style="magenta")

    def generate_events_panel(self, events: list[HcomEvent]) -> Panel:
        """Canlı mesaj ve olay akışı tablosu."""
        table = Table(expand=True, show_lines=False, box=None)
        table.add_column("Zaman", style="dim", no_wrap=True)
        table.add_column("Gönderen", style="bold green", no_wrap=True)
        table.add_column("Hedef", style="yellow", no_wrap=True)
        table.add_column("Mesaj / İçerik")

        if not events:
            table.add_row("-", "-", "-", "[dim]Olay kaydı bulunmuyor.[/dim]")
        else:
            for event in reversed(events[-6:]):
                if "T" in event.timestamp:
                    time_str = event.timestamp.split("T")[1][:8]
                elif len(event.timestamp) >= 8:
                    time_str = event.timestamp[:8]
                else:
                    time_str = "-"
                table.add_row(
                    time_str,
                    event.agent or "sistem",
                    event.target or "herkes",
                    event.content[:60] + ("..." if len(event.content) > 60 else ""),
                )

        return Panel(table, title="💬 Canlı Mesaj & Olay Akışı", border_style="green")

    def build_layout(
        self,
        agents: list[HcomAgentInfo],
        active_locks: list[LockInfo],
        records: list[HistoryRecord],
        events: list[HcomEvent],
    ) -> Layout:
        """Tüm bileşenleri organize eden ana terminal düzeni."""
        layout = Layout()
        layout.split_column(
            Layout(name="header", size=4),
            Layout(name="body", ratio=1),
            Layout(name="footer", size=9),
        )

        layout["body"].split_row(
            Layout(name="left", ratio=1),
            Layout(name="right", ratio=1),
        )

        layout["left"].split_column(
            Layout(self.generate_agents_panel(agents)),
            Layout(self.generate_locks_panel(active_locks)),
        )

        layout["header"].update(self.generate_header())
        layout["right"].update(self.generate_history_panel(records))
        layout["footer"].update(self.generate_events_panel(events))

        return layout

    async def fetch_data(
        self,
    ) -> tuple[list[HcomAgentInfo], list[LockInfo], list[HistoryRecord], list[HcomEvent]]:
        """Dashboard panelleri için tüm verileri eşzamanlı toplar."""
        agents_task = self.hcom.list_agents() if self.hcom.is_available() else self._empty_agents()
        events_task = (
            self.hcom.get_events(limit=10) if self.hcom.is_available() else self._empty_events()
        )

        agents, events = await asyncio.gather(agents_task, events_task)
        records = self.store.list_recent(limit=5)
        active_locks = self.locks.list_active_locks()

        return agents, active_locks, records, events

    @staticmethod
    async def _empty_agents() -> list[HcomAgentInfo]:
        return []

    @staticmethod
    async def _empty_events() -> list[HcomEvent]:
        return []

    def render_once(self) -> RenderableType:
        """Tek seferlik statik döküm üretir (CI ve betikler için)."""
        agents, active_locks, records, events = asyncio.run(self.fetch_data())
        return self.build_layout(agents, active_locks, records, events)

    def run_live(
        self,
        *,
        refresh_rate: float = 1.0,
        iterations: int | None = None,
        console: Console | None = None,
    ) -> None:
        """Terminalde etkileşimli canlı gösterge panelini çalıştırır."""
        con = console or Console()
        count = 0

        with Live(self.render_once(), console=con, screen=True, refresh_per_second=4) as live:
            while iterations is None or count < iterations:
                agents, active_locks, records, events = asyncio.run(self.fetch_data())
                live.update(self.build_layout(agents, active_locks, records, events))
                time.sleep(refresh_rate)
                count += 1
