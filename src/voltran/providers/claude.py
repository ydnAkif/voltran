"""Claude Code CLI sağlayıcı adaptörü."""

from __future__ import annotations

from collections.abc import Sequence

from voltran.models import ExecutionPolicy, ProviderCapabilities, ProviderTask
from voltran.providers.cli import CliProviderAdapter


class ClaudeAdapter(CliProviderAdapter):
    key = "claude"
    display_name = "Claude"
    executable = "claude"

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
        permission_mode = "acceptEdits" if policy.allow_writes else "plan"
        command = [
            executable,
            "--print",
            "--output-format",
            "text",
            "--no-session-persistence",
            "--permission-mode",
            permission_mode,
        ]
        if policy.allowed_tools:
            command.extend(("--allowed-tools", ",".join(policy.allowed_tools)))
        else:
            command.extend(("--tools", ""))
        if task.model:
            command.extend(("--model", task.model))
        return command
