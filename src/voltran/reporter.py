"""VOLTRAN Raporlama (Reporter) bileşeni — Tek sonuç raporu üretimi."""

from __future__ import annotations

import json

from voltran.models import ExecutionReport


class Reporter:
    """Yürütme sonuçlarını tek, denetlenebilir ve zengin bir rapora dönüştürür."""

    @staticmethod
    def to_markdown(report: ExecutionReport) -> str:
        lines: list[str] = [
            f"# VOLTRAN Görev Raporu: `{report.mode.value.upper()}`",
            "",
            f"**Çalışma ID:** `{report.run_id}`  ",
            f"**Tarih:** {report.created_at.strftime('%Y-%m-%d %H:%M:%S UTC')}  ",
            f"**Toplam Süre:** {report.total_duration_ms} ms  ",
            "",
            "## 🎯 Sonuç Özeti",
            "",
            report.final_summary.strip(),
            "",
        ]

        if report.synthesis is not None:
            lines.extend(
                [
                    "## ⚖️ Konsey Sentezi ve Güven Analizi",
                    "",
                    f"- **Güven Düzeyi:** %{int(report.synthesis.confidence_score * 100)}",
                ]
            )
            if report.synthesis.confidence_rationale:
                lines.append(f"- **Gerekçe:** {report.synthesis.confidence_rationale}")
            if report.synthesis.consensus:
                lines.append("\n### 🤝 Uzlaşılan Noktalar")
                for item in report.synthesis.consensus:
                    lines.append(f"- {item}")
            if report.synthesis.disagreements:
                lines.append("\n### ⚡ Farklılıklar ve Çelişkiler")
                for item in report.synthesis.disagreements:
                    lines.append(f"- {item}")
            lines.append("")

        lines.extend(
            [
                "## 👥 Görev Dağılımı ve Modeller",
                "",
                "| Rol | Sağlayıcı | Durum | Süre (ms) |",
                "| --- | --- | --- | --- |",
            ]
        )

        for exec_res in report.executions:
            status_emoji = "✅" if exec_res.status == "success" else "❌"
            p_name = exec_res.provider.capitalize()
            p_key = exec_res.provider
            row = (
                f"| {p_name} | `{p_key}` | {status_emoji} {exec_res.status} | "
                f"{exec_res.duration_ms} |"
            )
            lines.append(row)

        lines.append("")

        if report.next_step_recommendation:
            lines.extend(
                [
                    "## 💡 Önerilen Güvenli Sonraki Adım",
                    "",
                    report.next_step_recommendation,
                    "",
                ]
            )

        link = "[VOLTRAN](https://github.com/ydnAkif/voltran)"
        lines.extend(
            [
                "---",
                f"*{link} yerel orkestrasyon tarafından üretilmiştir.*",
            ]
        )
        return "\n".join(lines)

    @staticmethod
    def to_json(report: ExecutionReport) -> str:
        return json.dumps(report.model_dump(mode="json"), ensure_ascii=False, indent=2)
