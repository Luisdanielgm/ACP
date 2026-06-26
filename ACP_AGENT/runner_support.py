from __future__ import annotations

import json
import os
import queue
import re
import subprocess
import tempfile
import threading
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

_SESSION_ID_PATTERNS = (
    re.compile(r'"session_id"\s*:\s*"(?P<value>[^"]+)"'),
    re.compile(r'"sessionId"\s*:\s*"(?P<value>[^"]+)"'),
    re.compile(r"\bsession(?:\s+id)?[:=]\s*(?P<value>[A-Za-z0-9._:-]+)", re.IGNORECASE),
)
_LOST_SESSION_PATTERNS = (
    "session not found",
    "session does not exist",
    "could not resume",
    "unable to resume",
    "unknown session",
    "invalid session",
)


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="microseconds").replace("+00:00", "Z")


def write_json_atomic(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile("w", delete=False, encoding="utf-8", dir=path.parent, suffix=".tmp") as handle:
        json.dump(payload, handle, ensure_ascii=True, indent=2)
        handle.write("\n")
        temp_path = Path(handle.name)
    temp_path.replace(path)


def normalize_workspace_path(path_value: str | Path | None) -> str:
    if path_value is None:
        return str(Path.cwd().resolve())
    return str(Path(path_value).expanduser().resolve())


def workspace_key(path_value: str | Path | None) -> str:
    return normalize_workspace_path(path_value).lower()


def runner_state_key(*, session_id: str, agent_name: str, provider: str, workspace_path: str | Path | None) -> str:
    return "||".join([session_id, agent_name, provider, workspace_key(workspace_path)])


def load_runner_state(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {"entries": {}}
    try:
        parsed = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError, json.JSONDecodeError):
        return {"entries": {}}
    if not isinstance(parsed, dict):
        return {"entries": {}}
    entries = parsed.get("entries")
    if not isinstance(entries, dict):
        parsed["entries"] = {}
    return parsed


def load_runner_entry(path: Path, *, key: str) -> dict[str, Any]:
    payload = load_runner_state(path)
    entries = payload.get("entries")
    if not isinstance(entries, dict):
        return {}
    entry = entries.get(key)
    return dict(entry) if isinstance(entry, dict) else {}


def save_runner_entry(path: Path, *, key: str, entry: dict[str, Any]) -> None:
    payload = load_runner_state(path)
    entries = payload.setdefault("entries", {})
    if not isinstance(entries, dict):
        payload["entries"] = {}
        entries = payload["entries"]
    entries[key] = dict(entry)
    payload["updated_at"] = utc_now_iso()
    write_json_atomic(path, payload)


def update_runner_entry(path: Path, *, key: str, updates: dict[str, Any]) -> dict[str, Any]:
    current = load_runner_entry(path, key=key)
    current.update(updates)
    save_runner_entry(path, key=key, entry=current)
    return current


def extract_task_spec(
    *,
    message: dict[str, Any],
    default_provider: str,
    default_workspace: str | Path,
) -> dict[str, Any]:
    payload = message.get("payload")
    reply_to = message.get("from") if isinstance(message.get("from"), str) else None
    task_id: str | None = None
    instructions: str | None = None
    provider = default_provider
    workspace_path = normalize_workspace_path(default_workspace)
    metadata: dict[str, Any] | None = None
    if isinstance(payload, str):
        try:
            parsed = json.loads(payload)
        except (ValueError, json.JSONDecodeError):
            parsed = None
        if isinstance(parsed, dict) and isinstance(parsed.get("instructions"), str) and parsed.get("instructions").strip():
            instructions = parsed["instructions"].strip()
            if isinstance(parsed.get("task_id"), str) and parsed["task_id"].strip():
                task_id = parsed["task_id"].strip()
            if isinstance(parsed.get("provider"), str) and parsed["provider"].strip():
                provider = parsed["provider"].strip()
            if isinstance(parsed.get("workspace_path"), str) and parsed["workspace_path"].strip():
                workspace_path = normalize_workspace_path(parsed["workspace_path"])
            if isinstance(parsed.get("reply_to"), str) and parsed["reply_to"].strip():
                reply_to = parsed["reply_to"].strip()
            if isinstance(parsed.get("metadata"), dict):
                metadata = dict(parsed["metadata"])
        elif payload.strip():
            instructions = payload.strip()
    if instructions is None:
        raise ValueError("TASK payload must contain instructions.")
    return {
        "task_id": task_id,
        "instructions": instructions,
        "provider": provider,
        "workspace_path": workspace_path,
        "reply_to": reply_to,
        "metadata": metadata,
    }


def build_reply_payload(
    *,
    task_id: str | None,
    run_id: str,
    outcome: str,
    summary: str,
    provider: str,
    workspace_path: str,
    metadata: dict[str, Any] | None = None,
) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "run_id": run_id,
        "outcome": outcome,
        "summary": summary,
        "provider": provider,
        "workspace_path": workspace_path,
    }
    if task_id:
        payload["task_id"] = task_id
    if metadata:
        payload["metadata"] = dict(metadata)
    return payload


def _provider_command(
    *,
    provider: str,
    instructions: str,
    state_entry: dict[str, Any],
) -> tuple[list[str], str]:
    provider_session_id = state_entry.get("provider_session_id") if isinstance(state_entry, dict) else None
    if provider == "codex_local":
        if isinstance(provider_session_id, str) and provider_session_id.strip():
            return ["codex", "resume", provider_session_id.strip(), "-"], instructions
        return ["codex", "exec", "--skip-git-repo-check", "-"], instructions
    if provider == "claude_local":
        command = ["claude", "--print"]
        if isinstance(provider_session_id, str) and provider_session_id.strip():
            command.extend(["--resume", provider_session_id.strip()])
        return command, instructions
    raise ValueError(f"unsupported provider: {provider}")


def _extract_provider_session_id(*, text: str, fallback: str | None) -> str | None:
    for pattern in _SESSION_ID_PATTERNS:
        match = pattern.search(text)
        if match:
            return match.group("value")
    return fallback


def _looks_like_lost_session(*, text: str) -> bool:
    lowered = text.lower()
    return any(marker in lowered for marker in _LOST_SESSION_PATTERNS)


@dataclass
class ProviderExecutionResult:
    outcome: str
    summary: str
    started_at: str
    finished_at: str
    exit_code: int | None
    stdout_text: str
    stderr_text: str
    provider_session_id: str | None
    provider_session_params: dict[str, Any]
    metadata: dict[str, Any]


def execute_provider(
    *,
    provider: str,
    instructions: str,
    workspace_path: str | Path,
    timeout_seconds: float,
    state_entry: dict[str, Any],
    log_callback: Callable[[str, str], None] | None = None,
) -> ProviderExecutionResult:
    workspace = Path(normalize_workspace_path(workspace_path))
    workspace.mkdir(parents=True, exist_ok=True)
    initial_session_id = state_entry.get("provider_session_id") if isinstance(state_entry, dict) else None
    result = _execute_provider_once(
        provider=provider,
        instructions=instructions,
        workspace_path=workspace,
        timeout_seconds=timeout_seconds,
        state_entry=state_entry,
        log_callback=log_callback,
    )
    combined_output = "\n".join(part for part in (result.stdout_text, result.stderr_text) if part).strip()
    if (
        isinstance(initial_session_id, str)
        and initial_session_id.strip()
        and result.outcome == "failed"
        and _looks_like_lost_session(text=combined_output)
    ):
        fresh_state = dict(state_entry)
        fresh_state["provider_session_id"] = None
        retried = _execute_provider_once(
            provider=provider,
            instructions=instructions,
            workspace_path=workspace,
            timeout_seconds=timeout_seconds,
            state_entry=fresh_state,
            log_callback=log_callback,
        )
        retried.metadata["session_reset"] = True
        return retried
    return result


def _execute_provider_once(
    *,
    provider: str,
    instructions: str,
    workspace_path: Path,
    timeout_seconds: float,
    state_entry: dict[str, Any],
    log_callback: Callable[[str, str], None] | None = None,
) -> ProviderExecutionResult:
    command, stdin_text = _provider_command(provider=provider, instructions=instructions, state_entry=state_entry)
    started_at = utc_now_iso()
    stdout_lines: list[str] = []
    stderr_lines: list[str] = []
    line_queue: queue.Queue[tuple[str, str | None]] = queue.Queue()

    try:
        process = subprocess.Popen(
            command,
            cwd=str(workspace_path),
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            encoding="utf-8",
            errors="replace",
            bufsize=1,
            env=os.environ.copy(),
        )
    except FileNotFoundError as exc:
        finished_at = utc_now_iso()
        return ProviderExecutionResult(
            outcome="failed",
            summary=f"{provider} executable not found",
            started_at=started_at,
            finished_at=finished_at,
            exit_code=None,
            stdout_text="",
            stderr_text=str(exc),
            provider_session_id=state_entry.get("provider_session_id") if isinstance(state_entry, dict) else None,
            provider_session_params={"command": command},
            metadata={"error_type": "file_not_found"},
        )

    def _reader(stream_name: str, handle: Any) -> None:
        try:
            for line in iter(handle.readline, ""):
                line_queue.put((stream_name, line))
        finally:
            try:
                handle.close()
            except Exception:
                pass
            line_queue.put((stream_name, None))

    stdout_thread = threading.Thread(target=_reader, args=("stdout", process.stdout), daemon=True)
    stderr_thread = threading.Thread(target=_reader, args=("stderr", process.stderr), daemon=True)
    stdout_thread.start()
    stderr_thread.start()

    if process.stdin is not None:
        try:
            process.stdin.write(stdin_text)
            if not stdin_text.endswith("\n"):
                process.stdin.write("\n")
            process.stdin.close()
        except Exception:
            pass

    open_streams = {"stdout", "stderr"}
    timed_out = False
    try:
        while open_streams:
            try:
                stream_name, line = line_queue.get(timeout=0.2)
            except queue.Empty:
                if process.poll() is None:
                    elapsed = (
                        datetime.now(timezone.utc)
                        - datetime.fromisoformat(started_at[:-1] + "+00:00")
                    ).total_seconds()
                    if timeout_seconds > 0 and elapsed > timeout_seconds:
                        timed_out = True
                        process.kill()
                        break
                continue
            if line is None:
                open_streams.discard(stream_name)
                continue
            cleaned = line.rstrip("\r\n")
            if stream_name == "stdout":
                stdout_lines.append(cleaned)
            else:
                stderr_lines.append(cleaned)
            if callable(log_callback) and cleaned:
                log_callback(stream_name, cleaned)
        if timed_out:
            try:
                process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                pass
        else:
            process.wait(timeout=max(timeout_seconds, 1.0) if timeout_seconds > 0 else None)
    except subprocess.TimeoutExpired:
        timed_out = True
        process.kill()
    finally:
        stdout_thread.join(timeout=1)
        stderr_thread.join(timeout=1)

    finished_at = utc_now_iso()
    stdout_text = "\n".join(stdout_lines).strip()
    stderr_text = "\n".join(stderr_lines).strip()
    summary_source = stdout_text or stderr_text
    summary = summary_source.splitlines()[-1] if summary_source else f"{provider} run completed"
    provider_session_id = _extract_provider_session_id(
        text="\n".join(part for part in (stdout_text, stderr_text) if part),
        fallback=state_entry.get("provider_session_id") if isinstance(state_entry, dict) else None,
    )
    if timed_out:
        outcome = "timeout"
    elif process.returncode == 0:
        outcome = "success"
    else:
        outcome = "failed"

    return ProviderExecutionResult(
        outcome=outcome,
        summary=summary[:512],
        started_at=started_at,
        finished_at=finished_at,
        exit_code=process.returncode,
        stdout_text=stdout_text,
        stderr_text=stderr_text,
        provider_session_id=provider_session_id,
        provider_session_params={"command": command},
        metadata={"timed_out": timed_out, "exit_code": process.returncode},
    )
