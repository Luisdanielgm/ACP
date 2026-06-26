from __future__ import annotations

import sys
from pathlib import Path

import pytest
from pydantic import ValidationError

repo_root = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(repo_root / "apps" / "hub" / "src"))

from acp.protocol.models import MsgEnvelope


def test_msg_accepts_required_contract_fields() -> None:
    message = MsgEnvelope.model_validate(
        {
            "type": "MSG",
            "id": "8947ad19-fec4-44d9-ab5d-2543fca4789b",
            "ts": "2026-03-04T12:30:00Z",
            "from": "sender_1",
            "to": "receiver-1",
            "action": "TASK",
            "payload": "run task",
        }
    )

    assert message.action.value == "TASK"


@pytest.mark.parametrize("action", ["TASK", "REPLY", "INFO"])
def test_msg_accepts_only_supported_inbound_actions(action: str) -> None:
    message = MsgEnvelope.model_validate(
        {
            "type": "MSG",
            "id": "8947ad19-fec4-44d9-ab5d-2543fca4789b",
            "ts": "2026-03-04T12:30:00Z",
            "from": "sender_1",
            "to": "receiver-1",
            "action": action,
            "payload": "run task",
        }
    )

    assert message.action.value == action


def test_msg_rejects_missing_required_field() -> None:
    with pytest.raises(ValidationError):
        MsgEnvelope.model_validate(
            {
                "type": "MSG",
                "id": "8947ad19-fec4-44d9-ab5d-2543fca4789b",
                "ts": "2026-03-04T12:30:00Z",
                "from": "sender_1",
                "action": "TASK",
                "payload": "run task",
            }
        )


def test_msg_rejects_reserved_error_action_from_inbound_client() -> None:
    with pytest.raises(ValidationError):
        MsgEnvelope.model_validate(
            {
                "type": "MSG",
                "id": "8947ad19-fec4-44d9-ab5d-2543fca4789b",
                "ts": "2026-03-04T12:30:00Z",
                "from": "sender_1",
                "to": "receiver-1",
                "action": "ERROR",
                "payload": "not allowed",
            }
        )


def test_msg_rejects_non_rfc3339_timestamp() -> None:
    with pytest.raises(ValidationError):
        MsgEnvelope.model_validate(
            {
                "type": "MSG",
                "id": "8947ad19-fec4-44d9-ab5d-2543fca4789b",
                "ts": "2026-03-04 12:30:00",
                "from": "sender_1",
                "to": "receiver-1",
                "action": "TASK",
                "payload": "run task",
            }
        )


def test_msg_rejects_extra_fields() -> None:
    with pytest.raises(ValidationError):
        MsgEnvelope.model_validate(
            {
                "type": "MSG",
                "id": "8947ad19-fec4-44d9-ab5d-2543fca4789b",
                "ts": "2026-03-04T12:30:00Z",
                "from": "sender_1",
                "to": "receiver-1",
                "action": "TASK",
                "payload": "run task",
                "unexpected": "nope",
            }
        )


def test_msg_rejects_non_string_payload() -> None:
    with pytest.raises(ValidationError):
        MsgEnvelope.model_validate(
            {
                "type": "MSG",
                "id": "8947ad19-fec4-44d9-ab5d-2543fca4789b",
                "ts": "2026-03-04T12:30:00Z",
                "from": "sender_1",
                "to": "receiver-1",
                "action": "TASK",
                "payload": {"text": "invalid"},
            }
        )

