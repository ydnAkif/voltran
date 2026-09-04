from __future__ import annotations

from voltran.classifier import (
    SensitivityCategory,
    classify_sensitivity,
    normalize_turkish,
)


def test_empty_input_is_not_sensitive() -> None:
    report = classify_sensitivity(None, "", "   ")

    assert report.is_sensitive is False
    assert report.categories == ()
    assert report.summary() == "Hassas veri işareti bulunmadı."


def test_structural_patterns_are_detected() -> None:
    report = classify_sensitivity(
        "TC: 12345678901\n"
        "IBAN: TR330006100519786452100654\n"
        "Kart: 4111 2222 3333 4444\n"
        "E-posta: veli@okul.edu.tr\n"
        "Anahtar: sk-abcdefghijklmnopqrstuvwxyz123456"
    )

    assert report.is_sensitive is True
    assert SensitivityCategory.KIMLIK.value in report.categories
    assert SensitivityCategory.FINANS.value in report.categories
    assert SensitivityCategory.ILETISIM.value in report.categories
    assert SensitivityCategory.KIMLIK_BILGISI.value in report.categories


def test_report_never_leaks_the_matched_value() -> None:
    secret = "sk-abcdefghijklmnopqrstuvwxyz123456"
    report = classify_sensitivity(f"TC 12345678901 ve anahtar {secret}")

    rendered = report.summary()
    assert secret not in rendered
    assert "12345678901" not in rendered
    for finding in report.findings:
        assert secret not in finding.evidence
        assert "12345678901" not in finding.evidence


def test_keyword_rules_match_turkish_suffixes_and_uppercase() -> None:
    for prompt in (
        "Maaş bordromdaki kesintiyi incele",
        "MAAŞ BORDROSU KONTROLÜ",
        "Hastanın tanısını değerlendir",
        "Pasaportumdaki bilgileri kontrol et",
    ):
        assert classify_sensitivity(prompt).is_sensitive is True, prompt


def test_plain_technical_prompt_is_not_flagged() -> None:
    report = classify_sensitivity(
        "Bu C++ fonksiyonunun zaman karmaşıklığını düşür ve testlerini yaz"
    )

    assert report.is_sensitive is False


def test_categories_are_deduplicated_and_ordered() -> None:
    report = classify_sensitivity("IBAN TR330006100519786452100654 ve maaş bordrosu")

    assert report.categories == (SensitivityCategory.FINANS.value,)


def test_normalize_turkish_handles_dotless_and_dotted_i() -> None:
    assert normalize_turkish("KIYASLA") == "kıyasla"
    assert normalize_turkish("MİMARİ") == "mimari"
    assert normalize_turkish("IŞIK") == "ışık"
