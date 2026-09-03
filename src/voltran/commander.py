"""VOLTRAN Komutan (Commander) bileşeni — Görev analizi ve mod belirleme."""

from __future__ import annotations

import re
from pathlib import Path

from voltran.models import ExecutionMode, ExecutionPolicy, SubTask, TaskPlan

_COUNCIL_KEYWORDS = (
    r"\b(karşılaştır|kıyasla|mimari|finans|yatırım|risk|güvenlik|denetle|hakem|karar|"
    r"doğrula|tartış|konsensüs|audit|architecture|tradeoff|compare)\b"
)
_QUICK_KEYWORDS = (
    r"\b(hızlıca|kısaca|özetle|formatla|düzelt|çevir|anlamı ne|nedir|küçük|tek satır|"
    r"quick|summarize|format|typo)\b"
)
_VISUAL_KEYWORDS = r"\b(görsel|resim|çizim|diyagram|mockup|şema|logo|infografik|diagram)\b"


def detect_mode(
    prompt: str,
    *,
    explicit_mode: ExecutionMode | None = None,
) -> tuple[ExecutionMode, str]:
    """Görevin içeriğini inceleyerek uygun modu ve kısa gerekçesini tespit eder."""

    if explicit_mode is not None:
        return explicit_mode, "Kullanıcı tarafından açıkça belirtildi."

    lower = prompt.lower()

    if re.search(_VISUAL_KEYWORDS, lower):
        return (
            ExecutionMode.VISUAL,
            "Görev görsel/şematik üretim veya inceleme içeriyor.",
        )

    if re.search(_COUNCIL_KEYWORDS, lower):
        return (
            ExecutionMode.COUNCIL,
            "Yüksek doğruluk, mimari karar, risk veya karşılaştırmalı analiz gerektiriyor.",
        )

    if re.search(_QUICK_KEYWORDS, lower) and len(prompt.split()) < 30:
        return (
            ExecutionMode.QUICK,
            "Rutin özetleme, küçük biçimlendirme veya hızlı yanıt için uygun.",
        )

    return (
        ExecutionMode.EXPERT,
        "Teknik analiz, kodlama veya derinlemesine teşhis için varsayılan uzman modu.",
    )


class Commander:
    """Görev sınıflandırmasını yapar ve alt görev planının iskeletini oluşturur."""

    def create_plan(
        self,
        prompt: str,
        *,
        mode: ExecutionMode | None = None,
        context_file: Path | None = None,
        policy: ExecutionPolicy | None = None,
    ) -> TaskPlan:
        chosen_mode, reasoning = detect_mode(prompt, explicit_mode=mode)
        active_policy = policy or ExecutionPolicy()

        subtasks: list[SubTask] = []
        match chosen_mode:
            case ExecutionMode.QUICK:
                subtasks.append(
                    SubTask(
                        role="hızlı_işçi",
                        purpose="Görevi en hızlı ve doğrudan şekilde tamamla.",
                    )
                )
            case ExecutionMode.EXPERT:
                subtasks.append(
                    SubTask(
                        role="uzman_işçi",
                        purpose="Görevi teknik derinlikle incele ve çözüm üret.",
                    )
                )
            case ExecutionMode.COUNCIL:
                subtasks.append(
                    SubTask(
                        role="birinci_uzman",
                        purpose="Görevi bağımsız bir yaklaşımla analiz et.",
                    )
                )
                subtasks.append(
                    SubTask(
                        role="ikinci_uzman",
                        purpose="Görevi alternatif bir yaklaşımla bağımsız olarak analiz et.",
                    )
                )
            case ExecutionMode.VISUAL:
                subtasks.append(
                    SubTask(
                        role="görsel_uzman",
                        purpose="Görsel veya şematik analizi/üretimi gerçekleştir.",
                    )
                )

        return TaskPlan(
            mode=chosen_mode,
            reasoning=reasoning,
            subtasks=subtasks,
            context_file=context_file,
            policy=active_policy,
        )
