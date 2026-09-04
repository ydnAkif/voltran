"""VOLTRAN Hassas Veri Sınıflandırıcı (SEC-03).

Görev metnini ve bağlam dosyasını sağlayıcılara gönderilmeden önce inceler; finans,
sağlık, kimlik, iletişim ve kimlik bilgisi içeren içerikleri işaretler.

Bu katman metni **değiştirmez** — maskeleme `sanitizer` modülünün işidir. Burada
üretilen rapor yalnızca bulgunun *türünü* ve *sayısını* taşır, hiçbir zaman eşleşen
değerin kendisini taşımaz; çünkü rapor terminale basılır ve çalışma geçmişine girer.
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass, field
from enum import StrEnum


class SensitivityCategory(StrEnum):
    """REQUIREMENTS.md SEC-03'te sayılan hassas veri sınıfları."""

    FINANS = "finans"
    SAGLIK = "sağlık"
    KIMLIK = "kimlik"
    ILETISIM = "iletişim"
    KIMLIK_BILGISI = "kimlik bilgisi"


def normalize_turkish(text: str) -> str:
    """Türkçe I/İ harflerini casefold öncesinde doğru küçük harfe dönüştür.

    `str.casefold()` tek başına "I" harfini "i" yapar ve "KIYASLA" gibi bir girdi
    "kıyasla" ile eşleşmez; "İ" ise arkasında birleşik nokta bırakır.
    """

    turkish_lower = text.replace("I", "ı").replace("İ", "i")
    return unicodedata.normalize("NFC", turkish_lower.casefold().replace("i̇", "i"))


@dataclass(frozen=True, slots=True)
class SensitivityFinding:
    """Tek bir hassas veri bulgusu. Eşleşen değerin kendisini asla taşımaz."""

    category: SensitivityCategory
    evidence: str
    count: int


@dataclass(frozen=True, slots=True)
class SensitivityReport:
    """Bir görev girdisinin hassasiyet değerlendirmesi."""

    findings: tuple[SensitivityFinding, ...] = field(default_factory=tuple)

    @property
    def is_sensitive(self) -> bool:
        return bool(self.findings)

    @property
    def categories(self) -> tuple[str, ...]:
        seen: list[str] = []
        for finding in self.findings:
            if finding.category.value not in seen:
                seen.append(finding.category.value)
        return tuple(seen)

    def summary(self) -> str:
        """Kullanıcıya gösterilebilen tek satırlık, değer içermeyen özet."""

        if not self.findings:
            return "Hassas veri işareti bulunmadı."
        parts = [f"{finding.evidence} ×{finding.count}" for finding in self.findings]
        return ", ".join(parts)


# Yapısal desenler: yüksek kesinlik. Bunlar metnin ham hâlinde aranır.
_STRUCTURAL_RULES: tuple[tuple[SensitivityCategory, str, re.Pattern[str]], ...] = (
    (
        SensitivityCategory.KIMLIK,
        "T.C. kimlik numarası deseni",
        re.compile(r"\b[1-9]\d{10}\b"),
    ),
    (
        SensitivityCategory.FINANS,
        "IBAN deseni",
        re.compile(r"\b[A-Z]{2}\d{2}[A-Z0-9]{12,30}\b"),
    ),
    (
        SensitivityCategory.FINANS,
        "kart numarası deseni",
        re.compile(r"\b(?:\d{4}[ -]?){3}\d{4}\b"),
    ),
    (
        SensitivityCategory.ILETISIM,
        "e-posta adresi",
        re.compile(r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b"),
    ),
    (
        SensitivityCategory.ILETISIM,
        "telefon numarası deseni",
        re.compile(r"(?:\+90|0)?\s*[5]\d{2}[\s.-]?\d{3}[\s.-]?\d{2}[\s.-]?\d{2}\b"),
    ),
    (
        SensitivityCategory.KIMLIK_BILGISI,
        "API anahtarı veya erişim belirteci",
        re.compile(
            r"(?i)\b(?:sk-[A-Za-z0-9_-]{20,}|gh[pousr]_[A-Za-z0-9]{36,}"
            r"|bearer\s+[A-Za-z0-9_.-]{20,})\b"
        ),
    ),
    (
        SensitivityCategory.KIMLIK_BILGISI,
        "parola veya gizli anahtar ataması",
        re.compile(
            r"(?i)[A-Za-z0-9_]*(?:api[_-]?key|secret|token|password|passwd|pwd)"
            r"\s*[:=]\s*['\"]?(?=[^\s'\"]*\d)[A-Za-z0-9_\-./+=]{12,}"
        ),
    ),
)

# Alan sözcükleri: orta kesinlik. Türkçe ekleri yakalamak için sonda `\w*` kullanılır
# ve metin normalize_turkish() ile küçültülmüş hâlde aranır.
_KEYWORD_RULES: tuple[tuple[SensitivityCategory, str, re.Pattern[str]], ...] = (
    (
        SensitivityCategory.FINANS,
        "finansal içerik sözcüğü",
        re.compile(
            r"\b(maaş|bordro|fatura|iban|hesap numarası|kredi kartı|yatırım|portföy"
            r"|vergi|bütçe|banka|ödeme|borç|salary|payroll|invoice|bank account)\w*"
        ),
    ),
    (
        SensitivityCategory.SAGLIK,
        "sağlık içeriği sözcüğü",
        re.compile(
            r"\b(hasta|tanı|teşhis|reçete|tahlil|ameliyat|epikriz|hastalık"
            r"|patient|diagnosis|prescription|medical record)\w*"
        ),
    ),
    (
        SensitivityCategory.KIMLIK,
        "kimlik içeriği sözcüğü",
        re.compile(
            r"\b(tc kimlik|t\.c\. kimlik|kimlik numarası|pasaport|ehliyet|nüfus cüzdanı"
            r"|passport|national id)\w*"
        ),
    ),
)


def classify_sensitivity(*texts: str | None) -> SensitivityReport:
    """Verilen metinleri birleştirip hassas veri sınıflarını tespit eder."""

    combined = "\n".join(text for text in texts if text)
    if not combined.strip():
        return SensitivityReport()

    normalized = normalize_turkish(combined)
    findings: list[SensitivityFinding] = []

    for category, evidence, pattern in _STRUCTURAL_RULES:
        count = len(pattern.findall(combined))
        if count:
            findings.append(SensitivityFinding(category=category, evidence=evidence, count=count))

    for category, evidence, pattern in _KEYWORD_RULES:
        count = len(pattern.findall(normalized))
        if count:
            findings.append(SensitivityFinding(category=category, evidence=evidence, count=count))

    return SensitivityReport(findings=tuple(findings))
