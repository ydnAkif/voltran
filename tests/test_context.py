from __future__ import annotations

from pathlib import Path

import pytest

from voltran.context import (
    MAX_FILE_BYTES,
    ContextError,
    load_context,
    parse_line_range,
)


def test_small_file_is_sent_whole(tmp_path: Path) -> None:
    target = tmp_path / "app.py"
    target.write_text("print('merhaba')\n", encoding="utf-8")

    scope = load_context(target)

    assert scope.text == "print('merhaba')\n"
    assert scope.is_trimmed is False
    assert scope.trimmed_chars == 0
    assert scope.selection == "tamamı"
    assert "17/17 karakter" in scope.describe()


def test_large_file_never_exceeds_the_budget(tmp_path: Path) -> None:
    target = tmp_path / "buyuk.txt"
    target.write_text("A" * 10_000, encoding="utf-8")

    for budget in (100, 500, 1_000, 4_096):
        scope = load_context(target, max_chars=budget)
        assert len(scope.text) <= budget, budget
        assert scope.sent_chars == len(scope.text)
        assert scope.is_trimmed is True


def test_trim_keeps_head_and_tail_and_marks_the_gap(tmp_path: Path) -> None:
    target = tmp_path / "kod.c"
    target.write_text("BAS" + ("x" * 5_000) + "SON", encoding="utf-8")

    scope = load_context(target, max_chars=1_000)

    assert scope.text.startswith("BAS")
    assert scope.text.endswith("SON")
    assert "gönderilmedi" in scope.text
    assert scope.trimmed_chars > 0


def test_line_range_selects_only_the_requested_section(tmp_path: Path) -> None:
    target = tmp_path / "uzun.py"
    target.write_text("\n".join(f"satir-{index}" for index in range(1, 101)), encoding="utf-8")

    scope = load_context(target, line_range=(10, 12))

    assert "satir-10" in scope.text
    assert "satir-12" in scope.text
    assert "satir-13" not in scope.text
    assert "satir-9\n" not in scope.text
    assert scope.selection == "satır 10-12"
    # Aralık dışında kalan her şey "gönderilmedi" sayılır.
    assert scope.trimmed_chars == scope.source_chars - scope.sent_chars


def test_line_range_beyond_end_of_file_is_clamped(tmp_path: Path) -> None:
    target = tmp_path / "kisa.py"
    target.write_text("bir\niki\nuc\n", encoding="utf-8")

    scope = load_context(target, line_range=(2, 999))

    assert scope.text == "iki\nuc\n"
    assert scope.selection == "satır 2-3"


def test_binary_file_raises_controlled_error(tmp_path: Path) -> None:
    target = tmp_path / "resim.png"
    target.write_bytes(b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR")

    with pytest.raises(ContextError, match="ikili"):
        load_context(target)


def test_oversized_file_is_rejected_without_reading(tmp_path: Path) -> None:
    target = tmp_path / "dev.log"
    target.write_bytes(b"A" * (MAX_FILE_BYTES + 1))

    with pytest.raises(ContextError, match="çok büyük"):
        load_context(target)


def test_missing_and_directory_paths_raise_controlled_errors(tmp_path: Path) -> None:
    with pytest.raises(ContextError, match="bulunamadı"):
        load_context(tmp_path / "yok.py")

    with pytest.raises(ContextError, match="dosya değil"):
        load_context(tmp_path)


def test_line_range_outside_file_raises(tmp_path: Path) -> None:
    target = tmp_path / "kisa.py"
    target.write_text("bir\niki\n", encoding="utf-8")

    with pytest.raises(ContextError, match="dosya dışında"):
        load_context(target, line_range=(50, 60))


@pytest.mark.parametrize(
    ("value", "expected"),
    [("10-40", (10, 40)), (" 5 - 5 ", (5, 5)), ("12", (12, 12))],
)
def test_parse_line_range_accepts_valid_forms(value: str, expected: tuple[int, int]) -> None:
    assert parse_line_range(value) == expected


@pytest.mark.parametrize("value", ["abc", "0-10", "40-10", "-", "3-x"])
def test_parse_line_range_rejects_invalid_forms(value: str) -> None:
    with pytest.raises(ContextError):
        parse_line_range(value)
