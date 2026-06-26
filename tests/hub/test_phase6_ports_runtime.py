from __future__ import annotations

from dataclasses import dataclass

from acp.hub.app import HubRuntime, create_app
from acp.hub.auth_service import PermissiveAuthService
from acp.hub.event_store import InMemoryEventStore


@dataclass
class _CustomEventStore:
    events: list[tuple[str, dict[str, object]]]

    def append(self, *, event_type: str, payload: dict[str, object]) -> None:
        self.events.append((event_type, dict(payload)))


class _CustomAuthService:
    def authorize_ws_hello(self, *, token: str | None):
        return None

    def authorize_http_send(
        self,
        *,
        authorization: str | None,
        x_acp_token: str | None,
        body_token: str | None,
    ):
        return None

    def authorize_ws_message(self, *, session_name: str | None, claimed_sender: str | None):
        return None


def test_hub_runtime_defaults_include_phase6_ports_and_readiness_flags() -> None:
    runtime = HubRuntime()

    assert isinstance(runtime.event_store, InMemoryEventStore)
    assert isinstance(runtime.auth_service, PermissiveAuthService)

    status = runtime.as_status_payload()
    assert status["storage_ready"] is True
    assert status["auth_ready"] is True
    assert status["migration_ready"] is True
    assert status["auth_enforce"] is False
    assert status["persistence_strict"] is False
    assert status["token_rotation_active"] is False
    assert status["token_overlap_until"] is None
    assert isinstance(status["storage_ready"], bool)
    assert isinstance(status["auth_ready"], bool)
    assert isinstance(status["migration_ready"], bool)


def test_hub_runtime_accepts_injected_ports_without_overriding() -> None:
    custom_store = _CustomEventStore(events=[])
    custom_auth = _CustomAuthService()

    runtime = HubRuntime(event_store=custom_store, auth_service=custom_auth)

    assert runtime.event_store is custom_store
    assert runtime.auth_service is custom_auth


def test_default_event_store_collects_events_for_future_phases() -> None:
    runtime = HubRuntime()
    runtime.event_store.append(event_type="phase6.probe", payload={"ok": True})

    assert runtime.event_store.count() == 1
    assert runtime.event_store.snapshot()[0].event_type == "phase6.probe"


def test_runtime_payload_contains_safe_readiness_only(api_client, tokenized_runtime) -> None:
    app = create_app(runtime=tokenized_runtime)

    from fastapi.testclient import TestClient

    with TestClient(app) as client:
        response = client.get("/runtime")

    assert response.status_code == 200
    body = response.json()
    runtime_payload = body["runtime"]

    assert runtime_payload["token_required"] is True
    assert runtime_payload["storage_ready"] is True
    assert runtime_payload["auth_ready"] is True
    assert runtime_payload["migration_ready"] is True
    assert runtime_payload["auth_enforce"] is False
    assert runtime_payload["persistence_strict"] is False
    assert "secret-token" not in str(runtime_payload)
