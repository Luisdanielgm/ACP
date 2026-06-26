from __future__ import annotations

import asyncio
import json
import sys
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient

repo_root = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(repo_root / "apps" / "hub" / "src"))

from acp.hub.app import HubRuntime, create_app
from acp.hub.coordination_service import SessionCoordinationService
from acp.hub.coordination_store import SqliteCoordinationStore
from acp.hub.migrations import apply_sqlite_migrations
from acp.hub.session_registry import SessionRegistry
from acp.hub.sqlite_event_store import SqliteEventStore
from acp.hub.ws_ingress import run_ws_ingress


class FakeWebSocket:
    def __init__(self, inbound: list[str] | None = None) -> None:
        self._inbound = list(inbound or [])
        self.sent: list[dict[str, Any]] = []
        self.closed = False
        self.close_args: dict[str, Any] | None = None

    async def receive_text(self) -> str:
        if not self._inbound:
            raise StopAsyncIteration
        return self._inbound.pop(0)

    async def send_json(self, payload: dict[str, Any]) -> None:
        self.sent.append(payload)

    async def send_text(self, payload: str) -> None:
        self.sent.append(json.loads(payload))

    async def close(self, *, code: int, reason: str) -> None:
        self.closed = True
        self.close_args = {"code": code, "reason": reason}


class ObserverSocket:
    def __init__(self) -> None:
        self.sent: list[dict[str, Any]] = []

    async def send_json(self, payload: dict[str, Any]) -> None:
        self.sent.append(payload)

    async def send_text(self, payload: str) -> None:
        self.sent.append(json.loads(payload))


@pytest.fixture
def websocket_factory() -> Any:
    def _make(inbound: list[str] | None = None) -> FakeWebSocket:
        return FakeWebSocket(inbound=inbound)

    return _make


@pytest.fixture
def observer_socket_factory() -> Any:
    def _make() -> ObserverSocket:
        return ObserverSocket()

    return _make


@pytest.fixture
def hello_frame() -> Any:
    def _build(name: str, *, role: str = "agent") -> str:
        return json.dumps({"type": "HELLO", "role": role, "name": name})

    return _build


@pytest.fixture
def trace_sink() -> list[dict[str, Any]]:
    return []


@pytest.fixture
def assert_close_code() -> Any:
    def _assert(
        websocket: FakeWebSocket,
        *,
        expected_code: int,
        expected_reason: str,
    ) -> None:
        assert websocket.closed is True
        assert websocket.close_args == {"code": expected_code, "reason": expected_reason}

    return _assert


@pytest.fixture
def assert_lifecycle_trace_sequence() -> Any:
    def _assert(
        traces: list[dict[str, Any]],
        *,
        role: str,
        name: str,
        session_id: str,
    ) -> None:
        lifecycle_events = [
            event for event in traces if event.get("event") in {"CONNECT", "DISCONNECT"}
        ]
        assert [event["event"] for event in lifecycle_events] == ["CONNECT", "DISCONNECT"]
        assert [event["role"] for event in lifecycle_events] == [role, role]
        assert [event["name"] for event in lifecycle_events] == [name, name]
        assert [event["source_session"] for event in lifecycle_events] == [session_id, session_id]
        assert all("payload" not in event for event in traces)
        assert all("token" not in event for event in traces)

    return _assert


@pytest.fixture
def run_ingress() -> Any:
    def _run(
        websocket: FakeWebSocket,
        *,
        session_id: str,
        active_agents: dict[str, Any] | None = None,
        trace_sink: Any = None,
        session_registry: SessionRegistry | None = None,
        auth_service: Any | None = None,
        event_store: Any | None = None,
        required_token: str | None = None,
        persistence_strict: bool = False,
    ) -> None:
        asyncio.run(
            run_ws_ingress(
                websocket,
                session_id=session_id,
                active_agents=active_agents if active_agents is not None else {},
                trace_sink=trace_sink if trace_sink is not None else [],
                session_registry=session_registry,
                auth_service=auth_service,
                event_store=event_store,
                required_token=required_token,
                persistence_strict=persistence_strict,
            )
        )

    return _run


@pytest.fixture
def hub_runtime() -> HubRuntime:
    return HubRuntime()


@pytest.fixture
def tokenized_runtime() -> HubRuntime:
    return HubRuntime(required_token="secret-token")


@pytest.fixture
def api_client(hub_runtime: HubRuntime) -> Any:
    app = create_app(runtime=hub_runtime)
    with TestClient(app) as client:
        yield client


@pytest.fixture
def tokenized_api_client(tokenized_runtime: HubRuntime) -> Any:
    app = create_app(runtime=tokenized_runtime)
    with TestClient(app) as client:
        yield client


@pytest.fixture
def sqlite_db_path(tmp_path: Path) -> Path:
    return tmp_path / "acp-phase7.sqlite3"


@pytest.fixture
def sqlite_runtime_factory(sqlite_db_path: Path) -> Any:
    apply_sqlite_migrations(sqlite_path=sqlite_db_path)

    def _build() -> HubRuntime:
        return HubRuntime(
            event_store=SqliteEventStore(sqlite_path=sqlite_db_path),
            coordination=SessionCoordinationService(store=SqliteCoordinationStore(sqlite_path=sqlite_db_path)),
        )

    return _build


@pytest.fixture
def sqlite_runtime_pair(sqlite_runtime_factory) -> Any:
    def _build_pair() -> tuple[HubRuntime, HubRuntime]:
        first = sqlite_runtime_factory()
        second = sqlite_runtime_factory()
        return first, second

    return _build_pair


@pytest.fixture
def sqlite_store_snapshot(sqlite_runtime_factory) -> Any:
    def _snapshot() -> list[dict[str, Any]]:
        runtime = sqlite_runtime_factory()
        store = runtime.event_store
        if not isinstance(store, SqliteEventStore):
            return []
        return [event.payload for event in store.snapshot()]

    return _snapshot

