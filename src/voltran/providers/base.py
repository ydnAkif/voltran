"""Sağlayıcı adaptörlerinin ortak sözleşmesi."""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from voltran.models import (
    ExecutionPolicy,
    ProviderCapabilities,
    ProviderExecution,
    ProviderHealth,
    ProviderTask,
    TaskResult,
)


@runtime_checkable
class ProviderAdapter(Protocol):
    """Çekirdeği sağlayıcıya özel komut biçimlerinden ayırır."""

    key: str

    def availability(self) -> bool:
        """CLI aracının yerel olarak bulunup bulunmadığını döndür."""
        ...

    def capabilities(self) -> ProviderCapabilities:
        """Router için desteklenen yetenekleri bildir."""
        ...

    async def health_check(self) -> ProviderHealth:
        """Model çağrısı yapmadan CLI sağlığını kontrol et."""
        ...

    async def execute(
        self,
        task: ProviderTask,
        context: str | None,
        policy: ExecutionPolicy,
    ) -> ProviderExecution:
        """Görevi politika sınırları içinde yürüt."""
        ...

    async def cancel(self, run_id: str) -> bool:
        """Etkin çalışmayı ve alt süreçlerini sonlandır."""
        ...

    def normalize_result(self, raw_output: str) -> TaskResult:
        """Sağlayıcı çıktısını ortak sonuç sözleşmesine dönüştür."""
        ...
