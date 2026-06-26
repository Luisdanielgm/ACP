from __future__ import annotations

import json
from datetime import datetime, timezone
from uuid import uuid4

from fastapi.testclient import TestClient

from acp.hub.app import HubRuntime, create_app
from acp.hub.auth_service import PermissiveAuthService


def _msg_frame(*, sender: str, recipient: str, action: str = "TASK", msg_id: str | None = None) -> str:
    return json.dumps(
        {
            "type": "MSG",
            "id": msg_id or str(uuid4()),
            "ts": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
            "from": sender,
            "to": recipient,
            "action": action,
            "payload": "hello",
        }
    )


def _msg_body(*, sender: str, recipient: str, payload: str = "hello", msg_id: str | None = None) -> dict[str, str]:
    return {
        "id": msg_id or str(uuid4()),
        "ts": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "from": sender,
        "to": recipient,
        "action": "TASK",
        "payload": payload,
    }


class SpyAuthService(PermissiveAuthService):
    def __init__(self, *, required_token: str | None = None) -> None:
        super().__init__(required_token=required_token)
        self.calls: list[str] = []

    def authorize_ws_hello(self, *, token: str | None):
        self.calls.append("ws_hello")
        return super().authorize_ws_hello(token=token)

    def authorize_http_send(
        self,
        *,
        authorization: str | None,
        x_acp_token: str | None,
        body_token: str | None,
    ):
        self.calls.append("http_send")
        return super().authorize_http_send(
            authorization=authorization,
            x_acp_token=x_acp_token,
            body_token=body_token,
        )

    def authorize_ws_message(self, *, session_name: str | None, claimed_sender: str | None):
        self.calls.append("ws_message")
        return super().authorize_ws_message(session_name=session_name, claimed_sender=claimed_sender)


def test_http_send_uses_runtime_shared_auth_service(websocket_factory) -> None:
    spy = SpyAuthService(required_token="secret-token")
    runtime = HubRuntime(required_token="secret-token", auth_service=spy)
    receiver_socket = websocket_factory()
    assert runtime.registry.register_agent(
        session_id="receiver-session",
        websocket=receiver_socket,
        name="agent_receiver",
    )

    app = create_app(runtime=runtime)
    with TestClient(app) as client:
        response = client.post(
            "/send",
            json=_msg_body(sender="orchestrator_1", recipient="agent_receiver"),
            headers={"Authorization": "Bearer secret-token"},
        )

    assert response.status_code == 200
    assert "http_send" in spy.calls


def test_ws_ingress_uses_runtime_shared_auth_service(
    hello_frame,
    run_ingress,
    trace_sink,
    websocket_factory,
) -> None:
    spy = SpyAuthService(required_token="secret-token")

    sender_socket = websocket_factory(
        [
            json.dumps({"type": "HELLO", "role": "agent", "name": "agent_sender", "token": "secret-token"}),
            _msg_frame(sender="agent_sender", recipient="agent_receiver"),
        ]
    )
    receiver_socket = websocket_factory()
    active_agents: dict[str, object] = {}

    from acp.hub.session_registry import SessionRegistry

    registry = SessionRegistry(active_agents=active_agents)
    assert registry.register_agent(
        session_id="receiver-session",
        websocket=receiver_socket,
        name="agent_receiver",
    )

    run_ingress(
        sender_socket,
        session_id="sender-session",
        active_agents=active_agents,
        trace_sink=trace_sink,
        session_registry=registry,
        auth_service=spy,
    )

    assert "ws_hello" in spy.calls
    assert "ws_message" in spy.calls
    assert len(receiver_socket.sent) == 1
    assert receiver_socket.sent[0]["to"] == "agent_receiver"


def test_same_auth_service_instance_can_serve_http_and_ws_flows(
    run_ingress,
    trace_sink,
    websocket_factory,
) -> None:
    spy = SpyAuthService(required_token="secret-token")
    runtime = HubRuntime(required_token="secret-token", auth_service=spy)
    receiver_socket = websocket_factory()
    assert runtime.registry.register_agent(
        session_id="receiver-session",
        websocket=receiver_socket,
        name="agent_receiver",
    )

    app = create_app(runtime=runtime)
    with TestClient(app) as client:
        http_response = client.post(
            "/send",
            json=_msg_body(sender="orchestrator_1", recipient="agent_receiver"),
            headers={"Authorization": "Bearer secret-token"},
        )
    assert http_response.status_code == 200

    ws_sender = websocket_factory(
        [
            json.dumps({"type": "HELLO", "role": "agent", "name": "agent_sender", "token": "secret-token"}),
            _msg_frame(sender="agent_sender", recipient="agent_receiver"),
        ]
    )
    run_ingress(
        ws_sender,
        session_id="sender-session",
        active_agents=runtime.active_agents,
        trace_sink=trace_sink,
        session_registry=runtime.registry,
        auth_service=runtime.auth_service,
    )

    assert spy.calls.count("http_send") >= 1
    assert spy.calls.count("ws_hello") >= 1
    assert spy.calls.count("ws_message") >= 1
