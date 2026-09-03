"""VOLTRAN komut satırı arayüzü."""

from __future__ import annotations

import json
from typing import Annotated

import typer
from rich.console import Console
from rich.table import Table

from voltran import __version__
from voltran.doctor import build_doctor_report
from voltran.models import CheckStatus, DoctorReport

app = typer.Typer(
    name="voltran",
    help="Yerel ve denetlenebilir çoklu LLM orkestrasyonu.",
    no_args_is_help=True,
)
console = Console()

STATUS_LABELS = {
    CheckStatus.PASS: "[green]GEÇTİ[/green]",
    CheckStatus.WARNING: "[yellow]UYARI[/yellow]",
    CheckStatus.FAIL: "[red]HATA[/red]",
    CheckStatus.INFO: "[cyan]BİLGİ[/cyan]",
}


def _version_callback(value: bool) -> None:
    if value:
        typer.echo(f"voltran {__version__}")
        raise typer.Exit()


@app.callback()
def main(
    version: Annotated[
        bool | None,
        typer.Option("--version", callback=_version_callback, is_eager=True, help="Sürümü göster."),
    ] = None,
) -> None:
    """VOLTRAN komut grubunu başlatır."""


def _render_doctor_report(report: DoctorReport) -> None:
    table = Table(title="VOLTRAN sistem teşhisi", show_lines=False)
    table.add_column("Durum", no_wrap=True)
    table.add_column("Kontrol")
    table.add_column("Sonuç")
    for check in report.checks:
        summary = check.summary
        if check.remediation:
            summary = f"{summary}\n[dim]Öneri: {check.remediation}[/dim]"
        table.add_row(STATUS_LABELS[check.status], check.title, summary)
    console.print(table)
    labels = {"ready": "hazır", "degraded": "kısmen hazır", "failed": "hazır değil"}
    console.print(f"\nGenel durum: [bold]{labels[report.overall_status]}[/bold]")
    console.print("[dim]Bu komut sistemde hiçbir değişiklik yapmadı.[/dim]")


@app.command()
def doctor(
    json_output: Annotated[
        bool,
        typer.Option("--json", help="Makinece okunabilir JSON çıktı üret."),
    ] = False,
    sessions: Annotated[
        bool,
        typer.Option("--sessions/--no-sessions", help="Salt okunur oturum kontrollerini çalıştır."),
    ] = True,
    timeout: Annotated[
        float,
        typer.Option(min=0.1, max=30.0, help="Her CLI kontrolü için saniye sınırı."),
    ] = 3.0,
    strict: Annotated[
        bool,
        typer.Option(help="Genel durum hazır değilse sıfırdan farklı çıkış kodu kullan."),
    ] = False,
) -> None:
    """Ortamı, sağlayıcı CLI'larını ve izinleri değiştirmeden denetle."""

    report = build_doctor_report(check_sessions=sessions, timeout=timeout)
    if json_output:
        typer.echo(json.dumps(report.model_dump(mode="json"), ensure_ascii=False, indent=2))
    else:
        _render_doctor_report(report)
    if strict and report.overall_status != "ready":
        raise typer.Exit(code=1)
