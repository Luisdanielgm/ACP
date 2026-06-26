from __future__ import annotations

import sys
from pathlib import Path
from uuid import uuid4

repo_root = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(repo_root / "apps" / "hub" / "src"))

from acp.protocol.errors import PAYLOAD_TOO_LARGE
from acp.protocol.models import MAX_PAYLOAD_BYTES
from acp.protocol.validators import validate_envelope


def _msg(payload: str) -> dict[str, str]:
    return {
        "type": "MSG",
        "id": str(uuid4()),
        "ts": "2026-03-04T12:30:00Z",
        "from": "sender_1",
        "to": "receiver_1",
        "action": "TASK",
        "payload": payload,
    }


def test_payload_limit_accepts_32768_bytes() -> None:
    payload = "a" * MAX_PAYLOAD_BYTES
    result = validate_envelope(_msg(payload))

    assert result.ok is True
    assert result.error is None


def test_payload_limit_rejects_32769_bytes() -> None:
    payload = "a" * (MAX_PAYLOAD_BYTES + 1)
    result = validate_envelope(_msg(payload))

    assert result.ok is False
    assert result.error is not None
    assert result.error.code == PAYLOAD_TOO_LARGE


def test_payload_limit_accepts_utf8_multibyte_exact_boundary() -> None:
    payload = "á" * (MAX_PAYLOAD_BYTES // 2)
    result = validate_envelope(_msg(payload))

    assert result.ok is True
    assert result.error is None


def test_payload_limit_rejects_utf8_multibyte_32769_bytes() -> None:
    payload = ("á" * (MAX_PAYLOAD_BYTES // 2)) + "a"
    result = validate_envelope(_msg(payload))

    assert result.ok is False
    assert result.error is not None
    assert result.error.code == PAYLOAD_TOO_LARGE
    assert result.error.details == {"max_bytes": 32768, "actual_bytes": 32769}

