from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path
from typing import Any

import pytest


repo_root = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(repo_root / "ACP_AGENT"))
_SPEC = importlib.util.spec_from_file_location("acp_reply_collector", repo_root / "ACP_AGENT" / "reply_collector.py")
assert _SPEC is not None and _SPEC.loader is not None
collector_module = importlib.util.module_from_spec(_SPEC)
sys.modules[_SPEC.name] = collector_module
_SPEC.loader.exec_module(collector_module)


class RecordingStore:
    def __init__(self) -> None:
        self.records: dict[str, dict[str, Any]] = {}

    def get(self, key: str) -> dict[str, Any]:
        return dict(self.records.get(key) or {})

    def put(self, key: str, record: dict[str, Any]) -> None:
        self.records[key] = dict(record)


def _response(action: str = "REPLY") -> dict[str, Any]:
    return {
        "status": "message",
        "message": {
            "id": "msg-1",
            "session_id": "room-1",
            "from": "worker",
            "to": "collector",
            "action": action,
            "payload": json.dumps({"task_id": "task-1", "summary": "done"}),
        },
        "delivery": {"ack_required": True, "message_id": "msg-1", "receipt_handle": "receipt-1"},
    }


def test_reply_collector_forwards_then_acks_once(tmp_path: Path) -> None:
    collector = collector_module.ReplyCollector(
        forward_to="coordinator",
        allowed_senders=("worker",),
        store=RecordingStore(),
        state_path=tmp_path / "collector.json",
    )
    forwarded: list[dict[str, Any]] = []
    acknowledgements: list[dict[str, Any]] = []

    result = collector.handle(
        _response(),
        forward=lambda payload: forwarded.append(payload) or {"status": "queued", "message_id": payload["id"]},
        acknowledge=lambda delivery: acknowledgements.append(delivery) or {"status": "acknowledged", "message_id": delivery["message_id"]},
    )

    assert result["status"] == "completed"
    assert forwarded[0]["to"] == "coordinator"
    assert forwarded[0]["action"] == "REPLY"
    assert forwarded[0]["in_reply_to"] == "msg-1"
    assert len(acknowledgements) == 1
    assert collector.handle(_response(), forward=lambda _payload: pytest.fail("duplicate forward"), acknowledge=lambda _delivery: pytest.fail("duplicate ack"))["status"] == "duplicate"
    assert len(acknowledgements) == 1


def test_info_is_forwarded_and_host_actions_fail_closed(tmp_path: Path) -> None:
    collector = collector_module.ReplyCollector(
        forward_to="coordinator",
        allowed_senders=("worker",),
        store=RecordingStore(),
        state_path=tmp_path / "collector.json",
    )
    forwarded: list[dict[str, Any]] = []
    acknowledgements: list[dict[str, Any]] = []
    assert collector.handle(_response("INFO"), forward=lambda payload: forwarded.append(payload) or {"status": "queued", "message_id": payload["id"]}, acknowledge=lambda delivery: acknowledgements.append(delivery) or {"status": "acknowledged", "message_id": delivery["message_id"]})["status"] == "completed"
    assert forwarded[0]["action"] == "INFO"
    with pytest.raises(collector_module.CollectorDeliveryError, match="action is not collectable"):
        collector.handle(_response("TASK"), forward=lambda _payload: {}, acknowledge=acknowledgements.append)
    assert len(acknowledgements) == 1


def test_forward_failure_leaves_received_without_ack(tmp_path: Path) -> None:
    store = RecordingStore()
    collector = collector_module.ReplyCollector(
        forward_to="coordinator",
        allowed_senders=("worker",),
        store=store,
        state_path=tmp_path / "collector.json",
    )
    with pytest.raises(RuntimeError, match="forward unavailable"):
        collector.handle(_response(), forward=lambda _payload: (_ for _ in ()).throw(RuntimeError("forward unavailable")), acknowledge=lambda _payload: pytest.fail("must not ack"))
    assert next(iter(store.records.values()))["status"] == "received"


def test_malformed_forward_or_ack_never_completes(tmp_path: Path) -> None:
    collector = collector_module.ReplyCollector(
        forward_to="coordinator", allowed_senders=("worker",), store=RecordingStore(), state_path=tmp_path / "collector.json"
    )
    with pytest.raises(collector_module.CollectorDeliveryError, match="durably accepted"):
        collector.handle(_response(), forward=lambda _payload: {"status": "queued"}, acknowledge=lambda _delivery: {})
    with pytest.raises(collector_module.CollectorDeliveryError, match="did not confirm"):
        collector.handle(_response(), forward=lambda payload: {"status": "queued", "message_id": payload["id"]}, acknowledge=lambda _delivery: {"status": "error"})


def test_mismatched_lease_fails_closed(tmp_path: Path) -> None:
    collector = collector_module.ReplyCollector(
        forward_to="coordinator", allowed_senders=("worker",), store=RecordingStore(), state_path=tmp_path / "collector.json"
    )
    response = _response()
    response["delivery"]["message_id"] = "other-message"
    with pytest.raises(collector_module.CollectorDeliveryError):
        collector.handle(response, forward=lambda _payload: pytest.fail("must not forward"), acknowledge=lambda _delivery: pytest.fail("must not ack"))


@pytest.mark.parametrize("action", ["REPLY", "INFO"])
def test_task_wakeup_wraps_collectable_message_without_losing_traceability(
    tmp_path: Path, action: str
) -> None:
    collector = collector_module.ReplyCollector(
        forward_to="coordinator",
        allowed_senders=("worker",),
        store=RecordingStore(),
        state_path=tmp_path / "collector.json",
        forward_action="TASK",
    )
    forwarded: list[dict[str, Any]] = []

    result = collector.handle(
        _response(action),
        forward=lambda payload: forwarded.append(payload)
        or {"status": "queued", "message_id": payload["id"]},
        acknowledge=lambda delivery: {
            "status": "acknowledged",
            "message_id": delivery["message_id"],
        },
    )

    wrapper = forwarded[0]
    wrapped_payload = json.loads(wrapper["payload"])
    assert result["status"] == "completed"
    assert wrapper["action"] == "TASK"
    assert wrapper["in_reply_to"] == "msg-1"
    assert wrapped_payload["instructions"]
    assert wrapped_payload["original_action"] == action
    assert wrapped_payload["original_message_id"] == "msg-1"
    assert wrapped_payload["original_payload"] == _response(action)["message"]["payload"]
    assert wrapped_payload["original_sender"] == "worker"


def test_task_wakeup_retry_is_deterministic_and_waits_for_acceptance_before_ack(
    tmp_path: Path,
) -> None:
    collector = collector_module.ReplyCollector(
        forward_to="coordinator",
        allowed_senders=("worker",),
        store=RecordingStore(),
        state_path=tmp_path / "collector.json",
        forward_action="TASK",
    )
    forwarded: list[dict[str, Any]] = []
    acknowledgements: list[dict[str, Any]] = []

    with pytest.raises(collector_module.CollectorDeliveryError, match="durably accepted"):
        collector.handle(
            _response(),
            forward=lambda payload: forwarded.append(payload)
            or {"status": "queued", "message_id": "wrong-wrapper-id"},
            acknowledge=lambda delivery: acknowledgements.append(delivery),
        )
    assert acknowledgements == []

    result = collector.handle(
        _response(),
        forward=lambda payload: forwarded.append(payload)
        or {"status": "duplicate", "message_id": payload["id"]},
        acknowledge=lambda delivery: acknowledgements.append(delivery)
        or {"status": "acknowledged", "message_id": delivery["message_id"]},
    )

    assert result["status"] == "completed"
    assert forwarded[0] == forwarded[1]
    assert len(acknowledgements) == 1


def test_task_wakeup_malformed_source_fails_closed(tmp_path: Path) -> None:
    collector = collector_module.ReplyCollector(
        forward_to="coordinator",
        allowed_senders=("worker",),
        store=RecordingStore(),
        state_path=tmp_path / "collector.json",
        forward_action="TASK",
    )
    response = _response()
    response["message"]["payload"] = None

    with pytest.raises(collector_module.CollectorDeliveryError, match="payload"):
        collector.handle(
            response,
            forward=lambda _payload: pytest.fail("must not forward"),
            acknowledge=lambda _delivery: pytest.fail("must not ack"),
        )


def test_task_wakeup_oversized_payload_stays_retryable(tmp_path: Path) -> None:
    collector = collector_module.ReplyCollector(
        forward_to="coordinator", allowed_senders=("worker",), store=RecordingStore(), state_path=tmp_path / "collector.json", forward_action="TASK"
    )
    response = _response()
    response["message"]["payload"] = "x" * 32_700
    with pytest.raises(collector_module.CollectorDeliveryError, match="size limit"):
        collector.handle(response, forward=lambda _payload: pytest.fail("must not forward"), acknowledge=lambda _delivery: pytest.fail("must not ack"))
