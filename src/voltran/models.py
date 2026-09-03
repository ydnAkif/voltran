"""VOLTRAN'ın sağlayıcıdan bağımsız veri sözleşmeleri."""

from __future__ import annotations

from datetime import UTC, datetime
from enum import StrEnum
from pathlib import Path
from typing import Any
from uuid import uuid4

from pydantic import BaseModel, Field


class CheckStatus(StrEnum):
    """Tek bir teşhis kontrolünün sonucu."""

    PASS = "pass"
    WARNING = "warning"
    FAIL = "fail"
    INFO = "info"


class ExecutionStatus(StrEnum):
    """Bir sağlayıcı çalıştırmasının yaşam döngüsü sonucu."""

    SUCCESS = "success"
    FAILED = "failed"
    TIMED_OUT = "timed_out"
    CANCELLED = "cancelled"


class DoctorCheck(BaseModel):
    """Kullanıcıya gösterilebilen, gizli değer içermeyen teşhis kaydı."""

    check_id: str
    title: str
    status: CheckStatus
    summary: str
    details: dict[str, str] = Field(default_factory=dict)
    remediation: str | None = None


class DoctorReport(BaseModel):
    """`voltran doctor` komutunun makinece okunabilir çıktısı."""

    generated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    overall_status: str
    checks: list[DoctorCheck]


class TaskResult(BaseModel):
    """Tüm sağlayıcı adaptörlerinin döndüreceği asgari çıktı sözleşmesi."""

    summary: str
    claims: list[str] = Field(default_factory=list)
    evidence: list[str] = Field(default_factory=list)
    uncertainties: list[str] = Field(default_factory=list)
    risks: list[str] = Field(default_factory=list)
    artifacts: list[str] = Field(default_factory=list)
    status: str
    metadata: dict[str, Any] = Field(default_factory=dict)


class ProviderCapabilities(BaseModel):
    """Router'ın sağlayıcı seçerken kullanacağı yetenek bildirimi."""

    text: bool = True
    code: bool = True
    file_access: bool = False
    images: bool = False
    tool_use: bool = False
    structured_output: bool = False
    cancellation: bool = True


class ProviderHealth(BaseModel):
    """Bir adaptörün yerel erişilebilirlik özeti."""

    provider: str
    available: bool
    version: str | None = None
    message: str


class ProviderTask(BaseModel):
    """Sağlayıcıya gönderilecek tek ve sınırlandırılmış görev."""

    task_id: str = Field(default_factory=lambda: uuid4().hex)
    prompt: str = Field(min_length=1)
    role: str = ""
    purpose: str = ""
    instructions: str = ""
    working_directory: Path = Field(default_factory=Path.cwd)
    model: str | None = None


class ExecutionPolicy(BaseModel):
    """Alt sürecin yetki ve kaynak sınırları."""

    timeout_seconds: float = Field(default=300.0, ge=0.1, le=3600.0)
    allow_writes: bool = False
    blind_mode: bool = False
    allowed_tools: tuple[str, ...] = ()
    max_output_chars: int = Field(default=200_000, ge=1_000, le=2_000_000)


class ProviderExecution(BaseModel):
    """Bir sağlayıcı çağrısının normalize edilmiş zarfı."""

    run_id: str
    provider: str
    status: ExecutionStatus
    duration_ms: int = Field(ge=0)
    exit_code: int | None = None
    result: TaskResult | None = None
    error: str | None = None


class ExecutionMode(StrEnum):
    """VOLTRAN çalışma modu."""

    QUICK = "quick"
    EXPERT = "expert"
    COUNCIL = "council"
    VISUAL = "visual"


class SubTask(BaseModel):
    """Plan içindeki tek bir alt görev tanımı."""

    subtask_id: str = Field(default_factory=lambda: uuid4().hex[:8])
    role: str
    purpose: str
    assigned_provider: str | None = None
    model: str | None = None


class TaskPlan(BaseModel):
    """Komutan ve Router tarafından üretilen makinece doğrulanabilir plan."""

    mode: ExecutionMode
    reasoning: str
    subtasks: list[SubTask] = Field(default_factory=lambda: list[SubTask]())
    context_file: Path | None = None
    policy: ExecutionPolicy = Field(default_factory=ExecutionPolicy)


class CouncilSynthesis(BaseModel):
    """Council modunda bağımsız sonuçların karşılaştırma ve sentezi."""

    consensus: list[str] = Field(default_factory=lambda: list[str]())
    disagreements: list[str] = Field(default_factory=lambda: list[str]())
    confidence_score: float = Field(default=1.0, ge=0.0, le=1.0)
    confidence_rationale: str = ""


class ExecutionReport(BaseModel):
    """Kullanıcıya sunulan veya kaydedilen tek nihai sonuç raporu."""

    run_id: str = Field(default_factory=lambda: uuid4().hex)
    task_prompt: str
    mode: ExecutionMode
    plan: TaskPlan
    executions: list[ProviderExecution] = Field(default_factory=lambda: list[ProviderExecution]())
    final_summary: str
    synthesis: CouncilSynthesis | None = None
    next_step_recommendation: str | None = None
    total_duration_ms: int = 0
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))


class HistoryRecord(BaseModel):
    """Geçmiş listesinde gösterilmek üzere SQLite'tan okunan hafif kayıt."""

    run_id: str
    created_at: str
    mode: str
    prompt_preview: str
    providers_used: list[str] = Field(default_factory=lambda: list[str]())
    duration_ms: int
    status: str
