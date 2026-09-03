"""Google Antigravity CLI sağlayıcı adaptörü."""

from __future__ import annotations

import json
from collections.abc import Sequence
from typing import cast

from voltran.models import ExecutionPolicy, ProviderCapabilities, ProviderTask, TaskResult
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
            "--input-format",
            "stream-json",
            "--output-format",
            "stream-json",
            "--new-project",
            "--mode",
            mode,
            "--sandbox",
            "--disable-slash-commands",
            "--print-timeout",
            f"{policy.timeout_seconds:g}s",
        ]
        if task.model:
            command.extend(("--model", task.model))
        return command

    def _encode_input(self, prompt: str) -> bytes:
        payload = {"event": "user", "message": {"content": prompt}}
        return (json.dumps(payload, ensure_ascii=False) + "\n").encode()

    def normalize_result(self, raw_output: str) -> TaskResult:
        """Antigravity stream-json sonucundaki nihai yanıtı ortak sözleşmeye çevir."""

        for line in reversed(raw_output.splitlines()):
            try:
                payload_obj: object = json.loads(line)
            except json.JSONDecodeError:
                continue
            if not isinstance(payload_obj, dict):
                continue
            payload = cast(dict[str, object], payload_obj)
            if payload.get("event") != "result":
                continue
            result_obj = payload.get("result")
            if not isinstance(result_obj, dict):
                continue
            result = cast(dict[str, object], result_obj)
            response = result.get("response")
            if isinstance(response, str) and response.strip():
                return TaskResult(summary=response.strip(), status="success")
            error = result.get("error")
            if isinstance(error, str) and error.strip():
                return TaskResult(summary=error.strip(), status="error")
        return super().normalize_result(raw_output)
