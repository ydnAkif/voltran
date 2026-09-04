"""VOLTRAN Komutan (Commander) bileşeni — Görev analizi ve mod belirleme."""

from __future__ import annotations

import re
from pathlib import Path

from voltran.classifier import SensitivityReport, classify_sensitivity, normalize_turkish
from voltran.models import ExecutionMode, ExecutionPolicy, SubTask, TaskPlan

_COUNCIL_KEYWORDS = (
    r"\b(karşılaştır|kıyasla|mimari|finans|yatırım|risk|güvenlik|denetle|hakem|karar|"
    r"doğrula|tartış|konsensüs|audit|architecture|tradeoff|compare)\w*"
)
_QUICK_KEYWORDS = (
    r"\b(hızlıca|kısaca|özetle|formatla|düzelt|çevir|anlamı ne|nedir|küçük|tek satır|"
    r"quick|summarize|format|typo)\b"
)
_VISUAL_KEYWORDS = r"\b(görsel|resim|çizim|diyagram|mockup|şema|logo|infografik|diagram)\w*"


def detect_mode(
    prompt: str,
    *,
    explicit_mode: ExecutionMode | None = None,
    sensitivity: SensitivityReport | None = None,
) -> tuple[ExecutionMode, str]:
    """Görevin içeriğini inceleyerek uygun modu ve kısa gerekçesini tespit eder.

    SEC-03 gereği hassas veri tespit edilen bir görev, kullanıcı açıkça istemedikçe
    `council` moduna genişletilmez; aksi hâlde aynı veri üç ayrı sağlayıcıya birden
    gönderilmiş olur.
    """

    if explicit_mode is not None:
        return explicit_mode, "Kullanıcı tarafından açıkça belirtildi."

    lower = normalize_turkish(prompt)

    if re.search(_VISUAL_KEYWORDS, lower):
        return (
            ExecutionMode.VISUAL,
            "Görev görsel/şematik üretim veya inceleme içeriyor.",
        )

    if re.search(_COUNCIL_KEYWORDS, lower):
        if sensitivity is not None and sensitivity.is_sensitive:
            return (
                ExecutionMode.EXPERT,
                (
                    "Görev konsey ölçütlerini karşılıyor, ancak hassas veri "
                    f"({', '.join(sensitivity.categories)}) tespit edildiği için "
                    "otomatik olarak konseye genişletilmedi. Gerekiyorsa '-m council' "
                    "ile açıkça isteyin."
                ),
            )
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
        context_text: str | None = None,
    ) -> TaskPlan:
        # SEC-03: hassasiyet, mod seçiminden önce belirlenir; bağlam dosyasının
        # içeriği de görev metniyle birlikte değerlendirilir.
        sensitivity = classify_sensitivity(prompt, context_text)
        chosen_mode, reasoning = detect_mode(prompt, explicit_mode=mode, sensitivity=sensitivity)
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
                        role="Mimari ve risk analisti",
                        purpose="Ortak çözümü analiz, eleştiri ve önerilerle geliştir.",
                    )
                )
                subtasks.append(
                    SubTask(
                        role="Uygulama ve doğrulama uzmanı",
                        purpose="Diğer ortakların görüşlerine yanıt ver ve çözümü ilerlet.",
                    )
                )
                subtasks.append(
                    SubTask(
                        role="Eleştirel sentez uzmanı",
                        purpose="Ortak konuşmayı değerlendir ve uzlaşıya katkı sağla.",
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
            sensitivity_categories=list(sensitivity.categories),
        )
