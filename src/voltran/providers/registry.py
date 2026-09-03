"""Yerleşik sağlayıcı adaptörü kaydı."""

from voltran.providers.antigravity import AntigravityAdapter
from voltran.providers.base import ProviderAdapter
from voltran.providers.claude import ClaudeAdapter
from voltran.providers.codex import CodexAdapter


def default_registry() -> dict[str, ProviderAdapter]:
    """Yeni sağlayıcıların çekirdeği değiştirmeden eklenebileceği varsayılan kayıt."""

    adapters: tuple[ProviderAdapter, ...] = (
        CodexAdapter(),
        ClaudeAdapter(),
        AntigravityAdapter(),
    )
    return {adapter.key: adapter for adapter in adapters}
