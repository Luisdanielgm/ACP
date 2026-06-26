from __future__ import annotations

import asyncio
import json
import sys
from pathlib import Path
from uuid import uuid4

repo_root = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(repo_root / "apps" / "hub" / "src"))

from acp.hub.ws_ingress import run_ws_ingress
from acp.protocol.errors import (
    INVALID_FIELD,
    INVALID_JSON,
    PAYLOAD_TOO_LARGE,
    UNSUPPORTED_TYPE,
)
from acp.protocol.models import MAX_PAYLOAD_BYTES


class FakeWebSocket:
    def __init__(self, inbound: list[str]) -> None:
        self._inbound = list(inbound)
        self.sent: list[dict[str, object]] = []
        self.closed = False

    async def receive_text(self) -> str:
        if not self._inbound:
            raise StopAsyncIteration
        return self._inbound.pop(0)

    async def send_json(self, payload: dict[str, object]) -> None:
        self.sent.append(payload)

    async def send_text(self, payload: str) -> None:
        self.sent.append(json.loads(payload))

    async def close(self, *, code: int, reason: str) -> None:
        self.closed = True

def _msg(payload: str, *, include_to: bool = True) -> str:
    envelope: dict[str, object] = {
        "type": "MSG",
        "id": str(uuid4()),
        "ts": "2026-03-04T12:30:00Z",
        "from": "sender_1",
        "action": "TASK",
        "payload": payload,
    }
    if include_to:
        envelope["to"] = "receiver_1"
    return json.dumps(envelope)


def test_ingress_rejects_malformed_unsupported_invalid_and_overflow_with_drop_traces() -> None:
    oversized_payload = "x" * (MAX_PAYLOAD_BYTES + 1)
    socket = FakeWebSocket(
        [
            '{"token":"secret"',  # malformed json
            json.dumps({"type": "PING"}),  # unsupported type
            _msg("missing-to-field", include_to=False),  # schema-invalid MSG
            _msg(oversized_payload),  # overflow
        ]
    )
    traces: list[dict[str, object]] = []

    asyncio.run(
        run_ws_ingress(
            socket,
            session_id="session_rejects",
            active_agents={},
            trace_sink=traces,
        )
    )

    codes = [message["code"] for message in socket.sent]
    assert codes == [INVALID_JSON, UNSUPPORTED_TYPE, INVALID_FIELD, PAYLOAD_TOO_LARGE]
    assert all(message["action"] == "ERROR" for message in socket.sent)

    reason_codes = [trace["reason_code"] for trace in traces]
    assert reason_codes == [INVALID_JSON, UNSUPPORTED_TYPE, INVALID_FIELD, PAYLOAD_TOO_LARGE]
    assert all(trace["event"] == "DROP" for trace in traces)
    assert all("payload" not in trace for trace in traces)
    assert "secret" not in json.dumps(traces)


def test_overflow_drop_trace_exposes_only_safe_numeric_metadata() -> None:
    oversized_payload = "z" * (MAX_PAYLOAD_BYTES + 1)
    socket = FakeWebSocket([_msg(oversized_payload)])
    traces: list[dict[str, object]] = []

    asyncio.run(
        run_ws_ingress(
            socket,
            session_id="session_overflow",
            active_agents={},
            trace_sink=traces,
        )
    )

    assert len(socket.sent) == 1
    assert socket.sent[0]["code"] == PAYLOAD_TOO_LARGE
    assert socket.sent[0]["details"] == {"max_bytes": 32768, "actual_bytes": 32769}

    assert len(traces) == 1
    trace = traces[0]
    assert trace["reason_code"] == PAYLOAD_TOO_LARGE
    assert trace["payload_bytes"] == 32769
    assert trace["max_bytes"] == 32768
    assert trace["actual_bytes"] == 32769
    assert "raw_payload" not in trace

