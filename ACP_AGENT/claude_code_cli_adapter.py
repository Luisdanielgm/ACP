"""Host Bridge adapter for an explicitly bound existing Claude Code session."""

from __future__ import annotations

import json
import os
import subprocess
import time
from pathlib import Path
from typing import Any, Callable, Mapping

from host_bridge import (
    CredentialResolver,
    HostBinding,
    HostBindingError,
    HostDelivery,
    HostDeliveryError,
    HostManifest,
    HostResult,
)


Run = Callable[..., subprocess.CompletedProcess[str]]
_MAX_SUMMARY_CHARS = 16_000


class ClaudeCodeCliAdapter:
    """Resume one persisted Claude Code session only after an ACP delivery."""

    manifest = HostManifest(
        adapter_id="claude_code_cli",
        display_name="Claude Code CLI resume",
        capabilities=(
            "existing-session",
            "cli-resume",
            "streaming-terminal-result",
            "cancellation",
            "fail-closed-retry",
        ),
    )

    def __init__(
        self,
        *,
        request_timeout_seconds: float = 1800.0,
        deadline_monotonic: float | None = None,
        credential_resolver: CredentialResolver | None = None,
        runner: Run = subprocess.run,
    ) -> None:
        self.request_timeout_seconds = request_timeout_seconds
        self.deadline_monotonic = deadline_monotonic
        self.credential_resolver = credential_resolver
        self.runner = runner

    def deliver(self, binding: HostBinding, delivery: HostDelivery) -> HostResult:
        executable, session_id, directory, credential_ref = self._validated(binding)
        deadline = time.monotonic() + self.request_timeout_seconds
        if self.deadline_monotonic is not None:
            deadline = min(deadline, self.deadline_monotonic)
        environment = self._environment(credential_ref)
        if environment is None:
            self._require_local_auth(executable, directory, deadline)
        command = [
            executable,
            "-p",
            "--resume",
            session_id,
            "--output-format",
            "stream-json",
            "--verbose",
            delivery.instructions,
        ]
        try:
            result = self.runner(
                command,
                cwd=directory,
                env=environment,
                capture_output=True,
                text=True,
                encoding="utf-8",
                timeout=self._remaining(deadline),
                check=False,
            )
        except subprocess.TimeoutExpired:
            raise HostDeliveryError("Claude Code turn exceeded its completion deadline") from None
        except (OSError, subprocess.SubprocessError):
            raise HostDeliveryError("Claude Code did not return a terminal result") from None
        if result.returncode != 0:
            raise HostDeliveryError("Claude Code did not return a terminal result")
        return self._terminal_result(result.stdout, session_id)

    def reconcile(self, binding: HostBinding, delivery: HostDelivery) -> HostResult:
        """Never resend a CLI prompt when a prior process outcome is ambiguous."""
        self._validated(binding)
        raise HostDeliveryError("previous Claude Code acceptance is not visible; refusing duplicate turn")

    def _require_local_auth(self, executable: str, directory: str | None, deadline: float) -> None:
        try:
            result = self.runner(
                [executable, "auth", "status"],
                cwd=directory,
                env=None,
                capture_output=True,
                text=True,
                encoding="utf-8",
                timeout=self._remaining(deadline),
                check=False,
            )
        except (OSError, subprocess.SubprocessError):
            raise HostDeliveryError("Claude Code authentication is unavailable") from None
        if result.returncode != 0:
            raise HostDeliveryError("Claude Code authentication is unavailable")
        try:
            status = json.loads(result.stdout)
        except (TypeError, ValueError, json.JSONDecodeError):
            raise HostDeliveryError("Claude Code authentication is unavailable") from None
        if not isinstance(status, dict) or status.get("loggedIn") is not True:
            raise HostDeliveryError("Claude Code authentication is unavailable")

    def _environment(self, credential_ref: str | None) -> dict[str, str] | None:
        if credential_ref is None:
            return None
        try:
            credential = self.credential_resolver(credential_ref) if self.credential_resolver else None
        except Exception:
            credential = None
        token = credential.bearer_token if credential is not None else None
        if not isinstance(token, str) or not token:
            raise HostBindingError("Claude Code credential reference cannot be resolved")
        environment = dict(os.environ)
        environment["ANTHROPIC_API_KEY"] = token
        return environment

    def _validated(self, binding: HostBinding) -> tuple[str, str, str | None, str | None]:
        if binding.adapter_id != self.manifest.adapter_id:
            raise HostBindingError("binding targets a different host adapter")
        executable = self._required(binding.values, "executable")
        if not Path(executable).is_absolute():
            raise HostBindingError("Claude Code executable must be an explicit absolute path")
        session_id = self._required(binding.values, "session_id")
        directory = self._optional(binding.values, "directory")
        if directory is not None and not Path(directory).is_absolute():
            raise HostBindingError("Claude Code workspace must be an absolute path")
        return executable, session_id, directory, self._optional(binding.values, "credential_ref")

    @staticmethod
    def _required(values: Mapping[str, str], key: str) -> str:
        value = values.get(key)
        if not isinstance(value, str) or not value.strip():
            raise HostBindingError(f"Claude Code binding requires {key}")
        return value.strip()

    @staticmethod
    def _optional(values: Mapping[str, str], key: str) -> str | None:
        value = values.get(key)
        return value.strip() if isinstance(value, str) and value.strip() else None

    @staticmethod
    def _remaining(deadline: float) -> float:
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            raise HostDeliveryError("Claude Code turn exceeded its completion deadline")
        return remaining

    @classmethod
    def _terminal_result(cls, stdout: str, session_id: str) -> HostResult:
        terminal: Mapping[str, Any] | None = None
        for raw_line in stdout.splitlines():
            if not raw_line.strip():
                continue
            try:
                event = json.loads(raw_line)
            except (ValueError, json.JSONDecodeError):
                raise HostDeliveryError("Claude Code did not return a terminal result") from None
            if not isinstance(event, dict) or event.get("type") != "result":
                continue
            if terminal is not None:
                raise HostDeliveryError("Claude Code returned ambiguous terminal results")
            terminal = event
        if terminal is None:
            raise HostDeliveryError("Claude Code did not return a terminal result")
        if terminal.get("session_id") != session_id:
            raise HostDeliveryError("Claude Code returned a different session")
        if terminal.get("is_error") is not False:
            raise HostDeliveryError("Claude Code did not complete successfully")
        summary = terminal.get("result")
        if not isinstance(summary, str) or not summary.strip():
            raise HostDeliveryError("Claude Code did not return a terminal result")
        return HostResult(outcome="success", summary=summary.strip()[:_MAX_SUMMARY_CHARS])
