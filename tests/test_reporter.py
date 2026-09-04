from voltran.models import (
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
