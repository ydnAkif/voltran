"""VOLTRAN Gizlilik ve Veri Maskeleme (Sanitizer) katmanı."""

from __future__ import annotations

import re

Rule = tuple[re.Pattern[str], str]

# --- Yüksek kesinlikli gizli değer desenleri -------------------------------
# Bu desenler yalnızca gerçek sırlarda eşleşir; kod veya teknik metinde yanlış
# pozitif riski ihmal edilebilir düzeydedir.

# OpenAI & generic sk-
_OPENAI_KEY: Rule = (re.compile(r"\b(?:sk-[A-Za-z0-9_-]{20,})\b"), "[REDACTED_API_KEY]")
# Anthropic sk-ant-
_ANTHROPIC_KEY: Rule = (re.compile(r"\b(?:sk-ant-[A-Za-z0-9_-]{20,})\b"), "[REDACTED_API_KEY]")
# GitHub tokens
_GITHUB_TOKEN: Rule = (re.compile(r"\b(?:gh[pousr]_[A-Za-z0-9]{36,})\b"), "[REDACTED_TOKEN]")
# Bearer tokens
_BEARER_TOKEN: Rule = (
    re.compile(r"(?i)\bbearer\s+[A-Za-z0-9_.-]{20,}\b"),
    "Bearer [REDACTED_TOKEN]",
)

# Anahtar/değer biçimindeki kimlik bilgileri (`DB_PASSWORD=...`, `api_key: "..."`).
# Üç tasarım kararı:
#   1. Anahtar adında önek serbesttir; aksi hâlde `\b` yüzünden `DB_PASSWORD` veya
#      `APP_SECRET` gibi yaygın ortam değişkeni adları hiç yakalanmaz.
#   2. Değerde en az bir rakam aranır. Bu, `token = getUserTokenFromRequest` gibi saf
#      kod tanımlayıcılarının maskelenip kaynak dosyanın bozulmasını engeller.
#   3. Yalnızca değer maskelenir; anahtar adı okunabilir kalır, böylece hangi alanın
#      gizlendiği rapordan anlaşılır.
# Bilinen sınır: rakam içermeyen düz metin parolalar (`secret = abcdefghijklmnop`)
# bilinçli olarak maskelenmez — kod bozmama önceliklidir.
_CREDENTIAL_ASSIGNMENT: Rule = (
    re.compile(
        r"(?i)([A-Za-z0-9_]*(?:api[_-]?key|secret|token|password|passwd|pwd))"
        r"(\s*[:=]\s*)(['\"]?)(?=[^\s'\"]*\d)([A-Za-z0-9_\-./+=]{12,})(['\"]?)"
    ),
    r"\1\2\3[REDACTED_CREDENTIAL]\5",
)

# E-posta adresleri
_EMAIL: Rule = (
    re.compile(r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b"),
    "[REDACTED_EMAIL]",
)

# --- Yalnızca yerel kayıt için kullanılan geniş PII desenleri ---------------
# Bunlar sayısal sabitler, hash'ler ve kimlik adları gibi kod parçalarında da
# eşleşebilir; bu yüzden sağlayıcıya giden metinde kullanılmazlar.

# Kredi kartı numaraları (13-19 haneli)
_CARD: Rule = (re.compile(r"\b(?:\d{4}[ -]?){3}\d{4}\b"), "[REDACTED_CARD]")
# IBAN (TR ve genel)
_IBAN: Rule = (re.compile(r"\b[A-Z]{2}\d{2}[A-Z0-9]{12,30}\b"), "[REDACTED_IBAN]")
# T.C. Kimlik Numarası (11 haneli basit şablon)
_TCKN: Rule = (re.compile(r"\b[1-9]\d{10}\b"), "[REDACTED_TCKN]")
# Telefon numaraları (+90 veya 05xx)
_PHONE: Rule = (
    re.compile(r"(?:\+90|0)?\s*[5]\d{2}[\s.-]?\d{3}[\s.-]?\d{2}[\s.-]?\d{2}\b"),
    "[REDACTED_PHONE]",
)

_API_KEY_PATTERNS: list[Rule] = [
    _OPENAI_KEY,
    _ANTHROPIC_KEY,
    _GITHUB_TOKEN,
    _BEARER_TOKEN,
    _CREDENTIAL_ASSIGNMENT,
]

_PII_PATTERNS: list[Rule] = [_EMAIL, _CARD, _IBAN, _TCKN, _PHONE]

# Sağlayıcıya giden kod ve teknik metinde yalnızca yanlış pozitif riski düşük
# desenler kullanılır. Sayısal sabitler, hash'ler, IBAN-benzeri test fixture'ları
# ve diğer kod parçaları burada kasıtlı olarak maskelenmez.
_OUTBOUND_PATTERNS: list[Rule] = [
    _OPENAI_KEY,
    _ANTHROPIC_KEY,
    _GITHUB_TOKEN,
    _BEARER_TOKEN,
    _CREDENTIAL_ASSIGNMENT,
    _EMAIL,
]


def _apply(text: str, rules: list[Rule]) -> str:
    sanitized = text
    for pattern, replacement in rules:
        sanitized = pattern.sub(replacement, sanitized)
    return sanitized


def sanitize_text(text: str) -> str:
    """Metindeki API anahtarları, parolalar, e-posta, kimlik ve kart bilgilerini maskeler."""

    if not text:
        return text

    return _apply(text, [*_API_KEY_PATTERNS, *_PII_PATTERNS])


def sanitize_for_provider(text: str) -> str:
    """Sağlayıcıya gönderilecek metinde yüksek kesinlikli sırları maskele."""

    if not text:
        return text

    return _apply(text, _OUTBOUND_PATTERNS)
