"""Codex CLI sağlayıcı adaptörü."""

from __future__ import annotations

from collections.abc import Sequence

from voltran.models import ExecutionPolicy, ProviderCapabilities, ProviderTask
from voltran.providers.cli import CliProviderAdapter


class CodexAdapter(CliProviderAdapter):
    key = "codex"
    display_name = "Codex"
    executable = "codex"

    def capabilities(self) -> ProviderCapabilities:
        return ProviderCapabilities(
            file_access=True,
            images=True,
            tool_use=True,
            structured_output=True,
        )

    def _build_command(
        self,
        executable: str,
        task: ProviderTask,
        policy: ExecutionPolicy,
    ) -> Sequence[str]:
        sandbox = "workspace-write" if policy.allow_writes else "read-only"
        command = [
            executable,
            "exec",
            "--color",
            "never",
            "--ephemeral",
            "--sandbox",
            sandbox,
            "--skip-git-repo-check",
            "--cd",
            str(task.working_directory),
        ]
        if task.model:
            command.extend(("--model", task.model))
        command.append("-")
        return command
