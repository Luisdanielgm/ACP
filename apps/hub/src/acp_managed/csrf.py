"""Origin check for cookie-authenticated, state-changing managed requests.

The managed session cookie is ``SameSite=Lax``, which already blocks most
cross-site POSTs. This adds defense in depth: when a request carries the
browser session cookie (and no explicit Bearer credential) and declares an
``Origin`` that is not this hub, it is rejected.
"""

from __future__ import annotations

import urllib.parse

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from acp_managed.routing._helpers import _trusted_forwarded_host

SESSION_COOKIE = "acp_managed_session"
_UNSAFE_METHODS = frozenset({"POST", "PUT", "PATCH", "DELETE"})


def _expected_hosts(request: Request) -> set[str]:
    hosts = {request.headers.get("host", "").strip().lower()}
    forwarded = _trusted_forwarded_host(request).lower()
    if forwarded:
        hosts.add(forwarded)
    hosts.discard("")
    return hosts


def origin_is_allowed(request: Request) -> bool:
    if request.method not in _UNSAFE_METHODS:
        return True
    if not request.cookies.get(SESSION_COOKIE) or request.headers.get("authorization"):
        return True
    origin = request.headers.get("origin")
    if origin is None:
        return request.headers.get("sec-fetch-site", "same-origin") in {"same-origin", "none"}
    netloc = urllib.parse.urlparse(origin).netloc.lower()
    return bool(netloc) and netloc in _expected_hosts(request)


def install_origin_guard(app: FastAPI) -> None:
    @app.middleware("http")
    async def _origin_guard(request: Request, call_next):  # type: ignore[no-untyped-def]
        if not origin_is_allowed(request):
            return JSONResponse({"detail": "cross-origin request rejected"}, status_code=403)
        return await call_next(request)
