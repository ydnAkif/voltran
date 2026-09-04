"""VOLTRAN Görev Bazlı Değerlendirme ve Kıyaslama Motoru (Evaluation / Benchmark Suite).

Farklı çalışma modlarını (quick, expert, council) ve sağlayıcıları
standart senaryolar üzerinde doğruluk, süre, uzlaşma ve güven puanına göre ölçer.
"""

from __future__ import annotations

from dataclasses import dataclass

from voltran.commander import Commander
from voltran.engine import ExecutionEngine
from voltran.models import ExecutionMode, ExecutionReport, ExecutionStatus
from voltran.router import Router


@dataclass(frozen=True)
class BenchmarkTask:
    """Standart bir değerlendirme görevi."""

    task_id: str
    title: str
    category: str  # "architecture", "security", "coding", "reasoning"
    prompt: str
    target_mode: ExecutionMode
    description: str


@dataclass(frozen=True)
class BenchmarkResult:
    """Bir değerlendirme görevinin ölçüm sonucu."""

    task_id: str
    title: str
    category: str
    mode: ExecutionMode
    status: ExecutionStatus
    duration_ms: int
    confidence_score: float
    consensus_reached: bool
    summary: str


DEFAULT_BENCHMARK_SUITE: list[BenchmarkTask] = [
    BenchmarkTask(
        task_id="bench-arch-01",
        title="Mikroservis vs Monolit Mimarisi",
        category="architecture",
        prompt=(
            "Yüksek trafikli bir e-ticaret sistemi için monolit ve mikroservis "
            "mimarisini karşılaştır ve riskleri listele."
        ),
        target_mode=ExecutionMode.COUNCIL,
        description=(
            "Farklı modellerin mimari ticaret (trade-off) analizini ve uzlaşma kalitesini ölçer."
        ),
    ),
    BenchmarkTask(
        task_id="bench-sec-02",
        title="JWT ve Oturum Güvenliği Denetimi",
        category="security",
        prompt=(
            "Dağıtık bir sistemde JWT token iptali ve oturum yönetimi için en "
            "güvenli 3 deseni ve risklerini açıkla."
        ),
        target_mode=ExecutionMode.EXPERT,
        description=(
            "Uzman modellerin güvenlik açığı ve en iyi pratikleri tespit etme derinliğini ölçer."
        ),
    ),
    BenchmarkTask(
        task_id="bench-code-03",
        title="Asyncio Race Condition Analizi",
        category="coding",
        prompt=(
            "Python asyncio kütüphanesinde paylaşılan durum nesnelerinde oluşabilecek "
            "yarış durumlarını (race condition) ve çözüm yollarını kod örneğiyle özetle."
        ),
        target_mode=ExecutionMode.QUICK,
        description="Hızlı kodlama modellerinin sözdizimi doğruluğu ve açıklama netliğini ölçer.",
    ),
]


class BenchmarkRunner:
    """Değerlendirme görevlerini çalıştıran ve raporlayan orkestratör."""

    def __init__(
        self,
        tasks: list[BenchmarkTask] | None = None,
        *,
        commander: Commander | None = None,
        router: Router | None = None,
        engine: ExecutionEngine | None = None,
    ) -> None:
        self.tasks = tasks or DEFAULT_BENCHMARK_SUITE
        self.commander = commander or Commander()
        self.router = router or Router()
        self.engine = engine or ExecutionEngine()

    async def run_task(
        self,
        task: BenchmarkTask,
        *,
        dry_run: bool = False,
        timeout: float = 60.0,
    ) -> BenchmarkResult:
        """Tek bir kıyaslama görevini yürütür ve sonucu yapılandırılmış olarak döndürür."""
        plan = self.commander.create_plan(task.prompt, mode=task.target_mode)
        plan.policy.timeout_seconds = timeout

        self.router.assign_providers(plan, dry_run=dry_run)
        report: ExecutionReport = await self.engine.execute_plan(task.prompt, plan, dry_run=dry_run)

        # Durum ve uzlaşma tespiti
        statuses = {execution.status for execution in report.executions}
        if not statuses or ExecutionStatus.FAILED in statuses:
            overall_status = ExecutionStatus.FAILED
        elif ExecutionStatus.TIMED_OUT in statuses:
            overall_status = ExecutionStatus.TIMED_OUT
        elif ExecutionStatus.CANCELLED in statuses:
            overall_status = ExecutionStatus.CANCELLED
        else:
            overall_status = ExecutionStatus.SUCCESS

        confidence = report.synthesis.confidence_score if report.synthesis else 1.0
        consensus = bool(
            report.synthesis and report.synthesis.consensus and not report.synthesis.disagreements
        )

        return BenchmarkResult(
            task_id=task.task_id,
            title=task.title,
            category=task.category,
            mode=report.mode,
            status=overall_status,
            duration_ms=report.total_duration_ms,
            confidence_score=confidence,
            consensus_reached=consensus,
            summary=report.final_summary[:300],
        )

    async def run_all(
        self,
        *,
        dry_run: bool = False,
        timeout: float = 60.0,
    ) -> list[BenchmarkResult]:
        """Tüm kıyaslama paketini sırayla yürütür."""
        results: list[BenchmarkResult] = []
        for task in self.tasks:
            result = await self.run_task(task, dry_run=dry_run, timeout=timeout)
            results.append(result)
        return results
