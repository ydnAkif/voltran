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
from voltran.config import ConfigError, VoltranConfig, load_config, user_config_path
from voltran.context import (
    ContextError,
    ContextScope,
    load_context,
    parse_line_range,
)
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


def _render_data_sharing_preview(
    plan: TaskPlan,
    file: Path | None,
    scope: ContextScope | None,
) -> None:
    """FR-14: kuru çalışmada hangi verinin hangi sağlayıcıya gideceğini gösterir."""

    table = Table(title="Kuru Çalışma — Veri Paylaşım Önizlemesi", show_lines=False)
    table.add_column("Sağlayıcı", no_wrap=True)
    table.add_column("Rol")
    table.add_column("Paylaşılacak veri")

    shared = "Görev metni"
    if scope is not None and file is not None:
        shared = f"Görev metni + `{file.name}` ({scope.describe()})"

    for subtask in plan.subtasks:
        table.add_row(subtask.assigned_provider or "-", subtask.role, shared)

    console.print(table)
    console.print(f"[dim]Tahmini model çağrısı: {len(plan.subtasks)}[/dim]")
    if plan.sensitivity_categories:
        console.print(f"[dim]Hassas veri sınıfları: {', '.join(plan.sensitivity_categories)}[/dim]")
    if scope is not None and scope.is_trimmed:
        console.print(
            f"[yellow]Veri minimizasyonu:[/yellow] dosyanın {scope.trimmed_chars} karakteri "
            "sağlayıcıya gönderilmeyecek."
        )
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
        float | None,
        typer.Option(help="Model çalıştırmaları için saniye cinsinden zaman aşımı."),
    ] = None,
    blind: Annotated[
        bool | None,
        typer.Option(
            "--blind/--no-blind",
            help="Kör hakemlik: Modellerin marka ve firma kimliklerini gizle.",
        ),
    ] = None,
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
    max_context: Annotated[
        int | None,
        typer.Option(
            "--max-context",
            min=100,
            max=2_000_000,
            help="Bağlam dosyasından sağlayıcıya gönderilecek azami karakter sayısı.",
        ),
    ] = None,
    lines: Annotated[
        str | None,
        typer.Option(
            "--lines",
            help="Bağlam dosyasından yalnızca bu satır aralığını gönder. Örnek: --lines 40-120",
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

    # FR-13: komut satırı > proje (voltran.toml) > kullanıcı > güvenli varsayılan.
    try:
        settings = load_config(
            cli={
                "mode": mode.value if mode is not None else None,
                "timeout": timeout,
                "providers": _split_provider_options(providers) or None,
                "max_context": max_context,
                "blind": blind,
            }
        )
    except ConfigError as exc:
        console.print(f"[red]Yapılandırma hatası:[/red] {exc}")
        raise typer.Exit(code=2) from exc

    try:
        resolved_mode = ExecutionMode(settings.mode) if settings.mode is not None else None
    except ValueError as exc:
        valid = ", ".join(member.value for member in ExecutionMode)
        console.print(
            f"[red]Geçersiz mod:[/red] '{settings.mode}' "
            f"({settings.source_of('mode')}). Geçerli değerler: {valid}."
        )
        raise typer.Exit(code=2) from exc

    router = Router()
    try:
        allowed = router.validate_provider_keys(settings.providers)
    except ValueError as exc:
        console.print(f"[red]Sağlayıcı seçimi hatası:[/red] {exc}")
        raise typer.Exit(code=2) from exc

    # SEC-04: bağlam, sınıflandırmadan önce bütçelenir. Böylece hem uyarı hem de
    # önizleme, dosyanın tamamını değil sağlayıcıya *fiilen giden* kapsamı anlatır.
    scope: ContextScope | None = None
    line_range: tuple[int, int] | None = None
    if file is not None:
        try:
            line_range = parse_line_range(lines) if lines else None
            scope = load_context(file, max_chars=settings.max_context, line_range=line_range)
        except ContextError as exc:
            console.print(f"[red]Bağlam dosyası hatası:[/red] {exc}")
            raise typer.Exit(code=2) from exc

    context_text = scope.text if scope is not None else None
    sensitivity = classify_sensitivity(prompt, context_text)

    commander = Commander()
    plan = commander.create_plan(
        prompt,
        mode=resolved_mode,
        context_file=file,
        context_text=context_text,
    )
    plan.policy.timeout_seconds = settings.timeout
    plan.policy.blind_mode = settings.blind
    plan.policy.allow_writes = allow_writes
    plan.policy.max_context_chars = settings.max_context
    plan.policy.context_line_range = line_range

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
        if resolved_mode is None and plan.mode is not ExecutionMode.COUNCIL:
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
        _render_data_sharing_preview(plan, file, scope)

    lock_mgr = FileLockManager()
    lock_holder = f"voltran-orchestrator-{uuid4().hex}"
    if file and allow_writes and not lock_mgr.acquire(file, lock_holder):
        current_holder = lock_mgr.get_holder(file) or "bilinmeyen süreç"
        console.print(
            f"[red]Dosya kilidi alınamadı:[/red] {file} "
            f"([yellow]{current_holder}[/yellow] tarafından kullanılıyor)"
        )
        raise typer.Exit(code=1)

    engine = ExecutionEngine()
    try:
        report = asyncio.run(engine.execute_plan(prompt, plan, dry_run=dry_run))
    except KeyboardInterrupt:
        console.print("\n[yellow]Çalıştırma kullanıcı tarafından iptal edildi.[/yellow]")
        outcome = engine.last_workspace_outcome
        if outcome is not None and outcome.worktree.exists():
            console.print(
                f"[yellow]İzole çalışma alanı inceleme için korundu:[/yellow] {outcome.worktree}"
            )
            if outcome.patch_file is not None:
                console.print(f"[yellow]Değişiklik yaması:[/yellow] {outcome.patch_file}")
        raise typer.Exit(code=130) from None
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


def _config_rows(settings: VoltranConfig) -> list[tuple[str, str, str]]:
    """Yürürlükteki her ayarı ve geldiği katmanı satırlara çevirir."""

    values: dict[str, object] = {
        "mode": settings.mode if settings.mode is not None else "(otomatik seçilir)",
        "timeout": settings.timeout,
        "providers": ", ".join(settings.providers) if settings.providers else "(kısıt yok)",
        "max_context": settings.max_context,
        "blind": "evet" if settings.blind else "hayır",
    }
    return [(key, str(value), settings.source_of(key)) for key, value in values.items()]


@app.command()
def config(
    json_output: Annotated[
        bool,
        typer.Option("--json", help="Makinece okunabilir JSON çıktı üret."),
    ] = False,
) -> None:
    """Yürürlükteki yapılandırmayı ve her ayarın hangi katmandan geldiğini göster."""

    try:
        settings = load_config()
    except ConfigError as exc:
        console.print(f"[red]Yapılandırma hatası:[/red] {exc}")
        raise typer.Exit(code=2) from exc

    rows = _config_rows(settings)
    if json_output:
        typer.echo(
            json.dumps(
                {
                    "settings": {key: value for key, value, _ in rows},
                    "provenance": {key: source for key, _, source in rows},
                    "sources": [str(path) for path in settings.sources],
                },
                ensure_ascii=False,
                indent=2,
            )
        )
        return

    table = Table(title="VOLTRAN yürürlükteki yapılandırma", show_lines=False)
    table.add_column("Ayar", no_wrap=True)
    table.add_column("Değer")
    table.add_column("Kaynak", style="dim")
    for key, value, source in rows:
        table.add_row(key, value, source)
    console.print(table)

    console.print(
        "\n[dim]Öncelik: komut satırı > proje (voltran.toml) > kullanıcı > varsayılan.[/dim]"
    )
    if settings.sources:
        for path in settings.sources:
            console.print(f"[dim]Okunan dosya: {path}[/dim]")
    else:
        console.print("[dim]Hiçbir yapılandırma dosyası bulunamadı; varsayılanlar geçerli.[/dim]")
        console.print(f"[dim]Kullanıcı dosyası şuraya konabilir: {user_config_path()}[/dim]")
    console.print("[dim]Yazma izni (--write) güvenlik gereği yapılandırılamaz.[/dim]")


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


@app.command()
def replay(
    run_id: Annotated[
        str,
        typer.Argument(help="Yeniden oynatılacak çalıştırmanın kimliği (run_id)."),
    ],
    json_output: Annotated[
        bool,
        typer.Option("--json", help="Sonucu Markdown yerine ham JSON olarak yazdır."),
    ] = False,
    explain: Annotated[
        bool,
        typer.Option("--explain", help="Plan ve rol dağılımını çalıştırmadan önce açıkla."),
    ] = False,
    output: Annotated[
        Path | None,
        typer.Option("-o", "--output", help="Sonuç raporunun kaydedileceği Markdown dosyası."),
    ] = None,
) -> None:
    """Kaydedilmiş bir görevi aynı plan ve politikayla yeniden oynat (FR-12)."""

    from rich.markdown import Markdown

    from voltran.engine import ExecutionEngine
    from voltran.reporter import Reporter
    from voltran.store import RunStore

    store = RunStore()
    stored = store.get_run(run_id)
    if stored is None:
        console.print(f"[red]Çalıştırma bulunamadı:[/red] {run_id}")
        raise typer.Exit(code=1)

    if stored.plan is None:
        console.print(
            f"[yellow]Bu çalıştırma ({run_id}) eski formatta kaydedilmiş, "
            "plan bilgisi içermiyor ve yeniden oynatılamaz.[/yellow]"
        )
        raise typer.Exit(code=1)

    if explain and not json_output:
        console.print(f"[bold cyan]Yeniden Oynatılan Çalıştırma:[/bold cyan] {run_id}")
        console.print(f"[bold cyan]Planlanan Mod:[/bold cyan] {stored.plan.mode.value.upper()}")
        console.print(f"[bold cyan]Seçim Gerekçesi:[/bold cyan] {stored.plan.reasoning}")
        console.print(f"[dim]İstem: {stored.prompt}[/dim]\n")

    engine = ExecutionEngine()
    try:
        report = asyncio.run(engine.execute_plan(stored.prompt, stored.plan))
    except KeyboardInterrupt:
        console.print("\n[yellow]Yeniden oynatma kullanıcı tarafından iptal edildi.[/yellow]")
        raise typer.Exit(code=130) from None

    store.save_report(report)

    if json_output:
        typer.echo(Reporter.to_json(report))
    else:
        console.print(Markdown(Reporter.to_markdown(report)))

    if output is not None:
        output.write_text(Reporter.to_markdown(report), encoding="utf-8")
        console.print(f"\n[green]Rapor kaydedildi:[/green] {output}")


def _process_command_line(pid: int) -> str | None:
    """Verilen PID'in komut satırını döndürür; süreç yoksa None.

    `voltran cancel`, veritabanındaki bir PID'e sinyal göndermeden önce o PID'in
    hâlâ *bizim* sürecimiz olduğunu doğrulamak zorundadır. Çöken bir çalıştırma
    `active_runs` satırını geride bırakır ve işletim sistemi o PID'i bir süre
    sonra başka bir uygulamaya verir; doğrulama olmadan iptal komutu ilgisiz bir
    süreci öldürür.
    """

    import subprocess

    try:
        completed = subprocess.run(
            ["ps", "-p", str(pid), "-o", "args="],
            capture_output=True,
            check=False,
            text=True,
            timeout=3.0,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    if completed.returncode != 0:
        return None
    return completed.stdout.strip() or None


@app.command()
def cancel(
    run_id: Annotated[
        str,
        typer.Argument(help="İptal edilecek çalıştırmanın kimliği (run_id)."),
    ],
) -> None:
    """Devam eden bir çalıştırmayı ve alt süreçlerini sonlandır (FR-15)."""

    import os
    import signal
    import time
    from contextlib import suppress

    from voltran.store import RunStore

    store = RunStore()
    active = store.get_active_run(run_id)
    if active is None:
        stored = store.get_run(run_id)
        if stored:
            console.print(
                f"[yellow]Çalıştırma zaten aktif değil:[/yellow] {run_id} (Durum: {stored.status})"
            )
            return
        console.print(f"[red]Çalıştırma bulunamadı:[/red] {run_id}")
        raise typer.Exit(code=1)

    pid = active["pid"]

    # PID kimliğini doğrula. Aksi hâlde çöken bir çalıştırmadan kalan bayat kayıt,
    # işletim sisteminin aynı PID'i verdiği ilgisiz bir sürecin öldürülmesine yol açar.
    command_line = _process_command_line(pid)
    if command_line is None:
        store.unregister_active_run(run_id)
        store.mark_run_cancelled(run_id)
        console.print(
            f"[yellow]Süreç zaten çalışmıyor:[/yellow] {run_id} (PID {pid}). "
            "Geride kalan kayıt temizlendi."
        )
        return
    if "voltran" not in command_line.lower():
        store.unregister_active_run(run_id)
        console.print(
            f"[red]Güvenlik durdurması:[/red] PID {pid} artık bir VOLTRAN süreci değil "
            "(muhtemelen çöken bir çalıştırmadan kalan kayıt ve PID yeniden kullanılmış). "
            "Hiçbir sinyal gönderilmedi; bayat kayıt temizlendi."
        )
        raise typer.Exit(code=1)

    def _signal_process(sig: signal.Signals) -> None:
        """Süreci ve yalnızca ona ait olan süreç grubunu sonlandır."""

        if os.name == "posix":
            with suppress(ProcessLookupError, PermissionError):
                # Yalnızca kendi grubunun lideriyse gruba sinyal gönder. Etkileşimsiz
                # bir kabukta voltran, çağıranın süreç grubunu miras alır; grubu
                # körlemesine öldürmek çağıran betiği de kapatırdı.
                if os.getpgid(pid) == pid:
                    os.killpg(pid, sig)
        with suppress(ProcessLookupError, PermissionError):
            os.kill(pid, sig)

    terminated = False
    try:
        _signal_process(signal.SIGTERM)

        for _ in range(10):
            try:
                os.kill(pid, 0)
                time.sleep(0.1)
            except ProcessLookupError:
                terminated = True
                break

        if not terminated:
            _signal_process(signal.SIGKILL)
    except Exception as exc:
        console.print(f"[red]İptal işlemi sırasında hata oluştu:[/red] {exc}")
        raise typer.Exit(code=1) from exc

    store.unregister_active_run(run_id)
    store.mark_run_cancelled(run_id)
    console.print(f"[green]Çalıştırma başarıyla iptal edildi:[/green] {run_id}")
