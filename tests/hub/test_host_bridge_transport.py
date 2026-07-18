from __future__ import annotations

import argparse
import importlib.util
import json
import sys
import threading
import time
import urllib.error
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

import pytest


repo_root = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(repo_root / "ACP_AGENT"))
_ACP_SPEC = importlib.util.spec_from_file_location("acp_agent_host_bridge_transport", repo_root / "ACP_AGENT" / "acp.py")
assert _ACP_SPEC is not None and _ACP_SPEC.loader is not None
acp_cli = importlib.util.module_from_spec(_ACP_SPEC)
sys.modules[_ACP_SPEC.name] = acp_cli
_ACP_SPEC.loader.exec_module(acp_cli)

from host_bridge import (  # noqa: E402
    AdapterRegistry,
    HostBindingError,
    HostDeliveryError,
    HostManifest,
    HostResult,
)
import host_bridge as host_bridge_module  # noqa: E402


MESSAGE_ID = "68a9dd17-8b7a-477e-96e3-9cf2efc194f8"


class RecordingAdapter:
    manifest = HostManifest(
        adapter_id="opencode_server",
        display_name="Fake OpenCode server",
        capabilities=("existing-session",),
    )

    def __init__(self) -> None:
        self.deliveries: list[tuple[Any, Any]] = []

    def deliver(self, binding: Any, delivery: Any) -> HostResult:
        self.deliveries.append((binding, delivery))
        return HostResult(outcome="success", summary="Host finished")


class FakeHub:
    def __init__(self, responses: list[dict[str, Any]]) -> None:
        self.responses = list(responses)
        self.calls: list[tuple[str, dict[str, Any]]] = []
        self.crash_after_reply_acceptance = False
        self.malformed_ack = False
        self.malformed_reply = False
        self.accepted_reply_ids: set[str] = set()
        self.timeouts: list[tuple[str, float | None]] = []

    def post_json(self, *, route: str, payload: dict[str, Any], **_kwargs: Any) -> dict[str, Any]:
        self.calls.append((route, payload))
        self.timeouts.append((route, _kwargs.get("timeout_seconds")))
        if route == "/sessions/wait":
            response = self.responses.pop(0)
            if isinstance(response, BaseException):
                raise response
            return response
        if route == "/sessions/send":
            duplicate = payload["id"] in self.accepted_reply_ids
            self.accepted_reply_ids.add(payload["id"])
            if self.crash_after_reply_acceptance:
                raise RuntimeError("simulated reply transport crash")
            if self.malformed_reply:
                return {}
            return {
                "status": "queued",
                "message_id": payload["id"],
                "delivery": "duplicate" if duplicate else "immediate",
            }
        if route == "/sessions/ack":
            if self.malformed_ack:
                return {}
            return {"status": "acknowledged", "message_id": payload["message_id"]}
        if route == "/sessions/cancel-wait":
            return {"status": "cancelled"}
        raise AssertionError(f"unexpected route: {route}")


def _message_response(
    *,
    sender: str = "chief",
    host_session: str = "host-session-1",
    lease_seconds: float = 300.0,
) -> dict[str, Any]:
    return {
        "status": "message",
        "message": {
            "id": MESSAGE_ID,
            "session_id": "coordination-session",
            "from": sender,
            "to": "bridge-agent",
            "action": "TASK",
            "payload": json.dumps({"task_id": "task-1", "instructions": "Inspect the repository"}),
        },
        "delivery": {
            "ack_required": True,
            "message_id": MESSAGE_ID,
            "receipt_handle": "receipt-1",
            "lease_expires_at": (
                datetime.now(timezone.utc) + timedelta(seconds=lease_seconds)
            ).isoformat(timespec="microseconds").replace("+00:00", "Z"),
        },
        "host_session": host_session,
    }


def _write_config(tmp_path: Path, **overrides: Any) -> Path:
    config = {
        "agent_name": "bridge-agent",
        "hub_http": "https://hub.example",
        "session_id": "coordination-session",
        "member_token": "member-token",
        "host_bridge_adapter_id": "opencode_server",
        "host_bridge_endpoint": "http://127.0.0.1:4096",
        "host_bridge_session_id": "host-session-1",
        "host_bridge_allowed_senders": ["chief"],
        "host_bridge_state_path": str(tmp_path / "host-bridge-state.json"),
        "host_bridge_wait_timeout_seconds": 0.1,
        "host_bridge_host_timeout_seconds": 1.0,
        "host_bridge_retry_delay_seconds": 0.01,
    }
    config.update(overrides)
    path = tmp_path / "bridge-agent.json"
    path.write_text(json.dumps(config), encoding="utf-8")
    return path


def _args(config_path: Path, *, command: str = "once") -> argparse.Namespace:
    return argparse.Namespace(
        command="host-bridge",
        host_bridge_command=command,
        config=str(config_path),
        agent=None,
        adapter_id=None,
        endpoint=None,
        host_executable=None,
        host_session_id=None,
        directory=None,
        credential_ref=None,
        bridge_allowed_senders=None,
        state_path=None,
        wait_timeout_seconds=None,
        host_timeout_seconds=None,
        retry_delay_seconds=None,
        wait_action=None,
    )


def _registry(adapter: RecordingAdapter) -> AdapterRegistry:
    registry = AdapterRegistry()
    registry.register(adapter)
    return registry


def test_empty_host_bridge_cycles_never_touch_host_or_model(tmp_path: Path, monkeypatch: Any) -> None:
    config_path = _write_config(tmp_path)
    hub = FakeHub([{"status": "timeout"}, {"status": "timeout"}, {"status": "timeout"}])
    adapter = RecordingAdapter()
    monkeypatch.setattr(acp_cli, "post_json", hub.post_json)
    monkeypatch.setattr(acp_cli, "default_registry", lambda **_kwargs: _registry(adapter))

    result = acp_cli.host_bridge_start(_args(config_path, command="start"), max_cycles=3)

    assert result == {"status": "idle", "cycles": 3}
    assert [route for route, _ in hub.calls] == ["/sessions/wait"] * 3
    assert adapter.deliveries == []
    assert not (tmp_path / "host-bridge-state.json").exists()


def test_host_bridge_waits_only_for_task_action(tmp_path: Path, monkeypatch: Any) -> None:
    config_path = _write_config(tmp_path)
    hub = FakeHub([{"status": "timeout"}])
    adapter = RecordingAdapter()
    monkeypatch.setattr(acp_cli, "post_json", hub.post_json)
    monkeypatch.setattr(acp_cli, "default_registry", lambda **_kwargs: _registry(adapter))

    acp_cli.host_bridge_once(_args(config_path))

    wait_payload = hub.calls[0][1]
    assert wait_payload["action"] == "TASK"
    assert adapter.deliveries == []


def test_host_bridge_wait_action_is_fail_closed(tmp_path: Path) -> None:
    config_path = _write_config(tmp_path, host_bridge_wait_action="REPLY")

    with pytest.raises(HostBindingError, match="wait_action must be TASK"):
        acp_cli.resolve_host_bridge_profile(_args(config_path))

    empty_config_path = _write_config(tmp_path, host_bridge_wait_action="")
    with pytest.raises(HostBindingError, match="wait_action must be TASK"):
        acp_cli.resolve_host_bridge_profile(_args(empty_config_path))


def test_valid_delivery_uses_bound_session_then_replies_and_acks(tmp_path: Path, monkeypatch: Any) -> None:
    config_path = _write_config(tmp_path)
    hub = FakeHub([_message_response()])
    adapter = RecordingAdapter()
    monkeypatch.setattr(acp_cli, "post_json", hub.post_json)
    monkeypatch.setattr(acp_cli, "default_registry", lambda **_kwargs: _registry(adapter))

    result = acp_cli.host_bridge_once(_args(config_path))

    assert result == {"status": "completed", "outcome": "success"}
    assert len(adapter.deliveries) == 1
    binding, delivery = adapter.deliveries[0]
    assert binding.values["session_id"] == "host-session-1"
    assert delivery.message_id == MESSAGE_ID
    assert [route for route, _ in hub.calls] == ["/sessions/wait", "/sessions/send", "/sessions/ack"]
    reply = hub.calls[1][1]
    assert reply["action"] == "REPLY"
    assert reply["to"] == "chief"
    assert reply["in_reply_to"] == MESSAGE_ID
    assert reply["id"] in hub.accepted_reply_ids
    acknowledgment = hub.calls[2][1]
    assert acknowledgment["message_id"] == MESSAGE_ID
    assert acknowledgment["receipt_handle"] == "receipt-1"
    timeout_by_route = dict(hub.timeouts)
    assert 0 < timeout_by_route["/sessions/send"] <= 20
    assert 0 < timeout_by_route["/sessions/ack"] <= 20


def test_delivery_lease_reduces_host_budget_before_reply_and_ack(tmp_path: Path, monkeypatch: Any) -> None:
    config_path = _write_config(tmp_path, host_bridge_host_timeout_seconds=240.0)
    hub = FakeHub([_message_response(lease_seconds=70.0)])
    adapter = RecordingAdapter()
    configured_timeouts: list[float] = []

    def registry_factory(*, request_timeout_seconds: float, **_kwargs: Any) -> AdapterRegistry:
        configured_timeouts.append(request_timeout_seconds)
        return _registry(adapter)

    monkeypatch.setattr(acp_cli, "post_json", hub.post_json)
    monkeypatch.setattr(acp_cli, "default_registry", registry_factory)

    assert acp_cli.host_bridge_once(_args(config_path))["status"] == "completed"
    assert configured_timeouts[0] == 240.0
    assert 0 < configured_timeouts[-1] < 30.0
    assert len(adapter.deliveries) == 1


def test_hub_json_read_honors_absolute_deadline(monkeypatch: Any) -> None:
    release = threading.Event()

    class FakeSocket:
        def settimeout(self, _seconds: float) -> None:
            return None

    class Raw:
        _sock = FakeSocket()

    class Fp:
        raw = Raw()

    class SlowResponse:
        fp = Fp()

        def __enter__(self) -> "SlowResponse":
            return self

        def __exit__(self, *_args: Any) -> None:
            return None

        def read(self) -> bytes:
            release.wait(0.5)
            return b"{"

    monkeypatch.setattr(acp_cli.urllib.request, "urlopen", lambda *_args, **_kwargs: SlowResponse())

    started = time.perf_counter()
    try:
        with pytest.raises(ValueError, match="deadline"):
            acp_cli.request_json(
                method="POST",
                url="https://hub.example/sessions/send",
                payload={},
                timeout_seconds=0.01,
                deadline_monotonic=acp_cli.time.monotonic() + 0.01,
            )
        assert time.perf_counter() - started < 0.2
    finally:
        release.set()


def test_restart_after_reply_acceptance_reuses_reply_id_and_does_not_redeliver_host(
    tmp_path: Path,
    monkeypatch: Any,
) -> None:
    config_path = _write_config(tmp_path)
    hub = FakeHub([_message_response(), _message_response()])
    adapter = RecordingAdapter()
    hub.crash_after_reply_acceptance = True
    monkeypatch.setattr(acp_cli, "post_json", hub.post_json)
    monkeypatch.setattr(acp_cli, "default_registry", lambda **_kwargs: _registry(adapter))

    with pytest.raises(RuntimeError, match="reply transport crash"):
        acp_cli.host_bridge_once(_args(config_path))

    first_reply_id = next(payload["id"] for route, payload in hub.calls if route == "/sessions/send")
    hub.crash_after_reply_acceptance = False
    result = acp_cli.host_bridge_once(_args(config_path))
    reply_ids = [payload["id"] for route, payload in hub.calls if route == "/sessions/send"]

    assert result == {"status": "duplicate", "outcome": "success"}
    assert len(adapter.deliveries) == 1
    assert reply_ids == [first_reply_id, first_reply_id]
    assert len(hub.accepted_reply_ids) == 1
    assert len([route for route, _ in hub.calls if route == "/sessions/ack"]) == 1


@pytest.mark.parametrize("malformed_stage", ["reply", "ack"])
def test_malformed_hub_completion_never_advances_durable_delivery(
    tmp_path: Path,
    monkeypatch: Any,
    malformed_stage: str,
) -> None:
    config_path = _write_config(tmp_path)
    hub = FakeHub([_message_response()])
    adapter = RecordingAdapter()
    hub.malformed_reply = malformed_stage == "reply"
    hub.malformed_ack = malformed_stage == "ack"
    monkeypatch.setattr(acp_cli, "post_json", hub.post_json)
    monkeypatch.setattr(acp_cli, "default_registry", lambda **_kwargs: _registry(adapter))

    with pytest.raises(HostDeliveryError, match=f"ACP {malformed_stage}"):
        acp_cli.host_bridge_once(_args(config_path))

    ledger = json.loads((tmp_path / "host-bridge-state.json").read_text(encoding="utf-8"))
    record = next(iter(ledger["deliveries"].values()))
    assert record["status"] == "completed"
    assert record.get("replied", False) is (malformed_stage == "ack")
    assert record.get("acked") is not True
    if malformed_stage == "reply":
        assert not any(route == "/sessions/ack" for route, _ in hub.calls)


@pytest.mark.parametrize(
    ("config_overrides", "sender", "error_type"),
    [
        ({"host_bridge_endpoint": "https://host.example"}, "chief", HostBindingError),
        ({}, "intruder", HostDeliveryError),
    ],
)
def test_invalid_endpoint_or_sender_fails_closed_without_ack(
    tmp_path: Path,
    monkeypatch: Any,
    config_overrides: dict[str, Any],
    sender: str,
    error_type: type[Exception],
) -> None:
    config_path = _write_config(tmp_path, **config_overrides)
    hub = FakeHub([_message_response(sender=sender)])
    adapter = RecordingAdapter()
    monkeypatch.setattr(acp_cli, "post_json", hub.post_json)
    if sender == "intruder":
        monkeypatch.setattr(acp_cli, "default_registry", lambda **_kwargs: _registry(adapter))

    with pytest.raises(error_type):
        acp_cli.host_bridge_once(_args(config_path))

    assert adapter.deliveries == []
    assert not any(route in {"/sessions/send", "/sessions/ack"} for route, _ in hub.calls)


def test_invalid_host_session_fails_closed_without_ack(tmp_path: Path, monkeypatch: Any) -> None:
    config_path = _write_config(tmp_path, host_bridge_session_id="missing-session")
    hub = FakeHub([_message_response()])
    host_requests: list[str] = []

    def reject_host(request: Any, **_kwargs: Any) -> Any:
        host_requests.append(request.full_url)
        raise urllib.error.HTTPError(request.full_url, 404, "not found", hdrs=None, fp=None)

    monkeypatch.setattr(acp_cli, "post_json", hub.post_json)
    monkeypatch.setattr(host_bridge_module.urllib.request, "urlopen", reject_host)

    with pytest.raises(HostDeliveryError, match="HTTP 404"):
        acp_cli.host_bridge_once(_args(config_path))

    assert len(host_requests) == 1
    assert "/session/missing-session/message" in host_requests[0]
    assert not any(route in {"/sessions/send", "/sessions/ack"} for route, _ in hub.calls)


def test_timeout_then_sigint_stops_cleanly_without_ledger_corruption(tmp_path: Path, monkeypatch: Any) -> None:
    config_path = _write_config(tmp_path)
    hub = FakeHub([{"status": "timeout"}, KeyboardInterrupt()])
    adapter = RecordingAdapter()
    monkeypatch.setattr(acp_cli, "post_json", hub.post_json)
    monkeypatch.setattr(acp_cli, "default_registry", lambda **_kwargs: _registry(adapter))

    result = acp_cli.host_bridge_start(_args(config_path, command="start"))

    assert result["status"] == "stopped"
    assert result["reason"] == "interrupted"
    assert adapter.deliveries == []
    assert not (tmp_path / "host-bridge-state.json").exists()


def test_once_sigint_stops_cleanly_without_ledger_corruption(tmp_path: Path, monkeypatch: Any) -> None:
    config_path = _write_config(tmp_path)
    hub = FakeHub([KeyboardInterrupt()])
    adapter = RecordingAdapter()
    monkeypatch.setattr(acp_cli, "post_json", hub.post_json)
    monkeypatch.setattr(acp_cli, "default_registry", lambda **_kwargs: _registry(adapter))

    result = acp_cli.host_bridge_once(_args(config_path))

    assert result == {"status": "stopped", "reason": "interrupted", "cycles": 0}
    assert adapter.deliveries == []
    assert not (tmp_path / "host-bridge-state.json").exists()


def test_sigint_during_retry_delay_stops_cleanly(tmp_path: Path, monkeypatch: Any) -> None:
    config_path = _write_config(tmp_path)
    hub = FakeHub([_message_response(sender="intruder")])
    adapter = RecordingAdapter()
    monkeypatch.setattr(acp_cli, "post_json", hub.post_json)
    monkeypatch.setattr(acp_cli, "default_registry", lambda **_kwargs: _registry(adapter))
    monkeypatch.setattr(acp_cli.time, "sleep", lambda _seconds: (_ for _ in ()).throw(KeyboardInterrupt()))

    result = acp_cli.host_bridge_start(_args(config_path, command="start"))

    assert result == {"status": "stopped", "reason": "interrupted", "cycles": 0}
    assert adapter.deliveries == []
    assert not any(route in {"/sessions/send", "/sessions/ack"} for route, _ in hub.calls)


def test_delivery_failure_is_reported_as_waiting_before_retry(tmp_path: Path, monkeypatch: Any) -> None:
    config_path = _write_config(tmp_path)
    hub = FakeHub([_message_response(sender="intruder")])
    adapter = RecordingAdapter()
    statuses: list[tuple[str, str | None]] = []
    monkeypatch.setattr(acp_cli, "post_json", hub.post_json)
    monkeypatch.setattr(acp_cli, "default_registry", lambda **_kwargs: _registry(adapter))
    monkeypatch.setattr(
        acp_cli,
        "safe_update_session_status",
        lambda *, settings, state, text: statuses.append((state, text)),
    )
    monkeypatch.setattr(acp_cli.time, "sleep", lambda _seconds: (_ for _ in ()).throw(KeyboardInterrupt()))

    result = acp_cli.host_bridge_start(_args(config_path, command="start"))

    assert result == {"status": "stopped", "reason": "interrupted", "cycles": 0}
    assert statuses == [("waiting", "host bridge delivery failed: ACP delivery is not an authorized TASK; retrying safely")]


@pytest.mark.parametrize("response", [{}, {"status": "unexpected"}, []])
def test_malformed_wait_response_fails_closed_before_host(
    tmp_path: Path,
    monkeypatch: Any,
    response: Any,
) -> None:
    config_path = _write_config(tmp_path)
    hub = FakeHub([response])
    adapter = RecordingAdapter()
    monkeypatch.setattr(acp_cli, "post_json", hub.post_json)
    monkeypatch.setattr(acp_cli, "default_registry", lambda **_kwargs: _registry(adapter))

    with pytest.raises(HostDeliveryError, match="receive"):
        acp_cli.host_bridge_once(_args(config_path))

    assert adapter.deliveries == []
    assert not any(route in {"/sessions/send", "/sessions/ack"} for route, _ in hub.calls)


def test_non_string_receipt_fails_closed_before_host(tmp_path: Path, monkeypatch: Any) -> None:
    config_path = _write_config(tmp_path)
    response = _message_response()
    response["delivery"]["receipt_handle"] = {"invalid": True}
    hub = FakeHub([response])
    adapter = RecordingAdapter()
    monkeypatch.setattr(acp_cli, "post_json", hub.post_json)
    monkeypatch.setattr(acp_cli, "default_registry", lambda **_kwargs: _registry(adapter))

    with pytest.raises(HostDeliveryError, match="identity"):
        acp_cli.host_bridge_once(_args(config_path))

    assert adapter.deliveries == []
    assert not any(route in {"/sessions/send", "/sessions/ack"} for route, _ in hub.calls)


def test_host_timeout_cannot_outlive_delivery_lease(tmp_path: Path, monkeypatch: Any) -> None:
    config_path = _write_config(tmp_path, host_bridge_host_timeout_seconds=241.0)
    hub = FakeHub([])
    monkeypatch.setattr(acp_cli, "post_json", hub.post_json)

    with pytest.raises(ValueError, match="host_timeout_seconds"):
        acp_cli.host_bridge_once(_args(config_path))

    assert hub.calls == []


@pytest.mark.parametrize("mode", ["once", "start"])
def test_live_binding_lock_prevents_concurrent_bridge_processes(
    tmp_path: Path,
    monkeypatch: Any,
    mode: str,
) -> None:
    config_path = _write_config(tmp_path)
    args = _args(config_path, command=mode)
    profile = acp_cli.resolve_host_bridge_profile(args)
    hub = FakeHub([])
    monkeypatch.setattr(acp_cli, "post_json", hub.post_json)

    with acp_cli.reserve_config(profile["lock_target"]):
        with pytest.raises(ValueError, match="reserved by another process"):
            if mode == "once":
                acp_cli.host_bridge_once(args)
            else:
                acp_cli.host_bridge_start(args, max_cycles=1)

    assert hub.calls == []


@pytest.mark.parametrize(
    ("argument", "value", "error_type"),
    [
        ("host_session_id", "", HostBindingError),
        ("wait_timeout_seconds", 0.0, ValueError),
    ],
)
def test_explicit_invalid_cli_value_never_falls_back_to_config(
    tmp_path: Path,
    monkeypatch: Any,
    argument: str,
    value: Any,
    error_type: type[Exception],
) -> None:
    config_path = _write_config(tmp_path)
    args = _args(config_path)
    setattr(args, argument, value)
    hub = FakeHub([])
    monkeypatch.setattr(acp_cli, "post_json", hub.post_json)

    with pytest.raises(error_type):
        acp_cli.host_bridge_once(args)

    assert hub.calls == []


def test_host_bridge_cli_exposes_explicit_safe_binding_options() -> None:
    parser = acp_cli.build_parser()
    args = parser.parse_args(
        [
            "host-bridge",
            "once",
            "--config",
            "ACP_AGENT/agents/bridge.json",
            "--adapter-id",
            "kilo_serve",
            "--endpoint",
            "http://127.0.0.1:4096",
            "--host-session-id",
            "session-1",
            "--credential-ref",
            "env:KILO_HOST_CREDENTIAL",
            "--allow-sender",
            "chief",
            "--wait-action",
            "TASK",
        ]
    )

    assert args.command == "host-bridge"
    assert args.host_bridge_command == "once"
    assert args.adapter_id == "kilo_serve"
    assert args.host_session_id == "session-1"
    assert args.credential_ref == "env:KILO_HOST_CREDENTIAL"
    assert args.wait_action == "TASK"


def test_host_bridge_cli_accepts_explicit_codex_app_server_thread_binding() -> None:
    parser = acp_cli.build_parser()
    args = parser.parse_args(
        [
            "host-bridge",
            "once",
            "--config",
            "ACP_AGENT/agents/bridge.json",
            "--adapter-id",
            "codex_app_server",
            "--endpoint",
            "ws://127.0.0.1:4500",
            "--host-thread-id",
            "thread-existing",
            "--credential-ref",
            "env:CODEX_APP_SERVER_CREDENTIAL",
            "--allow-sender",
            "chief",
        ]
    )

    assert args.adapter_id == "codex_app_server"
    assert args.host_session_id == "thread-existing"


def test_codex_profile_uses_explicit_thread_id_without_cwd_override(tmp_path: Path) -> None:
    config_path = _write_config(
        tmp_path,
        host_bridge_adapter_id="codex_app_server",
        host_bridge_endpoint="ws://127.0.0.1:4500",
        host_bridge_thread_id="thread-existing",
        host_bridge_session_id=None,
    )
    profile = acp_cli.resolve_host_bridge_profile(_args(config_path))

    assert profile["binding"].adapter_id == "codex_app_server"
    assert dict(profile["binding"].values) == {
        "endpoint": "ws://127.0.0.1:4500",
        "thread_id": "thread-existing",
    }


def test_codex_profiles_share_endpoint_reservation_across_threads(tmp_path: Path) -> None:
    (tmp_path / "first").mkdir()
    (tmp_path / "second").mkdir()
    first_config = _write_config(
        tmp_path / "first",
        host_bridge_adapter_id="codex_app_server",
        host_bridge_endpoint="ws://127.0.0.1:4500",
        host_bridge_thread_id="thread-one",
        host_bridge_session_id=None,
    )
    second_config = _write_config(
        tmp_path / "second",
        host_bridge_adapter_id="codex_app_server",
        host_bridge_endpoint="ws://127.0.0.1:4500",
        host_bridge_thread_id="thread-two",
        host_bridge_session_id=None,
    )

    first = acp_cli.resolve_host_bridge_profile(_args(first_config))
    second = acp_cli.resolve_host_bridge_profile(_args(second_config))

    assert first["binding"].fingerprint() != second["binding"].fingerprint()
    assert first["lock_target"] == second["lock_target"]


def test_codex_profiles_on_different_endpoints_have_isolated_reservations(tmp_path: Path) -> None:
    (tmp_path / "first").mkdir()
    (tmp_path / "second").mkdir()
    first_config = _write_config(
        tmp_path / "first",
        host_bridge_adapter_id="codex_app_server",
        host_bridge_endpoint="ws://127.0.0.1:4500",
        host_bridge_thread_id="thread-one",
        host_bridge_session_id=None,
    )
    second_config = _write_config(
        tmp_path / "second",
        host_bridge_adapter_id="codex_app_server",
        host_bridge_endpoint="ws://127.0.0.1:4501",
        host_bridge_thread_id="thread-two",
        host_bridge_session_id=None,
    )

    first = acp_cli.resolve_host_bridge_profile(_args(first_config))
    second = acp_cli.resolve_host_bridge_profile(_args(second_config))

    assert first["lock_target"] != second["lock_target"]


def test_codex_bearer_credential_is_resolved_only_from_env(monkeypatch: Any) -> None:
    monkeypatch.setenv("CODEX_APP_SERVER_CREDENTIAL", json.dumps({"bearer_token": "test-bearer"}))

    credential = acp_cli._host_bridge_credential("env:CODEX_APP_SERVER_CREDENTIAL")

    assert credential is not None
    assert credential.bearer_token == "test-bearer"
    assert credential.username is None


def test_claude_cli_profile_uses_explicit_executable_and_existing_session(tmp_path: Path) -> None:
    config_path = _write_config(
        tmp_path,
        host_bridge_adapter_id="claude_code_cli",
        host_bridge_endpoint=None,
        host_bridge_executable=r"C:\\Tools\\claude.exe",
        host_bridge_session_id="claude-existing",
    )
    profile = acp_cli.resolve_host_bridge_profile(_args(config_path))

    assert profile["binding"].adapter_id == "claude_code_cli"
    assert dict(profile["binding"].values) == {
        "executable": r"C:\\Tools\\claude.exe",
        "session_id": "claude-existing",
    }


def test_codex_cli_profile_uses_explicit_executable_and_existing_session(tmp_path: Path) -> None:
    config_path = _write_config(
        tmp_path,
        host_bridge_adapter_id="codex_cli",
        host_bridge_endpoint=None,
        host_bridge_executable=r"C:\\Tools\\codex.exe",
        host_bridge_session_id="019f58d8-b3e2-7570-a416-4d2ee9140e90",
    )
    profile = acp_cli.resolve_host_bridge_profile(_args(config_path))

    assert profile["binding"].adapter_id == "codex_cli"
    assert dict(profile["binding"].values) == {
        "executable": r"C:\\Tools\\codex.exe",
        "session_id": "019f58d8-b3e2-7570-a416-4d2ee9140e90",
    }


def test_codex_cli_profile_rejects_endpoint(tmp_path: Path) -> None:
    config_path = _write_config(
        tmp_path,
        host_bridge_adapter_id="codex_cli",
        host_bridge_executable=r"C:\\Tools\\codex.exe",
        host_bridge_session_id="codex-existing",
    )

    with pytest.raises(HostBindingError, match="does not accept an endpoint"):
        acp_cli.resolve_host_bridge_profile(_args(config_path))


def test_claude_desktop_profile_is_rejected_as_unsupported(tmp_path: Path) -> None:
    config_path = _write_config(
        tmp_path,
        host_bridge_adapter_id="claude_desktop",
        host_bridge_endpoint=None,
    )

    with pytest.raises(HostBindingError, match="UNSUPPORTED_PENDING_OFFICIAL_INTERFACE"):
        acp_cli.resolve_host_bridge_profile(_args(config_path))


def test_host_bridge_cli_accepts_explicit_claude_executable() -> None:
    parser = acp_cli.build_parser()
    args = parser.parse_args(
        [
            "host-bridge",
            "once",
            "--adapter-id",
            "claude_code_cli",
            "--host-executable",
            r"C:\\Tools\\claude.exe",
            "--host-session-id",
            "claude-existing",
            "--allow-sender",
            "chief",
        ]
    )

    assert args.adapter_id == "claude_code_cli"
    assert args.host_executable == r"C:\\Tools\\claude.exe"


def test_literal_credential_is_rejected_before_wait(tmp_path: Path, monkeypatch: Any) -> None:
    config_path = _write_config(tmp_path, host_bridge_credential_ref="literal-password")
    hub = FakeHub([])
    monkeypatch.setattr(acp_cli, "post_json", hub.post_json)

    with pytest.raises(HostBindingError, match="credential_ref"):
        acp_cli.host_bridge_once(_args(config_path))

    assert hub.calls == []
