from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

import pytest


repo_root = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(repo_root / "ACP_AGENT"))

from claude_desktop_adapter import UNSUPPORTED_STATUS, ClaudeDesktopAdapter  # noqa: E402
from host_bridge import (  # noqa: E402
    AdapterRegistry,
    HostBinding,
    HostBindingError,
    HostBridge,
    HostDelivery,
    HostUnsupportedError,
    JsonBridgeStore,
    default_registry,
)


def _delivery() -> HostDelivery:
    return HostDelivery(
        message_id="msg-desktop-1",
        correlation_id="msg-desktop-1",
        sender="chief",
        instructions="Inspect the change",
    )


def _binding() -> HostBinding:
    return HostBinding(adapter_id="claude_desktop", values={"session_id": "desktop-chat-1"})


def _response() -> dict[str, Any]:
    return {
        "status": "message",
        "message": {
            "id": "msg-desktop-1",
            "session_id": "acp-session",
            "from": "chief",
            "to": "worker",
            "action": "TASK",
            "payload": json.dumps({"instructions": "Inspect the change"}),
        },
        "delivery": {"ack_required": True, "message_id": "msg-desktop-1", "receipt_handle": "receipt-1"},
    }


def test_unsupported_error_is_a_binding_error() -> None:
    assert issubclass(HostUnsupportedError, HostBindingError)


def test_claude_desktop_deliver_rejects_with_official_status() -> None:
    adapter = ClaudeDesktopAdapter()

    with pytest.raises(HostUnsupportedError, match=UNSUPPORTED_STATUS):
        adapter.deliver(_binding(), _delivery())


def test_claude_desktop_reconcile_rejects_with_official_status() -> None:
    adapter = ClaudeDesktopAdapter()

    with pytest.raises(HostUnsupportedError, match=UNSUPPORTED_STATUS):
        adapter.reconcile(_binding(), _delivery())


def test_claude_desktop_is_registered_in_default_registry() -> None:
    adapter = default_registry().get("claude_desktop")

    assert adapter.manifest.adapter_id == "claude_desktop"
    assert adapter.manifest.capabilities == ("unsupported-pending-official-interface",)


def test_claude_desktop_bridge_fails_closed_without_ack_or_reply(tmp_path: Path) -> None:
    registry = AdapterRegistry()
    registry.register(ClaudeDesktopAdapter())
    state_path = tmp_path / "state.json"
    bridge = HostBridge(
        registry=registry,
        binding=_binding(),
        store=JsonBridgeStore(state_path),
        allowed_senders=("chief",),
    )

    with pytest.raises(HostUnsupportedError, match=UNSUPPORTED_STATUS):
        bridge.handle(
            _response(),
            acknowledge=lambda _: pytest.fail("unsupported host must not ACK"),
            reply=lambda *_: pytest.fail("unsupported host must not REPLY"),
        )

    record = next(iter(json.loads(state_path.read_text(encoding="utf-8"))["deliveries"].values()))
    assert record["status"] != "completed"
    assert not record.get("acked")
    assert not record.get("replied")
