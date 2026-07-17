"""Durable, provider-free collector for ACP REPLY/INFO messages."""
from __future__ import annotations

import json
import tempfile
import uuid
from pathlib import Path
from typing import Any, Callable, Mapping, Protocol


class CollectorDeliveryError(RuntimeError):
    """Raised when a response cannot be safely forwarded and acknowledged."""


class CollectorStore(Protocol):
    def get(self, key: str) -> dict[str, Any]: ...
    def put(self, key: str, record: Mapping[str, Any]) -> None: ...


class ReplyCollector:
    """Forward REPLY/INFO durably before acknowledging the leased message.

    The collector has no model/provider path.  It is intentionally separate from
    a TASK-only HostBridge because ACP permits only one active wait per member.
    """

    def __init__(
        self,
        *,
        forward_to: str,
        allowed_senders: tuple[str, ...],
        store: CollectorStore,
        state_path: Path,
        collector_id: str = "reply-collector",
    ) -> None:
        if not forward_to or not collector_id:
            raise ValueError("forward target and collector identity are required")
        self.forward_to = forward_to
        self.allowed_senders = frozenset(allowed_senders)
        self.store = store
        self.state_path = Path(state_path)
        self.collector_id = collector_id

    def handle(
        self,
        response: Mapping[str, Any],
        *,
        forward: Callable[[dict[str, Any]], Mapping[str, Any]],
        acknowledge: Callable[[dict[str, Any]], Any],
    ) -> dict[str, Any]:
        message = response.get("message")
        delivery = response.get("delivery")
        if response.get("status") != "message" or not isinstance(message, Mapping) or not isinstance(delivery, Mapping):
            raise CollectorDeliveryError("invalid wait response")
        message_id = str(message.get("id") or "")
        sender = str(message.get("from") or "")
        action = str(message.get("action") or "").upper()
        leased_id = str(delivery.get("message_id") or "")
        receipt_handle = delivery.get("receipt_handle")
        if (
            not message_id
            or leased_id != message_id
            or delivery.get("ack_required") is not True
            or not isinstance(receipt_handle, str)
            or not receipt_handle
            or sender not in self.allowed_senders
        ):
            raise CollectorDeliveryError("sender or message id is not authorized")
        if action not in {"REPLY", "INFO"}:
            raise CollectorDeliveryError("action is not collectable")

        prior = self.store.get(message_id)
        if prior.get("status") == "acked":
            return {"status": "duplicate", "message_id": message_id}
        received = {"status": "received", "message_id": message_id, "action": action, "sender": sender}
        self.store.put(message_id, received)
        forwarded_id = str(uuid.uuid5(uuid.NAMESPACE_URL, f"acp-reply:{message_id}:{self.forward_to}"))
        payload = {
            "id": forwarded_id,
            "session_id": message.get("session_id"),
            "from": self.collector_id,
            "to": self.forward_to,
            "action": action,
            "payload": message.get("payload"),
            "in_reply_to": message_id,
        }
        accepted = forward(payload)
        if (
            not isinstance(accepted, Mapping)
            or str(accepted.get("status")) not in {"queued", "immediate", "duplicate"}
            or accepted.get("message_id") != forwarded_id
        ):
            raise CollectorDeliveryError("forward was not durably accepted")
        self.store.put(message_id, {**received, "status": "forwarded", "forwarded_id": forwarded_id})
        ack_result = acknowledge(dict(delivery))
        if (
            not isinstance(ack_result, Mapping)
            or ack_result.get("status") != "acknowledged"
            or ack_result.get("message_id") != str(delivery.get("message_id") or message_id)
        ):
            raise CollectorDeliveryError("ACP ack did not confirm the leased message")
        self.store.put(message_id, {**received, "status": "acked", "forwarded_id": forwarded_id})
        return {"status": "completed", "message_id": message_id, "forwarded_id": forwarded_id}


def load_state(path: Path) -> dict[str, Any]:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError):
        return {"next_action": "REPLY"}


def save_state(path: Path, state: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile("w", encoding="utf-8", dir=path.parent, delete=False) as handle:
        json.dump(dict(state), handle, sort_keys=True)
        temp = Path(handle.name)
    temp.replace(path)


def next_wait_action(path: Path) -> str:
    state = load_state(path)
    action = str(state.get("next_action") or "REPLY").upper()
    if action not in {"REPLY", "INFO"}:
        action = "REPLY"
    save_state(path, {**state, "next_action": "INFO" if action == "REPLY" else "REPLY"})
    return action
