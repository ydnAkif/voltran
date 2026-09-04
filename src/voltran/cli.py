"""VOLTRAN komut satırı arayüzü."""

from __future__ import annotations

import asyncio
import json
from pathlib import Path
from typing import Annotated
from uuid import uuid4

import typer
from rich.console import Console
from rich.table import Table

from voltran import __version__
from voltran.doctor import build_doctor_report
from voltran.models import CheckStatus, DoctorReport, ExecutionMode, TaskPlan

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


def _split_provider_options(values: list[str] | None) -> list[str]:
    """`--provider a,b --provider c` biçimini tek bir anahtar listesine düzler."""

    if not values:
        return []
    keys: list[str] = []
    for value in values:
        keys.extend(part.strip() for part in value.split(",") if part.strip())
    return keys


def _read_context_text(file: Path | None) -> str | None:
    """Bağlam dosyasını hassasiyet sınıflandırması için okur; okunamazsa sessiz geçer."""

    if file is None or not file.is_file():
        return None
    try:
        return file.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return None


def _render_data_sharing_preview(
    plan: TaskPlan,
    file: Path | None,
    context_text: str | None,
) -> None:
    """FR-14: kuru çalışmada hangi verinin hangi sağlayıcıya gideceğini gösterir."""

    table = Table(title="Kuru Çalışma — Veri Paylaşım Önizlemesi", show_lines=False)
    table.add_column("Sağlayıcı", no_wrap=True)
    table.add_column("Rol")
    table.add_column("Paylaşılacak veri")

    shared = "Görev metni"
    if context_text is not None and file is not None:
        shared = f"Görev metni + `{file.name}` ({len(context_text)} karakter)"
    elif file is not None:
        shared = "Görev metni (bağlam dosyası okunamadı)"

    for subtask in plan.subtasks:
        table.add_row(subtask.assigned_provider or "-", subtask.role, shared)

    console.print(table)
    console.print(f"[dim]Tahmini model çağrısı: {len(plan.subtasks)}[/dim]")
    if plan.sensitivity_categories:
        console.print(f"[dim]Hassas veri sınıfları: {', '.join(plan.sensitivity_categories)}[/dim]")
    console.print(
        "[dim]Gönderim öncesi API anahtarları, erişim belirteçleri, parola atamaları "
        "ve e-posta adresleri maskelenir.[/dim]\n"
    )


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
    blind: Annotated[
        bool,
        typer.Option("--blind", help="Kör hakemlik: Modellerin marka ve firma kimliklerini gizle."),
    ] = False,
    allow_writes: Annotated[
        bool,
        typer.Option(
            "--write",
            "-w",
            help=(
                "Dosya yazma izni: Modellerin görev kapsamındaki dosyalarda "
                "değişiklik yapmasına izin ver."
            ),
        ),
    ] = False,
    providers: Annotated[
        list[str] | None,
        typer.Option(
            "--provider",
            "-p",
            help=(
                "Yalnızca bu sağlayıcılara izin ver (tekrarlanabilir veya virgülle "
                "ayrılmış). Örnek: --provider claude --provider codex"
            ),
        ),
    ] = None,
) -> None:
    """Görevi uygun çalışma modu ve modellerle tek raporda yürüt."""

    from voltran.classifier import classify_sensitivity
    from voltran.commander import Commander
    from voltran.engine import ExecutionEngine
    from voltran.lock import FileLockManager
    from voltran.reporter import Reporter
    from voltran.router import Router
    from voltran.store import RunStore

    router = Router()
    try:
        allowed = router.validate_provider_keys(_split_provider_options(providers))
    except ValueError as exc:
        console.print(f"[red]Sağlayıcı seçimi hatası:[/red] {exc}")
        raise typer.Exit(code=2) from exc

    context_text = _read_context_text(file)
    sensitivity = classify_sensitivity(prompt, context_text)

    commander = Commander()
    plan = commander.create_plan(
        prompt,
        mode=mode,
        context_file=file,
        context_text=context_text,
    )
    plan.policy.timeout_seconds = timeout
    plan.policy.blind_mode = blind
    plan.policy.allow_writes = allow_writes

    try:
        router.assign_providers(plan, allowed_providers=allowed, dry_run=dry_run)
    except RuntimeError as exc:
        console.print(f"[red]Yönlendirme hatası:[/red] {exc}")
        raise typer.Exit(code=1) from exc

    if sensitivity.is_sensitive and not json_output:
        # SEC-03: hassas veri her koşulda görünür biçimde bildirilir.
        console.print(
            f"[bold yellow]⚠ Hassas veri uyarısı:[/bold yellow] {', '.join(sensitivity.categories)}"
        )
        console.print(f"  [dim]Bulgular: {sensitivity.summary()}[/dim]")
        targets = sorted({st.assigned_provider or "-" for st in plan.subtasks})
        console.print(f"  [dim]Bu görev şu sağlayıcılara gidecek: {', '.join(targets)}[/dim]")
        if mode is None and plan.mode is not ExecutionMode.COUNCIL:
            console.print("  [dim]Konsey moduna otomatik genişletme yapılmadı.[/dim]")
        console.print()

    if explain and not json_output:
        console.print(f"[bold cyan]Planlanan Mod:[/bold cyan] {plan.mode.value.upper()}")
        console.print(f"[bold cyan]Seçim Gerekçesi:[/bold cyan] {plan.reasoning}")
        if allowed:
            console.print(f"[bold cyan]Sağlayıcı İzin Listesi:[/bold cyan] {', '.join(allowed)}")
        if plan.policy.blind_mode:
            console.print("  [magenta]• Kör Hakemlik (Blind Peer Review) devrede.[/magenta]")
        if plan.policy.allow_writes:
            console.print("  [yellow]• Dosya Yazma (Write Safety) izni devrede.[/yellow]")
        for st in plan.subtasks:
            provider_tag = f"[green]{st.assigned_provider}[/green]"
            console.print(f"  • [yellow]{st.role}[/yellow] ➔ {provider_tag}: {st.purpose}")
        console.print()

    if dry_run and not json_output:
        _render_data_sharing_preview(plan, file, context_text)

    lock_mgr = FileLockManager()
    lock_holder = f"voltran-orchestrator-{uuid4().hex}"
    if file and allow_writes and not lock_mgr.acquire(file, lock_holder):
        current_holder = lock_mgr.get_holder(file) or "bilinmeyen süreç"
        console.print(
            f"[red]Dosya kilidi alınamadı:[/red] {file} "
            f"([yellow]{current_holder}[/yellow] tarafından kullanılıyor)"
        )
        raise typer.Exit(code=1)

    try:
        engine = ExecutionEngine()
        report = asyncio.run(engine.execute_plan(prompt, plan, dry_run=dry_run))
    finally:
        if file and allow_writes:
            lock_mgr.release(file, lock_holder)

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
def unlock(
    file: Annotated[
        Path | None,
        typer.Argument(help="Kilidi kaldırılacak dosya yolu."),
    ] = None,
    all_locks: Annotated[
        bool,
        typer.Option("--all", help="Bu projedeki tüm Voltran dosya kilitlerini kaldır."),
    ] = False,
) -> None:
    """Çöken çalışmalardan kalan dosya kilitlerini açık kullanıcı isteğiyle kaldır."""

    from voltran.lock import FileLockManager

    lock_mgr = FileLockManager()
    if all_locks:
        released = lock_mgr.release_all()
        console.print(f"[green]{released} kilit kaldırıldı.[/green]")
        return
    if file is None:
        console.print("[red]Bir dosya yolu veya --all belirtin.[/red]")
        raise typer.Exit(code=2)
    if not lock_mgr.has_lock(file):
        console.print(f"[dim]Kilit bulunmuyor:[/dim] {file}")
        return
    if not lock_mgr.force_release(file):
        console.print(f"[red]Kilit kaldırılamadı:[/red] {file}")
        raise typer.Exit(code=1)
    console.print(f"[green]Kilit kaldırıldı:[/green] {file}")


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


@app.command()
def bench(
    dry_run: Annotated[
        bool,
        typer.Option(
            "--dry-run",
            help="Modelleri gerçekte çağırmadan kıyaslama hattını simüle et.",
        ),
    ] = False,
    timeout: Annotated[
        float,
        typer.Option(help="Her görev için saniye cinsinden zaman aşımı."),
    ] = 60.0,
    json_output: Annotated[
        bool,
        typer.Option("--json", help="Çıktıyı JSON formatında üret."),
    ] = False,
) -> None:
    """Standart değerlendirme setini çalıştır ve modların performansını kıyasla."""
    import dataclasses

    from voltran.eval import BenchmarkRunner
    from voltran.models import ExecutionStatus

    runner = BenchmarkRunner()
    results = asyncio.run(runner.run_all(dry_run=dry_run, timeout=timeout))

    if json_output:
        typer.echo(
            json.dumps(
                [dataclasses.asdict(r) for r in results],
                ensure_ascii=False,
                indent=2,
                default=str,
            )
        )
        return

    table = Table(title="VOLTRAN Görev Bazlı Kıyaslama Raporu", show_lines=True)
    table.add_column("Görev ID", no_wrap=True)
    table.add_column("Başlık")
    table.add_column("Kategori")
    table.add_column("Mod")
    table.add_column("Durum", no_wrap=True)
    table.add_column("Süre (ms)", justify="right")
    table.add_column("Güven", justify="right")
    table.add_column("Uzlaşma")

    for res in results:
        status_color = "green" if res.status == ExecutionStatus.SUCCESS else "red"
        consensus_text = "[green]Var[/green]" if res.consensus_reached else "[dim]Tek/Yok[/dim]"
        table.add_row(
            res.task_id,
            res.title,
            res.category,
            res.mode.value.upper(),
            f"[{status_color}]{res.status.value}[/{status_color}]",
            str(res.duration_ms),
            f"%{round(res.confidence_score * 100)}",
            consensus_text,
        )

    console.print(table)


@app.command()
def dashboard(
    once: Annotated[
        bool,
        typer.Option("--once", help="Sürekli yenileme yerine tek seferlik göster ve çık."),
    ] = False,
    refresh_rate: Annotated[
        float,
        typer.Option(help="Yenileme aralığı (saniye cinsinden)."),
    ] = 1.0,
) -> None:
    """Canlı çoklu ajan izleme panelini (TUI Dashboard) başlat."""
    from voltran.dashboard import DashboardView

    view = DashboardView()
    if once:
        console.print(view.render_once())
    else:
        try:
            view.run_live(refresh_rate=refresh_rate, console=console)
        except KeyboardInterrupt:
            console.print("\n[dim]Gösterge paneli kapatıldı.[/dim]")
