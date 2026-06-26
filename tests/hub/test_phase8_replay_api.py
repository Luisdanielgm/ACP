from __future__ import annotations

from uuid import uuid4

from fastapi.testclient import TestClient

from acp.hub.app import HubRuntime, create_app
from acp.hub.sqlite_event_store import SqliteEventStore


def _seed_event(
    store: SqliteEventStore,
    *,
    event_id: str,
    event_type: str,
    created_at: str,
    msg_id: str,
    thread_id: str,
    from_name: str,
    to_name: str,
    action: str = "TASK",
) -> None:
    store.append(
        event_type=event_type,
        payload={
            "event_id": event_id,
            "created_at": created_at,
            "msg_id": msg_id,
            "thread_id": thread_id,
            "from": from_name,
            "to": to_name,
            "action": action,
            "ingress": "http",
        },
    )


def _client(runtime: HubRuntime) -> TestClient:
    return TestClient(create_app(runtime=runtime))


def test_replay_events_filters_use_and_semantics_and_actor_from_or_to(sqlite_runtime_factory) -> None:
    runtime = sqlite_runtime_factory()
    store = runtime.event_store
    assert isinstance(store, SqliteEventStore)

    msg1 = str(uuid4())
    msg2 = str(uuid4())
    msg3 = str(uuid4())
    thread1 = str(uuid4())
    thread2 = str(uuid4())
    thread3 = str(uuid4())

    _seed_event(
        store,
        event_id="evt-001",
        event_type="received",
        created_at="2026-03-05T10:00:00.000000Z",
        msg_id=msg1,
        thread_id=thread1,
        from_name="agent_alpha",
        to_name="agent_beta",
    )
    _seed_event(
        store,
        event_id="evt-002",
        event_type="routed",
        created_at="2026-03-05T10:00:01.000000Z",
        msg_id=msg1,
        thread_id=thread1,
        from_name="agent_alpha",
        to_name="agent_beta",
    )
    _seed_event(
        store,
        event_id="evt-003",
        event_type="rejected",
        created_at="2026-03-05T10:00:02.000000Z",
        msg_id=msg2,
        thread_id=thread2,
        from_name="agent_gamma",
        to_name="agent_alpha",
    )
    _seed_event(
        store,
        event_id="evt-004",
        event_type="delivery_failed",
        created_at="2026-03-05T10:00:03.000000Z",
        msg_id=msg3,
        thread_id=thread3,
        from_name="agent_delta",
        to_name="agent_epsilon",
    )

    with _client(runtime) as client:
        actor_response = client.get("/replay/events", params={"actor": "agent_alpha"})
        assert actor_response.status_code == 200
        actor_events = actor_response.json()["events"]
        assert len(actor_events) == 3
        assert all(
            event["payload"].get("from") == "agent_alpha"
            or event["payload"].get("to") == "agent_alpha"
            for event in actor_events
        )

        and_response = client.get(
            "/replay/events",
            params={
                "actor": "agent_alpha",
                "event_type": "routed",
                "thread_id": thread1,
            },
        )
        assert and_response.status_code == 200
        and_events = and_response.json()["events"]
        assert [event["event_id"] for event in and_events] == ["evt-002"]

        empty_and_response = client.get(
            "/replay/events",
            params={
                "actor": "agent_alpha",
                "event_type": "routed",
                "thread_id": thread2,
            },
        )
        assert empty_and_response.status_code == 200
        assert empty_and_response.json()["events"] == []


def test_replay_events_invalid_and_unknown_filters_return_safe_400(sqlite_runtime_factory) -> None:
    runtime = sqlite_runtime_factory()
    with _client(runtime) as client:
        unknown = client.get("/replay/events", params={"unknown_filter": "x"})
        assert unknown.status_code == 400
        assert unknown.json()["field"] == "unknown_filter"

        invalid_from = client.get("/replay/events", params={"from": "not-a-date"})
        assert invalid_from.status_code == 400
        assert invalid_from.json()["field"] == "from"

        invalid_message_id = client.get("/replay/events", params={"message_id": "bad"})
        assert invalid_message_id.status_code == 400
        assert invalid_message_id.json()["field"] == "message_id"

        invalid_actor = client.get("/replay/events", params={"actor": "bad actor"})
        assert invalid_actor.status_code == 400
        assert invalid_actor.json()["field"] == "actor"

        invalid_event_type = client.get("/replay/events", params={"event_type": "unknown"})
        assert invalid_event_type.status_code == 400
        assert invalid_event_type.json()["field"] == "event_type"

        invalid_range = client.get(
            "/replay/events",
            params={
                "from": "2026-03-05T10:00:03Z",
                "to": "2026-03-05T10:00:00Z",
            },
        )
        assert invalid_range.status_code == 400
        assert invalid_range.json()["field"] == "from"

        invalid_cursor = client.get("/replay/events", params={"cursor": "not_base64"})
        assert invalid_cursor.status_code == 400
        assert invalid_cursor.json()["field"] == "cursor"


def test_replay_events_cursor_pagination_is_deterministic_and_no_dup(sqlite_runtime_factory) -> None:
    runtime = sqlite_runtime_factory()
    store = runtime.event_store
    assert isinstance(store, SqliteEventStore)

    msg_id = str(uuid4())
    thread_id = str(uuid4())
    created = "2026-03-05T10:00:00.000000Z"

    _seed_event(
        store,
        event_id="evt-a",
        event_type="received",
        created_at=created,
        msg_id=msg_id,
        thread_id=thread_id,
        from_name="agent_sender",
        to_name="agent_receiver",
    )
    _seed_event(
        store,
        event_id="evt-b",
        event_type="received",
        created_at=created,
        msg_id=msg_id,
        thread_id=thread_id,
        from_name="agent_sender",
        to_name="agent_receiver",
    )
    _seed_event(
        store,
        event_id="evt-c",
        event_type="received",
        created_at=created,
        msg_id=msg_id,
        thread_id=thread_id,
        from_name="agent_sender",
        to_name="agent_receiver",
    )
    _seed_event(
        store,
        event_id="evt-d",
        event_type="routed",
        created_at="2026-03-05T10:00:01.000000Z",
        msg_id=msg_id,
        thread_id=thread_id,
        from_name="agent_sender",
        to_name="agent_receiver",
    )
    _seed_event(
        store,
        event_id="evt-e",
        event_type="rejected",
        created_at="2026-03-05T09:59:59.000000Z",
        msg_id=msg_id,
        thread_id=thread_id,
        from_name="agent_sender",
        to_name="agent_receiver",
    )

    with _client(runtime) as client:
        page1 = client.get("/replay/events", params={"order": "desc", "limit": 2})
        assert page1.status_code == 200
        payload1 = page1.json()
        ids1 = [event["event_id"] for event in payload1["events"]]
        assert ids1 == ["evt-d", "evt-c"]
        assert payload1["next_cursor"] is not None

        repeat = client.get("/replay/events", params={"order": "desc", "limit": 2})
        assert repeat.status_code == 200
        assert repeat.json()["events"] == payload1["events"]
        assert repeat.json()["next_cursor"] == payload1["next_cursor"]

        page2 = client.get(
            "/replay/events",
            params={"order": "desc", "limit": 2, "cursor": payload1["next_cursor"]},
        )
        assert page2.status_code == 200
        payload2 = page2.json()
        ids2 = [event["event_id"] for event in payload2["events"]]
        assert ids2 == ["evt-b", "evt-a"]
        assert payload2["next_cursor"] is not None

        page3 = client.get(
            "/replay/events",
            params={"order": "desc", "limit": 2, "cursor": payload2["next_cursor"]},
        )
        assert page3.status_code == 200
        ids3 = [event["event_id"] for event in page3.json()["events"]]
        assert ids3 == ["evt-e"]
        assert page3.json()["next_cursor"] is None

        all_ids = ids1 + ids2 + ids3
        assert len(all_ids) == len(set(all_ids))

        clamp = client.get("/replay/events", params={"limit": 999})
        assert clamp.status_code == 200
        assert clamp.json()["limit"] == 200


def test_replay_message_timeline_returns_metadata_and_partial_or_complete(sqlite_runtime_factory) -> None:
    runtime = sqlite_runtime_factory()
    store = runtime.event_store
    assert isinstance(store, SqliteEventStore)

    complete_msg = str(uuid4())
    partial_msg = str(uuid4())
    thread_id = str(uuid4())

    _seed_event(
        store,
        event_id="tl-001",
        event_type="received",
        created_at="2026-03-05T10:00:00.000000Z",
        msg_id=complete_msg,
        thread_id=thread_id,
        from_name="agent_sender",
        to_name="agent_receiver",
    )
    _seed_event(
        store,
        event_id="tl-002",
        event_type="routed",
        created_at="2026-03-05T10:00:01.000000Z",
        msg_id=complete_msg,
        thread_id=thread_id,
        from_name="agent_sender",
        to_name="agent_receiver",
    )
    _seed_event(
        store,
        event_id="tl-003",
        event_type="received",
        created_at="2026-03-05T11:00:00.000000Z",
        msg_id=partial_msg,
        thread_id=thread_id,
        from_name="agent_sender",
        to_name="agent_receiver",
    )

    with _client(runtime) as client:
        complete = client.get(f"/replay/messages/{complete_msg}")
        assert complete.status_code == 200
        complete_body = complete.json()
        assert complete_body["metadata"] == {
            "message_id": complete_msg,
            "timeline_status": "complete",
        }
        assert [event["event_id"] for event in complete_body["events"]] == ["tl-001", "tl-002"]

        partial = client.get(f"/replay/messages/{partial_msg}")
        assert partial.status_code == 200
        assert partial.json()["metadata"]["timeline_status"] == "partial"

        missing = client.get(f"/replay/messages/{uuid4()}")
        assert missing.status_code == 404
        assert missing.json()["field"] == "message_id"

        invalid = client.get("/replay/messages/not-a-uuid")
        assert invalid.status_code == 400
        assert invalid.json()["field"] == "message_id"
