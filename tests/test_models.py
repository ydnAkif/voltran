from voltran.models import TaskResult


def test_task_result_has_required_output_contract() -> None:
    result = TaskResult(summary="Tamamlandı", status="success")

    assert result.summary == "Tamamlandı"
    assert result.claims == []
    assert result.evidence == []
    assert result.uncertainties == []
    assert result.risks == []
    assert result.artifacts == []


def test_mutable_defaults_are_not_shared() -> None:
    first = TaskResult(summary="Bir", status="success")
    second = TaskResult(summary="İki", status="success")

    first.claims.append("iddia")

    assert second.claims == []
