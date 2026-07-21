from __future__ import annotations

import argparse
import importlib.util
import json
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

import pytest


repo_root = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(repo_root / "ACP_AGENT"))
from host_bridge import AdapterRegistry, HostManifest, HostResult
_SPEC = importlib.util.spec_from_file_location("acp_plan_transport", repo_root / "ACP_AGENT" / "acp.py")
assert _SPEC is not None and _SPEC.loader is not None
acp_cli = importlib.util.module_from_spec(_SPEC)
sys.modules[_SPEC.name] = acp_cli
_SPEC.loader.exec_module(acp_cli)


def _definition() -> dict[str, Any]:
    return {
        "plan_id": "desktop-plan",
        "tasks": [
            {"task_id": "worker-task", "owner": "worker", "instructions": "Run worker task", "status": "dispatched"},
            {"task_id": "desktop-next", "owner": "codex-coordinator", "instructions": "Continue the roadmap", "depends_on": ["worker-task"]},
        ],
    }


def _config(tmp_path: Path) -> Path:
    definition = tmp_path / "definition.json"
    definition.write_text(json.dumps(_definition()), encoding="utf-8")
    config = {
        "agent_name": "reply-collector",
        "hub_http": "https://hub.example",
        "session_id": "room-1",
        "member_token": "member-token",
        "reply_collector_forward_to": "codex-coordinator",
        "reply_collector_allowed_senders": ["worker"],
        "reply_collector_forward_action": "TASK",
        "reply_collector_state_path": str(tmp_path / "collector-state.json"),
        "coordinator_plan_definition_path": str(definition),
        "coordinator_plan_state_path": str(tmp_path / "plan-state.json"),
    }
    path = tmp_path / "collector.json"
    path.write_text(json.dumps(config), encoding="utf-8")
    return path


def _args(path: Path) -> argparse.Namespace:
    return argparse.Namespace(
        config=str(path), agent=None, forward_to=None, collector_allowed_senders=None,
        state_path=None, forward_action=None, wait_timeout_seconds=0.1,
        retry_delay_seconds=0.01, plan_definition=None, plan_state=None,
    )


def _reply() -> dict[str, Any]:
    return {
        "status": "message",
        "message": {"id": "reply-1", "session_id": "room-1", "from": "worker", "to": "reply-collector", "action": "REPLY", "payload": json.dumps({"task_id": "worker-task", "outcome": "success"})},
        "delivery": {"ack_required": True, "message_id": "reply-1", "receipt_handle": "receipt-1"},
    }


class FakeHub:
    def __init__(self, responses: list[dict[str, Any]]) -> None:
        self.responses = list(responses)
        self.calls: list[tuple[str, dict[str, Any]]] = []
        self.ids: set[str] = set()
        self.fail_ack_once = False
        self.fail_send = False

    def __call__(self, *, route: str, payload: dict[str, Any], **_kwargs: Any) -> dict[str, Any]:
        self.calls.append((route, payload))
        if route == "/sessions/wait":
            return self.responses.pop(0)
        if route == "/sessions/send":
            if self.fail_send:
                return {"status": "error"}
            duplicate = payload["id"] in self.ids
            self.ids.add(payload["id"])
            return {"message_id": payload["id"], "delivery": "duplicate" if duplicate else "queued"}
        if route == "/sessions/ack":
            if self.fail_ack_once:
                self.fail_ack_once = False
                return {"status": "error"}
            return {"status": "acknowledged", "message_id": payload["message_id"]}
        raise AssertionError(route)


def test_reply_result_emits_one_dependency_ready_task_before_ack(tmp_path: Path, monkeypatch: Any) -> None:
    profile = acp_cli.resolve_reply_collector_profile(_args(_config(tmp_path)))
    hub = FakeHub([_reply()])
    monkeypatch.setattr(acp_cli, "post_json", hub)

    result = acp_cli._reply_collector_once(profile)

    assert result["status"] == "completed"
    assert [route for route, _ in hub.calls] == ["/sessions/wait", "/sessions/send", "/sessions/ack"]
    sent = hub.calls[1][1]
    assert sent["to"] == "codex-coordinator"
    assert sent["action"] == "TASK"
    assert json.loads(sent["payload"])["task_id"] == "desktop-next"


def test_ack_crash_retries_same_task_id_without_duplicate_turn(tmp_path: Path, monkeypatch: Any) -> None:
    profile = acp_cli.resolve_reply_collector_profile(_args(_config(tmp_path)))
    hub = FakeHub([_reply(), _reply()])
    hub.fail_ack_once = True
    monkeypatch.setattr(acp_cli, "post_json", hub)

    with pytest.raises(acp_cli.CollectorDeliveryError, match="did not confirm"):
        acp_cli._reply_collector_once(profile)
    assert acp_cli._reply_collector_once(profile)["status"] == "completed"

    sends = [payload for route, payload in hub.calls if route == "/sessions/send"]
    assert len(sends) == 2
    assert sends[0]["id"] == sends[1]["id"]


def test_plan_send_failure_keeps_source_unacked_and_plan_pending(tmp_path: Path, monkeypatch: Any) -> None:
    profile = acp_cli.resolve_reply_collector_profile(_args(_config(tmp_path)))
    hub = FakeHub([_reply()])
    hub.fail_send = True
    monkeypatch.setattr(acp_cli, "post_json", hub)

    with pytest.raises(acp_cli.CollectorDeliveryError, match="durably accepted"):
        acp_cli._reply_collector_once(profile)

    assert not any(route == "/sessions/ack" for route, _ in hub.calls)
    state = json.loads((tmp_path / "plan-state.json").read_text(encoding="utf-8"))
    assert state["tasks"]["desktop-next"]["status"] == "ready_to_send"


def test_failed_result_with_retry_budget_dispatches_next_attempt_before_ack(tmp_path: Path, monkeypatch: Any) -> None:
    config = _config(tmp_path)
    config_payload = json.loads(config.read_text(encoding="utf-8"))
    definition_path = Path(config_payload["coordinator_plan_definition_path"])
    definition = json.loads(definition_path.read_text(encoding="utf-8"))
    definition["tasks"][0]["max_attempts"] = 2
    definition_path.write_text(json.dumps(definition), encoding="utf-8")
    failed = _reply()
    failed["message"]["payload"] = json.dumps({"task_id": "worker-task", "outcome": "failed"})
    profile = acp_cli.resolve_reply_collector_profile(_args(config))
    hub = FakeHub([failed])
    monkeypatch.setattr(acp_cli, "post_json", hub)

    assert acp_cli._reply_collector_once(profile)["status"] == "completed"

    sent = next(payload for route, payload in hub.calls if route == "/sessions/send")
    retry_payload = json.loads(sent["payload"])
    assert sent["to"] == "worker"
    assert retry_payload["task_id"] == "worker-task"
    assert retry_payload["attempt"] == 2
    assert [route for route, _ in hub.calls] == ["/sessions/wait", "/sessions/send", "/sessions/ack"]


def test_empty_wait_does_not_load_plan_or_emit_task(tmp_path: Path, monkeypatch: Any) -> None:
    config = _config(tmp_path)
    config_payload = json.loads(config.read_text(encoding="utf-8"))
    Path(config_payload["coordinator_plan_definition_path"]).unlink()
    profile = acp_cli.resolve_reply_collector_profile(_args(config))
    hub = FakeHub([{"status": "timeout"}])
    monkeypatch.setattr(acp_cli, "post_json", hub)

    assert acp_cli._reply_collector_once(profile) == {"status": "timeout"}
    assert [route for route, _ in hub.calls] == ["/sessions/wait"]


def test_plan_paths_are_required_as_a_distinct_pair(tmp_path: Path) -> None:
    config = _config(tmp_path)
    payload = json.loads(config.read_text(encoding="utf-8"))
    payload.pop("coordinator_plan_state_path")
    config.write_text(json.dumps(payload), encoding="utf-8")
    with pytest.raises(ValueError, match="requires both definition and state"):
        acp_cli.resolve_reply_collector_profile(_args(config))

    payload["coordinator_plan_state_path"] = payload["coordinator_plan_definition_path"]
    config.write_text(json.dumps(payload), encoding="utf-8")
    with pytest.raises(ValueError, match="must be distinct"):
        acp_cli.resolve_reply_collector_profile(_args(config))


def test_reply_collector_cli_exposes_explicit_plan_paths() -> None:
    args = acp_cli.build_parser().parse_args(
        [
            "reply-collector", "once", "--config", "collector.json",
            "--plan-definition", "roadmap.json", "--plan-state", "roadmap.state.json",
        ]
    )

    assert args.plan_definition == "roadmap.json"
    assert args.plan_state == "roadmap.state.json"


def test_invalid_plan_definition_fails_closed_without_ack(tmp_path: Path, monkeypatch: Any) -> None:
    config = _config(tmp_path)
    payload = json.loads(config.read_text(encoding="utf-8"))
    Path(payload["coordinator_plan_definition_path"]).write_text("not-json", encoding="utf-8")
    profile = acp_cli.resolve_reply_collector_profile(_args(config))
    hub = FakeHub([_reply()])
    monkeypatch.setattr(acp_cli, "post_json", hub)

    with pytest.raises(acp_cli.CollectorDeliveryError, match="unreadable"):
        acp_cli._reply_collector_once(profile)

    assert [route for route, _ in hub.calls] == ["/sessions/wait"]


def test_unstructured_info_keeps_legacy_wrapper_without_poisoning_plan(tmp_path: Path, monkeypatch: Any) -> None:
    profile = acp_cli.resolve_reply_collector_profile(_args(_config(tmp_path)))
    info = _reply()
    info["message"]["action"] = "INFO"
    info["message"]["payload"] = "Worker is waiting for an external approval."
    hub = FakeHub([info])
    monkeypatch.setattr(acp_cli, "post_json", hub)

    result = acp_cli._reply_collector_once(profile)

    assert result["status"] == "completed"
    sent = next(payload for route, payload in hub.calls if route == "/sessions/send")
    envelope = json.loads(sent["payload"])
    assert envelope["original_action"] == "INFO"
    assert envelope["original_payload"] == "Worker is waiting for an external approval."
    state = json.loads((tmp_path / "plan-state.json").read_text(encoding="utf-8"))
    assert state["receipts"] == {}


def test_terminal_plan_result_without_next_task_acks_without_wakeup_loop(tmp_path: Path, monkeypatch: Any) -> None:
    config = _config(tmp_path)
    config_payload = json.loads(config.read_text(encoding="utf-8"))
    definition_path = Path(config_payload["coordinator_plan_definition_path"])
    definition_path.write_text(
        json.dumps(
            {
                "plan_id": "terminal-plan",
                "tasks": [
                    {
                        "task_id": "worker-task",
                        "owner": "worker",
                        "instructions": "Finish the plan",
                        "status": "dispatched",
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
    profile = acp_cli.resolve_reply_collector_profile(_args(config))
    hub = FakeHub([_reply()])
    monkeypatch.setattr(acp_cli, "post_json", hub)

    result = acp_cli._reply_collector_once(profile)

    assert result == {"status": "completed", "message_id": "reply-1", "forwarded_id": None}
    assert [route for route, _ in hub.calls] == ["/sessions/wait", "/sessions/ack"]
    state = json.loads((tmp_path / "plan-state.json").read_text(encoding="utf-8"))
    assert state["tasks"]["worker-task"]["status"] == "completed"


def test_terminal_plan_result_retries_ack_without_creating_wakeup(tmp_path: Path, monkeypatch: Any) -> None:
    config = _config(tmp_path)
    config_payload = json.loads(config.read_text(encoding="utf-8"))
    definition_path = Path(config_payload["coordinator_plan_definition_path"])
    definition_path.write_text(
        json.dumps(
            {
                "plan_id": "terminal-plan",
                "tasks": [
                    {
                        "task_id": "worker-task",
                        "owner": "worker",
                        "instructions": "Finish the plan",
                        "status": "dispatched",
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
    profile = acp_cli.resolve_reply_collector_profile(_args(config))
    hub = FakeHub([_reply(), _reply()])
    hub.fail_ack_once = True
    monkeypatch.setattr(acp_cli, "post_json", hub)

    with pytest.raises(acp_cli.CollectorDeliveryError, match="did not confirm"):
        acp_cli._reply_collector_once(profile)
    assert acp_cli._reply_collector_once(profile)["forwarded_id"] is None

    assert [route for route, _ in hub.calls] == [
        "/sessions/wait",
        "/sessions/ack",
        "/sessions/wait",
        "/sessions/ack",
    ]


class RecordingCodexAdapter:
    manifest = HostManifest(
        adapter_id="codex_app_server",
        display_name="Fake Codex app-server",
        capabilities=("existing-session", "endpoint-serialized"),
    )

    def __init__(self) -> None:
        self.deliveries: list[tuple[Any, Any]] = []

    def deliver(self, binding: Any, delivery: Any) -> HostResult:
        self.deliveries.append((binding, delivery))
        return HostResult(outcome="success", summary="Roadmap turn completed")


def _coordinator_config(tmp_path: Path) -> Path:
    config = {
        "agent_name": "codex-coordinator",
        "hub_http": "https://hub.example",
        "session_id": "room-1",
        "member_token": "member-token",
        "host_bridge_adapter_id": "codex_app_server",
        "host_bridge_endpoint": "ws://127.0.0.1:4500",
        "host_bridge_thread_id": "desktop-thread-existing",
        "host_bridge_allowed_senders": ["reply-collector"],
        "host_bridge_state_path": str(tmp_path / "host-state.json"),
        "host_bridge_wait_timeout_seconds": 0.1,
        "host_bridge_host_timeout_seconds": 1.0,
        "host_bridge_retry_delay_seconds": 0.01,
    }
    path = tmp_path / "coordinator.json"
    path.write_text(json.dumps(config), encoding="utf-8")
    return path


def _host_args(path: Path) -> argparse.Namespace:
    return argparse.Namespace(
        command="host-bridge", host_bridge_command="once", config=str(path), agent=None,
        adapter_id=None, endpoint=None, host_executable=None, host_session_id=None,
        directory=None, credential_ref=None, bridge_allowed_senders=None, state_path=None,
        wait_timeout_seconds=None, host_timeout_seconds=None, retry_delay_seconds=None,
        wait_action=None, accepted_actions=None, reply_to=None,
    )


def test_planned_task_resumes_same_existing_desktop_thread_once(tmp_path: Path, monkeypatch: Any) -> None:
    collector_profile = acp_cli.resolve_reply_collector_profile(_args(_config(tmp_path)))
    collector_hub = FakeHub([_reply()])
    monkeypatch.setattr(acp_cli, "post_json", collector_hub)
    assert acp_cli._reply_collector_once(collector_profile)["status"] == "completed"
    planned = next(payload for route, payload in collector_hub.calls if route == "/sessions/send")

    host_message = {
        "status": "message",
        "message": {**planned, "session_id": "room-1", "from": "reply-collector", "to": "codex-coordinator"},
        "delivery": {
            "ack_required": True,
            "message_id": planned["id"],
            "receipt_handle": "host-receipt-1",
            "lease_expires_at": (datetime.now(timezone.utc) + timedelta(seconds=60)).isoformat().replace("+00:00", "Z"),
        },
    }
    host_hub = FakeHub([host_message])
    adapter = RecordingCodexAdapter()
    registry = AdapterRegistry()
    registry.register(adapter)
    monkeypatch.setattr(acp_cli, "post_json", host_hub)
    monkeypatch.setattr(acp_cli, "default_registry", lambda **_kwargs: registry)

    result = acp_cli.host_bridge_once(_host_args(_coordinator_config(tmp_path)))

    assert result == {"status": "completed", "outcome": "success"}
    assert len(adapter.deliveries) == 1
    binding, delivery = adapter.deliveries[0]
    assert binding.values["thread_id"] == "desktop-thread-existing"
    assert delivery.task_id == "desktop-next"
    assert [route for route, _ in host_hub.calls] == ["/sessions/wait", "/sessions/send", "/sessions/ack"]


def test_direct_reply_advances_product_plan_and_wakes_same_coordinator_ingress(
    tmp_path: Path,
    monkeypatch: Any,
) -> None:
    config_path = _coordinator_config(tmp_path)
    config = json.loads(config_path.read_text(encoding="utf-8"))
    definition_path = tmp_path / "direct-definition.json"
    definition_path.write_text(json.dumps(_definition()), encoding="utf-8")
    config.update(
        {
            "host_bridge_allowed_senders": ["worker"],
            "host_bridge_accepted_actions": ["TASK", "REPLY", "INFO"],
            "coordinator_plan_definition_path": str(definition_path),
            "coordinator_plan_state_path": str(tmp_path / "direct-plan-state.json"),
        }
    )
    config_path.write_text(json.dumps(config), encoding="utf-8")
    direct_reply = _reply()
    direct_reply["message"]["to"] = "codex-coordinator"
    direct_reply["delivery"]["lease_expires_at"] = (
        datetime.now(timezone.utc) + timedelta(seconds=60)
    ).isoformat().replace("+00:00", "Z")
    hub = FakeHub([direct_reply])
    adapter = RecordingCodexAdapter()
    registry = AdapterRegistry()
    registry.register(adapter)
    monkeypatch.setattr(acp_cli, "post_json", hub)
    monkeypatch.setattr(acp_cli, "default_registry", lambda **_kwargs: registry)

    result = acp_cli.host_bridge_once(_host_args(config_path))

    assert result == {"status": "completed", "outcome": "success"}
    assert len(adapter.deliveries) == 1
    assert adapter.deliveries[0][1].action == "REPLY"
    assert adapter.deliveries[0][1].message_id == "reply-1"
    assert [route for route, _ in hub.calls] == ["/sessions/wait", "/sessions/send", "/sessions/ack"]
    planned = hub.calls[1][1]
    assert planned["to"] == "codex-coordinator"
    assert json.loads(planned["payload"])["task_id"] == "desktop-next"


def test_direct_plan_ack_retry_reuses_emission_and_host_result(
    tmp_path: Path,
    monkeypatch: Any,
) -> None:
    config_path = _coordinator_config(tmp_path)
    config = json.loads(config_path.read_text(encoding="utf-8"))
    definition_path = tmp_path / "retry-definition.json"
    definition_path.write_text(json.dumps(_definition()), encoding="utf-8")
    config.update(
        {
            "host_bridge_allowed_senders": ["worker"],
            "host_bridge_accepted_actions": ["TASK", "REPLY", "INFO"],
            "coordinator_plan_definition_path": str(definition_path),
            "coordinator_plan_state_path": str(tmp_path / "retry-plan-state.json"),
        }
    )
    config_path.write_text(json.dumps(config), encoding="utf-8")
    reply = _reply()
    reply["message"]["to"] = "codex-coordinator"
    reply["delivery"]["lease_expires_at"] = (
        datetime.now(timezone.utc) + timedelta(seconds=60)
    ).isoformat().replace("+00:00", "Z")
    hub = FakeHub([reply, reply])
    hub.fail_ack_once = True
    adapter = RecordingCodexAdapter()
    registry = AdapterRegistry()
    registry.register(adapter)
    monkeypatch.setattr(acp_cli, "post_json", hub)
    monkeypatch.setattr(acp_cli, "default_registry", lambda **_kwargs: registry)

    with pytest.raises(Exception, match="ack did not confirm"):
        acp_cli.host_bridge_once(_host_args(config_path))
    assert acp_cli.host_bridge_once(_host_args(config_path))["status"] == "duplicate"

    sends = [payload for route, payload in hub.calls if route == "/sessions/send"]
    assert len(sends) == 2
    assert sends[0]["id"] == sends[1]["id"]
    assert len(adapter.deliveries) == 1


def test_direct_plan_send_failure_does_not_wake_host_or_ack(
    tmp_path: Path,
    monkeypatch: Any,
) -> None:
    config_path = _coordinator_config(tmp_path)
    config = json.loads(config_path.read_text(encoding="utf-8"))
    definition_path = tmp_path / "fail-definition.json"
    definition_path.write_text(json.dumps(_definition()), encoding="utf-8")
    config.update(
        {
            "host_bridge_allowed_senders": ["worker"],
            "host_bridge_accepted_actions": ["TASK", "REPLY", "INFO"],
            "coordinator_plan_definition_path": str(definition_path),
            "coordinator_plan_state_path": str(tmp_path / "fail-plan-state.json"),
        }
    )
    config_path.write_text(json.dumps(config), encoding="utf-8")
    reply = _reply()
    reply["message"]["to"] = "codex-coordinator"
    reply["delivery"]["lease_expires_at"] = (
        datetime.now(timezone.utc) + timedelta(seconds=60)
    ).isoformat().replace("+00:00", "Z")
    hub = FakeHub([reply])
    hub.fail_send = True
    adapter = RecordingCodexAdapter()
    registry = AdapterRegistry()
    registry.register(adapter)
    monkeypatch.setattr(acp_cli, "post_json", hub)
    monkeypatch.setattr(acp_cli, "default_registry", lambda **_kwargs: registry)

    with pytest.raises(Exception, match="not durably accepted"):
        acp_cli.host_bridge_once(_host_args(config_path))

    assert adapter.deliveries == []
    assert [route for route, _ in hub.calls] == ["/sessions/wait", "/sessions/send"]


def test_direct_plan_rejects_untrusted_result_before_state_or_dispatch(
    tmp_path: Path,
    monkeypatch: Any,
) -> None:
    config_path = _coordinator_config(tmp_path)
    config = json.loads(config_path.read_text(encoding="utf-8"))
    definition_path = tmp_path / "untrusted-definition.json"
    definition_path.write_text(json.dumps(_definition()), encoding="utf-8")
    state_path = tmp_path / "untrusted-plan-state.json"
    config.update(
        {
            "host_bridge_allowed_senders": ["worker"],
            "host_bridge_accepted_actions": ["TASK", "REPLY", "INFO"],
            "coordinator_plan_definition_path": str(definition_path),
            "coordinator_plan_state_path": str(state_path),
        }
    )
    config_path.write_text(json.dumps(config), encoding="utf-8")
    reply = _reply()
    reply["message"]["from"] = "intruder"
    reply["message"]["to"] = "codex-coordinator"
    reply["delivery"]["lease_expires_at"] = (
        datetime.now(timezone.utc) + timedelta(seconds=60)
    ).isoformat().replace("+00:00", "Z")
    hub = FakeHub([reply])
    adapter = RecordingCodexAdapter()
    registry = AdapterRegistry()
    registry.register(adapter)
    monkeypatch.setattr(acp_cli, "post_json", hub)
    monkeypatch.setattr(acp_cli, "default_registry", lambda **_kwargs: registry)

    with pytest.raises(Exception, match="not authorized"):
        acp_cli.host_bridge_once(_host_args(config_path))

    assert not state_path.exists()
    assert adapter.deliveries == []
    assert [route for route, _ in hub.calls] == ["/sessions/wait"]
