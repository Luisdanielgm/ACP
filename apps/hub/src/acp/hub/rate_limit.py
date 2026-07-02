"""Minimal in-process rate limiter for core hub endpoints.

This is a hub-local equivalent of acp_managed.rate_limit.FailureRateLimiter,
scoped down to what /sessions/join needs (a single per-IP failure window).
It is intentionally not imported from acp_managed: the core hub (acp.hub)
must not depend on the managed/workspace layer (acp_managed), which itself
depends on acp.hub, so importing acp_managed here would create a layering
violation / import cycle.

Single-process, in-memory counter; state resets on restart. Not designed
for multi-worker / multi-replica deployments.
"""

from __future__ import annotations

import threading
import time
from collections import deque
from dataclasses import dataclass
from typing import Deque


@dataclass(frozen=True)
class RateLimitDecision:
    """Outcome of a rate-limit check. retry_after is in seconds."""

    allowed: bool
    retry_after: int


class JoinAttemptRateLimiter:
    """Tracks failed /sessions/join attempts per client IP.

    Only failures are registered; successful joins never count against the
    window, mirroring the managed login rate-limit pattern.
    """

    def __init__(
        self,
        *,
        max_attempts: int = 10,
        window_seconds: int = 300,
        max_keys: int = 10_000,
    ) -> None:
        self._max_attempts = max_attempts
        self._window_seconds = window_seconds
        # Bound the number of tracked keys so a client rotating its apparent IP
        # cannot grow this dict without limit (memory-exhaustion vector).
        self._max_keys = max_keys
        self._lock = threading.Lock()
        self._events: dict[str, Deque[float]] = {}

    def _prune(self, events: Deque[float], now: float) -> None:
        cutoff = now - self._window_seconds
        while events and events[0] <= cutoff:
            events.popleft()

    def _sweep_expired(self, now: float) -> None:
        # Drop keys whose window has fully expired. Called only when the dict
        # grows past the cap, so this stays amortized-cheap on the hot path.
        stale = [key for key, events in self._events.items() if not events or events[-1] <= now - self._window_seconds]
        for key in stale:
            del self._events[key]

    def check(self, key: str) -> RateLimitDecision:
        now = time.monotonic()
        with self._lock:
            events = self._events.get(key)
            if events is None:
                return RateLimitDecision(allowed=True, retry_after=0)
            self._prune(events, now)
            if not events:
                # Window fully expired: forget the key so it can't linger.
                del self._events[key]
                return RateLimitDecision(allowed=True, retry_after=0)
            if len(events) >= self._max_attempts:
                oldest = events[0]
                retry_after = max(1, int(self._window_seconds - (now - oldest)))
                return RateLimitDecision(allowed=False, retry_after=retry_after)
            return RateLimitDecision(allowed=True, retry_after=0)

    def register_failure(self, key: str) -> None:
        now = time.monotonic()
        with self._lock:
            if len(self._events) > self._max_keys:
                self._sweep_expired(now)
            events = self._events.setdefault(key, deque())
            self._prune(events, now)
            events.append(now)


def client_ip_from_request(request, *, trust_forwarded_for: bool = False) -> str:  # type: ignore[no-untyped-def]
    """Best-effort client IP used as the rate-limit key.

    ``X-Forwarded-For`` is client-controlled and trivially spoofable, so it is
    honored ONLY when ``trust_forwarded_for`` is set (i.e. the hub is knowingly
    deployed behind a trusted reverse proxy, via ACP_TRUST_PROXY_HEADERS).
    Otherwise the direct socket peer (``request.client.host``) is used, which a
    remote client cannot forge. Defaulting to the socket peer keeps the join
    rate limiter from being bypassed by header rotation on a directly-exposed
    self-hosted hub.
    """
    if trust_forwarded_for:
        forwarded_for = request.headers.get("x-forwarded-for", "")
        if isinstance(forwarded_for, str) and forwarded_for.strip():
            first = forwarded_for.split(",")[0].strip()
            if first:
                return first
    client = getattr(request, "client", None)
    if client is not None and getattr(client, "host", None):
        return str(client.host)
    return "unknown"
