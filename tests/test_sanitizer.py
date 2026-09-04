from __future__ import annotations

from voltran.sanitizer import sanitize_for_provider, sanitize_text


def test_sanitize_masks_api_keys_and_tokens() -> None:
    raw = (
        "OpenAI anahtarım sk-1234567890abcdef1234567890 ve "
        "Anthropic sk-ant-api03-abcdef1234567890123456 ve "
        "GitHub ghp_123456789012345678901234567890123456 "
        "ve Bearer eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.test"
    )
    sanitized = sanitize_text(raw)

    assert "sk-1234567890" not in sanitized
    assert "sk-ant-api03" not in sanitized
    assert "ghp_123456" not in sanitized
    assert "[REDACTED_API_KEY]" in sanitized
    assert "[REDACTED_TOKEN]" in sanitized


def test_sanitize_masks_pii() -> None:
    raw = (
        "Kullanıcı e-postası: test.user@example.com, "
        "Kart: 4111 2222 3333 4444, "
        "IBAN: TR330006100519786452100654, "
        "TCKN: 12345678901"
    )
    sanitized = sanitize_text(raw)

    assert "test.user@example.com" not in sanitized
    assert "4111 2222 3333 4444" not in sanitized
    assert "TR330006100519786452100654" not in sanitized
    assert "[REDACTED_EMAIL]" in sanitized
    assert "[REDACTED_CARD]" in sanitized
    assert "[REDACTED_IBAN]" in sanitized
    assert "[REDACTED_TCKN]" in sanitized


def test_provider_sanitizer_preserves_code_like_pii_but_masks_high_confidence_secrets() -> None:
    source = (
        "uint64_t ogrenci_no = 20231234567;\n"
        'const char* HASH = "AB12CDEF3456789012345";\n'
        "// user@example.com sk-1234567890abcdef1234567890"
    )

    sanitized = sanitize_for_provider(source)

    assert "20231234567" in sanitized
    assert "AB12CDEF3456789012345" in sanitized
    assert "user@example.com" not in sanitized
    assert "sk-1234567890abcdef1234567890" not in sanitized


def test_sanitize_masks_prefixed_credential_assignments() -> None:
    raw = (
        "DB_PASSWORD=Sifre_Cok_Gizli_123456\n"
        'APP_SECRET: "aB3xY9zQ7mN2pL5k"\n'
        "api_key=abc123def456ghi789"
    )

    for sanitized in (sanitize_text(raw), sanitize_for_provider(raw)):
        assert "Sifre_Cok_Gizli_123456" not in sanitized
        assert "aB3xY9zQ7mN2pL5k" not in sanitized
        assert "abc123def456ghi789" not in sanitized
        # Anahtar adı okunabilir kalmalı ki hangi alanın gizlendiği anlaşılsın.
        assert "DB_PASSWORD=" in sanitized
        assert "APP_SECRET: " in sanitized
        assert sanitized.count("[REDACTED_CREDENTIAL]") == 3


def test_credential_pattern_does_not_corrupt_code_identifiers() -> None:
    source = (
        "const token = getUserTokenFromRequest;\n"
        "std::string password = userProvidedPassword;\n"
        "int secret_count = 12;\n"
        "REFRESH_TOKEN_TTL=3600"
    )

    assert sanitize_for_provider(source) == source
    assert "[REDACTED_CREDENTIAL]" not in sanitize_text(source)
