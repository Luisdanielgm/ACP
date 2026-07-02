from __future__ import annotations

from types import SimpleNamespace

from acp.hub.rate_limit import JoinAttemptRateLimiter, client_ip_from_request


def _request(*, headers: dict[str, str] | None = None, host: str | None = "10.0.0.1"):
    client = SimpleNamespace(host=host) if host is not None else None
    return SimpleNamespace(headers=headers or {}, client=client)


def test_limiter_blocks_after_max_attempts() -> None:
    limiter = JoinAttemptRateLimiter(max_attempts=3, window_seconds=300)
    assert limiter.check("ip-a").allowed is True
    for _ in range(3):
        limiter.register_failure("ip-a")
    decision = limiter.check("ip-a")
    assert decision.allowed is False
    assert decision.retry_after >= 1


def test_limiter_is_per_key() -> None:
    limiter = JoinAttemptRateLimiter(max_attempts=2, window_seconds=300)
    for _ in range(2):
        limiter.register_failure("ip-a")
    assert limiter.check("ip-a").allowed is False
    # A different key is unaffected by another key's failures.
    assert limiter.check("ip-b").allowed is True


def test_expired_window_evicts_key() -> None:
    # window_seconds=0 means every recorded failure is immediately expired, so
    # the key must be forgotten on the next check (no unbounded growth).
    limiter = JoinAttemptRateLimiter(max_attempts=1, window_seconds=0)
    limiter.register_failure("ip-a")
    assert limiter.check("ip-a").allowed is True
    assert "ip-a" not in limiter._events


def test_sweep_bounds_key_dict_under_rotation() -> None:
    # A client rotating its apparent IP must not grow the dict without bound.
    limiter = JoinAttemptRateLimiter(max_attempts=1, window_seconds=0, max_keys=5)
    for i in range(50):
        limiter.register_failure(f"ip-{i}")
    # All entries are immediately expired (window 0) and get swept once the
    # dict crosses max_keys, so it stays bounded well under the number of keys.
    assert len(limiter._events) <= 5


def test_forwarded_for_ignored_by_default() -> None:
    # Spoofed X-Forwarded-For must not become the rate-limit key; the direct
    # socket peer wins, so header rotation cannot bypass the limiter.
    request = _request(headers={"x-forwarded-for": "1.2.3.4"}, host="10.0.0.1")
    assert client_ip_from_request(request) == "10.0.0.1"


def test_forwarded_for_honored_when_trusted() -> None:
    request = _request(headers={"x-forwarded-for": "1.2.3.4, 5.6.7.8"}, host="10.0.0.1")
    assert client_ip_from_request(request, trust_forwarded_for=True) == "1.2.3.4"


def test_client_ip_falls_back_when_no_peer() -> None:
    request = _request(headers={}, host=None)
    assert client_ip_from_request(request) == "unknown"
