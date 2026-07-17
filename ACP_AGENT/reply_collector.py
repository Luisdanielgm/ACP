"""Durable, provider-free collector for ACP REPLY/INFO messages."""
from __future__ import annotations

import json
import tempfile
import uuid
from pathlib import Path
from typing import Any, Callable, Mapping, Protocol


class CollectorDeliveryError(RuntimeError):
    """Raised when a response cannot be safely forwarded and acknowledged."""


MAX_ACP_PAYLOAD_BYTES = 32_768


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
        forward_action: str | None = None,
    ) -> None:
        if not forward_to or not collector_id:
            raise ValueError("forward target and collector identity are required")
        if forward_action is not None and forward_action.upper() != "TASK":
            raise ValueError("forward_action must be TASK when configured")
        self.forward_to = forward_to
        self.allowed_senders = frozenset(allowed_senders)
        self.store = store
        self.state_path = Path(state_path)
        self.collector_id = collector_id
        self.forward_action = forward_action.upper() if forward_action is not None else None

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
        original_payload = message.get("payload")
        if self.forward_action == "TASK" and not isinstance(original_payload, str):
            raise CollectorDeliveryError("collectable message payload is malformed")

        prior = self.store.get(message_id)
        if prior.get("status") == "acked":
            return {"status": "duplicate", "message_id": message_id}
        received = {"status": "received", "message_id": message_id, "action": action, "sender": sender}
        self.store.put(message_id, received)
        id_namespace = "acp-reply-task-wakeup" if self.forward_action == "TASK" else "acp-reply"
        forwarded_id = str(uuid.uuid5(uuid.NAMESPACE_URL, f"{id_namespace}:{message_id}:{self.forward_to}"))
        forward_action = self.forward_action or action
        forward_payload = original_payload
        if self.forward_action == "TASK":
            forward_payload = json.dumps(
                {
                    "instructions": "Handle this collected response using the preserved source metadata.",
                    "original_action": action,
                    "original_message_id": message_id,
                    "original_payload": original_payload,
                    "original_sender": sender,
                },
                sort_keys=True,
                separators=(",", ":"),
            )
            if len(forward_payload.encode("utf-8")) > MAX_ACP_PAYLOAD_BYTES:
                raise CollectorDeliveryError("TASK wake payload exceeds ACP size limit; message remains retryable")
        payload = {
            "id": forwarded_id,
            "session_id": message.get("session_id"),
            "from": self.collector_id,
            "to": self.forward_to,
            "action": forward_action,
            "payload": forward_payload,
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
