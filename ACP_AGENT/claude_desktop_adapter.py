"""Explicit safe-rejection contract for a Claude Desktop host binding.

Claude Desktop exposes no official, stable, testable interface to bind or resume
an existing conversation.  MCP support in Claude Desktop lets the app call tools;
it does not provide a programmatic surface to reattach to and continue a specific
existing chat.  The only ways community projects "drive" Claude Desktop are
unofficial API relays or UI automation, neither of which is a supported host
resume interface and both of which this bundle refuses to use.

Until an official interface exists, this adapter is a first-class, fail-closed
contract: any delivery attempt is rejected with
``UNSUPPORTED_PENDING_OFFICIAL_INTERFACE`` and no conversation, process, or UI
action is ever started as a fallback.
"""

from __future__ import annotations

from host_bridge import (
    CredentialResolver,
    HostBinding,
    HostDelivery,
    HostManifest,
    HostResult,
    HostUnsupportedError,
)


UNSUPPORTED_STATUS = "UNSUPPORTED_PENDING_OFFICIAL_INTERFACE"


class ClaudeDesktopAdapter:
    """Reject Claude Desktop deliveries until an official resume interface ships."""

    manifest = HostManifest(
        adapter_id="claude_desktop",
        display_name="Claude Desktop (unsupported)",
        capabilities=("unsupported-pending-official-interface",),
    )

    def __init__(
        self,
        *,
        request_timeout_seconds: float = 1800.0,
        deadline_monotonic: float | None = None,
        credential_resolver: CredentialResolver | None = None,
    ) -> None:
        # Accepted for registry symmetry; there is no runtime path to configure.
        self.request_timeout_seconds = request_timeout_seconds
        self.deadline_monotonic = deadline_monotonic
        self.credential_resolver = credential_resolver

    def deliver(self, binding: HostBinding, delivery: HostDelivery) -> HostResult:
        self._reject()

    def reconcile(self, binding: HostBinding, delivery: HostDelivery) -> HostResult:
        self._reject()

    @staticmethod
    def _reject() -> HostResult:
        raise HostUnsupportedError(
            f"{UNSUPPORTED_STATUS}: Claude Desktop has no official interface to bind or "
            "resume an existing conversation; refusing to invent one or automate the UI."
        )
