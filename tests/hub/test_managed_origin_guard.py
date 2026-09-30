from __future__ import annotations

from starlette.requests import Request

from acp_managed.csrf import origin_is_allowed


def _request(method: str, headers: dict[str, str]) -> Request:
    raw = [(k.lower().encode(), v.encode()) for k, v in headers.items()]
    return Request({"type": "http", "method": method, "headers": raw, "path": "/x", "query_string": b""})


def test_safe_methods_and_bearer_requests_skip_the_check() -> None:
    assert origin_is_allowed(_request("GET", {"cookie": "acp_managed_session=a", "origin": "https://evil.test"}))
    assert origin_is_allowed(_request("POST", {"authorization": "Bearer t", "cookie": "acp_managed_session=a", "origin": "https://evil.test"}))
    assert origin_is_allowed(_request("POST", {"origin": "https://evil.test"}))


def test_cross_origin_cookie_post_is_rejected() -> None:
    headers = {"host": "hub.example.com", "cookie": "acp_managed_session=a", "origin": "https://evil.test"}
    assert not origin_is_allowed(_request("POST", headers))


def test_same_origin_cookie_post_is_allowed() -> None:
    headers = {"host": "hub.example.com", "cookie": "acp_managed_session=a", "origin": "https://hub.example.com"}
    assert origin_is_allowed(_request("POST", headers))


def test_cookie_post_without_origin_needs_same_origin_fetch_metadata() -> None:
    base = {"host": "hub.example.com", "cookie": "acp_managed_session=a"}
    assert origin_is_allowed(_request("POST", base))
    assert not origin_is_allowed(_request("POST", {**base, "sec-fetch-site": "cross-site"}))


def test_forwarded_host_ignored_unless_proxy_trusted(monkeypatch) -> None:
    headers = {"host": "internal:8000", "x-forwarded-host": "hub.example.com", "cookie": "acp_managed_session=a", "origin": "https://hub.example.com"}
    monkeypatch.delenv("ACP_TRUST_PROXY_HEADERS", raising=False)
    assert not origin_is_allowed(_request("POST", headers))
    monkeypatch.setenv("ACP_TRUST_PROXY_HEADERS", "1")
    assert origin_is_allowed(_request("POST", headers))
