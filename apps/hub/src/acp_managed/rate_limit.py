"""In-process sliding-window rate limiter for managed auth endpoints.

This is deliberately simple: a single-process counter keyed by (scope, key)
that tracks recent failure timestamps in a deque and rejects requests once a
threshold is crossed inside the rolling window. State resets on process
restart, which is acceptable because the hub is a single-process service
today (see README "MVP Limitations").

Not designed for multi-worker / multi-replica deployments. If the hub ever
gains horizontal scale, replace this with a shared Redis-backed limiter.
"""

from __future__ import annotations

import os
import threading
import time
from collections import defaultdict, deque
from dataclasses import dataclass
from typing import Deque, Iterable

_TRUTHY = {"1", "true", "yes", "on"}


@dataclass(frozen=True)
class RateLimitRule:
    """Bucket configuration: at most `max_attempts` events per `window_seconds`."""

    max_attempts: int
    window_seconds: int

    def __post_init__(self) -> None:
        if self.max_attempts < 1:
            raise ValueError("max_attempts must be >= 1")
        if self.window_seconds < 1:
            raise ValueError("window_seconds must be >= 1")


@dataclass(frozen=True)
class RateLimitDecision:
    """Outcome of a rate-limit check. retry_after is in seconds."""

    allowed: bool
    retry_after: int


class _SlidingWindow:
    __slots__ = ("rule", "events")

    def __init__(self, rule: RateLimitRule) -> None:
        self.rule = rule
        self.events: Deque[float] = deque()

    def _prune(self, now: float) -> None:
        cutoff = now - self.rule.window_seconds
        while self.events and self.events[0] <= cutoff:
            self.events.popleft()

    def check(self, now: float) -> RateLimitDecision:
        self._prune(now)
        if len(self.events) >= self.rule.max_attempts:
            oldest = self.events[0]
            retry_after = max(1, int(self.rule.window_seconds - (now - oldest)))
            return RateLimitDecision(allowed=False, retry_after=retry_after)
        return RateLimitDecision(allowed=True, retry_after=0)

    def register(self, now: float) -> None:
        self.events.append(now)


class FailureRateLimiter:
    """Tracks failures across multiple independent scopes.

    A typical login flow registers two scopes per attempt: per-IP and
    per-(IP, email). Both are checked before authenticating and only marked
    on actual failure.
    """

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._buckets: dict[tuple[str, str], _SlidingWindow] = {}
        self._last_gc: float = 0.0

    def check(self, scopes: Iterable[tuple[str, str, RateLimitRule]]) -> RateLimitDecision:
        """Return the tightest decision across all scopes without registering.

        Each scope is a (namespace, key, rule) triple. The strictest
        retry_after wins when multiple scopes are denied simultaneously.
        """
        now = time.monotonic()
        worst: RateLimitDecision | None = None
        with self._lock:
            self._maybe_gc(now)
            for namespace, key, rule in scopes:
                window = self._buckets.get((namespace, key))
                if window is None or window.rule != rule:
                    window = _SlidingWindow(rule)
                    self._buckets[(namespace, key)] = window
                decision = window.check(now)
                if not decision.allowed:
                    if worst is None or decision.retry_after > worst.retry_after:
                        worst = decision
        return worst or RateLimitDecision(allowed=True, retry_after=0)

    def register_failure(self, scopes: Iterable[tuple[str, str, RateLimitRule]]) -> None:
        now = time.monotonic()
        with self._lock:
            for namespace, key, rule in scopes:
                window = self._buckets.get((namespace, key))
                if window is None or window.rule != rule:
                    window = _SlidingWindow(rule)
                    self._buckets[(namespace, key)] = window
                window.register(now)

    def _maybe_gc(self, now: float) -> None:
        # Garbage-collect empty/expired buckets at most once per minute to
        # keep the in-memory footprint bounded under sustained traffic.
        if now - self._last_gc < 60.0:
            return
        self._last_gc = now
        empty_keys: list[tuple[str, str]] = []
        for key, window in self._buckets.items():
            window._prune(now)
            if not window.events:
                empty_keys.append(key)
        for key in empty_keys:
            self._buckets.pop(key, None)


# Default policy for managed auth endpoints. Tunable via env in the future.
LOGIN_PER_IP_RULE = RateLimitRule(max_attempts=20, window_seconds=300)
LOGIN_PER_IP_EMAIL_RULE = RateLimitRule(max_attempts=5, window_seconds=300)
INVITATION_PER_IP_RULE = RateLimitRule(max_attempts=20, window_seconds=300)
INVITATION_PER_TOKEN_RULE = RateLimitRule(max_attempts=10, window_seconds=300)


def _trust_proxy_headers_from_env() -> bool:
    configured = os.getenv("ACP_TRUST_PROXY_HEADERS")
    return configured is not None and configured.strip().lower() in _TRUTHY


def client_ip_from_request(request, *, trust_forwarded_for: bool | None = None) -> str:  # type: ignore[no-untyped-def]
    """Best-effort client IP used as the rate-limit / audit key.

    ``X-Forwarded-For`` is client-controlled and trivially spoofable, so it is
    honored ONLY when the hub is knowingly deployed behind a trusted reverse
    proxy (ACP_TRUST_PROXY_HEADERS). Otherwise the direct socket peer
    (``request.client.host``) is used, which a remote client cannot forge —
    without this, header rotation would bypass the per-IP auth rate limiters.
    Pass ``trust_forwarded_for`` explicitly to override the env default (e.g.
    in tests).
    """
    if trust_forwarded_for is None:
        trust_forwarded_for = _trust_proxy_headers_from_env()
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
