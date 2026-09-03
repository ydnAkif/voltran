"""VOLTRAN Yönlendirici (Router) bileşeni — Akıllı yetenek ve sağlayıcı eşleştirme."""

from __future__ import annotations

from collections.abc import Sequence

from voltran.models import ExecutionMode, ProviderCapabilities, TaskPlan
from voltran.providers import ProviderAdapter, default_registry


def score_adapter(
    adapter: ProviderAdapter,
    mode: ExecutionMode,
    *,
    has_file: bool = False,
) -> float:
    """Sağlayıcının göreve, yeteneğe ve moda uygunluk puanını (0.0 - 1.0) hesaplar."""

    if not adapter.availability():
        return 0.0

    caps = adapter.capabilities()
    base_score = 0.5

    # Dosya erişim yeteneği gerekiyorsa
    if has_file:
        if caps.file_access:
            base_score += 0.2
        else:
            base_score -= 0.3

    match mode:
        case ExecutionMode.QUICK:
            # Hızlı mod için hafif ve doğrudan CLI yanıtı veren modeller öncelikli
            weights = {"google": 0.3, "claude": 0.25, "codex": 0.2}
            base_score += weights.get(adapter.key, 0.1)
        case ExecutionMode.EXPERT:
            # Uzman modu için derin mantık ve kodlama gücü öncelikli
            weights = {"claude": 0.3, "codex": 0.28, "google": 0.2}
            base_score += weights.get(adapter.key, 0.1)
        case ExecutionMode.COUNCIL:
            # Konsey için güçlü modeller dengeli puanlanır
            weights = {"claude": 0.3, "codex": 0.29, "google": 0.25}
            base_score += weights.get(adapter.key, 0.1)
        case ExecutionMode.VISUAL:
            if caps.images:
                base_score += 0.4
            else:
                base_score -= 0.2

    return max(0.0, min(1.0, base_score))


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
        """Plandaki her alt göreve en uygun sağlayıcıyı puanlayarak atar."""

        has_file = plan.context_file is not None
        req_caps = ProviderCapabilities(file_access=True) if has_file else None

        available = self.available_adapters(
            allowed_keys=allowed_providers,
            required_caps=req_caps,
        )

        if not available:
            # Yetenek filtresi olmadan sadece erişilebilir olanları dene
            available = self.available_adapters(allowed_keys=allowed_providers)

        if not available:
            raise RuntimeError(
                "Kullanılabilir veya erişilebilir hiçbir sağlayıcı CLI bulunamadı. "
                "Lütfen 'voltran doctor' komutunu çalıştırarak araçların kurulu ve "
                "PATH üzerinde olduğunu doğrulayın."
            )

        # Sağlayıcıları göreve ve moda göre puanla ve sırala
        ranked = sorted(
            available,
            key=lambda a: score_adapter(a, plan.mode, has_file=has_file),
            reverse=True,
        )

        if plan.mode == ExecutionMode.COUNCIL:
            # Council için en yüksek puanlı iki farklı sağlayıcıyı eşleştir
            assigned_keys: set[str] = set()
            for idx, subtask in enumerate(plan.subtasks):
                candidate = next(
                    (a for a in ranked if a.key not in assigned_keys),
                    ranked[idx % len(ranked)],
                )
                subtask.assigned_provider = candidate.key
                assigned_keys.add(candidate.key)
        else:
            best_adapter = ranked[0]
            for subtask in plan.subtasks:
                subtask.assigned_provider = best_adapter.key

        return plan
