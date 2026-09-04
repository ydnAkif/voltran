from __future__ import annotations

from pathlib import Path

from voltran.commander import Commander, detect_mode
from voltran.models import ExecutionMode


def test_detect_mode_identifies_council_for_architecture_or_comparison() -> None:
    mode, reasoning = detect_mode(
        "Microservice mimarisini monolith ile karşılaştır ve riskleri listele"
    )
    assert mode == ExecutionMode.COUNCIL
    assert "karşılaştırmalı analiz" in reasoning


def test_detect_mode_identifies_quick_for_simple_tasks() -> None:
    mode, reasoning = detect_mode("Hızlıca bu çıktıyı özetle")
    assert mode == ExecutionMode.QUICK
    assert "özetleme" in reasoning


def test_detect_mode_identifies_visual_for_diagrams() -> None:
    mode, _ = detect_mode("Bu akış için bir mimari diyagram çiz")
    assert mode == ExecutionMode.VISUAL


def test_detect_mode_defaults_to_expert() -> None:
    mode, reasoning = detect_mode(
        "Python asyncio subprocess yönetimi için bellek sızıntısını araştır"
    )
    assert mode == ExecutionMode.EXPERT
    assert "varsayılan uzman modu" in reasoning


def test_detect_mode_respects_explicit_override() -> None:
    mode, reasoning = detect_mode("Hızlıca yap", explicit_mode=ExecutionMode.COUNCIL)
    assert mode == ExecutionMode.COUNCIL
    assert "Kullanıcı tarafından açıkça belirtildi" in reasoning


def test_detect_mode_handles_turkish_suffixes_and_capital_dotted_i() -> None:
    assert detect_mode("Bu modülün mimarisi doğru mu?")[0] is ExecutionMode.COUNCIL
    assert detect_mode("RİSKLERİ ayrıntılı biçimde değerlendir")[0] is ExecutionMode.COUNCIL
    assert detect_mode("KIYASLA")[0] is ExecutionMode.COUNCIL
    assert detect_mode("KARŞILAŞTIR")[0] is ExecutionMode.COUNCIL
    assert detect_mode("TARTIŞ")[0] is ExecutionMode.COUNCIL


def test_commander_creates_plan_with_subtasks(tmp_path: Path) -> None:
    commander = Commander()
    context_file = tmp_path / "code.py"
    context_file.write_text("print('hello')", encoding="utf-8")

    plan = commander.create_plan(
        "İki yaklaşımı karşılaştır",
        mode=ExecutionMode.COUNCIL,
        context_file=context_file,
    )

    assert plan.mode == ExecutionMode.COUNCIL
    assert len(plan.subtasks) == 3
    assert plan.context_file == context_file
    assert [subtask.role for subtask in plan.subtasks] == [
        "Mimari ve risk analisti",
        "Uygulama ve doğrulama uzmanı",
        "Eleştirel sentez uzmanı",
    ]
    assert all(
        provider_name not in subtask.role
        for subtask in plan.subtasks
        for provider_name in ("Claude", "Codex", "Antigravity")
    )


def test_sensitive_task_is_not_auto_expanded_to_council() -> None:
    # Görev konsey anahtar kelimesi içeriyor ("karşılaştır") ama hassas veri var.
    plan = Commander().create_plan(
        "Maaş bordromdaki yatırım kesintilerini karşılaştır ve riskleri listele"
    )

    assert plan.mode is ExecutionMode.EXPERT
    assert "finans" in plan.sensitivity_categories
    assert "konseye genişletilmedi" in plan.reasoning


def test_explicit_council_still_honoured_for_sensitive_task() -> None:
    plan = Commander().create_plan(
        "Maaş bordromu karşılaştır",
        mode=ExecutionMode.COUNCIL,
    )

    assert plan.mode is ExecutionMode.COUNCIL
    assert "finans" in plan.sensitivity_categories


def test_non_sensitive_task_still_reaches_council() -> None:
    plan = Commander().create_plan("Mikroservis mimarisini monolit ile karşılaştır")

    assert plan.mode is ExecutionMode.COUNCIL
    assert plan.sensitivity_categories == []


def test_context_text_participates_in_sensitivity_decision() -> None:
    plan = Commander().create_plan(
        "Bu dosyayı karşılaştır",
        context_text="TC: 12345678901",
    )

    assert plan.mode is ExecutionMode.EXPERT
    assert "kimlik" in plan.sensitivity_categories
