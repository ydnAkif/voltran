"""VOLTRAN Katmanlı Yapılandırma (FR-13).

Ayarlar dört katmandan, şu öncelikle birleştirilir:

1. Komut satırı seçeneği
2. Proje yapılandırması — çalışma dizininden yukarı doğru aranan `voltran.toml`
3. Kullanıcı yapılandırması — `$VOLTRAN_CONFIG_DIR` veya `$XDG_CONFIG_HOME/voltran`
4. Güvenli varsayılanlar

Proje dosyası bilinçli olarak `voltran.toml` adını taşır ve depo kökünde durur;
`.voltran/` dizini `.gitignore` içinde olduğu için oraya konan bir yapılandırma
ekiple paylaşılamazdı.

Bilinmeyen anahtar veya yanlış tür sessizce yok sayılmaz: yapılandırmasında yazım
hatası olan bir kullanıcı, ayarın uygulandığını sanır. Bu yüzden her ikisi de
`ConfigError` üretir.

Yazma izni (`--write`) bilinçli olarak yapılandırılabilir değildir. Dosya
değiştirme yetkisi her çalıştırmada açıkça verilmesi gereken bir karardır;
bir yapılandırma dosyasından sessizce açılabilseydi "güvenli varsayılan"
ilkesi anlamını yitirirdi.
"""

from __future__ import annotations

import os
import tomllib
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, cast

PROJECT_CONFIG_NAME = "voltran.toml"
USER_CONFIG_NAME = "config.toml"

DEFAULT_TIMEOUT_SECONDS = 300.0
DEFAULT_MAX_CONTEXT_CHARS = 40_000

# Anahtar -> beklenen tür. Listede olmayan her anahtar hata üretir.
_SCHEMA: dict[str, str] = {
    "mode": "str",
    "timeout": "float",
    "providers": "list[str]",
    "max_context": "int",
    "blind": "bool",
}

_LAYER_DEFAULT = "varsayılan"
_LAYER_CLI = "komut satırı"


class ConfigError(RuntimeError):
    """Yapılandırma okunamadı veya geçersiz; kullanıcıya kontrollü hata olarak iletilir."""


@dataclass(frozen=True, slots=True)
class VoltranConfig:
    """Katmanlar birleştirildikten sonra yürürlükteki ayarlar."""

    mode: str | None = None
    timeout: float = DEFAULT_TIMEOUT_SECONDS
    providers: tuple[str, ...] = ()
    max_context: int = DEFAULT_MAX_CONTEXT_CHARS
    blind: bool = False
    # Her ayarın hangi katmandan geldiği — denetlenebilirlik için.
    provenance: dict[str, str] = field(default_factory=lambda: dict[str, str]())
    # Okunan yapılandırma dosyaları, öncelik sırasına göre.
    sources: tuple[Path, ...] = ()

    def source_of(self, key: str) -> str:
        return self.provenance.get(key, _LAYER_DEFAULT)


def user_config_path() -> Path:
    """Kullanıcı yapılandırma dosyasının beklendiği yol."""

    explicit = os.environ.get("VOLTRAN_CONFIG_DIR")
    if explicit:
        return Path(explicit) / USER_CONFIG_NAME
    # `doctor.py` ile aynı yolu kullan; iki bileşen farklı dizine bakmasın.
    root = Path(os.environ.get("XDG_CONFIG_HOME", Path.home() / ".config"))
    return root / "voltran" / USER_CONFIG_NAME


def find_project_config(start_dir: Path | None = None) -> Path | None:
    """Çalışma dizininden köke doğru `voltran.toml` arar."""

    current = (start_dir or Path.cwd()).resolve()
    for candidate_dir in (current, *current.parents):
        candidate = candidate_dir / PROJECT_CONFIG_NAME
        if candidate.is_file():
            return candidate
    return None


def _read_toml(path: Path) -> dict[str, Any]:
    try:
        with path.open("rb") as stream:
            data = tomllib.load(stream)
    except tomllib.TOMLDecodeError as exc:
        raise ConfigError(f"Yapılandırma dosyası okunamadı ({path}): {exc}") from exc
    except OSError as exc:
        raise ConfigError(f"Yapılandırma dosyası açılamadı ({path}): {type(exc).__name__}") from exc

    # tomllib her zaman bir tablo döndürür ve TOML anahtarları metindir.
    payload: dict[str, Any] = dict(data)
    unknown = sorted(key for key in payload if key not in _SCHEMA)
    if unknown:
        raise ConfigError(
            f"Bilinmeyen yapılandırma anahtarı ({path}): {', '.join(unknown)}. "
            f"Geçerli anahtarlar: {', '.join(sorted(_SCHEMA))}."
        )
    return payload


def _coerce(key: str, raw: Any, path: Path) -> Any:
    expected = _SCHEMA[key]
    if expected == "str":
        if not isinstance(raw, str):
            raise ConfigError(f"'{key}' bir metin olmalıdır ({path}).")
        return raw
    if expected == "bool":
        if not isinstance(raw, bool):
            raise ConfigError(f"'{key}' true veya false olmalıdır ({path}).")
        return raw
    if expected == "int":
        # bool, int'in alt sınıfıdır; sessizce 1/0'a dönüşmesin.
        if isinstance(raw, bool) or not isinstance(raw, int):
            raise ConfigError(f"'{key}' bir tam sayı olmalıdır ({path}).")
        return raw
    if expected == "float":
        if isinstance(raw, bool) or not isinstance(raw, int | float):
            raise ConfigError(f"'{key}' bir sayı olmalıdır ({path}).")
        return float(raw)
    if expected == "list[str]":
        if not isinstance(raw, list):
            raise ConfigError(f"'{key}' bir metin listesi olmalıdır ({path}).")
        items = cast(list[Any], raw)
        if not all(isinstance(item, str) for item in items):
            raise ConfigError(f"'{key}' yalnızca metin öğeleri içerebilir ({path}).")
        return tuple(str(item) for item in items)
    raise ConfigError(f"'{key}' için tür tanımı eksik.")  # pragma: no cover - şema hatası


def load_config(
    *,
    cli: dict[str, Any] | None = None,
    start_dir: Path | None = None,
    user_config: Path | None = None,
) -> VoltranConfig:
    """Dört katmanı öncelik sırasına göre birleştirir.

    `cli` sözlüğünde yalnızca kullanıcının gerçekten verdiği seçenekler bulunmalıdır;
    `None` değerler "verilmedi" sayılır ve alt katmanların değeri korunur.
    """

    merged: dict[str, Any] = {}
    provenance: dict[str, str] = {}
    sources: list[Path] = []

    # 4 -> 2 sırayla oku; sonra okunan üstteki katman öncekini ezer.
    user_path = user_config if user_config is not None else user_config_path()
    project_path = find_project_config(start_dir)

    for path, label in ((user_path, "kullanıcı"), (project_path, "proje")):
        if path is None or not path.is_file():
            continue
        sources.append(path)
        for key, raw in _read_toml(path).items():
            merged[key] = _coerce(key, raw, path)
            # Katman başına tek dosya okunur; okunan yollar `sources` içinde
            # ayrıca listelenir, bu yüzden köken etiketi kısa tutulur.
            provenance[key] = label

    # 1. katman: komut satırı, her şeyi ezer.
    for key, value in (cli or {}).items():
        if value is None:
            continue
        if key not in _SCHEMA:
            raise ConfigError(f"Bilinmeyen komut satırı ayarı: {key}.")
        merged[key] = tuple(value) if key == "providers" else value
        provenance[key] = _LAYER_CLI

    defaults = VoltranConfig()
    return VoltranConfig(
        mode=merged.get("mode", defaults.mode),
        timeout=merged.get("timeout", defaults.timeout),
        providers=tuple(merged.get("providers", defaults.providers)),
        max_context=merged.get("max_context", defaults.max_context),
        blind=merged.get("blind", defaults.blind),
        provenance=provenance,
        sources=tuple(reversed(sources)),
    )
