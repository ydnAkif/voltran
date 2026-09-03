"""VOLTRAN komut satırı arayüzü."""

from __future__ import annotations

import asyncio
import json
from pathlib import Path
from typing import Annotated

import typer
from rich.console import Console
from rich.table import Table

from voltran import __version__
from voltran.doctor import build_doctor_report
from voltran.models import CheckStatus, DoctorReport, ExecutionMode

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


@app.command()
def run(
    prompt: Annotated[str, typer.Argument(help="Yürütülecek görev veya soru.")],
    mode: Annotated[
        ExecutionMode | None,
        typer.Option(
            "--mode",
            "-m",
            help="Çalışma modu: quick, expert, council, visual. Belirtilmezse otomatik seçilir.",
        ),
    ] = None,
    file: Annotated[
        Path | None,
        typer.Option("--file", "-f", help="Göreve bağlam olarak eklenecek yerel dosya yolu."),
    ] = None,
    dry_run: Annotated[
        bool,
        typer.Option(
            "--dry-run", help="Modelleri çalıştırmadan planı ve sağlayıcı dağılımını göster."
        ),
    ] = False,
    explain: Annotated[
        bool,
        typer.Option("--explain", help="Komutanın mod ve sağlayıcı seçim gerekçesini açıkla."),
    ] = False,
    json_output: Annotated[
        bool,
        typer.Option("--json", help="Çıktıyı JSON formatında üret."),
    ] = False,
    output: Annotated[
        Path | None,
        typer.Option("--output", "-o", help="Nihai Markdown raporunu dosyaya kaydet."),
    ] = None,
    timeout: Annotated[
        float,
        typer.Option(help="Model çalıştırmaları için saniye cinsinden zaman aşımı."),
    ] = 300.0,
) -> None:
    """Görevi uygun çalışma modu ve modellerle tek raporda yürüt."""

    from voltran.commander import Commander
    from voltran.engine import ExecutionEngine
    from voltran.reporter import Reporter
    from voltran.router import Router
    from voltran.store import RunStore

    commander = Commander()
    plan = commander.create_plan(prompt, mode=mode, context_file=file)
    plan.policy.timeout_seconds = timeout

    router = Router()
    try:
        router.assign_providers(plan, dry_run=dry_run)
    except RuntimeError as exc:
        console.print(f"[red]Yönlendirme hatası:[/red] {exc}")
        raise typer.Exit(code=1) from exc

    if explain and not json_output:
        console.print(f"[bold cyan]Planlanan Mod:[/bold cyan] {plan.mode.value.upper()}")
        console.print(f"[bold cyan]Seçim Gerekçesi:[/bold cyan] {plan.reasoning}")
        for st in plan.subtasks:
            provider_tag = f"[green]{st.assigned_provider}[/green]"
            console.print(f"  • [yellow]{st.role}[/yellow] ➔ {provider_tag}: {st.purpose}")
        console.print()

    engine = ExecutionEngine()
    report = asyncio.run(engine.execute_plan(prompt, plan, dry_run=dry_run))

    if not dry_run:
        RunStore().save_report(report)

    if json_output:
        typer.echo(Reporter.to_json(report))
    else:
        from rich.markdown import Markdown

        md_content = Reporter.to_markdown(report)
        console.print(Markdown(md_content))

    if output is not None:
        output.write_text(Reporter.to_markdown(report), encoding="utf-8")
        console.print(f"\n[green]Rapor kaydedildi:[/green] {output}")


@app.command()
def history(
    limit: Annotated[
        int, typer.Option("--limit", "-n", help="Gösterilecek en fazla kayıt sayısı.")
    ] = 10,
) -> None:
    """Yerel SQLite veritabanındaki geçmiş çalışmaları listele."""

    from voltran.store import RunStore

    records = RunStore().list_recent(limit=limit)
    if not records:
        console.print("[dim]Henüz kayıtlı bir çalışma bulunmuyor.[/dim]")
        return

    table = Table(title=f"Son {len(records)} Çalışma Geçmişi", show_lines=False)
    table.add_column("Çalışma ID", no_wrap=True)
    table.add_column("Tarih", no_wrap=True)
    table.add_column("Mod", no_wrap=True)
    table.add_column("Sağlayıcılar")
    table.add_column("Durum", no_wrap=True)
    table.add_column("Süre (ms)", justify="right")
    table.add_column("Görev Özeti")

    for rec in records:
        status_color = "green" if rec.status == "success" else "red"
        table.add_row(
            rec.run_id,
            rec.created_at[:19].replace("T", " "),
            rec.mode.upper(),
            ", ".join(rec.providers_used) or "-",
            f"[{status_color}]{rec.status}[/{status_color}]",
            str(rec.duration_ms),
            rec.prompt_preview[:40] + ("..." if len(rec.prompt_preview) > 40 else ""),
        )

    console.print(table)
