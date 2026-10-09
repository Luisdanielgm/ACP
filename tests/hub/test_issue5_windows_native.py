"""Issue #5: honest task outcome, native managed hub-up, local hub detection."""

from __future__ import annotations

import argparse
import importlib.util
import json
import sys
from pathlib import Path
from typing import Any

import pytest

repo_root = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(repo_root / "ACP_AGENT"))
_SPEC = importlib.util.spec_from_file_location("acp_agent_issue5", repo_root / "ACP_AGENT" / "acp.py")
assert _SPEC is not None and _SPEC.loader is not None
acp = importlib.util.module_from_spec(_SPEC)
sys.modules[_SPEC.name] = acp
_SPEC.loader.exec_module(acp)

import runner_support  # noqa: E402


# --- 1. outcome is the process verdict; task_outcome is what a chief can vouch for ----------


def test_runner_reply_says_outcome_is_process_level_and_task_unverified() -> None:
    payload = runner_support.build_reply_payload(
        task_id="t-1", run_id="r-1", outcome="success", summary="No pude crear fecha.py",
        provider="codex_local", workspace_path="/w",
    )
    assert payload["outcome"] == "success"
    assert payload["outcome_scope"] == "process"
    assert payload["task_outcome"] == "unverified"


def _chief_dirs(tmp_path: Path) -> dict[str, Path]:
    dirs = {name: tmp_path / name for name in ("pending", "assigned", "done", "failed")}
    for path in dirs.values():
        path.mkdir()
    return dirs


def _assign(dirs: dict[str, Path], task: dict[str, Any]) -> None:
    (dirs["assigned"] / f"{task['task_id']}.json").write_text(json.dumps(task), encoding="utf-8")
    (dirs["assigned"] / f"{task['task_id']}.assignment.json").write_text(
        json.dumps({"task_id": task["task_id"], "worker": "w1", "task_file": f"{task['task_id']}.json"}), encoding="utf-8"
    )


def _reply(task_id: str, outcome: str = "success") -> dict[str, Any]:
    return {"from": "w1", "id": "m1", "payload": {"task_id": task_id, "outcome": outcome, "summary": "x"}}


def test_chief_marks_a_success_without_verification_as_unverified(tmp_path: Path) -> None:
    dirs = _chief_dirs(tmp_path)
    _assign(dirs, {"task_id": "t1", "instructions": "do it"})
    result = acp._chief_record_reply(dirs=dirs, message=_reply("t1"))
    assert result["outcome"] == "success"
    assert result["task_outcome"] == "unverified"


def test_chief_marks_a_passing_verify_command_as_verified(tmp_path: Path) -> None:
    dirs = _chief_dirs(tmp_path)
    _assign(dirs, {"task_id": "t1", "instructions": "do it", "verify_command": [sys.executable, "-c", "pass"]})
    result = acp._chief_record_reply(dirs=dirs, message=_reply("t1"))
    assert result["task_outcome"] == "verified"


def test_chief_failing_verify_command_overrides_the_workers_success(tmp_path: Path) -> None:
    dirs = _chief_dirs(tmp_path)
    _assign(dirs, {"task_id": "t1", "instructions": "do it", "verify_command": [sys.executable, "-c", "raise SystemExit(1)"], "max_attempts": 1})
    result = acp._chief_record_reply(dirs=dirs, message=_reply("t1"))
    assert result["task_outcome"] == "verification_failed"
    assert result["outcome"] == "verification_failed"


def test_require_verify_without_a_verify_command_does_not_count_as_done(tmp_path: Path) -> None:
    dirs = _chief_dirs(tmp_path)
    _assign(dirs, {"task_id": "t1", "instructions": "do it", "require_verify": True, "max_attempts": 1})
    result = acp._chief_record_reply(dirs=dirs, message=_reply("t1"))
    assert result["task_outcome"] == "verification_failed"
    assert result["verify_result"]["reason"] == "verify_required_but_missing"
    assert result["moved_task_file"] is not None and "failed" in result["moved_task_file"]


def test_worker_reported_failure_is_failed(tmp_path: Path) -> None:
    dirs = _chief_dirs(tmp_path)
    _assign(dirs, {"task_id": "t1", "instructions": "do it"})
    assert acp._chief_record_reply(dirs=dirs, message=_reply("t1", "failed"))["task_outcome"] == "failed"


# --- 2. native managed hub-up ---------------------------------------------------------------


def test_load_env_file_handles_quotes_comments_and_export(tmp_path: Path) -> None:
    env_file = tmp_path / ".env"
    env_file.write_text(
        "# comment\n\nACP_A=plain\nexport ACP_B=\"double quoted\"\nACP_C='scrypt$salt$hash'\nnot a pair\nACP_D=\n",
        encoding="utf-8",
    )
    assert acp.load_env_file(env_file) == {"ACP_A": "plain", "ACP_B": "double quoted", "ACP_C": "scrypt$salt$hash", "ACP_D": ""}


def test_managed_command_targets_the_managed_asgi_app() -> None:
    command = acp.build_local_hub_command(host="127.0.0.1", port=8000, python_executable="py", asgi_app=acp.LOCAL_HUB_MANAGED_APP)
    assert "acp_managed.app:app" in command
    assert "acp.hub.app:app" not in command


def test_managed_env_keeps_data_local_even_if_the_env_file_says_docker_paths() -> None:
    env = acp.build_local_hub_env(
        sqlite_path="/local/acp.sqlite3",
        base_env={"PATH": "x"},
        extra_env={"ACP_SQLITE_PATH": "/data/acp/acp.sqlite3", "ACP_WORKSPACE_SLUG": "default"},
        auth_sqlite_path="/local/auth.sqlite3",
    )
    assert env["ACP_SQLITE_PATH"] == "/local/acp.sqlite3"
    assert env["ACP_MANAGED_AUTH_SQLITE_PATH"] == "/local/auth.sqlite3"
    assert env["ACP_WORKSPACE_SLUG"] == "default"


def test_managed_hub_up_needs_settings(tmp_path: Path, monkeypatch: Any) -> None:
    monkeypatch.setattr(acp, "ACP_ROOT", tmp_path / "ACP_AGENT")
    monkeypatch.setattr(acp, "local_hub_health_ok", lambda *a, **k: False)
    monkeypatch.setattr(acp, "local_hub_dependencies_available", lambda: True)
    with pytest.raises(ValueError, match="--env-file"):
        acp.ensure_local_hub_running(host="127.0.0.1", port=8000, managed=True)


def test_managed_hub_up_spawns_managed_app_and_warns_when_frontend_is_missing(tmp_path: Path, monkeypatch: Any) -> None:
    root = tmp_path / "ACP_AGENT"
    root.mkdir()
    env_file = tmp_path / "hub.env"
    env_file.write_text("ACP_WORKSPACE_SLUG=default\n", encoding="utf-8")
    monkeypatch.setattr(acp, "ACP_ROOT", root)
    monkeypatch.setattr(acp, "local_hub_dependencies_available", lambda: True)
    health = iter([False, False, True])
    monkeypatch.setattr(acp, "local_hub_health_ok", lambda *a, **k: next(health, True))
    seen: dict[str, Any] = {}

    class _Proc:
        pid = 99
        returncode = None

        def poll(self) -> None:
            return None

    def fake_spawn(command: list[str], env: dict[str, str], log_path: Path | None = None) -> _Proc:
        seen.update(command=command, env=env, log_path=log_path)
        return _Proc()

    monkeypatch.setattr(acp, "_spawn_local_hub_process", fake_spawn)
    result = acp.ensure_local_hub_running(host="127.0.0.1", port=8000, managed=True, env_file=env_file, poll_interval_seconds=0)
    assert "acp_managed.app:app" in seen["command"]
    assert seen["env"]["ACP_WORKSPACE_SLUG"] == "default"
    assert seen["log_path"] is not None
    assert result["status"] == "started" and result["managed"] is True
    assert result["login_url"].endswith("/managed/login")
    assert any("npm run build" in warning for warning in result["warnings"])


def test_hub_up_parser_accepts_managed_flags() -> None:
    args = acp.build_parser().parse_args(["hub-up", "--managed", "--env-file", "apps/hub/.env"])
    assert args.managed is True and args.env_file == "apps/hub/.env"


# --- 8. health / doctor find the local hub --------------------------------------------------


def test_simple_hub_resolution_uses_a_running_local_hub(monkeypatch: Any) -> None:
    monkeypatch.setattr(acp, "resolve_local_hub_http", lambda: "http://127.0.0.1:8000")
    args = argparse.Namespace(hub_http=None, token=None, agent=None, name=None, config=None, command="health")
    assert acp._resolve_hub_http_simple(args) == ("http://127.0.0.1:8000", None)


def test_explicit_hub_http_still_beats_the_local_hub(monkeypatch: Any) -> None:
    monkeypatch.setattr(acp, "resolve_local_hub_http", lambda: "http://127.0.0.1:8000")
    args = argparse.Namespace(hub_http="https://hub.example.com", token=None, agent=None, name=None, config=None, command="health")
    assert acp._resolve_hub_http_simple(args)[0] == "https://hub.example.com"


# --- 3. missing frontend build is explained, not silent -------------------------------------


def test_missing_frontend_build_answers_503_with_the_fix(monkeypatch: Any, caplog: Any) -> None:
    from fastapi import FastAPI, HTTPException

    from acp_managed.ui import spa

    monkeypatch.setattr(spa, "_managed_static_dir", lambda: None)
    with caplog.at_level("WARNING"):
        spa._register_managed_vue_spa(FastAPI())
    assert any("npm run build" in record.getMessage() for record in caplog.records)
    with pytest.raises(HTTPException) as excinfo:
        spa._managed_spa_response()
    assert excinfo.value.status_code == 503
    assert "npm run build" in excinfo.value.detail
