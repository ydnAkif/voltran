"""VOLTRAN Gizlilik ve Veri Maskeleme (Sanitizer) katmanı."""

from __future__ import annotations

import re

# Hassas veri ve gizli değer desenleri
_API_KEY_PATTERNS = [
    # OpenAI & generic sk-
    (re.compile(r"\b(?:sk-[A-Za-z0-9_-]{20,})\b"), "[REDACTED_API_KEY]"),
    # Anthropic sk-ant-
    (re.compile(r"\b(?:sk-ant-[A-Za-z0-9_-]{20,})\b"), "[REDACTED_API_KEY]"),
    # GitHub tokens
    (re.compile(r"\b(?:gh[pousr]_[A-Za-z0-9]{36,})\b"), "[REDACTED_TOKEN]"),
    # Bearer tokens
    (re.compile(r"(?i)\bbearer\s+[A-Za-z0-9_.-]{20,}\b"), "Bearer [REDACTED_TOKEN]"),
    # Genel uzun hex/base64 tokenlar (32+ karakter)
    (
        re.compile(
            r"(?i)\b(?:api[_-]?key|secret|token|password)\s*[:=]\s*['\"]?"
            r"([A-Za-z0-9_\-./+=]{16,})['\"]?"
        ),
        "[REDACTED_CREDENTIAL]",
    ),
]

_PII_PATTERNS = [
    # E-posta adresleri
    (re.compile(r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b"), "[REDACTED_EMAIL]"),
    # Kredi kartı numaraları (13-19 haneli)
    (re.compile(r"\b(?:\d{4}[ -]?){3}\d{4}\b"), "[REDACTED_CARD]"),
    # IBAN (TR ve genel)
    (re.compile(r"\b[A-Z]{2}\d{2}[A-Z0-9]{12,30}\b"), "[REDACTED_IBAN]"),
    # T.C. Kimlik Numarası (11 haneli basit şablon)
    (re.compile(r"\b[1-9]\d{10}\b"), "[REDACTED_TCKN]"),
    # Telefon numaraları (+90 veya 05xx)
    (
        re.compile(r"(?:\+90|0)?\s*[5]\d{2}[\s.-]?\d{3}[\s.-]?\d{2}[\s.-]?\d{2}\b"),
        "[REDACTED_PHONE]",
    ),
]

# Sağlayıcıya giden kod ve teknik metinde yalnızca yanlış pozitif riski düşük
# desenler kullanılır. Sayısal sabitler, hash'ler, IBAN-benzeri test fixture'ları
# ve diğer kod parçaları burada kasıtlı olarak maskelenmez.
_OUTBOUND_PATTERNS = [*_API_KEY_PATTERNS[:4], _PII_PATTERNS[0]]


def sanitize_text(text: str) -> str:
    """Metindeki API anahtarları, parolalar, e-posta, kimlik ve kart bilgilerini maskeler."""

    if not text:
        return text

    sanitized = text
    for pattern, replacement in _API_KEY_PATTERNS:
        sanitized = pattern.sub(replacement, sanitized)

    for pattern, replacement in _PII_PATTERNS:
        sanitized = pattern.sub(replacement, sanitized)

    return sanitized


def sanitize_for_provider(text: str) -> str:
    """Sağlayıcıya gönderilecek metinde yüksek kesinlikli sırları maskele."""

    sanitized = text
    for pattern, replacement in _OUTBOUND_PATTERNS:
        sanitized = pattern.sub(replacement, sanitized)
    return sanitized
