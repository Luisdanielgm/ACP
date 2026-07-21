"""Host Bridge adapter for an explicitly bound existing Codex CLI session."""

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


class CodexCliAdapter:
    """Resume one persisted Codex CLI session only after an ACP delivery.

    Uses the official non-interactive surface ``codex exec resume <session_id>``
    so a valid ACP TASK continues the existing session and never starts a new
    one.  The adapter reads the newline-delimited JSON event stream (``--json``)
    to correlate on the resumed thread id and to require a terminal turn.
    """

    manifest = HostManifest(
        adapter_id="codex_cli",
        display_name="Codex CLI resume",
        capabilities=(
            "existing-session",
            "cli-resume",
            "streaming-terminal-result",
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
        command = [
            executable,
            "exec",
            "resume",
            session_id,
            "--json",
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
            raise HostDeliveryError("Codex CLI turn exceeded its completion deadline") from None
        except (OSError, subprocess.SubprocessError):
            raise HostDeliveryError("Codex CLI is unavailable") from None
        if result.returncode != 0:
            raise HostDeliveryError("Codex CLI did not return a terminal result")
        return self._terminal_result(result.stdout, session_id)

    def reconcile(self, binding: HostBinding, delivery: HostDelivery) -> HostResult:
        """Never resend a CLI prompt when a prior process outcome is ambiguous."""
        self._validated(binding)
        raise HostDeliveryError("previous Codex CLI acceptance is not visible; refusing duplicate turn")

    def _environment(self, credential_ref: str | None) -> dict[str, str] | None:
        if credential_ref is None:
            return None
        try:
            credential = self.credential_resolver(credential_ref) if self.credential_resolver else None
        except Exception:
            credential = None
        token = credential.bearer_token if credential is not None else None
        if not isinstance(token, str) or not token:
            raise HostBindingError("Codex CLI credential reference cannot be resolved")
        environment = dict(os.environ)
        environment["OPENAI_API_KEY"] = token
        return environment

    def _validated(self, binding: HostBinding) -> tuple[str, str, str | None, str | None]:
        if binding.adapter_id != self.manifest.adapter_id:
            raise HostBindingError("binding targets a different host adapter")
        executable = self._required(binding.values, "executable")
        if not Path(executable).is_absolute():
            raise HostBindingError("Codex CLI executable must be an explicit absolute path")
        session_id = self._required(binding.values, "session_id")
        directory = self._optional(binding.values, "directory")
        if directory is not None and not Path(directory).is_absolute():
            raise HostBindingError("Codex CLI workspace must be an absolute path")
        return executable, session_id, directory, self._optional(binding.values, "credential_ref")

    @staticmethod
    def _required(values: Mapping[str, str], key: str) -> str:
        value = values.get(key)
        if not isinstance(value, str) or not value.strip():
            raise HostBindingError(f"Codex CLI binding requires {key}")
        return value.strip()

    @staticmethod
    def _optional(values: Mapping[str, str], key: str) -> str | None:
        value = values.get(key)
        return value.strip() if isinstance(value, str) and value.strip() else None

    @staticmethod
    def _remaining(deadline: float) -> float:
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            raise HostDeliveryError("Codex CLI turn exceeded its completion deadline")
        return remaining

    @classmethod
    def _terminal_result(cls, stdout: str, session_id: str) -> HostResult:
        thread_id: str | None = None
        final_text = ""
        completed_turns = 0
        for raw_line in stdout.splitlines():
            if not raw_line.strip():
                continue
            try:
                event = json.loads(raw_line)
            except (ValueError, json.JSONDecodeError):
                raise HostDeliveryError("Codex CLI did not return a terminal result") from None
            if not isinstance(event, dict):
                continue
            event_type = event.get("type")
            if event_type == "thread.started":
                candidate = event.get("thread_id")
                if not isinstance(candidate, str) or not candidate:
                    candidate = event.get("id")
                if isinstance(candidate, str) and candidate:
                    thread_id = candidate
            elif event_type in {"turn.failed", "error"}:
                raise HostDeliveryError("Codex CLI did not complete successfully")
            elif event_type == "item.completed":
                item = event.get("item")
                if isinstance(item, dict) and item.get("type") == "agent_message":
                    text = item.get("text")
                    if isinstance(text, str) and text.strip():
                        final_text = text.strip()
            elif event_type == "turn.completed":
                completed_turns += 1
        if completed_turns == 0:
            raise HostDeliveryError("Codex CLI did not return a terminal result")
        if completed_turns > 1:
            raise HostDeliveryError("Codex CLI returned ambiguous terminal results")
        if thread_id is None:
            raise HostDeliveryError("Codex CLI did not return a resumed session identity")
        if thread_id != session_id:
            raise HostDeliveryError("Codex CLI resumed a different session")
        summary = final_text or "Codex CLI completed without a text response"
        return HostResult(outcome="success", summary=summary[:_MAX_SUMMARY_CHARS])
