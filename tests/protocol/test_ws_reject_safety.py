from __future__ import annotations

import asyncio
import json
import sys
from pathlib import Path
from uuid import uuid4

repo_root = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(repo_root / "apps" / "hub" / "src"))

from acp.hub.ws_ingress import run_ws_ingress
from acp.protocol.errors import INVALID_FIELD, INVALID_JSON, PAYLOAD_TOO_LARGE
from acp.protocol.models import MAX_PAYLOAD_BYTES


class FakeWebSocket:
    def __init__(self, inbound: list[str]) -> None:
        self._inbound = list(inbound)
        self.sent: list[dict[str, object]] = []
        self.closed = False
        self.close_args: dict[str, object] | None = None

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
        self.close_args = {"code": code, "reason": reason}


def _hello(name: str, role: str = "agent") -> str:
    return json.dumps({"type": "HELLO", "role": role, "name": name})


def _msg(payload: str) -> str:
    return json.dumps(
        {
            "type": "MSG",
            "id": str(uuid4()),
            "ts": "2026-03-04T12:30:00Z",
            "from": "sender_1",
            "to": "receiver_1",
            "action": "TASK",
            "payload": payload,
        }
    )


def test_duplicate_agent_hello_rejects_and_closes_only_new_socket() -> None:
    existing = FakeWebSocket([])
    incoming = FakeWebSocket([_hello("agent_1", role="agent")])
    active_agents = {"agent_1": existing}
    traces: list[dict[str, object]] = []

    asyncio.run(
        run_ws_ingress(
            incoming,
            session_id="incoming_1",
            active_agents=active_agents,
            trace_sink=traces,
        )
    )

    assert incoming.closed is True
    assert existing.closed is False
    assert active_agents["agent_1"] is existing
    assert incoming.sent and incoming.sent[0]["code"] == INVALID_FIELD
    assert incoming.sent[0]["field"] == "name"
    assert any(trace.get("event") == "DROP" for trace in traces)


def test_invalid_json_rejected_without_closing_session() -> None:
    incoming = FakeWebSocket(['{"broken"', _hello("observer_1", role="observer")])
    active_agents: dict[str, FakeWebSocket] = {}
    traces: list[dict[str, object]] = []

    asyncio.run(
        run_ws_ingress(
            incoming,
            session_id="session_json",
            active_agents=active_agents,
            trace_sink=traces,
        )
    )

    assert incoming.closed is False
    assert incoming.sent and incoming.sent[0]["code"] == INVALID_JSON
    assert traces and traces[0]["reason_code"] == INVALID_JSON


def test_oversize_payload_maps_to_payload_too_large_with_drop_trace() -> None:
    oversize = "a" * (MAX_PAYLOAD_BYTES + 1)
    incoming = FakeWebSocket([_msg(oversize)])
    traces: list[dict[str, object]] = []

    asyncio.run(
        run_ws_ingress(
            incoming,
            session_id="session_overflow",
            active_agents={},
            trace_sink=traces,
        )
    )

    assert incoming.closed is False
    assert incoming.sent and incoming.sent[0]["code"] == PAYLOAD_TOO_LARGE
    assert traces and traces[0]["reason_code"] == PAYLOAD_TOO_LARGE


def test_invalid_session_does_not_disconnect_unrelated_connected_agent() -> None:
    healthy_agent = FakeWebSocket([])
    noisy_session = FakeWebSocket(['{"broken"', _msg("a" * (MAX_PAYLOAD_BYTES + 1))])
    active_agents = {"agent_live": healthy_agent}
    traces: list[dict[str, object]] = []

    asyncio.run(
        run_ws_ingress(
            noisy_session,
            session_id="session_noisy",
            active_agents=active_agents,
            trace_sink=traces,
        )
    )

    assert healthy_agent.closed is False
    assert active_agents["agent_live"] is healthy_agent
    assert [message["code"] for message in noisy_session.sent] == [INVALID_JSON, PAYLOAD_TOO_LARGE]
    assert [trace["reason_code"] for trace in traces] == [INVALID_JSON, PAYLOAD_TOO_LARGE]

