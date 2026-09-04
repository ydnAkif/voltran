from __future__ import annotations

from pathlib import Path

import pytest

from voltran.config import (
    DEFAULT_MAX_CONTEXT_CHARS,
    DEFAULT_TIMEOUT_SECONDS,
    ConfigError,
    VoltranConfig,
    find_project_config,
    load_config,
    user_config_path,
)


def _missing(tmp_path: Path) -> Path:
    return tmp_path / "yok" / "config.toml"


def test_defaults_apply_when_no_file_exists(tmp_path: Path) -> None:
    settings = load_config(start_dir=tmp_path, user_config=_missing(tmp_path))

    assert settings.mode is None
    assert settings.timeout == DEFAULT_TIMEOUT_SECONDS
    assert settings.providers == ()
    assert settings.max_context == DEFAULT_MAX_CONTEXT_CHARS
    assert settings.blind is False
    assert settings.sources == ()
    assert settings.source_of("timeout") == "varsayılan"


def test_user_config_is_applied(tmp_path: Path) -> None:
    user = tmp_path / "user.toml"
    user.write_text('mode = "quick"\ntimeout = 45\n', encoding="utf-8")

    settings = load_config(start_dir=tmp_path, user_config=user)

    assert settings.mode == "quick"
    assert settings.timeout == 45.0
    assert settings.source_of("mode") == "kullanıcı"
    assert settings.sources == (user,)


def test_project_config_overrides_user_config(tmp_path: Path) -> None:
    user = tmp_path / "user.toml"
    user.write_text('mode = "quick"\ntimeout = 45\nblind = true\n', encoding="utf-8")
    project = tmp_path / "voltran.toml"
    project.write_text('mode = "expert"\n', encoding="utf-8")

    settings = load_config(start_dir=tmp_path, user_config=user)

    assert settings.mode == "expert"
    assert settings.source_of("mode") == "proje"
    # Proje dosyasının belirtmediği ayarlar kullanıcı katmanından gelir.
    assert settings.timeout == 45.0
    assert settings.source_of("timeout") == "kullanıcı"
    assert settings.blind is True
    # Öncelik sırası: proje önce listelenir.
    assert settings.sources == (project, user)


def test_command_line_overrides_every_layer(tmp_path: Path) -> None:
    user = tmp_path / "user.toml"
    user.write_text("timeout = 45\n", encoding="utf-8")
    (tmp_path / "voltran.toml").write_text('mode = "expert"\ntimeout = 90\n', encoding="utf-8")

    settings = load_config(
        cli={"timeout": 5.0, "providers": ["codex"]},
        start_dir=tmp_path,
        user_config=user,
    )

    assert settings.timeout == 5.0
    assert settings.source_of("timeout") == "komut satırı"
    assert settings.providers == ("codex",)
    assert settings.source_of("providers") == "komut satırı"
    # Komut satırında verilmeyen ayar alt katmandan gelmeye devam eder.
    assert settings.mode == "expert"
    assert settings.source_of("mode") == "proje"


def test_none_valued_cli_options_do_not_override(tmp_path: Path) -> None:
    (tmp_path / "voltran.toml").write_text("timeout = 90\n", encoding="utf-8")

    settings = load_config(
        cli={"timeout": None, "mode": None, "blind": None},
        start_dir=tmp_path,
        user_config=_missing(tmp_path),
    )

    assert settings.timeout == 90.0
    assert settings.source_of("timeout") == "proje"


def test_project_config_is_discovered_from_a_subdirectory(tmp_path: Path) -> None:
    (tmp_path / "voltran.toml").write_text('mode = "council"\n', encoding="utf-8")
    nested = tmp_path / "src" / "derin"
    nested.mkdir(parents=True)

    assert find_project_config(nested) == tmp_path / "voltran.toml"
    settings = load_config(start_dir=nested, user_config=_missing(tmp_path))
    assert settings.mode == "council"


def test_unknown_key_is_rejected(tmp_path: Path) -> None:
    (tmp_path / "voltran.toml").write_text('modee = "expert"\n', encoding="utf-8")

    with pytest.raises(ConfigError, match="Bilinmeyen yapılandırma anahtarı"):
        load_config(start_dir=tmp_path, user_config=_missing(tmp_path))


def test_invalid_toml_is_rejected(tmp_path: Path) -> None:
    (tmp_path / "voltran.toml").write_text("mode = [bozuk\n", encoding="utf-8")

    with pytest.raises(ConfigError, match="okunamadı"):
        load_config(start_dir=tmp_path, user_config=_missing(tmp_path))


@pytest.mark.parametrize(
    ("body", "message"),
    [
        ("mode = 3\n", "metin olmalıdır"),
        ("timeout = true\n", "sayı olmalıdır"),
        ("max_context = 1.5\n", "tam sayı olmalıdır"),
        ("max_context = true\n", "tam sayı olmalıdır"),
        ('blind = "evet"\n', "true veya false"),
        ('providers = "codex"\n', "metin listesi"),
        ("providers = [1, 2]\n", "yalnızca metin"),
    ],
)
def test_wrong_types_are_rejected(tmp_path: Path, body: str, message: str) -> None:
    (tmp_path / "voltran.toml").write_text(body, encoding="utf-8")

    with pytest.raises(ConfigError, match=message):
        load_config(start_dir=tmp_path, user_config=_missing(tmp_path))


def test_unknown_cli_setting_is_rejected(tmp_path: Path) -> None:
    with pytest.raises(ConfigError, match="Bilinmeyen komut satırı ayarı"):
        load_config(cli={"allow_writes": True}, start_dir=tmp_path, user_config=_missing(tmp_path))


def test_write_permission_is_not_configurable(tmp_path: Path) -> None:
    """SEC güvencesi: --write bir yapılandırma dosyasından açılamamalıdır."""
    (tmp_path / "voltran.toml").write_text("allow_writes = true\n", encoding="utf-8")

    with pytest.raises(ConfigError, match="Bilinmeyen yapılandırma anahtarı"):
        load_config(start_dir=tmp_path, user_config=_missing(tmp_path))

    assert not hasattr(VoltranConfig(), "allow_writes")


def test_user_config_path_follows_the_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("VOLTRAN_CONFIG_DIR", "/tmp/voltran-cfg")
    assert user_config_path() == Path("/tmp/voltran-cfg/config.toml")

    monkeypatch.delenv("VOLTRAN_CONFIG_DIR")
    monkeypatch.setenv("XDG_CONFIG_HOME", "/tmp/xdg")
    assert user_config_path() == Path("/tmp/xdg/voltran/config.toml")
