from __future__ import annotations

import argparse
import importlib.util
import json
import sys
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest


repo_root = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(repo_root / "ACP_AGENT"))
_ACP_SPEC = importlib.util.spec_from_file_location("acp_agent_cli_security", repo_root / "ACP_AGENT" / "acp.py")
assert _ACP_SPEC is not None and _ACP_SPEC.loader is not None
acp_cli = importlib.util.module_from_spec(_ACP_SPEC)
sys.modules[_ACP_SPEC.name] = acp_cli
_ACP_SPEC.loader.exec_module(acp_cli)
def _config(tmp_path: Path, **overrides: Any) -> Path:
    path = tmp_path / "runner.json"
    payload = {
        "agent_name": "runner-a",
        "hub_http": "http://hub.test",
        "session_id": "session-1",
        "member_token": "member-1",
        **overrides,
    }
    path.write_text(json.dumps(payload), encoding="utf-8")
    return path
def _args(config: Path, *extra: str) -> argparse.Namespace:
    return acp_cli.build_parser().parse_args(
        ["runner", "once", "--config", str(config), "--provider", "codex_local", *extra]
    )


def _settings(**overrides: Any) -> argparse.Namespace:
    payload = {
        "session_id": "session-1",
        "member_token": "member-1",
        "agent_name": "runner-a",
        "hub_http": "http://hub.test",
        "token": None,
        **overrides,
    }
    return argparse.Namespace(**payload)


def _secure_profile(tmp_path: Path, **overrides: Any) -> dict[str, Any]:
    return {
        "provider": "codex_local",
        "workspace_path": str((tmp_path / "local-workspace").resolve()),
        "task_timeout_seconds": 30.0,
        "state_path": tmp_path / "runner-state.json",
        "auto_busy_heartbeat_minutes": 0.0,
        "auto_busy_heartbeat_interval_seconds": 45.0,
        "security_mode": "secure",
        "allowed_senders": ["trusted-chief"],
        "pin_provider": True,
        "pin_workspace": True,
        "reply_to": "local-chief",
        **overrides,
    }


@pytest.mark.parametrize(
    ("config_fields", "extra_args"),
    [
        ({}, ()),
        ({"delivery_mode": "runner", "runner_provider": "codex_local", "runner_workspace": "workspace"}, ()),
        ({"runner_provider": "codex_local", "runner_workspace": "workspace", "runner_security_version": 1}, ()),
        ({}, ("--legacy-runner-policy",)),
    ],
    ids=("new", "runner-fields-without-marker", "secure-allowlist-removed", "new-legacy-escape"),
)
def test_runner_without_allowlist_fails_closed(
    tmp_path: Path, config_fields: dict[str, Any], extra_args: tuple[str, ...]
) -> None:
    with pytest.raises(ValueError, match="trusted sender|pre-0.3.14"):
        acp_cli.resolve_runner_profile(_args(_config(tmp_path, **config_fields), *extra_args))


def test_pre_0314_runner_can_opt_into_explicit_legacy_policy(tmp_path: Path) -> None:
    config = _config(
        tmp_path,
        delivery_mode="runner",
        runner_provider="codex_local",
        runner_workspace=str(tmp_path / "workspace"),
    )

    profile = acp_cli.bootstrap_runner_session(
        _args(config, "--legacy-runner-policy"),
        command_name="runner once",
    )

    assert profile["security_mode"] == "legacy"
    assert json.loads(config.read_text(encoding="utf-8"))["runner_security_version"] == 0


def test_secure_runner_persists_allowlist_and_local_pins(tmp_path: Path) -> None:
    config = _config(tmp_path)
    profile = acp_cli.bootstrap_runner_session(
        _args(
            config,
            "--workspace",
            str(tmp_path / "workspace"),
            "--allow-sender",
            "chief",
            "--reply-to",
            "chief",
        ),
        command_name="runner once",
    )

    assert profile["allowed_senders"] == ["chief"]
    saved = json.loads(config.read_text(encoding="utf-8"))
    assert saved["runner_security_version"] == 1
    assert saved["runner_allowed_senders"] == ["chief"]
    assert saved["runner_reply_to"] == "chief"


def test_untrusted_task_clears_real_hub_current_task_before_waiting(
    api_client: Any,
    tmp_path: Path,
    monkeypatch: Any,
) -> None:
    chief = api_client.post("/sessions", json={"agent_name": "trusted-chief"}).json()
    runner = api_client.post(
        "/sessions/join", json={"agent_name": "runner-a", "join_code": chief["join_code"]}
    ).json()
    other = api_client.post(
        "/sessions/join", json={"agent_name": "other-member", "join_code": chief["join_code"]}
    ).json()
    api_client.post(
        "/sessions/send",
        json={
            "session_id": other["session_id"],
            "agent_name": "other-member",
            "member_token": other["member_token"],
            "to": "runner-a",
            "action": "TASK",
            "payload": "Untrusted work",
        },
    ).raise_for_status()
    waited = api_client.post(
        "/sessions/wait",
        json={**runner, "agent_name": "runner-a", "timeout_seconds": 1},
    )
    waited.raise_for_status()

    def member_detail() -> dict[str, Any]:
        body = api_client.get(
            f"/sessions/{runner['session_id']}/detail",
            params={"agent_name": "runner-a", "member_token": runner["member_token"]},
        ).json()["session"]
        return next(item for item in body["members"] if item["agent_name"] == "runner-a")

    assert member_detail()["current_task"] == "Untrusted work"

    def _post_json(*, route: str, payload: dict[str, Any], **kwargs: Any) -> dict[str, Any]:
        response = api_client.post(route, json=payload)
        response.raise_for_status()
        return response.json()

    monkeypatch.setattr(acp_cli, "post_json", _post_json)
    monkeypatch.setattr(acp_cli, "emit_json_line", lambda payload: None)
    monkeypatch.setattr(
        acp_cli,
        "execute_provider",
        lambda **kwargs: (_ for _ in ()).throw(AssertionError("provider must not execute")),
    )
    result = acp_cli.process_runner_message(
        settings=_settings(session_id=runner["session_id"], member_token=runner["member_token"]),
        profile=_secure_profile(tmp_path),
        message=waited.json()["message"],
    )

    member = member_detail()
    assert result["reason"] == "untrusted_sender"
    assert member["current_task"] is None
    assert member["current_task_from"] is None
    assert member["status"] == "waiting"


def test_secure_runner_ignores_remote_execution_and_reply_overrides(tmp_path: Path, monkeypatch: Any) -> None:
    calls: dict[str, dict[str, Any]] = {}
    result = SimpleNamespace(
        outcome="success",
        summary="Safe execution",
        started_at="2026-07-15T10:00:00.000000Z",
        finished_at="2026-07-15T10:00:01.000000Z",
        exit_code=0,
        stdout_text="done",
        stderr_text="",
        provider_session_id=None,
        provider_session_params={},
        metadata={},
    )
    monkeypatch.setattr(
        acp_cli,
        "execute_provider",
        lambda **kwargs: calls.setdefault("execute", kwargs) and result,
    )
    monkeypatch.setattr(
        acp_cli,
        "send_runner_reply",
        lambda **kwargs: calls.setdefault("reply", kwargs) or {"status": "queued"},
    )
    monkeypatch.setattr(acp_cli, "emit_runner_event", lambda **kwargs: {"status": "ok"})
    monkeypatch.setattr(acp_cli, "emit_json_line", lambda payload: None)
    monkeypatch.setattr(acp_cli, "publish_runner_waiting", lambda **kwargs: {"status": "ok"})

    profile = _secure_profile(tmp_path)
    acp_cli.process_runner_message(
        settings=_settings(),
        profile=profile,
        message={
            "id": "msg-1",
            "from": "trusted-chief",
            "action": "TASK",
            "payload": json.dumps(
                {
                    "instructions": "Implement safely",
                    "provider": "claude_local",
                    "workspace_path": str(tmp_path / "remote"),
                    "reply_to": "attacker",
                }
            ),
        },
    )

    assert calls["execute"]["provider"] == "codex_local"
    assert calls["execute"]["workspace_path"] == profile["workspace_path"]
    assert calls["reply"]["recipient"] == "local-chief"
