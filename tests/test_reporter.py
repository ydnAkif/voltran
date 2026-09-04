import json

from voltran.models import (
    CouncilSynthesis,
    ExecutionMode,
    ExecutionReport,
    ExecutionStatus,
    ProviderExecution,
    TaskPlan,
    TaskResult,
)
from voltran.reporter import Reporter


def test_markdown_table_renders_role_metadata() -> None:
    report = ExecutionReport(
        task_prompt="test",
        mode=ExecutionMode.EXPERT,
        plan=TaskPlan(mode=ExecutionMode.EXPERT, reasoning="test"),
        executions=[
            ProviderExecution(
                run_id="run",
                provider="codex",
                status=ExecutionStatus.SUCCESS,
                duration_ms=5,
                result=TaskResult(
                    summary="done",
                    status="success",
                    metadata={"role": "Güvenlik denetçisi"},
                ),
            )
        ],
        final_summary="done",
    )

    markdown = Reporter.to_markdown(report)

    assert "| Güvenlik denetçisi | `codex` |" in markdown
    assert "| Codex | `codex` |" not in markdown


def test_markdown_renders_council_synthesis_and_provider_errors() -> None:
    report = ExecutionReport(
        task_prompt="mimariyi karşılaştır",
        mode=ExecutionMode.COUNCIL,
        plan=TaskPlan(mode=ExecutionMode.COUNCIL, reasoning="test"),
        executions=[
            ProviderExecution(
                run_id="ok",
                provider="claude",
                status=ExecutionStatus.SUCCESS,
                duration_ms=12,
                result=TaskResult(
                    summary="öneri", status="success", metadata={"role": "Mimari analist"}
                ),
            ),
            ProviderExecution(
                run_id="hata",
                provider="google",
                status=ExecutionStatus.FAILED,
                duration_ms=3,
                error="Ajan geçerli çıktı üretmedi.",
            ),
        ],
        final_summary="ortak sonuç",
        synthesis=CouncilSynthesis(
            consensus=["Katmanlı mimari tercih edildi."],
            disagreements=["Veritabanı seçimi çözülemedi."],
            confidence_score=0.75,
            confidence_rationale="İki ajan izlendi.",
        ),
        next_step_recommendation="Kararı doğrulayın.",
    )

    markdown = Reporter.to_markdown(report)

    assert "%75" in markdown
    assert "İki ajan izlendi." in markdown
    assert "Katmanlı mimari tercih edildi." in markdown
    assert "Veritabanı seçimi çözülemedi." in markdown
    assert "Sağlayıcı Hataları" in markdown
    assert "Ajan geçerli çıktı üretmedi." in markdown
    assert "Kararı doğrulayın." in markdown


def test_json_round_trip_preserves_plan_and_sensitivity() -> None:
    report = ExecutionReport(
        task_prompt="bordroyu incele",
        mode=ExecutionMode.EXPERT,
        plan=TaskPlan(
            mode=ExecutionMode.EXPERT,
            reasoning="test",
            sensitivity_categories=["finans", "kimlik"],
        ),
        final_summary="özet",
    )

    payload = json.loads(Reporter.to_json(report))

    assert payload["plan"]["sensitivity_categories"] == ["finans", "kimlik"]
    assert payload["mode"] == "expert"
