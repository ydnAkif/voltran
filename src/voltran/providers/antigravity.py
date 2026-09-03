"""Google Antigravity CLI sağlayıcı adaptörü."""

from __future__ import annotations

from collections.abc import Sequence

from voltran.models import ExecutionPolicy, ProviderCapabilities, ProviderTask
from voltran.providers.cli import CliProviderAdapter


class AntigravityAdapter(CliProviderAdapter):
    key = "google"
    display_name = "Google Antigravity"
    executable = "agy"

    def capabilities(self) -> ProviderCapabilities:
        return ProviderCapabilities(
            file_access=True,
            images=False,
            tool_use=True,
            structured_output=True,
        )

    def _build_command(
        self,
        executable: str,
        task: ProviderTask,
        policy: ExecutionPolicy,
    ) -> Sequence[str]:
        mode = "accept-edits" if policy.allow_writes else "plan"
        command = [
            executable,
            "--output-format",
            "text",
            "--mode",
            mode,
            "--sandbox",
            "--disable-slash-commands",
            "--print-timeout",
            f"{policy.timeout_seconds:g}s",
        ]
        if task.model:
            command.extend(("--model", task.model))
        command.extend(("--print", "-"))
        return command
