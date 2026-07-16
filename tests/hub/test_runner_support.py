from __future__ import annotations

import importlib.util
import sys
from pathlib import Path


repo_root = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(repo_root / "ACP_AGENT"))
_RUNNER_SUPPORT_SPEC = importlib.util.spec_from_file_location(
    "acp_runner_support",
    repo_root / "ACP_AGENT" / "runner_support.py",
)
assert _RUNNER_SUPPORT_SPEC is not None and _RUNNER_SUPPORT_SPEC.loader is not None
runner_support = importlib.util.module_from_spec(_RUNNER_SUPPORT_SPEC)
sys.modules[_RUNNER_SUPPORT_SPEC.name] = runner_support
_RUNNER_SUPPORT_SPEC.loader.exec_module(runner_support)


def test_codex_provider_resolves_windows_command_shim(monkeypatch) -> None:
    monkeypatch.setattr(runner_support, "_is_windows", lambda: True, raising=False)
    monkeypatch.setattr(
        runner_support.shutil,
        "which",
        lambda executable: f"C:/npm/{executable}.CMD",
        raising=False,
    )

    command, stdin_text = runner_support._provider_command(
        provider="codex_local",
        instructions="Inspect the task",
        state_entry={},
    )

    assert command == [
        "C:/npm/codex.CMD",
        "exec",
        "--skip-git-repo-check",
        "-",
    ]
    assert stdin_text == "Inspect the task"


def test_codex_resume_stays_in_noninteractive_exec_mode(monkeypatch) -> None:
    monkeypatch.setattr(runner_support, "_provider_executable", lambda executable: executable)

    command, stdin_text = runner_support._provider_command(
        provider="codex_local",
        instructions="Continue the task",
        state_entry={"provider_session_id": "session-123"},
    )

    assert command == ["codex", "exec", "resume", "session-123", "-"]
    assert stdin_text == "Continue the task"


def test_provider_permission_error_returns_failed_result(monkeypatch, tmp_path: Path) -> None:
    def _deny_launch(*args, **kwargs):
        raise PermissionError(5, "Access is denied")

    monkeypatch.setattr(runner_support.subprocess, "Popen", _deny_launch)

    result = runner_support._execute_provider_once(
        provider="codex_local",
        instructions="Inspect the task",
        workspace_path=tmp_path,
        timeout_seconds=5,
        state_entry={},
    )

    assert result.outcome == "failed"
    assert result.summary == "codex_local executable could not be started"
    assert result.exit_code is None
    assert result.metadata == {"error_type": "execution_error"}
    assert "Access is denied" in result.stderr_text
