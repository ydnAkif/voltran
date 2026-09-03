"""VOLTRAN Yönlendirici (Router) bileşeni — Sağlayıcı ve yetenek eşleştirme."""

from __future__ import annotations

from collections.abc import Sequence

from voltran.models import ExecutionMode, ProviderCapabilities, TaskPlan
from voltran.providers import ProviderAdapter, default_registry


class Router:
    """Sağlayıcıların yeteneklerini ve durumlarını değerlendirerek planı doldurur."""

    def __init__(self, registry: dict[str, ProviderAdapter] | None = None) -> None:
        self.registry = registry if registry is not None else default_registry()

    def available_adapters(
        self,
        *,
        allowed_keys: Sequence[str] | None = None,
        required_caps: ProviderCapabilities | None = None,
    ) -> list[ProviderAdapter]:
        """Kullanılabilir ve gereksinimleri karşılayan adaptörleri döndürür."""

        adapters: list[ProviderAdapter] = []
        for key, adapter in self.registry.items():
            if allowed_keys is not None and key not in allowed_keys:
                continue
            if not adapter.availability():
                continue
            if required_caps is not None:
                caps = adapter.capabilities()
                if required_caps.file_access and not caps.file_access:
                    continue
                if required_caps.images and not caps.images:
                    continue
                if required_caps.tool_use and not caps.tool_use:
                    continue
            adapters.append(adapter)
        return adapters

    def assign_providers(
        self,
        plan: TaskPlan,
        *,
        allowed_providers: Sequence[str] | None = None,
    ) -> TaskPlan:
        """Plandaki her alt göreve en uygun sağlayıcıyı atar."""

        req_caps = None
        if plan.context_file is not None:
            req_caps = ProviderCapabilities(file_access=True)

        available = self.available_adapters(
            allowed_keys=allowed_providers,
            required_caps=req_caps,
        )

        if not available:
            # Fallback: yetenek filtresi olmadan sadece erişilebilir olanları dene
            available = self.available_adapters(allowed_keys=allowed_providers)

        if not available:
            # Hiç sağlayıcı yoksa veya mocklanmadıysa kayıtlı olanları sırayla ata
            available = list(self.registry.values())

        if not available:
            raise RuntimeError("Kayıtlı hiçbir model sağlayıcısı bulunamadı.")

        if plan.mode == ExecutionMode.COUNCIL:
            # Council için farklı sağlayıcıları eşleştirmeye çalış
            assigned_keys: set[str] = set()
            for idx, subtask in enumerate(plan.subtasks):
                # Henüz seçilmemiş bir sağlayıcı bul
                candidate = next(
                    (a for a in available if a.key not in assigned_keys),
                    available[idx % len(available)],
                )
                subtask.assigned_provider = candidate.key
                assigned_keys.add(candidate.key)
        else:
            # Quick ve Expert modları
            preferred_order = ["claude", "codex", "google"]
            candidate = next(
                (a for key in preferred_order for a in available if a.key == key),
                available[0],
            )
            for subtask in plan.subtasks:
                subtask.assigned_provider = candidate.key

        return plan
