"""At-least-once without observable duplicates (C-REL-05/06).

send_message dedups per (session_id, recipient, message_id). A client that
retries a send with the same envelope id must not produce a second delivery.
"""

from __future__ import annotations

from typing import Any
from uuid import uuid4

from fastapi.testclient import TestClient

from acp.hub.app import create_app
from acp.hub.coordination_store import InMemoryCoordinationStore, SqliteCoordinationStore
from acp.hub.migrations import apply_sqlite_migrations


def _create_session(client: Any, agent_name: str) -> dict[str, Any]:
    response = client.post("/sessions", json={"agent_name": agent_name})
    assert response.status_code in {200, 201}, response.text
    return response.json()


def _join_session(client: Any, agent_name: str, join_code: str) -> dict[str, Any]:
    response = client.post("/sessions/join", json={"agent_name": agent_name, "join_code": join_code})
    assert response.status_code == 200, response.text
    return response.json()


def test_inmemory_record_delivery_if_new_dedups_by_scope() -> None:
    store = InMemoryCoordinationStore()

    assert store.record_delivery_if_new(session_id="s", recipient="r", message_id="m1", processed_at="t1") is True
    assert store.record_delivery_if_new(session_id="s", recipient="r", message_id="m1", processed_at="t2") is False
    assert store.record_delivery_if_new(session_id="s", recipient="r", message_id="m2", processed_at="t3") is True
    assert store.record_delivery_if_new(session_id="s", recipient="r2", message_id="m1", processed_at="t4") is True


def test_sqlite_record_delivery_if_new_dedups_by_scope(tmp_path) -> None:
    db = tmp_path / "acp.sqlite3"
    apply_sqlite_migrations(sqlite_path=db)
    store = SqliteCoordinationStore(sqlite_path=db)

    assert store.record_delivery_if_new(session_id="s", recipient="r", message_id="m1", processed_at="t1") is True
    assert store.record_delivery_if_new(session_id="s", recipient="r", message_id="m1", processed_at="t2") is False
    assert store.record_delivery_if_new(session_id="s", recipient="r", message_id="m2", processed_at="t3") is True
    assert store.record_delivery_if_new(session_id="s", recipient="r2", message_id="m1", processed_at="t4") is True


def test_http_send_with_repeated_id_delivers_once(api_client: Any) -> None:
    chief = _create_session(api_client, "chief")
    worker = _join_session(api_client, "worker", chief["join_code"])
    message_id = str(uuid4())

    first = api_client.post(
        "/sessions/send",
        json={
            "session_id": chief["session_id"],
            "agent_name": "chief",
            "member_token": chief["member_token"],
            "to": "worker",
            "action": "TASK",
            "payload": "do the thing",
            "id": message_id,
        },
    )
    assert first.status_code == 200, first.text
    assert first.json()["delivery"] == "queued"
    assert first.json()["message_id"] == message_id

    # Retry with the SAME idempotency key -> deduped, no second delivery.
    second = api_client.post(
        "/sessions/send",
        json={
            "session_id": chief["session_id"],
            "agent_name": "chief",
            "member_token": chief["member_token"],
            "to": "worker",
            "action": "TASK",
            "payload": "do the thing",
            "id": message_id,
        },
    )
    assert second.status_code == 200, second.text
    assert second.json()["delivery"] == "duplicate"

    # The worker drains exactly one message; a second wait finds nothing pending.
    waited = api_client.post(
        "/sessions/wait",
        json={
            "session_id": worker["session_id"],
            "agent_name": "worker",
            "member_token": worker["member_token"],
            "timeout_seconds": 5,
        },
    )
    assert waited.status_code == 200
    assert waited.json()["message"]["payload"] == "do the thing"

    drained = api_client.post(
        "/sessions/wait",
        json={
            "session_id": worker["session_id"],
            "agent_name": "worker",
            "member_token": worker["member_token"],
            "timeout_seconds": 1,
        },
    )
    # No second copy: the dedup'd retry never enqueued, so this wait times out.
    assert drained.status_code == 200
    assert drained.json().get("status") == "timeout"
    assert "message" not in drained.json()
