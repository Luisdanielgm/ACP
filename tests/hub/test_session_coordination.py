from __future__ import annotations

import threading
import time
from typing import Any

from fastapi.testclient import TestClient

from acp.hub.app import create_app
from acp.hub.coordination_service import SessionConflictError
from acp.hub.dashboard_auth import DashboardSessionStore


def _create_session(client: Any, agent_name: str) -> dict[str, Any]:
    response = client.post("/sessions", json={"agent_name": agent_name})
    assert response.status_code == 201
    return response.json()


def _join_session(client: Any, agent_name: str, join_code: str) -> dict[str, Any]:
    response = client.post("/sessions/join", json={"agent_name": agent_name, "join_code": join_code})
    assert response.status_code == 200
    return response.json()


def test_session_create_join_and_snapshot(api_client: Any) -> None:
    chief = _create_session(api_client, "chief")
    worker = _join_session(api_client, "worker", chief["join_code"])

    snapshot = api_client.get(
        f"/sessions/{chief['session_id']}",
        params={"agent_name": "chief", "member_token": chief["member_token"]},
    )
    assert snapshot.status_code == 200
    body = snapshot.json()
    assert body["status"] == "ok"
    assert body["session"]["session_id"] == chief["session_id"]
    assert sorted(member["agent_name"] for member in body["session"]["members"]) == ["chief", "worker"]
    assert worker["session_id"] == chief["session_id"]


def test_session_members_advertise_capabilities(api_client: Any) -> None:
    chief_response = api_client.post(
        "/sessions",
        json={"agent_name": "chief", "capabilities": ["planning", "backend"]},
    )
    assert chief_response.status_code == 201
    chief = chief_response.json()

    worker_response = api_client.post(
        "/sessions/join",
        json={"agent_name": "worker", "join_code": chief["join_code"], "capabilities": "backend,python,backend"},
    )
    assert worker_response.status_code == 200
    worker = worker_response.json()

    status = api_client.post(
        "/sessions/status",
        json={
            "session_id": worker["session_id"],
            "agent_name": "worker",
            "member_token": worker["member_token"],
            "status": "waiting",
            "capabilities": ["backend", "fastapi"],
        },
    )
    assert status.status_code == 200
    assert status.json()["member"]["capabilities"] == ["backend", "fastapi"]

    snapshot = api_client.get(
        f"/sessions/{chief['session_id']}",
        params={"agent_name": "chief", "member_token": chief["member_token"]},
    )
    assert snapshot.status_code == 200
    members = {item["agent_name"]: item for item in snapshot.json()["session"]["members"]}
    assert members["chief"]["capabilities"] == ["planning", "backend"]
    assert members["worker"]["capabilities"] == ["backend", "fastapi"]


def test_session_wait_returns_queued_message(api_client: Any) -> None:
    chief = _create_session(api_client, "chief")
    worker = _join_session(api_client, "worker", chief["join_code"])

    wait_response: dict[str, Any] = {}

    def _waiter() -> None:
        response = api_client.post(
            "/sessions/wait",
            json={
                "session_id": worker["session_id"],
                "agent_name": "worker",
                "member_token": worker["member_token"],
                "timeout_seconds": 5,
            },
        )
        wait_response["status_code"] = response.status_code
        wait_response["body"] = response.json()

    thread = threading.Thread(target=_waiter)
    thread.start()
    time.sleep(0.3)

    send = api_client.post(
        "/sessions/send",
        json={
            "session_id": chief["session_id"],
            "agent_name": "chief",
            "member_token": chief["member_token"],
            "to": "worker",
            "action": "TASK",
            "payload": "Take auth ownership",
        },
    )
    assert send.status_code == 200
    assert send.json()["status"] == "queued"

    thread.join(timeout=5)
    assert wait_response["status_code"] == 200
    assert wait_response["body"]["status"] == "message"
    assert wait_response["body"]["message"]["from"] == "chief"
    assert wait_response["body"]["message"]["to"] == "worker"
    assert wait_response["body"]["message"]["payload"] == "Take auth ownership"


def test_session_wait_conflict_is_actionable(api_client: Any) -> None:
    chief = _create_session(api_client, "chief")
    worker = _join_session(api_client, "worker", chief["join_code"])
    first_wait_ready: dict[str, Any] = {}

    def _waiter() -> None:
        response = api_client.post(
            "/sessions/wait",
            json={
                "session_id": worker["session_id"],
                "agent_name": "worker",
                "member_token": worker["member_token"],
                "timeout_seconds": 2,
            },
        )
        first_wait_ready["status_code"] = response.status_code

    thread = threading.Thread(target=_waiter)
    thread.start()
    time.sleep(0.2)

    response = api_client.post(
        "/sessions/wait",
        json={
            "session_id": worker["session_id"],
            "agent_name": "worker",
            "member_token": worker["member_token"],
            "timeout_seconds": 1,
        },
    )

    assert response.status_code == 409
    body = response.json()
    assert body["code"] == "WAIT_ALREADY_ACTIVE"
    assert body["field"] == "agent_name"
    assert "Do not run concurrent waits" in body["message"]
    assert "listen" in body["details"]["recommended_command"]
    assert "--stop-after-message --timeout-seconds 300" in body["details"]["recommended_command"]

    thread.join(timeout=3)
    assert first_wait_ready.get("status_code") in {200, None}


def test_session_cancel_wait_clears_active_wait(api_client: Any) -> None:
    chief = _create_session(api_client, "chief")
    worker = _join_session(api_client, "worker", chief["join_code"])
    first_wait: dict[str, Any] = {}

    def _waiter() -> None:
        response = api_client.post(
            "/sessions/wait",
            json={
                "session_id": worker["session_id"],
                "agent_name": "worker",
                "member_token": worker["member_token"],
                "timeout_seconds": 10,
            },
        )
        first_wait["status_code"] = response.status_code

    thread = threading.Thread(target=_waiter)
    thread.start()
    time.sleep(0.2)

    cancelled = api_client.post(
        "/sessions/cancel-wait",
        json={
            "session_id": worker["session_id"],
            "agent_name": "worker",
            "member_token": worker["member_token"],
        },
    )
    assert cancelled.status_code == 200
    assert cancelled.json()["active_wait_cleared"] is True

    waited_again = api_client.post(
        "/sessions/wait",
        json={
            "session_id": worker["session_id"],
            "agent_name": "worker",
            "member_token": worker["member_token"],
            "timeout_seconds": 0.1,
        },
    )
    assert waited_again.status_code == 200
    assert waited_again.json()["status"] == "timeout"

    thread.join(timeout=2)


def test_member_endpoints_distinguish_gone_session_from_auth_failure(api_client: Any) -> None:
    # A session that no longer exists (closed, or lost on a Hub redeploy) must
    # answer 404 SESSION_NOT_FOUND so clients re-create/re-join, while a bad
    # member token on a live session stays 403 so clients fix their credentials.
    chief = _create_session(api_client, "chief")

    for route, extra in (
        ("/sessions/wait", {"timeout_seconds": 1}),
        ("/sessions/send", {"to": "ghost", "action": "INFO", "payload": "hi"}),
        ("/sessions/heartbeat", {}),
    ):
        gone = api_client.post(
            route,
            json={
                "session_id": "00000000-0000-4000-8000-000000000000",
                "agent_name": "chief",
                "member_token": chief["member_token"],
                **extra,
            },
        )
        assert gone.status_code == 404, route
        assert gone.json()["code"] == "SESSION_NOT_FOUND", route

    bad_token = api_client.post(
        "/sessions/wait",
        json={
            "session_id": chief["session_id"],
            "agent_name": "chief",
            "member_token": "wrong-token",
            "timeout_seconds": 1,
        },
    )
    assert bad_token.status_code == 403
    assert bad_token.json()["code"] != "SESSION_NOT_FOUND"


def test_session_member_token_can_be_sent_by_header(api_client: Any) -> None:
    chief = _create_session(api_client, "chief")
    worker = _join_session(api_client, "worker", chief["join_code"])

    send = api_client.post(
        "/sessions/send",
        headers={"X-ACP-Member-Token": chief["member_token"]},
        json={
            "session_id": chief["session_id"],
            "agent_name": "chief",
            "to": "worker",
            "action": "INFO",
            "payload": "header token works",
        },
    )
    assert send.status_code == 200

    waited = api_client.post(
        "/sessions/wait",
        headers={"X-ACP-Member-Token": worker["member_token"]},
        json={
            "session_id": worker["session_id"],
            "agent_name": "worker",
            "timeout_seconds": 5,
        },
    )
    assert waited.status_code == 200
    assert waited.json()["message"]["payload"] == "header token works"


def test_session_send_broadcasts_to_all_other_members(api_client: Any) -> None:
    chief = _create_session(api_client, "chief")
    worker_a = _join_session(api_client, "worker-a", chief["join_code"])
    worker_b = _join_session(api_client, "worker-b", chief["join_code"])

    sent = api_client.post(
        "/sessions/send",
        json={
            "session_id": chief["session_id"],
            "agent_name": "chief",
            "member_token": chief["member_token"],
            "to": "*",
            "action": "INFO",
            "payload": "standup now",
        },
    )
    assert sent.status_code == 200
    body = sent.json()
    assert body["to"] == "all"
    assert body["recipients"] == ["worker-a", "worker-b"]

    for worker, agent_name in ((worker_a, "worker-a"), (worker_b, "worker-b")):
        waited = api_client.post(
            "/sessions/wait",
            json={
                "session_id": worker["session_id"],
                "agent_name": agent_name,
                "member_token": worker["member_token"],
                "timeout_seconds": 5,
            },
        )
        assert waited.status_code == 200
        message = waited.json()["message"]
        assert message["payload"] == "standup now"
        assert message["to"] in {"worker-a", "worker-b"}


def test_sqlite_session_broadcast_queues_one_message_per_recipient(sqlite_runtime_pair) -> None:
    runtime1, runtime2 = sqlite_runtime_pair()
    with TestClient(create_app(runtime=runtime1)) as client1:
        chief = _create_session(client1, "chief")
        worker_a = _join_session(client1, "worker-a", chief["join_code"])
        worker_b = _join_session(client1, "worker-b", chief["join_code"])

        sent = client1.post(
            "/sessions/send",
            json={
                "session_id": chief["session_id"],
                "agent_name": "chief",
                "member_token": chief["member_token"],
                "to": "all",
                "action": "INFO",
                "payload": "sqlite broadcast",
            },
        )
        assert sent.status_code == 200
        assert sent.json()["recipients"] == ["worker-a", "worker-b"]

    with TestClient(create_app(runtime=runtime2)) as client2:
        for worker, agent_name in ((worker_a, "worker-a"), (worker_b, "worker-b")):
            waited = client2.post(
                "/sessions/wait",
                json={
                    "session_id": worker["session_id"],
                    "agent_name": agent_name,
                    "member_token": worker["member_token"],
                    "timeout_seconds": 5,
                },
            )
            assert waited.status_code == 200
            assert waited.json()["message"]["payload"] == "sqlite broadcast"


def test_session_send_reports_all_missing_required_fields(api_client: Any) -> None:
    response = api_client.post("/sessions/send", json={})

    assert response.status_code == 400
    body = response.json()
    assert body["field"] == "body"
    assert body["details"]["missing_fields"] == [
        "session_id",
        "agent_name",
        "to",
        "action",
        "payload",
        "member_token",
    ]


def test_session_rest_openapi_documents_request_bodies(api_client: Any) -> None:
    schema = api_client.get("/openapi.json").json()

    send_body = schema["paths"]["/sessions/send"]["post"]["requestBody"]
    wait_body = schema["paths"]["/sessions/wait"]["post"]["requestBody"]
    join_body = schema["paths"]["/sessions/join"]["post"]["requestBody"]

    assert send_body["content"]["application/json"]["schema"]["required"] == [
        "session_id",
        "agent_name",
        "to",
        "action",
        "payload",
    ]
    assert wait_body["content"]["application/json"]["schema"]["properties"]["member_token"]["description"]
    assert join_body["content"]["application/json"]["schema"]["required"] == ["agent_name", "join_code"]
    assert "capabilities" in join_body["content"]["application/json"]["schema"]["properties"]


def test_session_status_update_requires_member_token(api_client: Any) -> None:
    chief = _create_session(api_client, "chief")

    denied = api_client.post(
        "/sessions/status",
        json={
            "session_id": chief["session_id"],
            "agent_name": "chief",
            "member_token": "wrong-token",
            "status": "busy",
            "status_text": "reviewing auth",
        },
    )
    assert denied.status_code == 403

    allowed = api_client.post(
        "/sessions/status",
        json={
            "session_id": chief["session_id"],
            "agent_name": "chief",
            "member_token": chief["member_token"],
            "status": "busy",
            "status_text": "reviewing auth",
        },
    )
    assert allowed.status_code == 200
    assert allowed.json()["member"]["status"] == "busy"
    assert allowed.json()["member"]["status_text"] == "reviewing auth"


def test_session_heartbeat_refreshes_member_liveness(api_client: Any) -> None:
    chief = _create_session(api_client, "chief")

    status = api_client.post(
        "/sessions/status",
        json={
            "session_id": chief["session_id"],
            "agent_name": "chief",
            "member_token": chief["member_token"],
            "status": "busy",
            "status_text": "reviewing auth",
        },
    )
    assert status.status_code == 200

    heartbeat = api_client.post(
        "/sessions/heartbeat",
        json={
            "session_id": chief["session_id"],
            "agent_name": "chief",
            "member_token": chief["member_token"],
            "detail": "still processing auth review",
        },
    )
    assert heartbeat.status_code == 200
    member = heartbeat.json()["member"]
    assert member["status"] == "busy"
    assert member["status_text"] == "still processing auth review"
    assert member["heartbeat_state"] == "live"
    assert isinstance(member["heartbeat_age_seconds"], int)

    detail = api_client.get(
        f"/sessions/{chief['session_id']}/detail",
        params={"agent_name": "chief", "member_token": chief["member_token"]},
    )
    assert detail.status_code == 200
    payload = detail.json()["session"]
    chief_member = next(item for item in payload["members"] if item["agent_name"] == "chief")
    assert chief_member["heartbeat_state"] == "live"


def test_leave_session_frees_agent_identity(api_client: Any) -> None:
    chief = _create_session(api_client, "chief")

    left = api_client.post(
        "/sessions/leave",
        json={
            "session_id": chief["session_id"],
            "agent_name": "chief",
            "member_token": chief["member_token"],
        },
    )
    assert left.status_code == 200
    assert left.json()["status"] == "left"
    assert left.json()["session_closed"] is True

    recreated = _create_session(api_client, "chief")
    assert recreated["session_id"] != chief["session_id"]


def test_leave_session_allows_collaborator_to_join_new_session(api_client: Any) -> None:
    chief_a = _create_session(api_client, "chief-a")
    worker = _join_session(api_client, "worker", chief_a["join_code"])

    left = api_client.post(
        "/sessions/leave",
        json={
            "session_id": worker["session_id"],
            "agent_name": "worker",
            "member_token": worker["member_token"],
        },
    )
    assert left.status_code == 200
    assert left.json()["session_closed"] is False

    chief_b = _create_session(api_client, "chief-b")
    rejoined = _join_session(api_client, "worker", chief_b["join_code"])
    assert rejoined["session_id"] == chief_b["session_id"]


def test_session_detail_exposes_history_pending_and_current_task(api_client: Any) -> None:
    chief = _create_session(api_client, "chief")
    worker = _join_session(api_client, "worker", chief["join_code"])

    queued = api_client.post(
        "/sessions/send",
        json={
            "session_id": chief["session_id"],
            "agent_name": "chief",
            "member_token": chief["member_token"],
            "to": "worker",
            "action": "TASK",
            "payload": "Take ownership of auth.py",
        },
    )
    assert queued.status_code == 200
    assert queued.json()["delivery"] == "queued"

    detail = api_client.get(
        f"/sessions/{chief['session_id']}/detail",
        params={"agent_name": "worker", "member_token": worker["member_token"]},
    )
    assert detail.status_code == 200
    body = detail.json()
    assert body["status"] == "ok"
    assert body["session"]["summary"]["pending_total"] == 1
    worker_member = next(item for item in body["session"]["members"] if item["agent_name"] == "worker")
    assert worker_member["pending_count"] == 1
    assert worker_member["current_task"] == "Take ownership of auth.py"
    assert any(event["event"] == "MESSAGE_SENT" for event in body["session"]["history"])


def test_reply_clears_worker_current_task(api_client: Any) -> None:
    chief = _create_session(api_client, "chief")
    worker = _join_session(api_client, "worker", chief["join_code"])

    queued = api_client.post(
        "/sessions/send",
        json={
            "session_id": chief["session_id"],
            "agent_name": "chief",
            "member_token": chief["member_token"],
            "to": "worker",
            "action": "TASK",
            "payload": "Take ownership of auth.py",
        },
    )
    assert queued.status_code == 200

    replied = api_client.post(
        "/sessions/send",
        json={
            "session_id": worker["session_id"],
            "agent_name": "worker",
            "member_token": worker["member_token"],
            "to": "chief",
            "action": "REPLY",
            "payload": {"task_id": "auth", "outcome": "success"},
        },
    )
    assert replied.status_code == 200

    detail = api_client.get(
        f"/sessions/{chief['session_id']}/detail",
        params={"agent_name": "worker", "member_token": worker["member_token"]},
    )
    assert detail.status_code == 200
    worker_member = next(item for item in detail.json()["session"]["members"] if item["agent_name"] == "worker")
    assert worker_member["current_task"] is None
    assert worker_member["current_task_from"] is None
    assert worker_member["current_task_at"] is None


def test_pending_delivery_prioritizes_reply_over_task_and_info(api_client: Any) -> None:
    chief = _create_session(api_client, "chief")
    worker = _join_session(api_client, "worker", chief["join_code"])

    for action, payload in (
        ("INFO", "non urgent context"),
        ("TASK", "implement auth"),
        ("REPLY", "build is green"),
    ):
        response = api_client.post(
            "/sessions/send",
            json={
                "session_id": chief["session_id"],
                "agent_name": "chief",
                "member_token": chief["member_token"],
                "to": "worker",
                "action": action,
                "payload": payload,
            },
        )
        assert response.status_code == 200

    first = api_client.post(
        "/sessions/wait",
        json={
            "session_id": worker["session_id"],
            "agent_name": "worker",
            "member_token": worker["member_token"],
            "timeout_seconds": 5,
        },
    )
    assert first.status_code == 200
    assert first.json()["status"] == "message"
    assert first.json()["message"]["action"] == "REPLY"

    second = api_client.post(
        "/sessions/wait",
        json={
            "session_id": worker["session_id"],
            "agent_name": "worker",
            "member_token": worker["member_token"],
            "timeout_seconds": 5,
        },
    )
    assert second.status_code == 200
    assert second.json()["message"]["action"] == "TASK"

    third = api_client.post(
        "/sessions/wait",
        json={
            "session_id": worker["session_id"],
            "agent_name": "worker",
            "member_token": worker["member_token"],
            "timeout_seconds": 5,
        },
    )
    assert third.status_code == 200
    assert third.json()["message"]["action"] == "INFO"


def test_session_wait_timeout_keeps_member_in_waiting_state(api_client: Any) -> None:
    chief = _create_session(api_client, "chief")

    timed_out = api_client.post(
        "/sessions/wait",
        json={
            "session_id": chief["session_id"],
            "agent_name": "chief",
            "member_token": chief["member_token"],
            "timeout_seconds": 0.1,
        },
    )
    assert timed_out.status_code == 200
    assert timed_out.json()["status"] == "timeout"

    detail = api_client.get(
        f"/sessions/{chief['session_id']}/detail",
        params={"agent_name": "chief", "member_token": chief["member_token"]},
    )
    assert detail.status_code == 200
    body = detail.json()["session"]
    chief_member = next(item for item in body["members"] if item["agent_name"] == "chief")
    assert chief_member["status"] == "waiting"
    assert chief_member["status_text"] == "waiting for session activity"
    assert any(event["event"] == "WAIT_TIMEOUT" for event in body["history"])


def test_session_wait_does_not_override_busy_member_state(api_client: Any) -> None:
    chief = _create_session(api_client, "chief")
    worker = _join_session(api_client, "worker", chief["join_code"])

    busy = api_client.post(
        "/sessions/status",
        json={
            "session_id": worker["session_id"],
            "agent_name": "worker",
            "member_token": worker["member_token"],
            "status": "busy",
            "status_text": "processing auth review",
        },
    )
    assert busy.status_code == 200

    timed_out = api_client.post(
        "/sessions/wait",
        json={
            "session_id": worker["session_id"],
            "agent_name": "worker",
            "member_token": worker["member_token"],
            "timeout_seconds": 0.1,
        },
    )
    assert timed_out.status_code == 200
    assert timed_out.json()["status"] == "timeout"

    detail = api_client.get(
        f"/sessions/{chief['session_id']}/detail",
        params={"agent_name": "worker", "member_token": worker["member_token"]},
    )
    assert detail.status_code == 200
    worker_member = next(item for item in detail.json()["session"]["members"] if item["agent_name"] == "worker")
    assert worker_member["status"] == "busy"
    assert worker_member["status_text"] == "processing auth review"


def test_queued_delivery_does_not_override_busy_member_state(api_client: Any) -> None:
    chief = _create_session(api_client, "chief")
    worker = _join_session(api_client, "worker", chief["join_code"])

    busy = api_client.post(
        "/sessions/status",
        json={
            "session_id": worker["session_id"],
            "agent_name": "worker",
            "member_token": worker["member_token"],
            "status": "busy",
            "status_text": "working on auth fix",
        },
    )
    assert busy.status_code == 200

    queued = api_client.post(
        "/sessions/send",
        json={
            "session_id": chief["session_id"],
            "agent_name": "chief",
            "member_token": chief["member_token"],
            "to": "worker",
            "action": "INFO",
            "payload": "there is one more edge case",
        },
    )
    assert queued.status_code == 200
    assert queued.json()["delivery"] == "queued"

    detail = api_client.get(
        f"/sessions/{chief['session_id']}/detail",
        params={"agent_name": "worker", "member_token": worker["member_token"]},
    )
    assert detail.status_code == 200
    worker_member = next(item for item in detail.json()["session"]["members"] if item["agent_name"] == "worker")
    assert worker_member["status"] == "busy"
    assert worker_member["status_text"] == "working on auth fix"


def test_queued_delivery_does_not_fake_destination_liveness(api_client: Any) -> None:
    chief = _create_session(api_client, "chief")
    worker = _join_session(api_client, "worker", chief["join_code"])

    detail_before = api_client.get(
        f"/sessions/{chief['session_id']}/detail",
        params={"agent_name": "worker", "member_token": worker["member_token"]},
    )
    assert detail_before.status_code == 200
    worker_before = next(item for item in detail_before.json()["session"]["members"] if item["agent_name"] == "worker")

    queued = api_client.post(
        "/sessions/send",
        json={
            "session_id": chief["session_id"],
            "agent_name": "chief",
            "member_token": chief["member_token"],
            "to": "worker",
            "action": "INFO",
            "payload": "queued but not consumed yet",
        },
    )
    assert queued.status_code == 200
    assert queued.json()["delivery"] == "queued"

    detail_after = api_client.get(
        f"/sessions/{chief['session_id']}/detail",
        params={"agent_name": "worker", "member_token": worker["member_token"]},
    )
    assert detail_after.status_code == 200
    worker_after = next(item for item in detail_after.json()["session"]["members"] if item["agent_name"] == "worker")
    assert worker_after["last_seen_at"] == worker_before["last_seen_at"]
    assert worker_after["last_action"] == worker_before["last_action"]
    assert worker_after["last_message_at"] == worker_before["last_message_at"]


def test_session_wait_rejects_duplicate_active_wait_request(hub_runtime: Any, api_client: Any) -> None:
    chief = _create_session(api_client, "chief")
    queue_key = (chief["session_id"], "chief")

    class _PendingWaiter:
        def done(self) -> bool:
            return False

    class _WaitRegistration:
        future = _PendingWaiter()

        def ttl_seconds(self) -> int:
            return 5

    hub_runtime.coordination._waiters[queue_key] = _WaitRegistration()  # type: ignore[assignment]

    denied = api_client.post(
        "/sessions/wait",
        json={
            "session_id": chief["session_id"],
            "agent_name": "chief",
            "member_token": chief["member_token"],
            "timeout_seconds": 5,
        },
    )
    assert denied.status_code == 409
    body = denied.json()
    assert body["code"] == "WAIT_ALREADY_ACTIVE"
    assert "Do not run concurrent waits" in body["message"]
    assert body["details"]["wait_ttl_seconds"] == 5


def test_session_wait_evicts_expired_zombie_wait(hub_runtime: Any, api_client: Any) -> None:
    # A wait registration whose declared lifetime already elapsed (TTL <= 0) but
    # was never reaped (client died mid-wait) must not block the same member from
    # listening again. The Hub evicts it instead of returning WAIT_ALREADY_ACTIVE.
    chief = _create_session(api_client, "chief")
    queue_key = (chief["session_id"], "chief")

    class _PendingWaiter:
        def done(self) -> bool:
            return False

    class _ExpiredRegistration:
        future = _PendingWaiter()

        def ttl_seconds(self) -> int:
            return 0

    hub_runtime.coordination._waiters[queue_key] = _ExpiredRegistration()  # type: ignore[assignment]

    allowed = api_client.post(
        "/sessions/wait",
        json={
            "session_id": chief["session_id"],
            "agent_name": "chief",
            "member_token": chief["member_token"],
            "timeout_seconds": 0.1,
        },
    )
    assert allowed.status_code == 200
    assert allowed.json()["status"] == "timeout"
    # The zombie registration was evicted and the fresh wait reaped itself.
    assert queue_key not in hub_runtime.coordination._waiters


def test_dashboard_overview_requires_token_when_configured(tokenized_api_client: Any) -> None:
    denied = tokenized_api_client.get("/dashboard/overview")
    assert denied.status_code == 401

    created = tokenized_api_client.post(
        "/sessions",
        json={"agent_name": "chief", "token": "secret-token"},
        headers={"X-ACP-Token": "secret-token"},
    )
    assert created.status_code == 201

    allowed = tokenized_api_client.get("/dashboard/overview", headers={"X-ACP-Token": "secret-token"})
    assert allowed.status_code == 200
    body = allowed.json()
    assert body["status"] == "ok"
    assert body["overview"]["session_count"] == 1
    assert body["overview"]["sessions"][0]["session_id"] == created.json()["session_id"]


def test_sqlite_coordination_recovers_live_session_queue_and_history(sqlite_runtime_pair) -> None:
    runtime1, runtime2 = sqlite_runtime_pair()
    with TestClient(create_app(runtime=runtime1)) as client1:
        chief = _create_session(client1, "chief")
        worker = _join_session(client1, "worker", chief["join_code"])

        status = client1.post(
            "/sessions/status",
            json={
                "session_id": chief["session_id"],
                "agent_name": "chief",
                "member_token": chief["member_token"],
                "status": "busy",
                "status_text": "triaging auth issue",
            },
        )
        assert status.status_code == 200

        queued = client1.post(
            "/sessions/send",
            json={
                "session_id": chief["session_id"],
                "agent_name": "chief",
                "member_token": chief["member_token"],
                "to": "worker",
                "action": "TASK",
                "payload": "Take ownership of auth.py",
            },
        )
        assert queued.status_code == 200
        assert queued.json()["delivery"] == "queued"

    with TestClient(create_app(runtime=runtime2)) as client2:
        overview = client2.get("/dashboard/overview")
        assert overview.status_code == 200
        assert overview.json()["overview"]["session_count"] == 1

        detail = client2.get(
            f"/sessions/{chief['session_id']}/detail",
            params={"agent_name": "worker", "member_token": worker["member_token"]},
        )
        assert detail.status_code == 200
        body = detail.json()["session"]
        worker_member = next(item for item in body["members"] if item["agent_name"] == "worker")
        assert worker_member["pending_count"] == 1
        assert worker_member["current_task"] == "Take ownership of auth.py"
        assert any(event["event"] == "MESSAGE_SENT" for event in body["history"])

        waited = client2.post(
            "/sessions/wait",
            json={
                "session_id": worker["session_id"],
                "agent_name": "worker",
                "member_token": worker["member_token"],
                "timeout_seconds": 5,
            },
        )
        assert waited.status_code == 200
        assert waited.json()["status"] == "message"
        assert waited.json()["message"]["payload"] == "Take ownership of auth.py"


def test_sqlite_coordination_recovers_admin_notice_after_restart(sqlite_runtime_pair) -> None:
    runtime1, runtime2 = sqlite_runtime_pair()
    with TestClient(create_app(runtime=runtime1)) as client1:
        chief = _create_session(client1, "chief")
        worker = _join_session(client1, "worker", chief["join_code"])

        disconnected = client1.post(
            f"/sessions/{chief['session_id']}/admin/members/worker/disconnect",
            json={},
        )
        assert disconnected.status_code == 200
        assert disconnected.json()["session_closed"] is False

    with TestClient(create_app(runtime=runtime2)) as client2:
        notice = client2.post(
            "/sessions/wait",
            json={
                "session_id": worker["session_id"],
                "agent_name": "worker",
                "member_token": worker["member_token"],
                "timeout_seconds": 5,
            },
        )
        assert notice.status_code == 200
        body = notice.json()
        assert body["status"] == "message"
        assert body["message"]["system_event"] == "MEMBER_DISCONNECTED"
        assert body["message"]["session_closed"] is False


def test_session_detail_requires_member_credentials_or_admin_token(api_client: Any) -> None:
    chief = _create_session(api_client, "chief")

    denied = api_client.get(f"/sessions/{chief['session_id']}/detail")
    assert denied.status_code == 401

    allowed = api_client.get(
        f"/sessions/{chief['session_id']}/detail",
        params={"agent_name": "chief", "member_token": chief["member_token"]},
    )
    assert allowed.status_code == 200


def test_session_detail_allows_admin_token_when_configured(tokenized_api_client: Any) -> None:
    created = tokenized_api_client.post(
        "/sessions",
        json={"agent_name": "chief", "token": "secret-token"},
        headers={"X-ACP-Token": "secret-token"},
    )
    assert created.status_code == 201

    detail = tokenized_api_client.get(
        f"/sessions/{created.json()['session_id']}/detail",
        params={"token": "secret-token"},
    )
    assert detail.status_code == 200
    assert detail.json()["session"]["session_id"] == created.json()["session_id"]


def test_dashboard_login_creates_cookie_session_for_overview(tokenized_api_client: Any) -> None:
    login = tokenized_api_client.post("/dashboard/auth/login", json={"token": "secret-token"})
    assert login.status_code == 200
    assert "acp_dashboard_session" in login.headers.get("set-cookie", "")
    assert "Max-Age=" in login.headers.get("set-cookie", "")

    session_info = tokenized_api_client.get("/dashboard/auth/session")
    assert session_info.status_code == 200
    assert session_info.json()["authenticated"] is True

    overview = tokenized_api_client.get("/dashboard/overview")
    assert overview.status_code == 200
    assert overview.json()["status"] == "ok"


def test_admin_can_close_session_from_dashboard_cookie(tokenized_api_client: Any) -> None:
    created = tokenized_api_client.post(
        "/sessions",
        json={"agent_name": "chief", "token": "secret-token"},
        headers={"X-ACP-Token": "secret-token"},
    )
    assert created.status_code == 201

    joined = tokenized_api_client.post(
        "/sessions/join",
        json={"agent_name": "worker", "join_code": created.json()["join_code"], "token": "secret-token"},
        headers={"X-ACP-Token": "secret-token"},
    )
    assert joined.status_code == 200

    login = tokenized_api_client.post("/dashboard/auth/login", json={"token": "secret-token"})
    assert login.status_code == 200

    closed = tokenized_api_client.post(
        f"/sessions/{created.json()['session_id']}/admin/close",
        json={},
    )
    assert closed.status_code == 200
    body = closed.json()
    assert body["status"] == "closed"
    assert body["session_closed"] is True
    assert sorted(body["removed_members"]) == ["chief", "worker"]

    detail = tokenized_api_client.get(
        f"/sessions/{created.json()['session_id']}/detail",
        params={"token": "secret-token"},
    )
    # The session was deleted by the close, so detail is Not Found, not Forbidden.
    assert detail.status_code == 404
    assert detail.json()["code"] == "SESSION_NOT_FOUND"


def test_admin_can_disconnect_member_without_closing_session(tokenized_api_client: Any) -> None:
    created = tokenized_api_client.post(
        "/sessions",
        json={"agent_name": "chief", "token": "secret-token"},
        headers={"X-ACP-Token": "secret-token"},
    )
    assert created.status_code == 201

    joined = tokenized_api_client.post(
        "/sessions/join",
        json={"agent_name": "worker", "join_code": created.json()["join_code"], "token": "secret-token"},
        headers={"X-ACP-Token": "secret-token"},
    )
    assert joined.status_code == 200

    disconnected = tokenized_api_client.post(
        f"/sessions/{created.json()['session_id']}/admin/members/worker/disconnect",
        params={"token": "secret-token"},
        json={},
    )
    assert disconnected.status_code == 200
    body = disconnected.json()
    assert body["status"] == "removed"
    assert body["agent_name"] == "worker"
    assert body["session_closed"] is False

    detail = tokenized_api_client.get(
        f"/sessions/{created.json()['session_id']}/detail",
        params={"token": "secret-token"},
    )
    assert detail.status_code == 200
    members = detail.json()["session"]["members"]
    assert [member["agent_name"] for member in members] == ["chief"]

    new_session = tokenized_api_client.post(
        "/sessions",
        json={"agent_name": "chief-b", "token": "secret-token"},
        headers={"X-ACP-Token": "secret-token"},
    )
    assert new_session.status_code == 201

    rejoined = tokenized_api_client.post(
        "/sessions/join",
        json={"agent_name": "worker", "join_code": new_session.json()["join_code"], "token": "secret-token"},
        headers={"X-ACP-Token": "secret-token"},
    )
    assert rejoined.status_code == 200


def test_admin_disconnect_notice_is_delivered_to_removed_member(api_client: Any) -> None:
    created = _create_session(api_client, "chief")
    joined = _join_session(api_client, "worker", created["join_code"])

    disconnected = api_client.post(
        f"/sessions/{created['session_id']}/admin/members/worker/disconnect",
        json={},
    )
    assert disconnected.status_code == 200
    assert disconnected.json()["session_closed"] is False

    notice = api_client.post(
        "/sessions/wait",
        json={
            "session_id": joined["session_id"],
            "agent_name": "worker",
            "member_token": joined["member_token"],
            "timeout_seconds": 5,
        },
    )
    assert notice.status_code == 200
    body = notice.json()
    assert body["status"] == "message"
    assert body["message"]["from"] == "system"
    assert body["message"]["system_event"] == "MEMBER_DISCONNECTED"
    assert body["message"]["session_closed"] is False
    assert "disconnected from the session by admin" in body["message"]["payload"]


def test_admin_close_notice_is_delivered_to_removed_members(api_client: Any) -> None:
    created = _create_session(api_client, "chief")
    joined = _join_session(api_client, "worker", created["join_code"])

    closed = api_client.post(
        f"/sessions/{created['session_id']}/admin/close",
        json={},
    )
    assert closed.status_code == 200
    assert closed.json()["session_closed"] is True

    chief_notice = api_client.post(
        "/sessions/wait",
        json={
            "session_id": created["session_id"],
            "agent_name": "chief",
            "member_token": created["member_token"],
            "timeout_seconds": 5,
        },
    )
    assert chief_notice.status_code == 200
    chief_body = chief_notice.json()
    assert chief_body["status"] == "message"
    assert chief_body["message"]["system_event"] == "SESSION_CLOSED"
    assert chief_body["message"]["session_closed"] is True
    assert chief_body["message"]["removed_by"] == "admin"

    worker_notice = api_client.post(
        "/sessions/wait",
        json={
            "session_id": joined["session_id"],
            "agent_name": "worker",
            "member_token": joined["member_token"],
            "timeout_seconds": 5,
        },
    )
    assert worker_notice.status_code == 200
    worker_body = worker_notice.json()
    assert worker_body["status"] == "message"
    assert worker_body["message"]["system_event"] == "SESSION_CLOSED"
    assert worker_body["message"]["session_closed"] is True


def test_dashboard_auth_session_reports_token_requirement(tokenized_api_client: Any) -> None:
    session_info = tokenized_api_client.get("/dashboard/auth/session")

    assert session_info.status_code == 200
    body = session_info.json()
    assert body["authenticated"] is False
    assert body["token_required"] is True


def test_dashboard_logout_revokes_cookie_session(tokenized_api_client: Any) -> None:
    login = tokenized_api_client.post("/dashboard/auth/login", json={"token": "secret-token"})
    assert login.status_code == 200

    logout = tokenized_api_client.post("/dashboard/auth/logout")
    assert logout.status_code == 200

    session_info = tokenized_api_client.get("/dashboard/auth/session")
    assert session_info.status_code == 200
    assert session_info.json()["authenticated"] is False

    denied = tokenized_api_client.get("/dashboard/overview")
    assert denied.status_code == 401


def test_dashboard_login_marks_cookie_secure_on_https(tokenized_runtime) -> None:
    app = create_app(runtime=tokenized_runtime)
    with TestClient(app, base_url="https://testserver") as client:
        login = client.post("/dashboard/auth/login", json={"token": "secret-token"})

    assert login.status_code == 200
    assert "Secure" in login.headers.get("set-cookie", "")


def test_dashboard_session_store_expires_idle_sessions() -> None:
    store = DashboardSessionStore(ttl_seconds=1)
    session = store.create()
    session.last_seen_at = "2000-01-01T00:00:00.000000Z"

    assert store.get(session.session_id) is None
    assert store.count() == 0


def test_admin_close_missing_session_returns_session_not_found(tokenized_api_client: Any) -> None:
    closed = tokenized_api_client.post(
        "/sessions/does-not-exist/admin/close",
        json={},
        headers={"X-ACP-Token": "secret-token"},
    )
    assert closed.status_code == 404
    assert closed.json()["code"] == "SESSION_NOT_FOUND"


def test_admin_disconnect_missing_session_returns_session_not_found(tokenized_api_client: Any) -> None:
    disconnected = tokenized_api_client.post(
        "/sessions/does-not-exist/admin/members/worker/disconnect",
        json={},
        headers={"X-ACP-Token": "secret-token"},
    )
    assert disconnected.status_code == 404
    assert disconnected.json()["code"] == "SESSION_NOT_FOUND"
