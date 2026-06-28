from __future__ import annotations

import argparse
import importlib.util
import json
import sys
from pathlib import Path
from typing import Any

repo_root = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(repo_root / "ACP_AGENT"))
_ACP_SPEC = importlib.util.spec_from_file_location("acp_agent_cli_ux", repo_root / "ACP_AGENT" / "acp.py")
assert _ACP_SPEC is not None and _ACP_SPEC.loader is not None
acp_cli = importlib.util.module_from_spec(_ACP_SPEC)
sys.modules[_ACP_SPEC.name] = acp_cli
_ACP_SPEC.loader.exec_module(acp_cli)


def test_resolve_cli_config_path_uses_single_available_config(tmp_path: Path, monkeypatch: Any) -> None:
    agents_dir = tmp_path / "agents"
    agents_dir.mkdir(parents=True)
    config_path = agents_dir / "codex-chief.json"
    config_path.write_text("{}", encoding="utf-8")
    monkeypatch.setattr(acp_cli, "ACP_ROOT", tmp_path)

    resolved = acp_cli.resolve_cli_config_path(
        config_path=None,
        agent_name=None,
        command_name="session-info",
    )

    assert resolved == config_path.resolve()


def test_resolve_cli_config_path_requires_selector_with_multiple_configs(tmp_path: Path, monkeypatch: Any) -> None:
    agents_dir = tmp_path / "agents"
    agents_dir.mkdir(parents=True)
    (agents_dir / "codex-chief.json").write_text("{}", encoding="utf-8")
    (agents_dir / "claude-review.json").write_text("{}", encoding="utf-8")
    monkeypatch.setattr(acp_cli, "ACP_ROOT", tmp_path)

    try:
        acp_cli.resolve_cli_config_path(
            config_path=None,
            agent_name=None,
            command_name="listen",
        )
    except ValueError as exc:
        message = str(exc)
    else:
        raise AssertionError("expected ValueError when multiple configs exist without selector")

    assert "--agent <name>" in message
    assert "codex-chief" in message
    assert "claude-review" in message


def test_runner_start_accepts_pure_flags_and_creates_config(tmp_path: Path, monkeypatch: Any) -> None:
    monkeypatch.setattr(acp_cli, "ACP_ROOT", tmp_path)

    profile = acp_cli.bootstrap_runner_session(
        argparse.Namespace(
            command="runner",
            runner_command="start",
            config=None,
            agent="worker-1",
            hub_http="https://hub.example",
            hub_ws=None,
            token=None,
            provider="claude_local",
            workspace=str(tmp_path),
            session_id="session-1",
            member_token="member-1",
            join_code=None,
            wait_timeout_seconds=120.0,
            task_timeout_seconds=1800.0,
            retry_delay_seconds=2.0,
        ),
        command_name="runner start",
    )

    config_path = tmp_path / "agents" / "worker-1.json"
    saved = json.loads(config_path.read_text(encoding="utf-8"))
    assert profile["settings"].config_path == config_path.resolve()
    assert saved["agent_name"] == "worker-1"
    assert saved["hub_http"] == "https://hub.example"
    assert saved["delivery_mode"] == "runner"
    assert saved["runner_provider"] == "claude_local"
    assert saved["session_id"] == "session-1"
    assert saved["member_token"] == "member-1"


def test_task_and_reply_shortcuts_force_expected_action(monkeypatch: Any) -> None:
    seen: list[tuple[str, str]] = []

    def _fake_dispatch(args: argparse.Namespace) -> dict[str, Any]:
        seen.append((args.action, args.payload))
        return {"status": "ok", "action": args.action, "payload": args.payload}

    monkeypatch.setattr(acp_cli, "dispatch_send", _fake_dispatch)

    task_result = acp_cli.task_from_args(
        argparse.Namespace(
            command="task",
            config=None,
            agent="chief",
            to="worker",
            payload=None,
            text=["Review", "auth"],
            thread_id=None,
            in_reply_to=None,
        )
    )
    reply_result = acp_cli.reply_from_args(
        argparse.Namespace(
            command="reply",
            config=None,
            agent="worker",
            to="chief",
            payload="Done",
            text=[],
            thread_id=None,
            in_reply_to=None,
        )
    )

    assert task_result["action"] == "TASK"
    assert reply_result["action"] == "REPLY"
    assert seen == [("TASK", "Review auth"), ("REPLY", "Done")]


def test_create_session_and_optionally_listen_emits_payload_and_starts_listener(monkeypatch: Any, tmp_path: Path) -> None:
    emitted: list[dict[str, Any]] = []
    listened: list[tuple[Path, str, str]] = []
    config_path = tmp_path / "agents" / "chief.json"
    config_path.parent.mkdir(parents=True)
    config_path.write_text("{}", encoding="utf-8")

    monkeypatch.setattr(acp_cli, "create_session_from_args", lambda args: {"status": "ok", "session_id": "session-1"})
    monkeypatch.setattr(acp_cli, "emit_json_line", lambda payload: emitted.append(dict(payload)))
    monkeypatch.setattr(
        acp_cli,
        "resolve_cli_config_path",
        lambda **kwargs: config_path,
    )
    monkeypatch.setattr(
        acp_cli,
        "maybe_start_listen_after_session",
        lambda *, config_path, mode, command_name: listened.append((config_path, mode, command_name)),
    )

    payload = acp_cli.create_session_and_optionally_listen(
        argparse.Namespace(command="start", config=None, agent="chief"),
        listen_after=True,
    )

    assert payload["session_id"] == "session-1"
    assert emitted == [{"status": "ok", "session_id": "session-1"}]
    assert listened == [(config_path, "persistent", "start")]


def test_managed_start_persists_binding_and_uses_workspace_token(monkeypatch: Any, tmp_path: Path) -> None:
    config_path = tmp_path / "agents" / "codex-chief.json"
    config_path.parent.mkdir(parents=True)
    config_path.write_text(
        json.dumps(
            {
                "agent_name": "codex-chief",
                "hub_http": "https://hub.example",
                "hub_ws": "wss://hub.example/ws",
            },
            ensure_ascii=True,
        ),
        encoding="utf-8",
    )

    captured: dict[str, Any] = {}

    def _fake_request_json(**kwargs: Any) -> dict[str, Any]:
        captured.update(kwargs)
        return {
            "workspace": {"slug": "team-one"},
            "workspace_session": {"session_id": "session-1"},
            "agent_token": {"label": "codex-chief"},
            "acp_session": {
                "status": "created",
                "session_id": "session-1",
                "member_token": "member-1",
                "join_code": "JOIN123",
                "member_role": "chief",
                "session": {"session_id": "session-1"},
            },
        }

    monkeypatch.setattr(acp_cli, "request_json", _fake_request_json)
    monkeypatch.setattr(acp_cli, "safe_update_session_status", lambda **kwargs: None)

    payload = acp_cli.managed_start_from_args(
        argparse.Namespace(
            command="managed-start",
            config=str(config_path),
            agent=None,
            hub_http=None,
            hub_ws=None,
            token=None,
            workspace="team-one",
            agent_token="acpagt_secret",
            title="Sprint",
            project="ACP",
            no_listen=False,
        )
    )

    saved = json.loads(config_path.read_text(encoding="utf-8"))
    assert captured["url"] == "https://hub.example/managed/agent/workspaces/team-one/sessions"
    assert captured["headers"]["Authorization"] == "Bearer acpagt_secret"
    assert saved["session_id"] == "session-1"
    assert saved["member_token"] == "member-1"
    assert saved["join_code"] == "JOIN123"
    assert saved["managed_agent_token"] == "acpagt_secret"
    assert saved["dashboard_session_path"] == "/managed/dashboard/session"
    assert payload["managed_command"] == "managed-start"
    assert payload["managed_workspace"]["slug"] == "team-one"
    assert payload["session_dashboard_url"].startswith("https://hub.example/managed/dashboard/session?")
    assert payload["session_dashboard_url_template"].startswith("https://hub.example/managed/dashboard/session?")
    assert "member_token=" not in payload["session_dashboard_url"].split("#", 1)[0]
    assert payload["session_dashboard_url"].endswith("#member_token=member-1")
    assert "member_token=" not in payload["session_dashboard_url_template"].split("#", 1)[0]
    assert payload["session_dashboard_url_template"].endswith("#member_token=%3Cmember_token%3E")


def test_managed_start_creates_chief_config_from_pure_flags(monkeypatch: Any, tmp_path: Path) -> None:
    monkeypatch.setattr(acp_cli, "ACP_ROOT", tmp_path)
    captured: dict[str, Any] = {}

    def _fake_request_json(**kwargs: Any) -> dict[str, Any]:
        captured.update(kwargs)
        return {
            "workspace": {"slug": "team-one"},
            "workspace_session": {"session_id": "session-chief"},
            "agent_token": {"label": "arch-lead"},
            "acp_session": {
                "status": "created",
                "session_id": "session-chief",
                "member_token": "chief-member",
                "join_code": "JOIN123",
                "member_role": "chief",
            },
        }

    monkeypatch.setattr(acp_cli, "request_json", _fake_request_json)
    monkeypatch.setattr(acp_cli, "safe_update_session_status", lambda **kwargs: None)

    payload = acp_cli.managed_start_from_args(
        argparse.Namespace(
            command="managed-start",
            config=None,
            agent="arch-lead",
            hub_http="https://hub.example",
            hub_ws=None,
            token=None,
            workspace=None,
            agent_token="acpagt_secret",
            title="Competition",
            project="cauce",
            no_listen=True,
        )
    )

    config_path = tmp_path / "agents" / "arch-lead.json"
    saved = json.loads(config_path.read_text(encoding="utf-8"))
    assert captured["url"] == "https://hub.example/managed/agent/sessions"
    assert payload["session_id"] == "session-chief"
    assert saved["agent_name"] == "arch-lead"
    assert saved["hub_http"] == "https://hub.example"
    assert saved["session_id"] == "session-chief"
    assert saved["member_token"] == "chief-member"
    assert saved["managed_agent_token"] == "acpagt_secret"


def test_managed_join_and_optionally_listen_emits_payload_without_listener_by_default(monkeypatch: Any, tmp_path: Path) -> None:
    emitted: list[dict[str, Any]] = []
    listened: list[tuple[Path, str, str]] = []
    config_path = tmp_path / "agents" / "helper.json"
    config_path.parent.mkdir(parents=True)
    config_path.write_text("{}", encoding="utf-8")

    monkeypatch.setattr(acp_cli, "managed_join_from_args", lambda args: {"status": "joined", "session_id": "session-2"})
    monkeypatch.setattr(acp_cli, "emit_json_line", lambda payload: emitted.append(dict(payload)))
    monkeypatch.setattr(acp_cli, "resolve_cli_config_path", lambda **kwargs: config_path)
    monkeypatch.setattr(
        acp_cli,
        "maybe_start_listen_after_session",
        lambda *, config_path, mode, command_name: listened.append((config_path, mode, command_name)),
    )

    payload = acp_cli.managed_join_and_optionally_listen(
        argparse.Namespace(command="managed-join", config=None, agent="helper"),
        listen_mode="none",
    )

    assert payload["session_id"] == "session-2"
    assert emitted == [{"status": "joined", "session_id": "session-2"}]
    assert listened == [(config_path, "none", "managed-join")]


def test_managed_join_publishes_and_persists_capabilities(monkeypatch: Any, tmp_path: Path) -> None:
    config_path = tmp_path / "agents" / "helper.json"
    config_path.parent.mkdir(parents=True)
    config_path.write_text(
        json.dumps({"agent_name": "helper", "hub_http": "https://hub.example", "managed_agent_token": "acpagt_secret"}),
        encoding="utf-8",
    )
    captured: dict[str, Any] = {}

    def _fake_request_json(**kwargs: Any) -> dict[str, Any]:
        captured.update(kwargs)
        return {
            "workspace": {"slug": "team-one"},
            "workspace_session": {"session_id": "session-2"},
            "agent_token": {"label": "helper"},
            "acp_session": {
                "session_id": "session-2",
                "member_token": "member-token",
                "join_code": "ABC123",
                "member_role": "member",
            },
        }

    monkeypatch.setattr(acp_cli, "request_json", _fake_request_json)

    payload = acp_cli.managed_join_from_args(
        argparse.Namespace(
            command="managed-join",
            config=str(config_path),
            agent=None,
            hub_http=None,
            hub_ws=None,
            token=None,
            workspace=None,
            agent_token=None,
            session_id="session-2",
            capabilities="backend,python",
        )
    )

    assert captured["payload"]["capabilities"] == ["backend", "python"]
    assert payload["managed_command"] == "managed-join"
    saved = json.loads(config_path.read_text(encoding="utf-8"))
    assert saved["capabilities"] == ["backend", "python"]


def test_managed_join_listen_once_uses_stop_after_message(monkeypatch: Any, tmp_path: Path) -> None:
    seen: list[argparse.Namespace] = []
    config_path = tmp_path / "agents" / "helper.json"
    config_path.parent.mkdir(parents=True)
    config_path.write_text("{}", encoding="utf-8")

    monkeypatch.setattr(acp_cli, "listen_for_session_message", lambda args: seen.append(args))

    acp_cli.maybe_start_listen_after_session(
        config_path=config_path,
        mode="once",
        command_name="managed-join",
    )

    assert len(seen) == 1
    assert seen[0].stop_after_message is True
    assert seen[0].timeout_seconds == acp_cli.DEFAULT_LISTEN_TIMEOUT_SECONDS


def test_managed_join_listen_mode_defaults_to_none() -> None:
    assert acp_cli._managed_join_listen_mode(
        argparse.Namespace(listen_once=False, listen_persistent=False, no_listen=False)
    ) == "none"
    assert acp_cli._managed_join_listen_mode(
        argparse.Namespace(listen_once=True, listen_persistent=False, no_listen=False)
    ) == "once"
    assert acp_cli._managed_join_listen_mode(
        argparse.Namespace(listen_once=False, listen_persistent=True, no_listen=False)
    ) == "persistent"


def test_managed_sessions_from_args_uses_bearer_token(monkeypatch: Any, tmp_path: Path) -> None:
    config_path = tmp_path / "agents" / "helper.json"
    config_path.parent.mkdir(parents=True)
    config_path.write_text(
        json.dumps({"agent_name": "helper", "hub_http": "https://hub.example"}, ensure_ascii=True),
        encoding="utf-8",
    )
    captured: dict[str, Any] = {}

    def _fake_request_json(**kwargs: Any) -> dict[str, Any]:
        captured.update(kwargs)
        return {"sessions": [], "count": 0}

    monkeypatch.setattr(acp_cli, "request_json", _fake_request_json)

    payload = acp_cli.managed_sessions_from_args(
        argparse.Namespace(
            command="managed-sessions",
            config=str(config_path),
            agent=None,
            hub_http=None,
            token=None,
            workspace="team-one",
            agent_token="acpagt_secret",
        )
    )

    assert captured["method"] == "GET"
    assert captured["url"] == "https://hub.example/managed/agent/workspaces/team-one/sessions"
    assert captured["headers"]["Authorization"] == "Bearer acpagt_secret"
    assert payload["managed_command"] == "managed-sessions"


def test_managed_sessions_accepts_pure_flags_with_multiple_configs(monkeypatch: Any, tmp_path: Path) -> None:
    monkeypatch.setattr(acp_cli, "ACP_ROOT", tmp_path)
    agents_dir = tmp_path / "agents"
    agents_dir.mkdir(parents=True)
    (agents_dir / "executor-a.json").write_text(json.dumps({"agent_name": "executor-a"}), encoding="utf-8")
    (agents_dir / "executor-b.json").write_text(json.dumps({"agent_name": "executor-b"}), encoding="utf-8")
    captured: dict[str, Any] = {}

    def _fake_request_json(**kwargs: Any) -> dict[str, Any]:
        captured.update(kwargs)
        return {"sessions": [], "count": 0}

    monkeypatch.setattr(acp_cli, "request_json", _fake_request_json)

    payload = acp_cli.managed_sessions_from_args(
        argparse.Namespace(
            command="managed-sessions",
            config=None,
            agent=None,
            hub_http="https://hub.example",
            token=None,
            workspace=None,
            agent_token="acpagt_secret",
        )
    )

    assert captured["url"] == "https://hub.example/managed/agent/sessions"
    assert payload["managed_command"] == "managed-sessions"


def test_managed_sessions_can_use_token_from_selected_config(monkeypatch: Any, tmp_path: Path) -> None:
    config_path = tmp_path / "agents" / "executor-a.json"
    config_path.parent.mkdir(parents=True)
    config_path.write_text(
        json.dumps(
            {
                "agent_name": "executor-a",
                "hub_http": "https://hub.example",
                "managed_agent_token": "acpagt_config_secret",
            },
            ensure_ascii=True,
        ),
        encoding="utf-8",
    )
    captured: dict[str, Any] = {}

    def _fake_request_json(**kwargs: Any) -> dict[str, Any]:
        captured.update(kwargs)
        return {"sessions": [], "count": 0}

    monkeypatch.setattr(acp_cli, "request_json", _fake_request_json)

    payload = acp_cli.managed_sessions_from_args(
        argparse.Namespace(
            command="managed-sessions",
            config=str(config_path),
            agent=None,
            hub_http=None,
            token=None,
            workspace=None,
            agent_token=None,
        )
    )

    assert captured["headers"]["Authorization"] == "Bearer acpagt_config_secret"
    assert payload["managed_command"] == "managed-sessions"


def test_managed_close_accepts_pure_flags_without_existing_config(monkeypatch: Any, tmp_path: Path) -> None:
    monkeypatch.setattr(acp_cli, "ACP_ROOT", tmp_path)
    captured: dict[str, Any] = {}

    def _fake_request_json(**kwargs: Any) -> dict[str, Any]:
        captured.update(kwargs)
        return {"status": "closed", "workspace": {"slug": "team-one"}}

    monkeypatch.setattr(acp_cli, "request_json", _fake_request_json)

    payload = acp_cli.managed_close_from_args(
        argparse.Namespace(
            command="managed-close",
            config=None,
            agent="cleanup-agent",
            hub_http="https://hub.example",
            token=None,
            workspace="team-one",
            agent_token="acpagt_secret",
            session_id="session-1",
            detail="cleanup",
        )
    )

    assert captured["method"] == "POST"
    assert captured["url"] == "https://hub.example/managed/agent/workspaces/team-one/sessions/session-1/close"
    assert captured["headers"]["Authorization"] == "Bearer acpagt_secret"
    assert captured["payload"] == {"detail": "cleanup"}
    assert payload["managed_command"] == "managed-close"


def test_onboard_worker_joins_project_session_announces_ready_and_prepares_runner(monkeypatch: Any, tmp_path: Path) -> None:
    monkeypatch.setattr(acp_cli, "ACP_ROOT", tmp_path)
    monkeypatch.setattr(acp_cli, "safe_update_session_status", lambda **kwargs: None)
    captured_requests: list[dict[str, Any]] = []
    captured_posts: list[dict[str, Any]] = []

    def _fake_request_json(**kwargs: Any) -> dict[str, Any]:
        captured_requests.append(dict(kwargs))
        url = str(kwargs["url"])
        if url.endswith("/managed/agent/bootstrap"):
            return {"status": "ok"}
        if url.endswith("/managed/agent/workspaces/team-one/sessions") and kwargs["method"] == "GET":
            return {
                "workspace": {"slug": "team-one"},
                "sessions": [
                    {
                        "session_id": "session-1",
                        "owner_agent_name": "chief-agent",
                        "title": "Sprint",
                        "project": "ACP",
                        "created_at": "2026-05-30T00:00:00Z",
                    }
                ],
                "count": 1,
            }
        if url.endswith("/managed/agent/workspaces/team-one/sessions/session-1/join"):
            return {
                "workspace": {"slug": "team-one"},
                "workspace_session": {"session_id": "session-1", "project": "ACP"},
                "acp_session": {
                    "session_id": "session-1",
                    "member_token": "member-1",
                    "member_role": "member",
                    "join_code": "ABCD12",
                },
                "agent_token": {"redacted": True},
            }
        raise AssertionError(f"unexpected request_json call: {kwargs}")

    def _fake_post_json(**kwargs: Any) -> dict[str, Any]:
        captured_posts.append(dict(kwargs))
        return {"status": "ok"}

    monkeypatch.setattr(acp_cli, "request_json", _fake_request_json)
    monkeypatch.setattr(acp_cli, "post_json", _fake_post_json)

    payload = acp_cli.onboard_from_args(
        argparse.Namespace(
            command="onboard",
            config=None,
            agent="worker-1",
            hub_http="https://hub.example",
            hub_ws=None,
            token=None,
            workspace=str(tmp_path),
            managed_workspace="team-one",
            agent_token="acpagt_secret",
            session_id=None,
            project="ACP",
            role="worker",
            provider="claude_local",
            wait_for_session=0.0,
            prefer_latest=False,
            to=None,
            skip_ready=False,
            start_runner=False,
            wait_timeout_seconds=120.0,
            task_timeout_seconds=1800.0,
            retry_delay_seconds=2.0,
        )
    )

    config_path = tmp_path / "agents" / "worker-1.json"
    saved = json.loads(config_path.read_text(encoding="utf-8"))
    assert saved["session_id"] == "session-1"
    assert saved["member_token"] == "member-1"
    assert saved["managed_agent_token"] == "acpagt_secret"
    assert saved["delivery_mode"] == "runner"
    assert saved["runner_provider"] == "claude_local"
    assert payload["status"] == "onboarded"
    assert payload["ready_sent"] is True
    assert payload["ready_to"] == "chief-agent"
    assert payload["runner_command"][-2:] == ["--config", str(config_path.resolve())]
    ready_call = next(item for item in captured_posts if item["route"] == "/sessions/send")
    assert ready_call["payload"]["to"] == "chief-agent"
    assert ready_call["payload"]["action"] == "INFO"
    assert ready_call["payload"]["payload"]["type"] == "READY"
    assert ready_call["payload"]["payload"]["delivery_mode"] == "runner"
    status_call = next(item for item in captured_posts if item["route"] == "/sessions/status")
    assert status_call["payload"]["status"] == "waiting"
    assert captured_requests[0]["url"] == "https://hub.example/managed/agent/bootstrap"


def test_onboard_project_id_prefers_acp_project_file(tmp_path: Path) -> None:
    project_dir = tmp_path / "repo"
    (project_dir / ".acp").mkdir(parents=True)
    (project_dir / ".acp" / "project-id").write_text("cauce-router\n", encoding="utf-8")

    assert acp_cli.derive_onboard_project_id(str(project_dir), None) == "cauce-router"


def test_onboard_session_selection_requires_disambiguation_for_multiple_project_matches() -> None:
    sessions = [
        {"session_id": "older", "project": "ACP", "created_at": "2026-05-30T00:00:00Z"},
        {"session_id": "newer", "project": "ACP", "created_at": "2026-05-30T01:00:00Z"},
    ]

    try:
        acp_cli.select_onboard_workspace_session(
            sessions,
            session_id=None,
            project="ACP",
            prefer_latest=False,
        )
    except ValueError as exc:
        message = str(exc)
    else:
        raise AssertionError("expected ambiguous project matches to fail without --session-id or --prefer-latest")

    assert "multiple managed workspace sessions matched" in message
    assert acp_cli.select_onboard_workspace_session(
        sessions,
        session_id=None,
        project="ACP",
        prefer_latest=True,
    )["session_id"] == "newer"


def test_chief_once_dispatches_pending_file_to_waiting_worker(monkeypatch: Any, tmp_path: Path) -> None:
    config_path = tmp_path / "agents" / "chief.json"
    config_path.parent.mkdir(parents=True)
    config_path.write_text(
        json.dumps(
            {
                "agent_name": "chief",
                "hub_http": "https://hub.example",
                "session_id": "session-1",
                "member_token": "chief-token",
            }
        ),
        encoding="utf-8",
    )
    backlog_dir = tmp_path / "coord" / "backlog"
    backlog_dir.mkdir(parents=True)
    (backlog_dir / "fix-auth.task.md").write_text("Fix auth regression and run tests.", encoding="utf-8")
    captured_posts: list[dict[str, Any]] = []

    def _fake_get_json(**kwargs: Any) -> dict[str, Any]:
        assert kwargs["route"].startswith("/sessions/session-1")
        return {
            "status": "ok",
            "session": {
                "session_id": "session-1",
                "members": [
                    {"agent_name": "chief", "role": "chief", "status": "waiting", "heartbeat_state": "live"},
                    {
                        "agent_name": "worker-1",
                        "role": "member",
                        "status": "waiting",
                        "heartbeat_state": "live",
                        "pending_count": 0,
                        "delivery_mode": "runner",
                    },
                ],
            },
        }

    def _fake_post_json(**kwargs: Any) -> dict[str, Any]:
        captured_posts.append(dict(kwargs))
        return {"status": "sent", "delivery": "queued"}

    monkeypatch.setattr(acp_cli, "get_json", _fake_get_json)
    monkeypatch.setattr(acp_cli, "post_json", _fake_post_json)
    monkeypatch.setattr(acp_cli, "safe_update_session_status", lambda **kwargs: None)

    payload = acp_cli.chief_once(
        argparse.Namespace(
            command="chief",
            chief_command="once",
            config=str(config_path),
            agent=None,
            hub_http=None,
            hub_ws=None,
            token=None,
            backlog_dir=str(backlog_dir),
            workspace=str(tmp_path),
            provider="claude_local",
            wait_timeout_seconds=0.0,
            tick_seconds=0.0,
        )
    )

    assert payload["status"] == "chief_tick"
    assert payload["dispatched_count"] == 1
    assert payload["dispatched"][0]["worker"] == "worker-1"
    assert not (backlog_dir / "fix-auth.task.md").exists()
    assert (backlog_dir / "assigned" / "fix-auth.task.md").exists()
    send_call = next(item for item in captured_posts if item["route"] == "/sessions/send")
    assert send_call["payload"]["to"] == "worker-1"
    assert send_call["payload"]["action"] == "TASK"
    task_payload = json.loads(send_call["payload"]["payload"])
    assert task_payload["task_id"] == "fix-auth"
    assert task_payload["instructions"] == "Fix auth regression and run tests."
    assert task_payload["reply_to"] == "chief"
    assert task_payload["provider"] == "claude_local"


def test_chief_once_prefers_worker_matching_required_capabilities(monkeypatch: Any, tmp_path: Path) -> None:
    config_path = tmp_path / "agents" / "chief.json"
    config_path.parent.mkdir(parents=True)
    config_path.write_text(
        json.dumps(
            {
                "agent_name": "chief",
                "hub_http": "https://hub.example",
                "session_id": "session-1",
                "member_token": "chief-token",
            }
        ),
        encoding="utf-8",
    )
    backlog_dir = tmp_path / "coord" / "backlog"
    backlog_dir.mkdir(parents=True)
    (backlog_dir / "api.json").write_text(
        json.dumps(
            {
                "task_id": "api",
                "instructions": "Implement API endpoint.",
                "required_capabilities": ["backend"],
            }
        ),
        encoding="utf-8",
    )
    captured_posts: list[dict[str, Any]] = []

    def _fake_get_json(**kwargs: Any) -> dict[str, Any]:
        return {
            "status": "ok",
            "session": {
                "session_id": "session-1",
                "members": [
                    {"agent_name": "chief", "role": "chief", "status": "waiting", "heartbeat_state": "live"},
                    {
                        "agent_name": "worker-a",
                        "role": "member",
                        "status": "waiting",
                        "heartbeat_state": "live",
                        "pending_count": 0,
                        "capabilities": ["frontend"],
                    },
                    {
                        "agent_name": "worker-b",
                        "role": "member",
                        "status": "waiting",
                        "heartbeat_state": "live",
                        "pending_count": 0,
                        "capabilities": ["backend", "python"],
                    },
                ],
            },
        }

    def _fake_post_json(**kwargs: Any) -> dict[str, Any]:
        captured_posts.append(dict(kwargs))
        return {"status": "sent", "delivery": "queued"}

    monkeypatch.setattr(acp_cli, "get_json", _fake_get_json)
    monkeypatch.setattr(acp_cli, "post_json", _fake_post_json)
    monkeypatch.setattr(acp_cli, "safe_update_session_status", lambda **kwargs: None)

    payload = acp_cli.chief_once(
        argparse.Namespace(
            command="chief",
            chief_command="once",
            config=str(config_path),
            agent=None,
            hub_http=None,
            hub_ws=None,
            token=None,
            backlog_dir=str(backlog_dir),
            workspace=str(tmp_path),
            provider="claude_local",
            wait_timeout_seconds=0.0,
            tick_seconds=0.0,
        )
    )

    assert payload["dispatched"][0]["worker"] == "worker-b"
    assert payload["dispatched"][0]["required_capabilities"] == ["backend"]
    assert payload["dispatched"][0]["worker_capabilities"] == ["backend", "python"]
    send_call = next(item for item in captured_posts if item["route"] == "/sessions/send")
    assert send_call["payload"]["to"] == "worker-b"
    task_payload = json.loads(send_call["payload"]["payload"])
    assert task_payload["required_capabilities"] == ["backend"]


def test_chief_once_dispatches_at_most_one_task_per_worker_per_tick(monkeypatch: Any, tmp_path: Path) -> None:
    config_path = tmp_path / "agents" / "chief.json"
    config_path.parent.mkdir(parents=True)
    config_path.write_text(
        json.dumps(
            {
                "agent_name": "chief",
                "hub_http": "https://hub.example",
                "session_id": "session-1",
                "member_token": "chief-token",
            }
        ),
        encoding="utf-8",
    )
    backlog_dir = tmp_path / "coord" / "backlog"
    backlog_dir.mkdir(parents=True)
    (backlog_dir / "first.task.md").write_text("First task.", encoding="utf-8")
    (backlog_dir / "second.task.md").write_text("Second task.", encoding="utf-8")
    captured_posts: list[dict[str, Any]] = []

    monkeypatch.setattr(
        acp_cli,
        "get_json",
        lambda **kwargs: {
            "status": "ok",
            "session": {
                "session_id": "session-1",
                "members": [
                    {"agent_name": "chief", "role": "chief", "status": "waiting", "heartbeat_state": "live"},
                    {
                        "agent_name": "worker-1",
                        "role": "member",
                        "status": "waiting",
                        "heartbeat_state": "live",
                        "pending_count": 0,
                    },
                ],
            },
        },
    )
    monkeypatch.setattr(acp_cli, "post_json", lambda **kwargs: captured_posts.append(dict(kwargs)) or {"status": "sent"})
    monkeypatch.setattr(acp_cli, "safe_update_session_status", lambda **kwargs: None)

    payload = acp_cli.chief_once(
        argparse.Namespace(
            command="chief",
            chief_command="once",
            config=str(config_path),
            agent=None,
            hub_http=None,
            hub_ws=None,
            token=None,
            backlog_dir=str(backlog_dir),
            workspace=str(tmp_path),
            provider="claude_local",
            wait_timeout_seconds=0.0,
            tick_seconds=0.0,
        )
    )

    assert payload["dispatched_count"] == 1
    assert len(list((backlog_dir / "assigned").glob("*.task.md"))) == 1
    assert len([item for item in captured_posts if item["route"] == "/sessions/send"]) == 1
    assert len(list(backlog_dir.glob("*.task.md"))) == 1


def test_chief_once_does_not_dispatch_to_waiting_worker_with_current_task(monkeypatch: Any, tmp_path: Path) -> None:
    config_path = tmp_path / "agents" / "chief.json"
    config_path.parent.mkdir(parents=True)
    config_path.write_text(
        json.dumps(
            {
                "agent_name": "chief",
                "hub_http": "https://hub.example",
                "session_id": "session-1",
                "member_token": "chief-token",
            }
        ),
        encoding="utf-8",
    )
    backlog_dir = tmp_path / "coord" / "backlog"
    backlog_dir.mkdir(parents=True)
    (backlog_dir / "next.task.md").write_text("Next task.", encoding="utf-8")

    monkeypatch.setattr(
        acp_cli,
        "get_json",
        lambda **kwargs: {
            "status": "ok",
            "session": {
                "session_id": "session-1",
                "members": [
                    {"agent_name": "chief", "role": "chief", "status": "waiting", "heartbeat_state": "live"},
                    {
                        "agent_name": "worker-1",
                        "role": "member",
                        "status": "waiting",
                        "heartbeat_state": "live",
                        "pending_count": 0,
                        "current_task": "already-assigned",
                    },
                ],
            },
        },
    )
    monkeypatch.setattr(acp_cli, "post_json", lambda **kwargs: {"status": "sent"})
    monkeypatch.setattr(acp_cli, "safe_update_session_status", lambda **kwargs: None)

    payload = acp_cli.chief_once(
        argparse.Namespace(
            command="chief",
            chief_command="once",
            config=str(config_path),
            agent=None,
            hub_http=None,
            hub_ws=None,
            token=None,
            backlog_dir=str(backlog_dir),
            workspace=str(tmp_path),
            provider="claude_local",
            wait_timeout_seconds=0.0,
            tick_seconds=0.0,
        )
    )

    assert payload["dispatched_count"] == 0
    assert (backlog_dir / "next.task.md").exists()


def test_chief_once_records_runner_reply_and_moves_assigned_task(monkeypatch: Any, tmp_path: Path) -> None:
    config_path = tmp_path / "agents" / "chief.json"
    config_path.parent.mkdir(parents=True)
    config_path.write_text(
        json.dumps(
            {
                "agent_name": "chief",
                "hub_http": "https://hub.example",
                "session_id": "session-1",
                "member_token": "chief-token",
            }
        ),
        encoding="utf-8",
    )
    backlog_dir = tmp_path / "coord" / "backlog"
    assigned_dir = backlog_dir / "assigned"
    assigned_dir.mkdir(parents=True)
    (assigned_dir / "fix-auth.task.md").write_text("Fix auth regression.", encoding="utf-8")

    def _fake_post_json(**kwargs: Any) -> dict[str, Any]:
        if kwargs["route"] == "/sessions/wait":
            return {
                "status": "message",
                "message": {
                    "id": "msg-1",
                    "from": "worker-1",
                    "to": "chief",
                    "action": "REPLY",
                    "payload": {
                        "task_id": "fix-auth",
                        "outcome": "success",
                        "summary": "Tests pass.",
                    },
                },
            }
        return {"status": "ok"}

    def _fake_get_json(**kwargs: Any) -> dict[str, Any]:
        return {
            "status": "ok",
            "session": {
                "session_id": "session-1",
                "members": [{"agent_name": "chief", "role": "chief", "status": "waiting"}],
            },
        }

    monkeypatch.setattr(acp_cli, "post_json", _fake_post_json)
    monkeypatch.setattr(acp_cli, "get_json", _fake_get_json)
    monkeypatch.setattr(acp_cli, "safe_update_session_status", lambda **kwargs: None)

    payload = acp_cli.chief_once(
        argparse.Namespace(
            command="chief",
            chief_command="once",
            config=str(config_path),
            agent=None,
            hub_http=None,
            hub_ws=None,
            token=None,
            backlog_dir=str(backlog_dir),
            workspace=None,
            provider=None,
            wait_timeout_seconds=1.0,
            tick_seconds=0.0,
        )
    )

    assert payload["message_result"]["status"] == "recorded"
    assert payload["message_result"]["outcome"] == "success"
    assert not (assigned_dir / "fix-auth.task.md").exists()
    assert (backlog_dir / "done" / "fix-auth.task.md").exists()
    result_files = list((backlog_dir / "done").glob("fix-auth.result*.json"))
    assert result_files


def test_chief_once_infers_missing_reply_task_id_from_worker_assignment(monkeypatch: Any, tmp_path: Path) -> None:
    config_path = tmp_path / "agents" / "chief.json"
    config_path.parent.mkdir(parents=True)
    config_path.write_text(
        json.dumps(
            {
                "agent_name": "chief",
                "hub_http": "https://hub.example",
                "session_id": "session-1",
                "member_token": "chief-token",
            }
        ),
        encoding="utf-8",
    )
    backlog_dir = tmp_path / "coord" / "backlog"
    assigned_dir = backlog_dir / "assigned"
    assigned_dir.mkdir(parents=True)
    (assigned_dir / "fix-auth.task.md").write_text("Fix auth regression.", encoding="utf-8")
    (assigned_dir / "fix-auth.assignment.json").write_text(
        json.dumps({"task_id": "fix-auth", "worker": "worker-1", "task_file": "fix-auth.task.md"}),
        encoding="utf-8",
    )

    monkeypatch.setattr(
        acp_cli,
        "post_json",
        lambda **kwargs: {
            "status": "message",
            "message": {
                "id": "msg-1",
                "from": "worker-1",
                "to": "chief",
                "action": "REPLY",
                "payload": {"outcome": "success", "summary": "Tests pass."},
            },
        }
        if kwargs["route"] == "/sessions/wait"
        else {"status": "ok"},
    )
    monkeypatch.setattr(
        acp_cli,
        "get_json",
        lambda **kwargs: {
            "status": "ok",
            "session": {"session_id": "session-1", "members": [{"agent_name": "chief", "role": "chief", "status": "waiting"}]},
        },
    )
    monkeypatch.setattr(acp_cli, "safe_update_session_status", lambda **kwargs: None)

    payload = acp_cli.chief_once(
        argparse.Namespace(
            command="chief",
            chief_command="once",
            config=str(config_path),
            agent=None,
            hub_http=None,
            hub_ws=None,
            token=None,
            backlog_dir=str(backlog_dir),
            workspace=None,
            provider=None,
            wait_timeout_seconds=1.0,
            tick_seconds=0.0,
        )
    )

    assert payload["message_result"]["task_id"] == "fix-auth"
    assert payload["message_result"]["inferred_task_id"] is True
    assert (backlog_dir / "done" / "fix-auth.task.md").exists()


def test_chief_once_infers_done_text_and_moves_assignment(monkeypatch: Any, tmp_path: Path) -> None:
    config_path = tmp_path / "agents" / "chief.json"
    config_path.parent.mkdir(parents=True)
    config_path.write_text(
        json.dumps(
            {
                "agent_name": "chief",
                "hub_http": "https://hub.example",
                "session_id": "session-1",
                "member_token": "chief-token",
            }
        ),
        encoding="utf-8",
    )
    backlog_dir = tmp_path / "coord" / "backlog"
    assigned_dir = backlog_dir / "assigned"
    assigned_dir.mkdir(parents=True)
    (assigned_dir / "df-2.task.md").write_text("Review the UX flow.", encoding="utf-8")
    (assigned_dir / "df-2.assignment.json").write_text(
        json.dumps({"task_id": "df-2", "worker": "worker-1", "task_file": "df-2.task.md"}),
        encoding="utf-8",
    )

    monkeypatch.setattr(
        acp_cli,
        "post_json",
        lambda **kwargs: {
            "status": "message",
            "message": {
                "id": "msg-1",
                "from": "worker-1",
                "to": "chief",
                "action": "REPLY",
                "payload": "DONE reviewed the full flow.",
            },
        }
        if kwargs["route"] == "/sessions/wait"
        else {"status": "ok"},
    )
    monkeypatch.setattr(
        acp_cli,
        "get_json",
        lambda **kwargs: {
            "status": "ok",
            "session": {"session_id": "session-1", "members": [{"agent_name": "chief", "role": "chief", "status": "waiting"}]},
        },
    )
    monkeypatch.setattr(acp_cli, "safe_update_session_status", lambda **kwargs: None)

    payload = acp_cli.chief_once(
        argparse.Namespace(
            command="chief",
            chief_command="once",
            config=str(config_path),
            agent=None,
            hub_http=None,
            hub_ws=None,
            token=None,
            backlog_dir=str(backlog_dir),
            workspace=None,
            provider=None,
            wait_timeout_seconds=1.0,
            tick_seconds=0.0,
        )
    )

    assert payload["message_result"]["task_id"] == "df-2"
    assert payload["message_result"]["outcome"] == "success"
    assert payload["message_result"]["inferred_outcome"] is True
    assert not (assigned_dir / "df-2.assignment.json").exists()
    assert (backlog_dir / "done" / "df-2.assignment.json").exists()
    assert (backlog_dir / "done" / "df-2.task.md").exists()


def test_chief_once_finds_assigned_task_via_assignment_metadata(monkeypatch: Any, tmp_path: Path) -> None:
    config_path = tmp_path / "agents" / "chief.json"
    config_path.parent.mkdir(parents=True)
    config_path.write_text(
        json.dumps(
            {
                "agent_name": "chief",
                "hub_http": "https://hub.example",
                "session_id": "session-1",
                "member_token": "chief-token",
            }
        ),
        encoding="utf-8",
    )
    backlog_dir = tmp_path / "coord" / "backlog"
    assigned_dir = backlog_dir / "assigned"
    assigned_dir.mkdir(parents=True)
    (assigned_dir / "human-title.md").write_text("Task file name does not include task_id.", encoding="utf-8")
    (assigned_dir / "df-3.assignment.json").write_text(
        json.dumps({"task_id": "df-3", "worker": "worker-1", "task_file": "human-title.md"}),
        encoding="utf-8",
    )

    monkeypatch.setattr(
        acp_cli,
        "post_json",
        lambda **kwargs: {
            "status": "message",
            "message": {
                "id": "msg-1",
                "from": "worker-1",
                "to": "chief",
                "action": "REPLY",
                "payload": {"task_id": "df-3", "outcome": "success", "summary": "Done."},
            },
        }
        if kwargs["route"] == "/sessions/wait"
        else {"status": "ok"},
    )
    monkeypatch.setattr(
        acp_cli,
        "get_json",
        lambda **kwargs: {
            "status": "ok",
            "session": {"session_id": "session-1", "members": [{"agent_name": "chief", "role": "chief", "status": "waiting"}]},
        },
    )
    monkeypatch.setattr(acp_cli, "safe_update_session_status", lambda **kwargs: None)

    payload = acp_cli.chief_once(
        argparse.Namespace(
            command="chief",
            chief_command="once",
            config=str(config_path),
            agent=None,
            hub_http=None,
            hub_ws=None,
            token=None,
            backlog_dir=str(backlog_dir),
            workspace=None,
            provider=None,
            wait_timeout_seconds=1.0,
            tick_seconds=0.0,
        )
    )

    assert payload["message_result"]["task_id"] == "df-3"
    assert payload["message_result"]["verify_result"]["reason"] == "no_verify_command"
    assert (backlog_dir / "done" / "human-title.md").exists()
    assert not (assigned_dir / "df-3.assignment.json").exists()


def test_replay_uses_managed_session_surface_without_admin_token(monkeypatch: Any, tmp_path: Path) -> None:
    config_path = tmp_path / "agents" / "chief.json"
    config_path.parent.mkdir(parents=True)
    config_path.write_text(
        json.dumps(
            {
                "agent_name": "chief",
                "hub_http": "https://hub.example",
                "session_id": "session-1",
                "member_token": "chief-member-token",
                "managed_agent_token": "managed-token",
            }
        ),
        encoding="utf-8",
    )
    calls: list[dict[str, Any]] = []

    def _fake_request_json(**kwargs: Any) -> dict[str, Any]:
        calls.append(kwargs)
        return {"events": [{"event_type": "message_sent"}], "next_cursor": None, "order": "desc", "limit": 5}

    monkeypatch.setattr(acp_cli, "request_json", _fake_request_json)

    payload = acp_cli.cmd_replay(
        argparse.Namespace(
            command="replay",
            config=str(config_path),
            agent=None,
            hub_http=None,
            token=None,
            agent_token=None,
            session_id=None,
            from_ts=None,
            to_ts=None,
            actor="worker",
            action="REPLY",
            event_type=None,
            message_id=None,
            thread_id=None,
            order="desc",
            limit="5",
            cursor=None,
        )
    )

    assert payload["managed"] is True
    assert payload["session_id"] == "session-1"
    assert calls[0]["url"] == "https://hub.example/managed/agent/sessions/session-1/replay?actor=worker&action=REPLY&order=desc&limit=5"
    assert calls[0]["headers"]["Authorization"] == "Bearer managed-token"


def test_chief_once_requeues_expired_assignments(monkeypatch: Any, tmp_path: Path) -> None:
    config_path = tmp_path / "agents" / "chief.json"
    config_path.parent.mkdir(parents=True)
    config_path.write_text(
        json.dumps(
            {
                "agent_name": "chief",
                "hub_http": "https://hub.example",
                "session_id": "session-1",
                "member_token": "chief-token",
            }
        ),
        encoding="utf-8",
    )
    backlog_dir = tmp_path / "coord" / "backlog"
    assigned_dir = backlog_dir / "assigned"
    assigned_dir.mkdir(parents=True)
    (assigned_dir / "stale.task.md").write_text("Run stale task.", encoding="utf-8")
    old_timestamp = "2026-01-01T00:00:00Z"
    (assigned_dir / "stale.assignment.json").write_text(
        json.dumps({"task_id": "stale", "worker": "worker-1", "task_file": "stale.task.md", "assigned_at": old_timestamp}),
        encoding="utf-8",
    )

    monkeypatch.setattr(
        acp_cli,
        "get_json",
        lambda **kwargs: {
            "status": "ok",
            "session": {"session_id": "session-1", "members": [{"agent_name": "chief", "role": "chief", "status": "waiting"}]},
        },
    )
    monkeypatch.setattr(acp_cli, "post_json", lambda **kwargs: {"status": "ok"})
    monkeypatch.setattr(acp_cli, "safe_update_session_status", lambda **kwargs: None)

    payload = acp_cli.chief_once(
        argparse.Namespace(
            command="chief",
            chief_command="once",
            config=str(config_path),
            agent=None,
            hub_http=None,
            hub_ws=None,
            token=None,
            backlog_dir=str(backlog_dir),
            workspace=None,
            provider=None,
            wait_timeout_seconds=0.0,
            tick_seconds=0.0,
            assignment_ttl_seconds=1.0,
        )
    )

    assert payload["expired_assignment_count"] == 1
    assert payload["expired_assignments"][0]["task_id"] == "stale"
    assert not (assigned_dir / "stale.assignment.json").exists()
    assert not (assigned_dir / "stale.task.md").exists()
    assert (backlog_dir / "stale.task.md").exists()
    assert list((backlog_dir / "failed").glob("stale.result*.json"))


def test_chief_once_requeues_successful_reply_when_verification_fails(monkeypatch: Any, tmp_path: Path) -> None:
    config_path = tmp_path / "agents" / "chief.json"
    config_path.parent.mkdir(parents=True)
    config_path.write_text(
        json.dumps(
            {
                "agent_name": "chief",
                "hub_http": "https://hub.example",
                "session_id": "session-1",
                "member_token": "chief-token",
            }
        ),
        encoding="utf-8",
    )
    backlog_dir = tmp_path / "coord" / "backlog"
    assigned_dir = backlog_dir / "assigned"
    assigned_dir.mkdir(parents=True)
    (assigned_dir / "fix-auth.json").write_text(
        json.dumps(
            {
                "task_id": "fix-auth",
                "instructions": "Fix auth regression.",
                "verify_command": [sys.executable, "-c", "raise SystemExit(7)"],
                "verify_timeout_seconds": 5,
            }
        ),
        encoding="utf-8",
    )
    captured_posts: list[dict[str, Any]] = []

    def _fake_post_json(**kwargs: Any) -> dict[str, Any]:
        captured_posts.append(dict(kwargs))
        if kwargs["route"] == "/sessions/wait":
            return {
                "status": "message",
                "message": {
                    "id": "msg-1",
                    "from": "worker-1",
                    "to": "chief",
                    "action": "REPLY",
                    "payload": {
                        "task_id": "fix-auth",
                        "outcome": "success",
                        "summary": "Fixed.",
                    },
                },
            }
        return {"status": "sent"}

    def _fake_get_json(**kwargs: Any) -> dict[str, Any]:
        return {
            "status": "ok",
            "session": {
                "session_id": "session-1",
                "members": [
                    {"agent_name": "chief", "role": "chief", "status": "waiting", "heartbeat_state": "live"},
                    {
                        "agent_name": "worker-1",
                        "role": "member",
                        "status": "waiting",
                        "heartbeat_state": "live",
                        "pending_count": 0,
                    },
                ],
            },
        }

    monkeypatch.setattr(acp_cli, "post_json", _fake_post_json)
    monkeypatch.setattr(acp_cli, "get_json", _fake_get_json)
    monkeypatch.setattr(acp_cli, "safe_update_session_status", lambda **kwargs: None)

    payload = acp_cli.chief_once(
        argparse.Namespace(
            command="chief",
            chief_command="once",
            config=str(config_path),
            agent=None,
            hub_http=None,
            hub_ws=None,
            token=None,
            backlog_dir=str(backlog_dir),
            workspace=None,
            provider=None,
            wait_timeout_seconds=1.0,
            tick_seconds=0.0,
        )
    )

    assert payload["message_result"]["outcome"] == "verification_failed"
    assert payload["message_result"]["verify_result"]["exit_code"] == 7
    assert payload["dispatched_count"] == 1
    assert payload["message_result"]["requeued_task_file"]
    assigned_task = assigned_dir / "fix-auth.json"
    assert assigned_task.exists()
    failed_results = list((backlog_dir / "failed").glob("fix-auth.result*.json"))
    assert failed_results
    send_call = next(item for item in captured_posts if item["route"] == "/sessions/send")
    task_payload = json.loads(send_call["payload"]["payload"])
    assert task_payload["task_id"] == "fix-auth"
    assert "Chief verification failed" in task_payload["instructions"]
    assert "Original instructions" in task_payload["instructions"]


def test_chief_once_requeues_when_semantic_judge_rejects(monkeypatch: Any, tmp_path: Path) -> None:
    config_path = tmp_path / "agents" / "chief.json"
    config_path.parent.mkdir(parents=True)
    config_path.write_text(
        json.dumps(
            {
                "agent_name": "chief",
                "hub_http": "https://hub.example",
                "session_id": "session-1",
                "member_token": "chief-token",
            }
        ),
        encoding="utf-8",
    )
    backlog_dir = tmp_path / "coord" / "backlog"
    assigned_dir = backlog_dir / "assigned"
    assigned_dir.mkdir(parents=True)
    (assigned_dir / "review.json").write_text(
        json.dumps(
            {
                "task_id": "review",
                "instructions": "Review ACP onboarding UX.",
                "acceptance_criteria": "The reply must include concrete UX fixes and evidence.",
                "judge_provider": "codex_local",
                "judge_timeout_seconds": 10,
            }
        ),
        encoding="utf-8",
    )
    captured_posts: list[dict[str, Any]] = []

    def _fake_execute_provider(**kwargs: Any) -> argparse.Namespace:
        assert kwargs["provider"] == "codex_local"
        assert "concrete UX fixes" in kwargs["instructions"]
        return argparse.Namespace(
            outcome="success",
            exit_code=0,
            stdout_text='{"pass": false, "feedback": "Add evidence and exact reproduction steps."}',
            stderr_text="",
            provider_session_id=None,
            provider_session_params={},
            metadata={},
        )

    def _fake_post_json(**kwargs: Any) -> dict[str, Any]:
        captured_posts.append(dict(kwargs))
        if kwargs["route"] == "/sessions/wait":
            return {
                "status": "message",
                "message": {
                    "id": "msg-1",
                    "from": "worker-1",
                    "to": "chief",
                    "action": "REPLY",
                    "payload": {
                        "task_id": "review",
                        "outcome": "success",
                        "summary": "Looks good.",
                    },
                },
            }
        return {"status": "sent"}

    def _fake_get_json(**kwargs: Any) -> dict[str, Any]:
        return {
            "status": "ok",
            "session": {
                "session_id": "session-1",
                "members": [
                    {"agent_name": "chief", "role": "chief", "status": "waiting", "heartbeat_state": "live"},
                    {
                        "agent_name": "worker-1",
                        "role": "member",
                        "status": "waiting",
                        "heartbeat_state": "live",
                        "pending_count": 0,
                    },
                ],
            },
        }

    monkeypatch.setattr(acp_cli, "execute_provider", _fake_execute_provider)
    monkeypatch.setattr(acp_cli, "post_json", _fake_post_json)
    monkeypatch.setattr(acp_cli, "get_json", _fake_get_json)
    monkeypatch.setattr(acp_cli, "safe_update_session_status", lambda **kwargs: None)

    payload = acp_cli.chief_once(
        argparse.Namespace(
            command="chief",
            chief_command="once",
            config=str(config_path),
            agent=None,
            hub_http=None,
            hub_ws=None,
            token=None,
            backlog_dir=str(backlog_dir),
            workspace=None,
            provider=None,
            wait_timeout_seconds=1.0,
            tick_seconds=0.0,
        )
    )

    assert payload["message_result"]["outcome"] == "judge_failed"
    assert payload["message_result"]["judge_result"]["feedback"] == "Add evidence and exact reproduction steps."
    assert payload["message_result"]["requeued_task_file"]
    assert payload["dispatched_count"] == 1
    assigned_task = assigned_dir / "review.json"
    assert assigned_task.exists()
    requeued_payload = json.loads(assigned_task.read_text(encoding="utf-8"))
    assert requeued_payload["metadata"]["feedback_count"] == 1
    assert requeued_payload["metadata"]["judge_history"][0]["status"] == "failed"
    send_call = next(item for item in captured_posts if item["route"] == "/sessions/send")
    task_payload = json.loads(send_call["payload"]["payload"])
    assert "Add evidence and exact reproduction steps" in task_payload["instructions"]
    assert task_payload["acceptance_criteria"] == "The reply must include concrete UX fixes and evidence."


def test_chief_once_marks_judge_failure_failed_when_attempts_exhausted(monkeypatch: Any, tmp_path: Path) -> None:
    config_path = tmp_path / "agents" / "chief.json"
    config_path.parent.mkdir(parents=True)
    config_path.write_text(
        json.dumps(
            {
                "agent_name": "chief",
                "hub_http": "https://hub.example",
                "session_id": "session-1",
                "member_token": "chief-token",
            }
        ),
        encoding="utf-8",
    )
    backlog_dir = tmp_path / "coord" / "backlog"
    assigned_dir = backlog_dir / "assigned"
    assigned_dir.mkdir(parents=True)
    (assigned_dir / "review.json").write_text(
        json.dumps(
            {
                "task_id": "review",
                "instructions": "Review ACP onboarding UX.",
                "acceptance_criteria": "Must include exact reproduction steps.",
                "judge_provider": "codex_local",
                "max_attempts": 2,
                "metadata": {"feedback_count": 1},
            }
        ),
        encoding="utf-8",
    )

    monkeypatch.setattr(
        acp_cli,
        "execute_provider",
        lambda **kwargs: argparse.Namespace(
            outcome="success",
            exit_code=0,
            stdout_text='{"pass": false, "feedback": "Still missing reproduction steps."}',
            stderr_text="",
            provider_session_id=None,
            provider_session_params={},
            metadata={},
        ),
    )
    monkeypatch.setattr(
        acp_cli,
        "post_json",
        lambda **kwargs: {
            "status": "message",
            "message": {
                "id": "msg-1",
                "from": "worker-1",
                "to": "chief",
                "action": "REPLY",
                "payload": {"task_id": "review", "outcome": "success", "summary": "Done."},
            },
        }
        if kwargs["route"] == "/sessions/wait"
        else {"status": "sent"},
    )
    monkeypatch.setattr(
        acp_cli,
        "get_json",
        lambda **kwargs: {
            "status": "ok",
            "session": {
                "session_id": "session-1",
                "members": [{"agent_name": "chief", "role": "chief", "status": "waiting", "heartbeat_state": "live"}],
            },
        },
    )
    monkeypatch.setattr(acp_cli, "safe_update_session_status", lambda **kwargs: None)

    payload = acp_cli.chief_once(
        argparse.Namespace(
            command="chief",
            chief_command="once",
            config=str(config_path),
            agent=None,
            hub_http=None,
            hub_ws=None,
            token=None,
            backlog_dir=str(backlog_dir),
            workspace=None,
            provider=None,
            wait_timeout_seconds=1.0,
            tick_seconds=0.0,
        )
    )

    assert payload["message_result"]["outcome"] == "judge_failed"
    assert payload["message_result"]["attempt_number"] == 2
    assert payload["message_result"]["max_attempts"] == 2
    assert payload["message_result"]["attempts_exhausted"] is True
    assert payload["message_result"]["requeued_task_file"] is None
    assert (backlog_dir / "failed" / "review.json").exists()


def test_connect_existing_chief_is_self_describing(tmp_path: Path) -> None:
    config_path = tmp_path / "agents" / "chief.json"
    config_path.parent.mkdir(parents=True)
    config_path.write_text(
        json.dumps(
            {
                "agent_name": "chief",
                "hub_http": "https://hub.example",
                "session_id": "session-1",
                "member_token": "chief-token",
                "member_role": "chief",
            }
        ),
        encoding="utf-8",
    )

    payload = acp_cli.connect_from_args(
        argparse.Namespace(
            command="connect",
            config=str(config_path),
            agent=None,
            hub_http=None,
            hub_ws=None,
            workspace=None,
            managed_workspace=None,
            agent_token=None,
            session_id=None,
            project=None,
            role="auto",
            capabilities=None,
            provider=None,
            wait_for_session=0.0,
            prefer_latest=False,
            skip_ready=False,
            start_runner=False,
            start_chief=False,
            backlog_dir=None,
            wait_timeout_seconds=0.0,
            task_timeout_seconds=0.0,
            retry_delay_seconds=0.0,
        )
    )

    assert payload["status"] == "connected"
    assert payload["connect_role"] == "chief"
    assert payload["chief_command"][2:4] == ["chief", "start"]


def test_coordinate_connects_worker_then_waits_for_one_message(tmp_path: Path, monkeypatch: Any) -> None:
    config_path = tmp_path / "agents" / "worker-1.json"
    calls: dict[str, argparse.Namespace] = {}

    def fake_connect(args: argparse.Namespace) -> dict[str, Any]:
        calls["connect"] = args
        return {
            "status": "onboarded",
            "connect_role": "worker",
            "agent_name": "worker-1",
            "config_path": str(config_path),
        }

    def fake_listen(args: argparse.Namespace) -> dict[str, Any]:
        calls["listen"] = args
        return {"status": "message", "message": {"action": "TASK", "payload": "implement slice"}}

    monkeypatch.setattr(acp_cli, "connect_from_args", fake_connect)
    monkeypatch.setattr(acp_cli, "listen_for_session_message", fake_listen)

    payload = acp_cli.coordinate_from_args(
        argparse.Namespace(
            command="coordinate",
            config=None,
            agent="worker-1",
            hub_http="https://hub.example",
            hub_ws=None,
            workspace=str(tmp_path),
            managed_workspace=None,
            agent_token="managed-token",
            session_id=None,
            project="ACP",
            role="worker",
            capabilities="backend,python",
            provider=None,
            wait_for_session=5.0,
            prefer_latest=True,
            skip_ready=False,
            listen_timeout_seconds=12.5,
            retry_delay_seconds=3.0,
        )
    )

    assert payload["status"] == "message_received"
    assert payload["connect"]["agent_name"] == "worker-1"
    assert payload["message"]["message"]["action"] == "TASK"
    assert calls["connect"].start_runner is False
    assert calls["connect"].start_chief is False
    assert calls["listen"].config == str(config_path)
    assert calls["listen"].stop_after_message is True
    assert calls["listen"].timeout_seconds == 12.5
    assert calls["listen"].retry_delay_seconds == 3.0


def test_coordinate_cli_prints_single_json_payload(tmp_path: Path, monkeypatch: Any, capsys: Any) -> None:
    config_path = tmp_path / "agents" / "worker-1.json"

    monkeypatch.setattr(acp_cli, "ACP_ROOT", tmp_path)
    monkeypatch.setattr(
        acp_cli,
        "connect_from_args",
        lambda args: {
            "status": "onboarded",
            "connect_role": "worker",
            "agent_name": "worker-1",
            "config_path": str(config_path),
        },
    )
    monkeypatch.setattr(
        acp_cli,
        "listen_for_session_message",
        lambda args: {"status": "message", "message": {"action": "INFO", "payload": "hello"}},
    )

    exit_code = acp_cli.main(
        [
            "coordinate",
            "--agent",
            "worker-1",
            "--agent-token",
            "managed-token",
            "--hub-http",
            "https://hub.example",
            "--project",
            "ACP",
        ]
    )

    assert exit_code == 0
    stdout_lines = [line for line in capsys.readouterr().out.splitlines() if line.strip()]
    assert len(stdout_lines) == 1
    payload = json.loads(stdout_lines[0])
    assert payload["status"] == "message_received"
    assert payload["message"]["message"]["action"] == "INFO"


def test_coordinate_allows_missing_named_config_for_first_connect(tmp_path: Path, monkeypatch: Any) -> None:
    monkeypatch.setattr(acp_cli, "ACP_ROOT", tmp_path)

    settings = acp_cli.resolve_hub_agent_settings(
        argparse.Namespace(
            command="coordinate",
            config=None,
            agent="worker-1",
            hub_http="https://hub.example",
            hub_ws=None,
            token=None,
        )
    )

    assert settings.config == {}
    assert settings.agent_name == "worker-1"
    assert settings.config_path == (tmp_path / "agents" / "worker-1.json").resolve()


def test_coordinate_orients_existing_chief_without_waiting(tmp_path: Path, monkeypatch: Any) -> None:
    config_path = tmp_path / "agents" / "chief.json"

    def fake_connect(args: argparse.Namespace) -> dict[str, Any]:
        return {
            "status": "connected",
            "connect_role": "chief",
            "config_path": str(config_path),
            "chief_command": ["python", "ACP_AGENT/acp.py", "chief", "start", "--config", str(config_path)],
        }

    def fail_listen(args: argparse.Namespace) -> dict[str, Any]:
        raise AssertionError("coordinate must not wait as a chief")

    monkeypatch.setattr(acp_cli, "connect_from_args", fake_connect)
    monkeypatch.setattr(acp_cli, "listen_for_session_message", fail_listen)

    payload = acp_cli.coordinate_from_args(
        argparse.Namespace(
            command="coordinate",
            config=str(config_path),
            agent=None,
            hub_http=None,
            hub_ws=None,
            workspace=str(tmp_path),
            managed_workspace=None,
            agent_token=None,
            session_id=None,
            project=None,
            role="auto",
            capabilities=None,
            provider=None,
            wait_for_session=0.0,
            prefer_latest=False,
            skip_ready=False,
            listen_timeout_seconds=12.5,
            retry_delay_seconds=3.0,
        )
    )

    assert payload["status"] == "connected"
    assert payload["coordinate_role"] == "chief"
    assert payload["next_command"][2:4] == ["chief", "start"]


def test_invite_generates_role_aware_prompt_without_config() -> None:
    payload = acp_cli.invite_from_args(
        argparse.Namespace(
            command="invite",
            config=None,
            agent="worker-backend",
            role="worker",
            capabilities="backend,python",
            project="ACP",
            workspace="C:/repo/ACP",
            session_id="session-1",
            hub_http="https://hub.example",
        )
    )

    assert payload["role"] == "worker"
    assert payload["capabilities"] == ["backend", "python"]
    assert "--capabilities backend,python" in payload["command"]
    assert "<MANAGED_TOKEN>" in payload["prompt"]
    assert "esperá TASKs" in payload["prompt"]


def test_no_session_orientation_hint_points_to_connect() -> None:
    message = acp_cli._with_orientation_hint("session_id and member_token are required in config. Create or join a session first.")

    assert "acp.py connect --role worker" in message
    assert "acp.py connect --role chief" in message
    assert "onboard-help" in message


def test_onboard_help_is_self_contained_without_global_skill() -> None:
    payload = acp_cli.onboard_help_from_args(
        argparse.Namespace(command="onboard-help", hub_http="https://hub.example", project="ACP", agent="worker-a")
    )

    assert payload["skill_required"] is False
    assert payload["tool_path"].endswith("acp.py")
    assert payload["bundled_skill_path"].replace("\\", "/").endswith("skills/acp-session-coordinator/SKILL.md")
    assert "connect --role worker" in payload["worker_command"]
    assert "no extra broker is required" in payload["text"]


def test_send_task_id_builds_structured_payload(tmp_path: Path) -> None:
    settings = acp_cli.HubAgentSettings(
        config_path=tmp_path / "agents" / "worker.json",
        config={},
        base_dir=tmp_path,
        agent_name="worker",
        hub_http="https://hub.example",
        hub_ws=None,
        token=None,
        session_id="session-1",
        member_token="member-token",
        dashboard_session_path="/dashboard/session",
    )
    payload = acp_cli.build_session_send_payload(
        argparse.Namespace(
            to="chief",
            action="REPLY",
            payload="Implemented and tested.",
            text=[],
            task_id="task-1",
            thread_id="thread-1",
            in_reply_to="msg-1",
        ),
        settings,
    )

    assert payload["payload"] == {"summary": "Implemented and tested.", "task_id": "task-1"}
    assert payload["thread_id"] == "thread-1"
    assert payload["in_reply_to"] == "msg-1"


def test_chief_wait_self_heals_own_wait_already_active(monkeypatch: Any, tmp_path: Path) -> None:
    config_path = tmp_path / "agents" / "chief.json"
    config_path.parent.mkdir(parents=True)
    config_path.write_text(
        json.dumps(
            {
                "agent_name": "chief",
                "hub_http": "https://hub.example",
                "session_id": "session-1",
                "member_token": "chief-token",
            }
        ),
        encoding="utf-8",
    )
    settings = acp_cli.resolve_hub_agent_settings(argparse.Namespace(command="chief", config=str(config_path), agent=None, hub_http=None, hub_ws=None, token=None))
    dirs = {"base": tmp_path / "coord" / "backlog"}
    calls: list[str] = []

    def _fake_post_json(**kwargs: Any) -> dict[str, Any]:
        calls.append(kwargs["route"])
        if kwargs["route"] == "/sessions/wait" and calls.count("/sessions/wait") == 1:
            raise ValueError("hub HTTP 409: {\"code\":\"WAIT_ALREADY_ACTIVE\"}")
        if kwargs["route"] == "/sessions/cancel-wait":
            return {"status": "cancelled"}
        return {"status": "timeout"}

    monkeypatch.setattr(acp_cli, "post_json", _fake_post_json)

    payload = acp_cli.chief_wait_once_with_self_heal(settings=settings, dirs=dirs, timeout_seconds=1.0)

    assert payload["status"] == "timeout"
    assert payload["self_healed_wait"]["status"] == "cancelled_previous_wait"
    assert calls == ["/sessions/wait", "/sessions/cancel-wait", "/sessions/wait"]


def test_busy_hold_marker_is_detected_inside_json_task_payload() -> None:
    marked = acp_cli._extract_marked_busy_hold(
        json.dumps({"instructions": "[long:5] Probe slow deployment."}),
        default_window_minutes=30.0,
    )
    defaulted = acp_cli._extract_marked_busy_hold(
        json.dumps({"instructions": "[long] Probe slow deployment."}),
        default_window_minutes=12.0,
    )

    assert marked == {"window_minutes": 5.0, "detail": "Probe slow deployment.", "marker": "[long:5]"}
    assert defaulted == {"window_minutes": 12.0, "detail": "Probe slow deployment.", "marker": "[long]"}


def test_update_check_uses_config_hub_manifest(tmp_path: Path, monkeypatch: Any) -> None:
    config_path = tmp_path / "agents" / "worker.json"
    config_path.parent.mkdir(parents=True)
    config_path.write_text(
        json.dumps({"agent_name": "worker", "hub_http": "https://hub.example"}),
        encoding="utf-8",
    )
    captured: dict[str, Any] = {}

    def _fake_check_release_update(*, target_dir: Path, manifest_url: str) -> dict[str, Any]:
        captured["target_dir"] = target_dir
        captured["manifest_url"] = manifest_url
        return {"status": "current", "local_version": "1.0.0", "remote_version": "1.0.0"}

    monkeypatch.setattr(acp_cli, "ACP_ROOT", tmp_path)
    monkeypatch.setattr(acp_cli, "check_release_update", _fake_check_release_update)

    payload = acp_cli.cmd_update_check(
        argparse.Namespace(
            command="update-check",
            config=str(config_path),
            agent=None,
            hub_http=None,
            manifest_url=None,
            token=None,
        )
    )

    assert captured["manifest_url"] == "https://hub.example/downloads/ACP_AGENT.json"
    assert captured["target_dir"] == tmp_path
    assert payload["status"] == "current"
    assert payload["manifest_url"] == "https://hub.example/downloads/ACP_AGENT.json"


def test_idle_update_notify_reports_available_without_applying(tmp_path: Path, monkeypatch: Any) -> None:
    settings = acp_cli.HubAgentSettings(
        config_path=tmp_path / "agents" / "worker.json",
        config={"update_policy": "notify"},
        base_dir=tmp_path,
        agent_name="worker",
        hub_http="https://hub.example",
        hub_ws="wss://hub.example/ws",
        token=None,
        session_id="session-1",
        member_token="member-1",
        dashboard_session_path="/dashboard/session",
    )

    monkeypatch.setattr(
        acp_cli,
        "check_release_update",
        lambda **kwargs: {
            "status": "update_available",
            "local_version": "1.0.0",
            "remote_version": "1.1.0",
            "auto_update": {"safe": True},
        },
    )

    payload = acp_cli.maybe_handle_idle_update(
        settings=settings,
        args=argparse.Namespace(update_policy=None, manifest_url=None, allow_tracked_auto_update=False),
    )

    assert payload == {
        "status": "update_available",
        "local_version": "1.0.0",
        "remote_version": "1.1.0",
        "manifest_url": "https://hub.example/downloads/ACP_AGENT.json",
        "auto_update": {"safe": True},
    }


def test_attach_session_persists_existing_binding(monkeypatch: Any, tmp_path: Path) -> None:
    config_path = tmp_path / "agents" / "chief.json"
    config_path.parent.mkdir(parents=True)
    config_path.write_text(
        json.dumps(
            {
                "agent_name": "codex-chief",
                "hub_http": "https://hub.example",
                "hub_ws": "wss://hub.example/ws",
            },
            ensure_ascii=True,
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr(acp_cli, "safe_update_session_status", lambda **kwargs: None)

    payload = acp_cli.attach_session_from_args(
        argparse.Namespace(
            command="attach-session",
            config=str(config_path),
            agent=None,
            hub_http=None,
            hub_ws=None,
            token=None,
            session_id="session-1",
            member_token="member-1",
            join_code="JOIN123",
            member_role="chief",
            no_listen=False,
        )
    )

    saved = json.loads(config_path.read_text(encoding="utf-8"))
    assert saved["session_id"] == "session-1"
    assert saved["member_token"] == "member-1"
    assert saved["join_code"] == "JOIN123"
    assert saved["member_role"] == "chief"
    assert payload["managed_command"] == "attach-session"
    assert payload["status"] == "attached"


def test_init_from_args_wraps_installer(monkeypatch: Any) -> None:
    captured: dict[str, Any] = {}

    class _Completed:
        returncode = 0
        stdout = json.dumps({"status": "ok", "hub_http": "https://hub.example"})
        stderr = ""

    def _fake_run(command: list[str], **kwargs: Any) -> Any:
        captured["command"] = list(command)
        captured["kwargs"] = dict(kwargs)
        return _Completed()

    monkeypatch.setattr(acp_cli.subprocess, "run", _fake_run)

    result = acp_cli.init_from_args(
        argparse.Namespace(
            command="init",
            hub_mode="custom",
            hub_http="https://hub.example",
            hub_ws="wss://hub.example/ws",
            agent=["codex-chief"],
            token="secret",
            skill_home=None,
            skip_install_deps=True,
            force=True,
            non_interactive=True,
        )
    )

    assert result["status"] == "ok"
    assert "install_from_bundle.py" in " ".join(captured["command"])
    assert "--agent" in captured["command"]
    assert "--hub-http" in captured["command"]
    assert "--skip-install-deps" in captured["command"]
    assert "--non-interactive" in captured["command"]
    assert captured["kwargs"]["capture_output"] is True


def test_listen_clears_stale_binding_and_exits_when_session_is_gone(monkeypatch: Any, tmp_path: Path) -> None:
    # After a Hub redeploy (in-memory store) or a closed session with no live
    # notice, /sessions/wait returns 403 "session does not exist". The listen
    # loop must clear the dead local binding and exit cleanly instead of raising
    # an opaque 403 or looping forever on a stale session_id/member_token.
    monkeypatch.setattr(acp_cli, "ACP_ROOT", tmp_path)
    agents_dir = tmp_path / "agents"
    agents_dir.mkdir(parents=True)
    config_path = agents_dir / "worker-1.json"
    config_path.write_text(
        json.dumps(
            {
                "agent_name": "worker-1",
                "hub_http": "https://hub.example",
                "session_id": "session-gone",
                "member_token": "member-token-123",
            }
        ),
        encoding="utf-8",
    )

    monkeypatch.setattr(acp_cli, "maybe_handle_idle_update", lambda *, settings, args: None)
    monkeypatch.setattr(acp_cli, "safe_update_session_status", lambda **kwargs: None)

    def _session_gone(*args: Any, **kwargs: Any) -> dict[str, Any]:
        raise ValueError(
            'hub HTTP 403: {"code":"INVALID_FIELD","field":"session_id","message":"session does not exist."}'
        )

    monkeypatch.setattr(acp_cli, "post_json", _session_gone)

    result = acp_cli.listen_for_session_message(
        acp_cli._listen_namespace_for_config(config_path, stop_after_message=True)
    )

    assert result["status"] == "session_ended"
    assert result["cleared_local_session"] is True
    saved = json.loads(config_path.read_text(encoding="utf-8"))
    assert "session_id" not in saved
    assert "member_token" not in saved
    assert saved["agent_name"] == "worker-1"


def test_listen_still_raises_on_auth_failure(monkeypatch: Any, tmp_path: Path) -> None:
    # A 401 (bad ACP_TOKEN) is NOT a stale session binding; the loop must keep
    # surfacing it instead of silently clearing credentials.
    monkeypatch.setattr(acp_cli, "ACP_ROOT", tmp_path)
    agents_dir = tmp_path / "agents"
    agents_dir.mkdir(parents=True)
    config_path = agents_dir / "worker-1.json"
    config_path.write_text(
        json.dumps(
            {
                "agent_name": "worker-1",
                "hub_http": "https://hub.example",
                "session_id": "session-1",
                "member_token": "member-token-123",
            }
        ),
        encoding="utf-8",
    )

    monkeypatch.setattr(acp_cli, "maybe_handle_idle_update", lambda *, settings, args: None)
    monkeypatch.setattr(acp_cli, "safe_update_session_status", lambda **kwargs: None)

    def _unauthorized(*args: Any, **kwargs: Any) -> dict[str, Any]:
        raise ValueError('hub HTTP 401: {"message":"token is invalid."}')

    monkeypatch.setattr(acp_cli, "post_json", _unauthorized)

    try:
        acp_cli.listen_for_session_message(
            acp_cli._listen_namespace_for_config(config_path, stop_after_message=True)
        )
    except ValueError as exc:
        assert "hub HTTP 401:" in str(exc)
    else:
        raise AssertionError("expected ValueError on 401 auth failure")

    # Credentials must be preserved on an auth failure.
    saved = json.loads(config_path.read_text(encoding="utf-8"))
    assert saved["session_id"] == "session-1"
    assert saved["member_token"] == "member-token-123"


def test_request_json_retries_transient_gateway_errors(monkeypatch: Any) -> None:
    calls: list[str] = []

    class _ErrorBody:
        def read(self) -> bytes:
            return b'{"status":"error"}'

        def close(self) -> None:
            return None

    class _Response:
        def __enter__(self) -> "_Response":
            return self

        def __exit__(self, *args: object) -> None:
            return None

        def read(self) -> bytes:
            return b'{"status":"ok"}'

    def _urlopen(request: object, timeout: float) -> object:
        calls.append(str(timeout))
        if len(calls) == 1:
            raise acp_cli.urllib.error.HTTPError(
                url="https://hub.example/sessions/wait",
                code=502,
                msg="Bad Gateway",
                hdrs=None,
                fp=_ErrorBody(),
            )
        return _Response()

    monkeypatch.setattr(acp_cli.urllib.request, "urlopen", _urlopen)
    monkeypatch.setattr(acp_cli.time, "sleep", lambda seconds: None)

    result = acp_cli.post_json(
        hub_http="https://hub.example",
        route="/sessions/wait",
        payload={"session_id": "s", "agent_name": "a", "member_token": "m"},
    )

    assert result == {"status": "ok"}
    assert len(calls) == 2


def test_send_route_does_not_retry_transient_gateway_errors(monkeypatch: Any) -> None:
    calls: list[str] = []

    class _ErrorBody:
        def read(self) -> bytes:
            return b'{"status":"error"}'

        def close(self) -> None:
            return None

    def _urlopen(request: object, timeout: float) -> object:
        calls.append(str(timeout))
        raise acp_cli.urllib.error.HTTPError(
            url="https://hub.example/sessions/send",
            code=502,
            msg="Bad Gateway",
            hdrs=None,
            fp=_ErrorBody(),
        )

    monkeypatch.setattr(acp_cli.urllib.request, "urlopen", _urlopen)
    monkeypatch.setattr(acp_cli.time, "sleep", lambda seconds: None)

    try:
        acp_cli.post_json(
            hub_http="https://hub.example",
            route="/sessions/send",
            payload={"session_id": "s", "agent_name": "a", "member_token": "m"},
        )
    except ValueError as exc:
        assert "hub HTTP 502" in str(exc)
    else:
        raise AssertionError("expected transient send failure to surface without retry")

    assert len(calls) == 1


def test_resolve_send_payload_text_reads_from_file(tmp_path: Path) -> None:
    payload_path = tmp_path / "payload.json"
    body = '{"instructions": "ship it", "task_id": "t-1"}'
    payload_path.write_text(body, encoding="utf-8")

    args = argparse.Namespace(payload=None, payload_file=str(payload_path), text=[])

    assert acp_cli.resolve_send_payload_text(args) == body


def test_resolve_send_payload_text_reads_from_stdin_with_dash(monkeypatch: Any) -> None:
    import io

    monkeypatch.setattr(sys, "stdin", io.StringIO('{"summary": "done"}'))
    args = argparse.Namespace(payload=None, payload_file="-", text=[])

    assert acp_cli.resolve_send_payload_text(args) == '{"summary": "done"}'


def test_resolve_send_payload_text_file_takes_precedence_over_payload(tmp_path: Path) -> None:
    payload_path = tmp_path / "p.json"
    payload_path.write_text("from-file", encoding="utf-8")

    args = argparse.Namespace(payload="from-flag", payload_file=str(payload_path), text=[])

    assert acp_cli.resolve_send_payload_text(args) == "from-file"


def test_resolve_send_payload_text_empty_file_raises(tmp_path: Path) -> None:
    payload_path = tmp_path / "empty.txt"
    payload_path.write_text("   ", encoding="utf-8")

    args = argparse.Namespace(payload=None, payload_file=str(payload_path), text=[])

    try:
        acp_cli.resolve_send_payload_text(args)
    except ValueError as exc:
        assert "empty" in str(exc).lower()
    else:
        raise AssertionError("expected ValueError for empty payload file")


def test_resolve_structured_send_payload_parses_json_from_file(tmp_path: Path) -> None:
    payload_path = tmp_path / "task.json"
    payload_path.write_text('{"instructions": "harden auth", "extra": 1}', encoding="utf-8")

    args = argparse.Namespace(
        payload=None,
        payload_file=str(payload_path),
        text=[],
        task_id="task-9",
        action="TASK",
    )

    result = acp_cli.resolve_structured_send_payload(args)

    assert result == {"instructions": "harden auth", "extra": 1, "task_id": "task-9"}


def test_send_parser_accepts_payload_file_without_payload() -> None:
    args = acp_cli.build_parser().parse_args(
        ["send", "--to", "chief", "--action", "REPLY", "--payload-file", "out.json"]
    )

    assert args.payload_file == "out.json"
    assert args.payload is None


def test_task_reply_read_stdin_payload_only_once(monkeypatch: Any) -> None:
    import io

    seen: list[tuple[str, str]] = []

    def _fake_dispatch(args: argparse.Namespace) -> dict[str, Any]:
        # Force the downstream re-resolution path that build_session_send_payload triggers.
        seen.append((args.action, acp_cli.resolve_send_payload_text(args)))
        return {"status": "ok"}

    monkeypatch.setattr(acp_cli, "dispatch_send", _fake_dispatch)
    monkeypatch.setattr(sys, "stdin", io.StringIO("piped-task"))

    acp_cli.task_from_args(
        argparse.Namespace(
            command="task",
            config=None,
            agent="chief",
            to="worker",
            payload=None,
            payload_file="-",
            text=[],
            thread_id=None,
            in_reply_to=None,
        )
    )

    assert seen == [("TASK", "piped-task")]


# --- Local embedded Hub (Fase 1) ---


def test_build_local_hub_command_uses_uvicorn() -> None:
    cmd = acp_cli.build_local_hub_command(host="127.0.0.1", port=8123, python_executable="py")

    assert cmd[:3] == ["py", "-m", "uvicorn"]
    assert "acp.hub.app:app" in cmd
    assert cmd[cmd.index("--host") + 1] == "127.0.0.1"
    assert cmd[cmd.index("--port") + 1] == "8123"


def test_build_local_hub_env_sets_sqlite_backend() -> None:
    env = acp_cli.build_local_hub_env(sqlite_path="/tmp/acp.sqlite3", base_env={"PATH": "x"})

    assert env["ACP_PERSISTENCE_BACKEND"] == "sqlite"
    assert env["ACP_SQLITE_PATH"] == "/tmp/acp.sqlite3"
    assert env["PATH"] == "x"


def test_local_hub_state_roundtrip(tmp_path: Path, monkeypatch: Any) -> None:
    monkeypatch.setattr(acp_cli, "ACP_ROOT", tmp_path)

    assert acp_cli.read_local_hub_state() is None
    acp_cli.write_local_hub_state({"hub_http": "http://127.0.0.1:8000", "pid": 4321})
    state = acp_cli.read_local_hub_state()
    assert state is not None
    assert state["hub_http"] == "http://127.0.0.1:8000"
    assert state["pid"] == 4321
    acp_cli.clear_local_hub_state()
    assert acp_cli.read_local_hub_state() is None


def test_resolve_local_hub_http_returns_url_when_healthy(tmp_path: Path, monkeypatch: Any) -> None:
    monkeypatch.setattr(acp_cli, "ACP_ROOT", tmp_path)
    acp_cli.write_local_hub_state({"hub_http": "http://127.0.0.1:8000", "pid": 1})
    monkeypatch.setattr(acp_cli, "local_hub_health_ok", lambda url, **kw: True)

    assert acp_cli.resolve_local_hub_http() == "http://127.0.0.1:8000"


def test_resolve_local_hub_http_none_when_unhealthy(tmp_path: Path, monkeypatch: Any) -> None:
    monkeypatch.setattr(acp_cli, "ACP_ROOT", tmp_path)
    acp_cli.write_local_hub_state({"hub_http": "http://127.0.0.1:8000", "pid": 1})
    monkeypatch.setattr(acp_cli, "local_hub_health_ok", lambda url, **kw: False)

    assert acp_cli.resolve_local_hub_http() is None


def test_resolve_local_hub_http_none_when_no_state(tmp_path: Path, monkeypatch: Any) -> None:
    monkeypatch.setattr(acp_cli, "ACP_ROOT", tmp_path)

    assert acp_cli.resolve_local_hub_http() is None


def test_ensure_local_hub_running_reuses_healthy(tmp_path: Path, monkeypatch: Any) -> None:
    monkeypatch.setattr(acp_cli, "ACP_ROOT", tmp_path)
    acp_cli.write_local_hub_state({"hub_http": "http://127.0.0.1:8000", "pid": 99})
    monkeypatch.setattr(acp_cli, "local_hub_health_ok", lambda url, **kw: True)

    def _no_spawn(*args: Any, **kwargs: Any) -> Any:
        raise AssertionError("must not spawn when a healthy hub already runs")

    monkeypatch.setattr(acp_cli, "_spawn_local_hub_process", _no_spawn)

    result = acp_cli.ensure_local_hub_running(host="127.0.0.1", port=8000)

    assert result["status"] == "already_running"
    assert result["hub_http"] == "http://127.0.0.1:8000"


def test_ensure_local_hub_running_spawns_when_absent(tmp_path: Path, monkeypatch: Any) -> None:
    monkeypatch.setattr(acp_cli, "ACP_ROOT", tmp_path)
    spawned = {"done": False}

    def fake_health(url: str, **kwargs: Any) -> bool:
        return spawned["done"]

    class FakeProc:
        pid = 555

        def poll(self) -> None:
            return None

    def fake_spawn(command: Any, env: Any) -> Any:
        spawned["done"] = True
        return FakeProc()

    monkeypatch.setattr(acp_cli, "local_hub_health_ok", fake_health)
    monkeypatch.setattr(acp_cli, "_spawn_local_hub_process", fake_spawn)
    monkeypatch.setattr(acp_cli, "local_hub_dependencies_available", lambda: True)

    result = acp_cli.ensure_local_hub_running(
        host="127.0.0.1", port=8000, startup_timeout_seconds=2.0, poll_interval_seconds=0.01
    )

    assert result["status"] == "started"
    assert result["pid"] == 555
    saved = acp_cli.read_local_hub_state()
    assert saved is not None and saved["pid"] == 555


def test_ensure_local_hub_running_errors_without_deps(tmp_path: Path, monkeypatch: Any) -> None:
    monkeypatch.setattr(acp_cli, "ACP_ROOT", tmp_path)
    monkeypatch.setattr(acp_cli, "local_hub_health_ok", lambda url, **kw: False)
    monkeypatch.setattr(acp_cli, "local_hub_dependencies_available", lambda: False)

    try:
        acp_cli.ensure_local_hub_running(host="127.0.0.1", port=8000)
    except ValueError as exc:
        assert "pip install" in str(exc)
    else:
        raise AssertionError("expected ValueError when hub dependencies are missing")


def test_stop_local_hub_terminates_and_clears(tmp_path: Path, monkeypatch: Any) -> None:
    monkeypatch.setattr(acp_cli, "ACP_ROOT", tmp_path)
    acp_cli.write_local_hub_state({"hub_http": "http://127.0.0.1:8000", "pid": 777})
    killed: list[int] = []
    monkeypatch.setattr(acp_cli, "_terminate_pid", lambda pid: killed.append(pid) or True)

    result = acp_cli.stop_local_hub()

    assert result["status"] == "stopped"
    assert killed == [777]
    assert acp_cli.read_local_hub_state() is None


def test_stop_local_hub_when_not_running(tmp_path: Path, monkeypatch: Any) -> None:
    monkeypatch.setattr(acp_cli, "ACP_ROOT", tmp_path)

    assert acp_cli.stop_local_hub()["status"] == "not_running"


def test_resolve_hub_agent_settings_falls_back_to_local_hub(tmp_path: Path, monkeypatch: Any) -> None:
    monkeypatch.setattr(acp_cli, "ACP_ROOT", tmp_path)
    agents_dir = tmp_path / "agents"
    agents_dir.mkdir()
    (agents_dir / "w.json").write_text(json.dumps({"agent_name": "w"}), encoding="utf-8")
    monkeypatch.setattr(acp_cli, "resolve_local_hub_http", lambda: "http://127.0.0.1:8000")

    settings = acp_cli.resolve_hub_agent_settings(
        argparse.Namespace(command="status", config=None, agent="w", hub_http=None, hub_ws=None, token=None),
        require_hub_http=True,
    )

    assert settings.hub_http == "http://127.0.0.1:8000"


def test_hub_parser_has_lifecycle_subcommands() -> None:
    up = acp_cli.build_parser().parse_args(["hub-up", "--port", "8200"])
    assert up.command == "hub-up"
    assert up.port == 8200

    down = acp_cli.build_parser().parse_args(["hub-down"])
    assert down.command == "hub-down"

    status = acp_cli.build_parser().parse_args(["hub-status"])
    assert status.command == "hub-status"


def _patch_quickstart_installer(monkeypatch: Any, tmp_path: Path) -> dict[str, Any]:
    import install_from_bundle as installer

    captured: dict[str, Any] = {}
    monkeypatch.setattr(installer, "ensure_runtime_dependencies", lambda **k: {"installed": False})
    monkeypatch.setattr(installer, "resolve_skill_homes", lambda args: [tmp_path / "skills_home"])
    monkeypatch.setattr(
        installer, "install_skill", lambda *, skill_home, force: skill_home / "acp-session-coordinator"
    )

    def fake_init(*, acp_root: Any, hub_mode: str, hub_http: str, hub_ws: str, agent_names: Any, token: Any, force: bool) -> Any:
        captured["hub_mode"] = hub_mode
        captured["hub_http"] = hub_http
        captured["agent_names"] = list(agent_names)
        return acp_root

    monkeypatch.setattr(installer, "initialize_agent_folder", fake_init)
    monkeypatch.setattr(installer, "write_bundle_info", lambda **k: {"installed_version": "test"})
    return captured


def test_quickstart_local_provisions_and_starts_hub(tmp_path: Path, monkeypatch: Any) -> None:
    monkeypatch.setattr(acp_cli, "ACP_ROOT", tmp_path)
    captured = _patch_quickstart_installer(monkeypatch, tmp_path)
    monkeypatch.setattr(
        acp_cli,
        "ensure_local_hub_running",
        lambda *, host, port, **k: {"status": "started", "hub_http": f"http://{host}:{port}", "pid": 4242},
    )

    result = acp_cli.quickstart_from_args(
        argparse.Namespace(
            command="quickstart",
            agent=["dev"],
            host="127.0.0.1",
            port=8090,
            token=None,
            skill_home=None,
            claude_skill_home=None,
            skip_install_deps=False,
        )
    )

    assert result["status"] == "ok"
    assert result["mode"] == "local"
    assert result["hub_http"] == "http://127.0.0.1:8090"
    assert result["hub"]["status"] == "started"
    assert result["agents"] == ["dev"]
    assert captured["hub_mode"] == "local"
    assert captured["hub_http"] == "http://127.0.0.1:8090"
    assert captured["agent_names"] == ["dev"]


def test_quickstart_reports_hub_start_failure_gracefully(tmp_path: Path, monkeypatch: Any) -> None:
    monkeypatch.setattr(acp_cli, "ACP_ROOT", tmp_path)
    _patch_quickstart_installer(monkeypatch, tmp_path)

    def _raise(**kwargs: Any) -> Any:
        raise ValueError("Local hub requires the hub package. Install it with: python -m pip install -e apps/hub")

    monkeypatch.setattr(acp_cli, "ensure_local_hub_running", _raise)

    result = acp_cli.quickstart_from_args(
        argparse.Namespace(
            command="quickstart",
            agent=["dev"],
            host="127.0.0.1",
            port=8000,
            token=None,
            skill_home=None,
            claude_skill_home=None,
            skip_install_deps=False,
        )
    )

    assert result["status"] == "ok"
    assert result["hub"]["status"] == "not_started"
    assert "pip install" in result["hub"]["detail"]


def test_quickstart_parser() -> None:
    args = acp_cli.build_parser().parse_args(["quickstart", "--agent", "dev", "--port", "8090"])
    assert args.command == "quickstart"
    assert args.agent == ["dev"]
    assert args.port == 8090


def test_terminate_pid_returns_false_when_taskkill_fails(monkeypatch: Any) -> None:
    import subprocess as sp

    monkeypatch.setattr(acp_cli.os, "name", "nt")
    monkeypatch.setattr(acp_cli.subprocess, "run", lambda *a, **k: sp.CompletedProcess(a[0] if a else [], 1))

    assert acp_cli._terminate_pid(999999) is False


def test_terminate_pid_returns_true_when_taskkill_succeeds(monkeypatch: Any) -> None:
    import subprocess as sp

    monkeypatch.setattr(acp_cli.os, "name", "nt")
    monkeypatch.setattr(acp_cli.subprocess, "run", lambda *a, **k: sp.CompletedProcess(a[0] if a else [], 0))

    assert acp_cli._terminate_pid(4321) is True


def test_reconnect_backoff_escalates_when_hello_keeps_failing(tmp_path: Path, monkeypatch: Any) -> None:
    import asyncio

    runtime = acp_cli.ACPClientRuntime(
        agent_name="a",
        hub_ws="ws://hub.invalid/ws",
        inbox_dir=tmp_path / "inbox",
        outbox_dir=tmp_path / "outbox",
        sent_dir=tmp_path / "sent",
        token="bad-token",
        backoff=(0.5, 1.0, 2.0),
    )

    sleeps: list[float] = []

    async def fake_connect(attempt: int) -> object:
        return object()  # pretend the TCP connect always succeeds

    async def fake_hello(*args: Any, **kwargs: Any) -> None:
        raise RuntimeError("hello rejected")  # the session never becomes productive

    async def fake_close(*args: Any, **kwargs: Any) -> None:
        return None

    async def fake_sleep(delay: float) -> None:
        sleeps.append(delay)
        if len(sleeps) >= 3:
            runtime.stop()

    monkeypatch.setattr(runtime, "_connect_or_backoff", fake_connect)
    monkeypatch.setattr(acp_cli, "register_hello", fake_hello)
    monkeypatch.setattr(acp_cli, "safe_close", fake_close)
    monkeypatch.setattr(acp_cli.asyncio, "sleep", fake_sleep)

    asyncio.run(runtime.run())

    # Bug: attempt resets to 0 on every successful TCP connect, so a connect that
    # immediately fails HELLO never escalates -> [0.5, 0.5, 0.5] (hub spam on bad token).
    # Correct: backoff escalates while HELLO keeps failing.
    assert sleeps == [0.5, 1.0, 2.0]
