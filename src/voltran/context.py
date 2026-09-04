"""VOLTRAN Bağlam Bütçesi (SEC-04 — veri minimizasyonu).

Bir bağlam dosyasının tamamını sağlayıcıya göndermek, gereksinim belgesinin
"yalnızca gerekli parçayı gönder" ilkesine aykırıdır ve sağlayıcı stdin bütçesini
aşabilir. Bu modül dosyayı okunabilirlik, boyut ve bölüm seçimi süzgeçlerinden
geçirir; gönderilen ve kesilen miktarı ölçülebilir biçimde raporlar.

Kesme her zaman **görünür** yapılır: modele, aradan ne kadar veri çıkarıldığını
söyleyen bir işaret bırakılır. Aksi hâlde model eksik dosyayı tam sanır ve
olmayan satırlar hakkında güvenle yanlış yorum yapar.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

# Sağlayıcıya gönderilecek varsayılan üst sınır. Tipik bir CLI istemi için
# güvenli; `--max-context` ile büyütülüp küçültülebilir.
DEFAULT_MAX_CONTEXT_CHARS = 40_000

# Bu sınırın üstündeki dosyalar hiç okunmaz; kontrollü hata üretilir.
MAX_FILE_BYTES = 5 * 1024 * 1024

# İkili dosya tespiti için okunacak ön ek.
_SNIFF_BYTES = 8192

_TRIM_MARKER = (
    "\n\n[... VOLTRAN veri minimizasyonu: ortadaki {removed} karakter gönderilmedi ...]\n\n"
)


class ContextError(RuntimeError):
    """Bağlam dosyası kullanılamaz; çağıran tarafa kontrollü hata olarak iletilir."""


@dataclass(frozen=True, slots=True)
class ContextScope:
    """Sağlayıcıya fiilen gönderilen bağlamın ölçülebilir kapsamı."""

    text: str
    source_chars: int
    sent_chars: int
    trimmed_chars: int
    selection: str

    @property
    def is_trimmed(self) -> bool:
        return self.trimmed_chars > 0

    def describe(self) -> str:
        """Kullanıcıya ve rapora yazılabilen tek satırlık kapsam özeti."""

        if self.source_chars == 0:
            return "boş dosya"
        oran = round(self.sent_chars / self.source_chars * 100)
        base = f"{self.sent_chars}/{self.source_chars} karakter (%{oran}), {self.selection}"
        if self.is_trimmed:
            return f"{base}; {self.trimmed_chars} karakter gönderilmedi"
        return base


def parse_line_range(value: str) -> tuple[int, int]:
    """`--lines 10-40` biçimini doğrular ve (baslangic, bitis) olarak döndürür."""

    raw = value.strip()
    start_text, separator, end_text = raw.partition("-")
    if not separator:
        start_text = end_text = raw
    try:
        start = int(start_text)
        end = int(end_text)
    except ValueError as exc:
        raise ContextError(
            f"Geçersiz satır aralığı: '{value}'. Beklenen biçim: 10-40 veya 12."
        ) from exc
    if start < 1:
        raise ContextError("Satır numaraları 1'den küçük olamaz.")
    if end < start:
        raise ContextError(f"Satır aralığı ters: {start}-{end}.")
    return start, end


def _read_source(path: Path) -> str:
    if not path.exists():
        raise ContextError(f"Bağlam dosyası bulunamadı: {path}")
    if not path.is_file():
        raise ContextError(f"Bağlam yolu bir dosya değil: {path}")

    try:
        size = path.stat().st_size
    except OSError as exc:
        raise ContextError(f"Bağlam dosyası okunamadı: {type(exc).__name__}") from exc

    if size > MAX_FILE_BYTES:
        limit_mb = MAX_FILE_BYTES // (1024 * 1024)
        raise ContextError(
            f"Bağlam dosyası çok büyük: {size // 1024} KB "
            f"(sınır {limit_mb} MB). Dosyayı bölün veya '--lines' ile bir aralık seçin."
        )

    try:
        head = path.read_bytes()[:_SNIFF_BYTES]
    except OSError as exc:
        raise ContextError(f"Bağlam dosyası okunamadı: {type(exc).__name__}") from exc

    if b"\x00" in head:
        raise ContextError(
            f"Bağlam dosyası ikili (binary) görünüyor: {path.name}. "
            "Yalnızca metin dosyaları bağlam olarak gönderilebilir."
        )

    try:
        return path.read_text(encoding="utf-8", errors="replace")
    except OSError as exc:
        raise ContextError(f"Bağlam dosyası okunamadı: {type(exc).__name__}") from exc


def _select_lines(source: str, line_range: tuple[int, int]) -> tuple[str, str]:
    start, end = line_range
    lines = source.splitlines(keepends=True)
    if start > len(lines):
        raise ContextError(f"Satır aralığı dosya dışında: {start}-{end}, dosya {len(lines)} satır.")
    selected = "".join(lines[start - 1 : end])
    return selected, f"satır {start}-{min(end, len(lines))}"


def _apply_budget(text: str, max_chars: int) -> tuple[str, int]:
    """Bütçeyi aşan metni baş ve son parçayı koruyarak kısaltır.

    Kırpma işareti de bütçeye dâhildir: sonuç hiçbir koşulda `max_chars` değerini
    aşmaz, çünkü bu sınırın amacı sağlayıcı stdin bütçesini korumaktır.
    """

    if len(text) <= max_chars:
        return text, 0

    # İşaretin uzunluğu, kesilecek miktarın basamak sayısına bağlıdır; en kötü
    # durumu (tüm metnin kesilmesi) baz alarak yer ayırıyoruz.
    marker_reserve = len(_TRIM_MARKER.format(removed=len(text)))
    budget = max_chars - marker_reserve
    if budget < 2:
        # Bütçe işarete bile yetmiyor: sessiz kesme yapmak yerine yalnızca baş
        # tarafı gönder ve kesilen miktarı çağırana bildir.
        return text[:max_chars], len(text) - max_chars

    # Baş taraf (içe aktarmalar, tanımlar) ve son taraf (sonuç, çıkış noktaları)
    # bir incelemede genellikle ortadan daha bilgilendiricidir.
    head_budget = budget * 2 // 3
    tail_budget = budget - head_budget
    head = text[:head_budget]
    tail = text[len(text) - tail_budget :]
    removed = len(text) - len(head) - len(tail)
    return f"{head}{_TRIM_MARKER.format(removed=removed)}{tail}", removed


def load_context(
    path: Path,
    *,
    max_chars: int = DEFAULT_MAX_CONTEXT_CHARS,
    line_range: tuple[int, int] | None = None,
) -> ContextScope:
    """Bağlam dosyasını okuyup bütçeye sığdırır ve gönderilen kapsamı raporlar.

    Okunamayan, ikili veya aşırı büyük dosyalarda `ContextError` yükseltir; sessizce
    bozuk bir bağlam göndermez.
    """

    if max_chars < 1:
        raise ContextError("Bağlam bütçesi en az 1 karakter olmalıdır.")

    source = _read_source(path)
    source_chars = len(source)

    if line_range is not None:
        selected, selection = _select_lines(source, line_range)
    else:
        selected, selection = source, "tamamı"

    text, removed = _apply_budget(selected, max_chars)
    if removed:
        selection = f"{selection} (baş+son kırpıldı)"

    return ContextScope(
        text=text,
        source_chars=source_chars,
        sent_chars=len(text),
        trimmed_chars=removed + (source_chars - len(selected) if line_range else 0),
        selection=selection,
    )
