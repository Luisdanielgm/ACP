from __future__ import annotations

import json
import sys
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

import pytest


repo_root = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(repo_root / "ACP_AGENT"))

from host_bridge import (  # noqa: E402
    AdapterRegistry,
    HostBinding,
    HostBindingError,
    HostBridge,
    HostCredential,
    HostDelivery,
    HostDeliveryError,
    HostManifest,
    HostResult,
    JsonBridgeStore,
    KiloServeAdapter,
    OpenCodeServerAdapter,
)
import host_bridge as host_bridge_module  # noqa: E402


def _response(message_id: str = "msg-1", *, session_id: str = "session-1") -> dict[str, Any]:
    return {
        "status": "message",
        "message": {
            "id": message_id,
            "session_id": session_id,
            "from": "chief",
            "to": "worker",
            "action": "TASK",
            "payload": json.dumps({"task_id": "task-1", "instructions": "Inspect the change"}),
        },
        "delivery": {
            "ack_required": True,
            "message_id": message_id,
            "receipt_handle": f"receipt-{message_id}",
        },
    }


class _CountingAdapter:
    manifest = HostManifest(
        adapter_id="counting",
        display_name="Counting adapter",
        capabilities=("existing-session", "correlated-result"),
    )

    def __init__(self) -> None:
        self.deliveries: list[HostDelivery] = []

    def deliver(self, binding: HostBinding, delivery: HostDelivery) -> HostResult:
        self.deliveries.append(delivery)
        return HostResult(outcome="success", summary="Finished once")


def _bridge(tmp_path: Path, adapter: Any) -> HostBridge:
    registry = AdapterRegistry()
    registry.register(adapter)
    return HostBridge(
        registry=registry,
        binding=HostBinding(adapter_id=adapter.manifest.adapter_id, values={"session_id": "existing"}),
        store=JsonBridgeStore(tmp_path / "bridge-state.json"),
        allowed_senders=("chief",),
    )


def test_empty_inbox_never_calls_adapter_or_model(tmp_path: Path) -> None:
    adapter = _CountingAdapter()
    bridge = _bridge(tmp_path, adapter)
    receives = 0

    def receive() -> dict[str, str]:
        nonlocal receives
        receives += 1
        return {"status": "timeout"}

    for _ in range(4):
        assert bridge.poll_once(receive=receive, acknowledge=lambda _: None, reply=lambda *_: None)["status"] == "idle"

    assert receives == 4
    assert adapter.deliveries == []


def test_one_message_is_activated_replied_and_acked_once(tmp_path: Path) -> None:
    adapter = _CountingAdapter()
    bridge = _bridge(tmp_path, adapter)
    acknowledgments: list[str] = []
    replies: list[tuple[str, str]] = []

    result = bridge.handle(
        _response(),
        acknowledge=lambda response: acknowledgments.append(response["delivery"]["message_id"]),
        reply=lambda delivery, host_result, reply_id: replies.append((delivery.correlation_id, reply_id)),
    )

    assert result["status"] == "completed"
    assert len(adapter.deliveries) == 1
    assert acknowledgments == ["msg-1"]
    assert len(replies) == 1
    assert replies[0][0] == "msg-1"


def test_restart_reuses_durable_result_without_duplicate_activation(tmp_path: Path) -> None:
    state_path = tmp_path / "bridge-state.json"
    first_adapter = _CountingAdapter()
    first = _bridge(tmp_path, first_adapter)
    with pytest.raises(RuntimeError, match="simulated crash"):
        first.handle(
            _response(),
            acknowledge=lambda _: pytest.fail("ACK must follow a durable correlated reply"),
            reply=lambda *_: (_ for _ in ()).throw(RuntimeError("simulated crash")),
        )

    restarted_adapter = _CountingAdapter()
    registry = AdapterRegistry()
    registry.register(restarted_adapter)
    restarted = HostBridge(
        registry=registry,
        binding=HostBinding(adapter_id="counting", values={"session_id": "existing"}),
        store=JsonBridgeStore(state_path),
        allowed_senders=("chief",),
    )
    acknowledgments: list[str] = []
    replies: list[str] = []

    result = restarted.handle(
        _response(),
        acknowledge=lambda response: acknowledgments.append(response["delivery"]["receipt_handle"]),
        reply=lambda _delivery, _result, reply_id: replies.append(reply_id),
    )

    assert result["status"] == "duplicate"
    assert restarted_adapter.deliveries == []
    assert len(replies) == 1
    assert acknowledgments == ["receipt-msg-1"]


def test_restart_rejects_a_different_binding_before_reply_or_ack(tmp_path: Path) -> None:
    first_adapter = _CountingAdapter()
    first = _bridge(tmp_path, first_adapter)
    with pytest.raises(RuntimeError, match="simulated crash"):
        first.handle(
            _response(),
            acknowledge=lambda _: pytest.fail("ACK must follow a durable correlated reply"),
            reply=lambda *_: (_ for _ in ()).throw(RuntimeError("simulated crash")),
        )

    restarted_adapter = _CountingAdapter()
    registry = AdapterRegistry()
    registry.register(restarted_adapter)
    restarted = HostBridge(
        registry=registry,
        binding=HostBinding(adapter_id="counting", values={"session_id": "different"}),
        store=JsonBridgeStore(tmp_path / "bridge-state.json"),
        allowed_senders=("chief",),
    )

    with pytest.raises(HostBindingError, match="binding changed"):
        restarted.handle(
            _response(),
            acknowledge=lambda _: pytest.fail("changed binding must not ACK"),
            reply=lambda *_: pytest.fail("changed binding must not REPLY"),
        )

    assert restarted_adapter.deliveries == []


@pytest.fixture
def fake_host() -> Any:
    state: dict[str, Any] = {"requests": [], "activations": 0, "messages": []}

    class Handler(BaseHTTPRequestHandler):
        def do_GET(self) -> None:  # noqa: N802
            parsed = urlparse(self.path)
            state["requests"].append(
                {
                    "method": "GET",
                    "path": parsed.path,
                    "query": parsed.query,
                    "auth": self.headers.get("Authorization"),
                }
            )
            if parsed.path == "/session/malformed-history/message":
                payload = json.dumps(
                    {
                        "info": {
                            "id": state["malformed_history_message_id"],
                            "role": "user",
                            "sessionID": "malformed-history",
                        },
                        "parts": [{"type": "text", "text": "Already accepted"}],
                    }
                ).encode()
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(payload)))
                self.end_headers()
                self.wfile.write(payload)
                return
            if parsed.path not in {
                "/session/existing-session/message",
                "/session/invalid-result/message",
                "/session/array-result/message",
                "/session/error-result/message",
                "/session/false-completed-result/message",
                "/session/incomplete-result/message",
            }:
                self.send_response(404)
                self.end_headers()
                return
            payload = json.dumps(state["messages"]).encode()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(payload)))
            self.end_headers()
            self.wfile.write(payload)

        def do_POST(self) -> None:  # noqa: N802
            parsed = urlparse(self.path)
            length = int(self.headers.get("Content-Length", "0"))
            body = json.loads(self.rfile.read(length) or b"{}")
            state["requests"].append(
                {
                    "method": "POST",
                    "path": parsed.path,
                    "query": parsed.query,
                    "body": body,
                    "auth": self.headers.get("Authorization"),
                }
            )
            if parsed.path == "/session/invalid-result/message":
                payload = json.dumps(
                    {
                        "info": {
                            "id": "assistant-invalid",
                            "role": "assistant",
                            "parentID": "different-message",
                        },
                        "parts": [{"type": "text", "text": "Wrong correlation"}],
                    }
                ).encode()
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(payload)))
                self.end_headers()
                self.wfile.write(payload)
                return
            if parsed.path in {
                "/session/array-result/message",
                "/session/error-result/message",
                "/session/false-completed-result/message",
                "/session/incomplete-result/message",
            }:
                session_id = parsed.path.split("/")[2]
                info: dict[str, Any] = {
                    "id": f"assistant-{session_id}",
                    "role": "assistant",
                    "parentID": body["messageID"],
                    "sessionID": session_id,
                }
                if session_id != "incomplete-result":
                    info["time"] = {
                        "completed": False if session_id == "false-completed-result" else 1
                    }
                if session_id == "error-result":
                    info["error"] = {"name": "ProviderError"}
                assistant = {
                    "info": info,
                    "parts": [{"type": "text", "text": "Must not be accepted"}],
                }
                payload = json.dumps([assistant] if session_id == "array-result" else assistant).encode()
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(payload)))
                self.end_headers()
                self.wfile.write(payload)
                return
            if parsed.path != "/session/existing-session/message":
                self.send_response(404)
                self.end_headers()
                return
            state["activations"] += 1
            user = {
                "info": {
                    "id": body["messageID"],
                    "role": "user",
                    "sessionID": "existing-session",
                },
                "parts": body["parts"],
            }
            assistant = {
                "info": {
                    "id": f"assistant-{state['activations']}",
                    "role": "assistant",
                    "parentID": body["messageID"],
                    "sessionID": "existing-session",
                    "time": {"completed": 1},
                },
                "parts": [{"type": "text", "text": "Host finished"}],
            }
            state["messages"].extend([user, assistant])
            payload = json.dumps(assistant).encode()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(payload)))
            self.end_headers()
            self.wfile.write(payload)

        def log_message(self, *_args: Any) -> None:
            return

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield f"http://127.0.0.1:{server.server_port}", state
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)


@pytest.mark.parametrize("adapter_type", [OpenCodeServerAdapter, KiloServeAdapter])
def test_http_host_adapters_share_the_same_conformance_contract(adapter_type: Any, fake_host: Any) -> None:
    endpoint, state = fake_host
    adapter = adapter_type(request_timeout_seconds=2)
    binding = HostBinding(
        adapter_id=adapter.manifest.adapter_id,
        values={"endpoint": endpoint, "session_id": "existing-session", "directory": "C:/workspace"},
    )

    result = adapter.deliver(
        binding,
        HostDelivery(message_id="msg-1", correlation_id="msg-1", sender="chief", instructions="Inspect"),
    )
    repeated = adapter.deliver(
        binding,
        HostDelivery(message_id="msg-1", correlation_id="msg-1", sender="chief", instructions="Inspect"),
    )

    assert result == HostResult(outcome="success", summary="Host finished")
    assert repeated == result
    assert state["activations"] == 1
    posts = [request for request in state["requests"] if request["method"] == "POST"]
    assert len(posts) == 1
    assert posts[0]["body"]["parts"] == [{"type": "text", "text": "Inspect"}]
    assert "directory=" in posts[0]["query"]


def test_http_host_adapter_uses_one_deadline_for_history_and_activation(monkeypatch: Any) -> None:
    adapter = OpenCodeServerAdapter(request_timeout_seconds=10)
    binding = HostBinding(
        adapter_id=adapter.manifest.adapter_id,
        values={"endpoint": "http://127.0.0.1:4096", "session_id": "existing-session"},
    )
    delivery = HostDelivery(
        message_id="msg-1",
        correlation_id="msg-1",
        sender="chief",
        instructions="Inspect",
    )
    now = [100.0]
    timeouts: list[float] = []
    monkeypatch.setattr(host_bridge_module.time, "monotonic", lambda: now[0])

    def request_json(*, method: str, timeout_seconds: float, **_kwargs: Any) -> Any:
        timeouts.append(timeout_seconds)
        if method == "GET":
            now[0] += 6.0
            return []
        return {
            "info": {
                "id": "assistant-1",
                "role": "assistant",
                "parentID": delivery.host_message_id(),
                "sessionID": "existing-session",
                "time": {"completed": 1},
            },
            "parts": [{"type": "text", "text": "Host finished"}],
        }

    monkeypatch.setattr(adapter, "_request_json", request_json)

    assert adapter.deliver(binding, delivery).summary == "Host finished"
    assert timeouts == pytest.approx([10.0, 4.0])


def test_http_host_adapter_preserves_an_upstream_absolute_deadline(monkeypatch: Any) -> None:
    adapter = OpenCodeServerAdapter(request_timeout_seconds=10, deadline_monotonic=107.0)
    binding = HostBinding(
        adapter_id=adapter.manifest.adapter_id,
        values={"endpoint": "http://127.0.0.1:4096", "session_id": "existing-session"},
    )
    delivery = HostDelivery(
        message_id="msg-1",
        correlation_id="msg-1",
        sender="chief",
        instructions="Inspect",
    )
    now = [100.0]
    timeouts: list[float] = []
    monkeypatch.setattr(host_bridge_module.time, "monotonic", lambda: now[0])

    def request_json(*, method: str, timeout_seconds: float, **_kwargs: Any) -> Any:
        timeouts.append(timeout_seconds)
        if method == "GET":
            now[0] += 6.0
            return []
        return {
            "info": {
                "id": "assistant-1",
                "role": "assistant",
                "parentID": delivery.host_message_id(),
                "sessionID": "existing-session",
                "time": {"completed": 1},
            },
            "parts": [{"type": "text", "text": "Host finished"}],
        }

    monkeypatch.setattr(adapter, "_request_json", request_json)

    assert adapter.deliver(binding, delivery).summary == "Host finished"
    assert timeouts == pytest.approx([7.0, 1.0])


def test_http_host_json_read_stops_at_its_deadline(monkeypatch: Any) -> None:
    adapter = OpenCodeServerAdapter(request_timeout_seconds=0.01)
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

    monkeypatch.setattr(host_bridge_module.urllib.request, "urlopen", lambda *_args, **_kwargs: SlowResponse())

    started = time.perf_counter()
    try:
        with pytest.raises(HostDeliveryError, match="deadline"):
            adapter._request_json(
                url="http://127.0.0.1:4096/session/existing/message",
                method="GET",
                headers={},
                timeout_seconds=0.01,
            )
        assert time.perf_counter() - started < 0.2
    finally:
        release.set()


def test_crash_after_host_acceptance_recovers_without_second_activation(tmp_path: Path, fake_host: Any) -> None:
    endpoint, state = fake_host
    state_path = tmp_path / "bridge-state.json"

    class CrashBeforeCompletedStore(JsonBridgeStore):
        def put(self, key: str, record: Any) -> None:
            if record.get("status") == "completed":
                raise RuntimeError("simulated ledger crash")
            super().put(key, record)

    adapter = OpenCodeServerAdapter(request_timeout_seconds=2)
    registry = AdapterRegistry()
    registry.register(adapter)
    binding = HostBinding(
        adapter_id=adapter.manifest.adapter_id,
        values={"endpoint": endpoint, "session_id": "existing-session"},
    )
    first = HostBridge(
        registry=registry,
        binding=binding,
        store=CrashBeforeCompletedStore(state_path),
        allowed_senders=("chief",),
    )
    with pytest.raises(RuntimeError, match="ledger crash"):
        first.handle(
            _response(),
            acknowledge=lambda _: pytest.fail("crashed delivery must not ACK"),
            reply=lambda *_: pytest.fail("crashed delivery must not REPLY"),
        )

    restarted = HostBridge(
        registry=registry,
        binding=binding,
        store=JsonBridgeStore(state_path),
        allowed_senders=("chief",),
    )
    acknowledgments: list[str] = []
    replies: list[str] = []
    result = restarted.handle(
        _response(),
        acknowledge=lambda response: acknowledgments.append(response["delivery"]["message_id"]),
        reply=lambda _delivery, host_result, _reply_id: replies.append(host_result.summary),
    )

    assert result["status"] == "completed"
    assert state["activations"] == 1
    assert replies == ["Host finished"]
    assert acknowledgments == ["msg-1"]


def test_existing_incomplete_host_message_is_never_resubmitted(fake_host: Any) -> None:
    endpoint, state = fake_host
    delivery = HostDelivery(
        message_id="msg-1",
        correlation_id="msg-1",
        sender="chief",
        instructions="Inspect",
    )
    state["messages"].append(
        {
            "info": {
                "id": delivery.host_message_id(),
                "role": "user",
                "sessionID": "existing-session",
            },
            "parts": [{"type": "text", "text": "Inspect"}],
        }
    )
    adapter = OpenCodeServerAdapter(request_timeout_seconds=0.1)
    binding = HostBinding(
        adapter_id=adapter.manifest.adapter_id,
        values={"endpoint": endpoint, "session_id": "existing-session"},
    )

    with pytest.raises(HostDeliveryError, match="existing host delivery"):
        adapter.deliver(binding, delivery)

    assert state["activations"] == 0
    assert not any(request["method"] == "POST" for request in state["requests"])


def test_malformed_non_list_history_fails_before_post(fake_host: Any) -> None:
    endpoint, state = fake_host
    delivery = HostDelivery(
        message_id="msg-1",
        correlation_id="msg-1",
        sender="chief",
        instructions="Inspect",
    )
    state["malformed_history_message_id"] = delivery.host_message_id()
    adapter = OpenCodeServerAdapter(request_timeout_seconds=1)
    binding = HostBinding(
        adapter_id=adapter.manifest.adapter_id,
        values={"endpoint": endpoint, "session_id": "malformed-history"},
    )

    with pytest.raises(HostDeliveryError, match="history has an invalid format"):
        adapter.deliver(binding, delivery)

    assert not any(request["method"] == "POST" for request in state["requests"])


def test_invalid_host_session_fails_closed_without_ack(tmp_path: Path, fake_host: Any) -> None:
    endpoint, _state = fake_host
    adapter = OpenCodeServerAdapter(request_timeout_seconds=2)
    registry = AdapterRegistry()
    registry.register(adapter)
    bridge = HostBridge(
        registry=registry,
        binding=HostBinding(
            adapter_id=adapter.manifest.adapter_id,
            values={"endpoint": endpoint, "session_id": "missing"},
        ),
        store=JsonBridgeStore(tmp_path / "bridge-state.json"),
        allowed_senders=("chief",),
    )
    acknowledgments: list[str] = []

    with pytest.raises(HostDeliveryError, match="HTTP 404"):
        bridge.handle(_response(), acknowledge=lambda response: acknowledgments.append("ack"), reply=lambda *_: None)

    assert acknowledgments == []


@pytest.mark.parametrize(
    "host_session",
    [
        "invalid-result",
        "array-result",
        "error-result",
        "false-completed-result",
        "incomplete-result",
    ],
)
def test_nonconforming_host_result_fails_closed_without_ack(
    tmp_path: Path,
    fake_host: Any,
    host_session: str,
) -> None:
    endpoint, state = fake_host
    adapter = OpenCodeServerAdapter(request_timeout_seconds=2)
    registry = AdapterRegistry()
    registry.register(adapter)
    bridge = HostBridge(
        registry=registry,
        binding=HostBinding(
            adapter_id=adapter.manifest.adapter_id,
            values={"endpoint": endpoint, "session_id": host_session},
        ),
        store=JsonBridgeStore(tmp_path / "bridge-state.json"),
        allowed_senders=("chief",),
    )
    acknowledgments: list[str] = []

    with pytest.raises(HostDeliveryError, match="valid correlated result"):
        bridge.handle(
            _response(),
            acknowledge=lambda _: acknowledgments.append("ack"),
            reply=lambda *_: None,
        )

    assert acknowledgments == []


def test_binding_and_durable_state_never_contain_credentials(tmp_path: Path, fake_host: Any) -> None:
    endpoint, state = fake_host
    secret = "not-for-state-or-logs"
    adapter = OpenCodeServerAdapter(
        request_timeout_seconds=2,
        credential_resolver=lambda ref: (
            HostCredential(username="bridge", password=secret)
            if ref == "local-host"
            else None
        ),
    )
    binding = HostBinding(
        adapter_id=adapter.manifest.adapter_id,
        values={"endpoint": endpoint, "session_id": "existing-session", "credential_ref": "local-host"},
    )
    registry = AdapterRegistry()
    registry.register(adapter)
    store_path = tmp_path / "bridge-state.json"
    bridge = HostBridge(
        registry=registry,
        binding=binding,
        store=JsonBridgeStore(store_path),
        allowed_senders=("chief",),
    )

    bridge.handle(_response(), acknowledge=lambda _: None, reply=lambda *_: None)

    persisted = store_path.read_text(encoding="utf-8")
    assert secret not in persisted
    assert endpoint not in persisted
    assert binding.safe_descriptor() == {"adapter_id": "opencode_server", "binding_fingerprint": binding.fingerprint()}
    assert state["requests"][0]["auth"].startswith("Basic ")


def test_binding_rejects_embedded_secrets_without_echoing_them() -> None:
    secret = "embedded-secret"

    with pytest.raises(HostBindingError) as error:
        HostBinding(
            adapter_id="opencode_server",
            values={"endpoint": f"http://user:{secret}@127.0.0.1:4096", "session_id": "existing-session"},
        )

    assert secret not in str(error.value)


@pytest.mark.parametrize(
    "secret_key",
    [
        "access_token",
        "auth",
        "bearer",
        "client_secret",
        "cookie",
        "credential",
        "api-key",
        "signing_key",
    ],
)
def test_binding_rejects_common_secret_key_variants(secret_key: str) -> None:
    with pytest.raises(HostBindingError, match="secret-bearing"):
        HostBinding(
            adapter_id="opencode_server",
            values={
                "endpoint": "http://127.0.0.1:4096",
                "session_id": "existing-session",
                secret_key: "must-not-be-stored",
            },
        )


def test_credential_resolver_error_is_sanitized() -> None:
    secret = "resolver-secret"
    adapter = OpenCodeServerAdapter(
        credential_resolver=lambda _ref: (_ for _ in ()).throw(RuntimeError(secret)),
    )
    binding = HostBinding(
        adapter_id=adapter.manifest.adapter_id,
        values={
            "endpoint": "http://127.0.0.1:4096",
            "session_id": "existing-session",
            "credential_ref": "local-host",
        },
    )

    with pytest.raises(HostBindingError) as error:
        adapter.deliver(
            binding,
            HostDelivery(message_id="msg-1", correlation_id="msg-1", sender="chief", instructions="Inspect"),
        )

    assert secret not in str(error.value)


def test_http_adapter_rejects_bearer_only_credential_without_request(fake_host: Any) -> None:
    endpoint, state = fake_host
    adapter = OpenCodeServerAdapter(
        credential_resolver=lambda _ref: HostCredential(bearer_token="bearer-only")
    )
    binding = HostBinding(
        adapter_id="opencode_server",
        values={
            "endpoint": endpoint,
            "session_id": "existing-session",
            "credential_ref": "local-host",
        },
    )

    with pytest.raises(HostBindingError, match="credential reference"):
        adapter.deliver(
            binding,
            HostDelivery(message_id="msg-1", correlation_id="msg-1", sender="chief", instructions="Inspect"),
        )

    assert state["requests"] == []


def test_non_loopback_endpoint_fails_closed_without_ack(tmp_path: Path) -> None:
    adapter = OpenCodeServerAdapter()
    registry = AdapterRegistry()
    registry.register(adapter)
    bridge = HostBridge(
        registry=registry,
        binding=HostBinding(
            adapter_id=adapter.manifest.adapter_id,
            values={"endpoint": "https://host.example", "session_id": "existing-session"},
        ),
        store=JsonBridgeStore(tmp_path / "bridge-state.json"),
        allowed_senders=("chief",),
    )
    acknowledgments: list[str] = []

    with pytest.raises(HostBindingError, match="loopback"):
        bridge.handle(_response(), acknowledge=lambda _: acknowledgments.append("ack"), reply=lambda *_: None)

    assert acknowledgments == []
