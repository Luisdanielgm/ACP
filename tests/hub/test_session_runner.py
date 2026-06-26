from __future__ import annotations

import argparse
import importlib.util
import json
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

repo_root = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(repo_root / "ACP_AGENT"))
_ACP_SPEC = importlib.util.spec_from_file_location("acp_agent_cli", repo_root / "ACP_AGENT" / "acp.py")
assert _ACP_SPEC is not None and _ACP_SPEC.loader is not None
acp_cli = importlib.util.module_from_spec(_ACP_SPEC)
sys.modules[_ACP_SPEC.name] = acp_cli
_ACP_SPEC.loader.exec_module(acp_cli)


def _create_session(client: Any, agent_name: str, **extra: Any) -> dict[str, Any]:
    response = client.post("/sessions", json={"agent_name": agent_name, **extra})
    assert response.status_code == 201
    return response.json()


def _join_session(client: Any, agent_name: str, join_code: str, **extra: Any) -> dict[str, Any]:
    response = client.post("/sessions/join", json={"agent_name": agent_name, "join_code": join_code, **extra})
    assert response.status_code == 200
    return response.json()


def test_runner_member_metadata_and_structured_payload_roundtrip(api_client: Any) -> None:
    chief = _create_session(api_client, "chief")
    runner = _join_session(
        api_client,
        "runner-a",
        chief["join_code"],
        delivery_mode="runner",
        provider="codex_local",
        workspace_path="C:/workspace/demo",
    )

    detail = api_client.get(
        f"/sessions/{chief['session_id']}/detail",
        params={"agent_name": "runner-a", "member_token": runner["member_token"]},
    )
    assert detail.status_code == 200
    member = next(item for item in detail.json()["session"]["members"] if item["agent_name"] == "runner-a")
    assert member["delivery_mode"] == "runner"
    assert member["provider"] == "codex_local"
    assert member["workspace_path"] == "C:/workspace/demo"

    send = api_client.post(
        "/sessions/send",
        json={
            "session_id": chief["session_id"],
            "agent_name": "chief",
            "member_token": chief["member_token"],
            "to": "runner-a",
            "action": "TASK",
            "payload": {
                "task_id": "task-123",
                "instructions": "Review the auth flow",
                "provider": "claude_local",
                "workspace_path": "C:/workspace/override",
                "reply_to": "chief",
                "metadata": {"priority": "high"},
            },
        },
    )
    assert send.status_code == 200

    waited = api_client.post(
        "/sessions/wait",
        json={
            "session_id": runner["session_id"],
            "agent_name": "runner-a",
            "member_token": runner["member_token"],
            "timeout_seconds": 5,
        },
    )
    assert waited.status_code == 200
    message = waited.json()["message"]
    payload = json.loads(message["payload"])
    assert payload["task_id"] == "task-123"
    assert payload["provider"] == "claude_local"
    assert payload["workspace_path"] == "C:/workspace/override"


def test_runner_events_update_member_state_and_history(api_client: Any) -> None:
    chief = _create_session(api_client, "chief")
    runner = _join_session(
        api_client,
        "runner-a",
        chief["join_code"],
        delivery_mode="runner",
        provider="codex_local",
        workspace_path="C:/workspace/demo",
    )

    for payload in (
        {
            "event": "RUN_STARTED",
            "run_id": "run-1",
            "task_id": "task-123",
            "summary": "Reviewing auth flow",
            "detail": "runner started codex_local",
        },
        {
            "event": "RUN_LOG",
            "run_id": "run-1",
            "log_chunk": "Reading src/auth.py",
            "detail": "codex emitted stdout",
        },
        {
            "event": "RUN_FINISHED",
            "run_id": "run-1",
            "outcome": "success",
            "summary": "Auth flow reviewed",
            "detail": "codex run finished",
        },
        {
            "event": "RUN_REPLY_SENT",
            "run_id": "run-1",
            "outcome": "success",
            "summary": "Reply posted",
            "detail": "reply sent to chief",
        },
    ):
        response = api_client.post(
            "/sessions/runs/events",
            json={
                "session_id": runner["session_id"],
                "agent_name": "runner-a",
                "member_token": runner["member_token"],
                "provider": "codex_local",
                "workspace_path": "C:/workspace/demo",
                **payload,
            },
        )
        assert response.status_code == 200

    detail = api_client.get(
        f"/sessions/{chief['session_id']}/detail",
        params={"agent_name": "runner-a", "member_token": runner["member_token"]},
    )
    assert detail.status_code == 200
    body = detail.json()["session"]
    member = next(item for item in body["members"] if item["agent_name"] == "runner-a")
    assert member["status"] == "waiting"
    assert member["current_run"] is None
    assert member["last_run"]["run_id"] == "run-1"
    assert member["last_run"]["outcome"] == "success"
    assert any(event["event"] == "RUN_STARTED" for event in body["history"])
    assert any(event["event"] == "RUN_LOG" for event in body["history"])
    assert any(event["event"] == "RUN_REPLY_SENT" for event in body["history"])


def test_stale_runner_run_is_interrupted_on_refresh(api_client: Any, hub_runtime: Any) -> None:
    chief = _create_session(api_client, "chief")
    runner = _join_session(
        api_client,
        "runner-a",
        chief["join_code"],
        delivery_mode="runner",
        provider="codex_local",
        workspace_path="C:/workspace/demo",
    )

    started = api_client.post(
        "/sessions/runs/events",
        json={
            "session_id": runner["session_id"],
            "agent_name": "runner-a",
            "member_token": runner["member_token"],
            "event": "RUN_STARTED",
            "run_id": "run-stale",
            "provider": "codex_local",
            "workspace_path": "C:/workspace/demo",
            "detail": "runner started codex_local",
        },
    )
    assert started.status_code == 200

    store = hub_runtime.coordination._store
    session = store.get_session(chief["session_id"])
    assert session is not None
    member = session.members["runner-a"]
    stale_at = datetime.now(timezone.utc) - timedelta(seconds=400)
    member.last_seen_at = stale_at.isoformat(timespec="microseconds").replace("+00:00", "Z")
    store.update_member(chief["session_id"], member)

    detail = api_client.get(
        f"/sessions/{chief['session_id']}/detail",
        params={"agent_name": "runner-a", "member_token": runner["member_token"]},
    )
    assert detail.status_code == 200
    refreshed_member = next(item for item in detail.json()["session"]["members"] if item["agent_name"] == "runner-a")
    assert refreshed_member["current_run"] is None
    assert refreshed_member["last_run"]["outcome"] == "interrupted"
    assert refreshed_member["status"] == "waiting"
    assert any(event["event"] == "RUN_INTERRUPTED" for event in detail.json()["session"]["history"])


def test_runner_once_processes_task_and_persists_local_state(tmp_path: Path, monkeypatch: Any) -> None:
    config_path = tmp_path / "runner.json"
    config_path.write_text(
        json.dumps(
            {
                "agent_name": "runner-a",
                "hub_http": "http://hub.test",
                "session_id": "session-1",
                "member_token": "member-1",
                "runner_provider": "codex_local",
                "runner_workspace": str(tmp_path / "workspace"),
            }
        ),
        encoding="utf-8",
    )

    emitted: list[dict[str, Any]] = []
    sent_payloads: list[tuple[str, dict[str, Any]]] = []

    class _Result:
        outcome = "success"
        summary = "Implemented the requested change"
        started_at = "2026-03-18T10:00:00.000000Z"
        finished_at = "2026-03-18T10:01:00.000000Z"
        exit_code = 0
        stdout_text = "done"
        stderr_text = ""
        provider_session_id = "provider-session-1"
        provider_session_params = {"command": ["codex", "exec", "--skip-git-repo-check", "-"]}
        metadata = {"exit_code": 0}

    def _fake_post_json(*, hub_http: str, route: str, payload: dict[str, Any], token: str | None = None) -> dict[str, Any]:
        sent_payloads.append((route, dict(payload)))
        if route == "/sessions/status":
            return {"status": "ok", "member": {"status": payload["status"]}}
        if route == "/sessions/wait":
            return {
                "status": "message",
                "message": {
                    "id": "msg-1",
                    "from": "chief",
                    "to": "runner-a",
                    "action": "TASK",
                    "payload": json.dumps(
                        {
                            "task_id": "task-123",
                            "instructions": "Implement the runner integration",
                            "metadata": {"priority": "high"},
                        }
                    ),
                },
            }
        if route == "/sessions/runs/events":
            return {"status": "ok", "member": {"status": "busy"}}
        if route == "/sessions/send":
            return {"status": "queued", "delivery": "queued"}
        raise AssertionError(route)

    monkeypatch.setattr(acp_cli, "post_json", _fake_post_json)
    monkeypatch.setattr(acp_cli, "emit_json_line", lambda payload: emitted.append(dict(payload)))
    monkeypatch.setattr(acp_cli, "execute_provider", lambda **kwargs: _Result())

    args = argparse.Namespace(
        command="runner",
        runner_command="once",
        config=str(config_path),
        join_code=None,
        name=None,
        hub_http=None,
        token=None,
        provider="codex_local",
        workspace=str(tmp_path / "workspace"),
        session_id=None,
        member_token=None,
        wait_timeout_seconds=5.0,
        task_timeout_seconds=30.0,
    )

    result = acp_cli.runner_once(args)
    assert result["status"] == "runner_completed"
    assert result["outcome"] == "success"

    send_route, send_payload = next(item for item in sent_payloads if item[0] == "/sessions/send")
    assert send_route == "/sessions/send"
    assert send_payload["payload"]["task_id"] == "task-123"
    assert send_payload["payload"]["outcome"] == "success"
    assert send_payload["payload"]["run_id"]

    state_path = tmp_path / ".acp_runner_state.json"
    persisted = json.loads(state_path.read_text(encoding="utf-8"))
    entries = persisted["entries"]
    assert len(entries) == 1
    entry = next(iter(entries.values()))
    assert entry["provider_session_id"] == "provider-session-1"
    assert entry["last_run_status"] == "success"
    assert entry["last_run_started_at"] == "2026-03-18T10:00:00.000000Z"
    assert entry["last_run_finished_at"] == "2026-03-18T10:01:00.000000Z"
    assert emitted[-1]["status"] == "runner_completed"
