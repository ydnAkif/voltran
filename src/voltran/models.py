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
    working_directory: Path = Field(default_factory=Path.cwd)
    model: str | None = None


class ExecutionPolicy(BaseModel):
    """Alt sürecin yetki ve kaynak sınırları."""

    timeout_seconds: float = Field(default=300.0, ge=0.1, le=3600.0)
    allow_writes: bool = False
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
