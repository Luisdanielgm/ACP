from __future__ import annotations

from typing import Any

import pytest

from acp.hub.dashboard_auth import MemberSession, MemberSessionStore

_MEMBER_COOKIE_NAME = "acp_member_session"


def _create_session(client: Any, agent_name: str) -> dict[str, Any]:
    response = client.post("/sessions", json={"agent_name": agent_name})
    assert response.status_code == 201
    return response.json()


def _join_session(client: Any, agent_name: str, join_code: str) -> dict[str, Any]:
    response = client.post("/sessions/join", json={"agent_name": agent_name, "join_code": join_code})
    assert response.status_code == 200
    return response.json()


def _auth_member(client: Any, session_id: str, agent_name: str, member_token: str) -> Any:
    return client.post(
        "/dashboard/session/auth",
        json={"session_id": session_id, "agent_name": agent_name, "member_token": member_token},
    )


# --- endpoint / integration tests -------------------------------------------------


def test_member_session_auth_sets_cookie_and_detail_works_with_cookie_only(api_client: Any) -> None:
    # (a) valid creds -> cookie set; a subsequent /detail using ONLY the cookie returns 200.
    chief = _create_session(api_client, "chief")
    worker = _join_session(api_client, "worker", chief["join_code"])

    auth = _auth_member(api_client, chief["session_id"], "worker", worker["member_token"])
    assert auth.status_code == 200
    assert _MEMBER_COOKIE_NAME in auth.cookies
    assert auth.cookies[_MEMBER_COOKIE_NAME] != worker["member_token"]

    # No agent_name / member_token / header — only the cookie jar (auto-sent by TestClient).
    detail = api_client.get(f"/sessions/{chief['session_id']}/detail")
    assert detail.status_code == 200
    body = detail.json()
    assert body["status"] == "ok"
    assert body["session"]["session_id"] == chief["session_id"]


def test_member_session_auth_rejects_bad_member_token_no_cookie(api_client: Any) -> None:
    # (b) bad member_token -> auth endpoint rejects, no cookie.
    chief = _create_session(api_client, "chief")
    _join_session(api_client, "worker", chief["join_code"])

    auth = _auth_member(api_client, chief["session_id"], "worker", "not-the-real-token")
    assert auth.status_code in (401, 403)
    assert _MEMBER_COOKIE_NAME not in auth.cookies


def test_member_cookie_is_scoped_to_its_session(api_client: Any) -> None:
    # (c) a cookie minted for session A is rejected on session B's /detail.
    chief_a = _create_session(api_client, "chief")
    worker_a = _join_session(api_client, "worker", chief_a["join_code"])
    chief_b = _create_session(api_client, "chief-b")
    _join_session(api_client, "worker-b", chief_b["join_code"])

    auth = _auth_member(api_client, chief_a["session_id"], "worker", worker_a["member_token"])
    assert auth.status_code == 200
    # Session A's cookie is now in the jar; auto-sent to session B's detail.

    detail = api_client.get(f"/sessions/{chief_b['session_id']}/detail")
    # Must NOT authorize: no admin, no member token, cross-session cookie ignored.
    assert detail.status_code in (401, 403)
    assert detail.json().get("session") is None


def test_member_cookie_does_not_authorize_admin_endpoints(tokenized_api_client: Any) -> None:
    # (d) the member cookie must NOT authorize admin/close or admin disconnect.
    # Use a tokenized runtime so admin endpoints actually require a token.
    admin = {"X-ACP-Token": "secret-token"}
    chief = _create_session_tokenized(tokenized_api_client, "chief", admin)
    worker = tokenized_api_client.post(
        "/sessions/join",
        json={"agent_name": "worker", "join_code": chief["join_code"]},
        headers=admin,
    ).json()

    # Auth as member -> the member cookie is now in the client's cookie jar.
    auth = _auth_member(tokenized_api_client, chief["session_id"], "worker", worker["member_token"])
    assert auth.status_code == 200
    assert _MEMBER_COOKIE_NAME in tokenized_api_client.cookies

    # admin/close carrying ONLY the member cookie (no admin token) -> rejected.
    close = tokenized_api_client.post(f"/sessions/{chief['session_id']}/admin/close", json={})
    assert close.status_code in (401, 403)

    # admin disconnect carrying ONLY the member cookie -> rejected.
    disconnect = tokenized_api_client.post(
        f"/sessions/{chief['session_id']}/admin/members/worker/disconnect",
        json={},
    )
    assert disconnect.status_code in (401, 403)


def test_member_cookie_revalidated_after_admin_remove(tokenized_api_client: Any) -> None:
    # (e) after admin removes the member, a /detail poll carrying the cookie is
    # denied (no stale-access window). Disconnect eagerly revokes the cookie
    # server-side (401, no creds); even without that, per-request token
    # re-validation would reject it (403). Either way: access denied.
    admin = {"X-ACP-Token": "secret-token"}
    chief = _create_session_tokenized(tokenized_api_client, "chief", admin)
    worker = tokenized_api_client.post(
        "/sessions/join",
        json={"agent_name": "worker", "join_code": chief["join_code"]},
        headers=admin,
    ).json()

    auth = _auth_member(tokenized_api_client, chief["session_id"], "worker", worker["member_token"])
    assert auth.status_code == 200

    # Cookie works before removal (jar auto-sends it, no other creds).
    ok = tokenized_api_client.get(f"/sessions/{chief['session_id']}/detail")
    assert ok.status_code == 200

    # Admin removes worker (needs admin token).
    removed = tokenized_api_client.post(
        f"/sessions/{chief['session_id']}/admin/members/worker/disconnect",
        json={},
        headers=admin,
    )
    assert removed.status_code == 200

    # The cookie must no longer grant access.
    after = tokenized_api_client.get(f"/sessions/{chief['session_id']}/detail")
    assert after.status_code in (401, 403, 404)
    assert after.json().get("session") is None


def test_member_cookie_rejected_after_same_name_rejoin(tokenized_api_client: Any) -> None:
    # (MAJOR guard) After the member is removed and a NEW agent rejoins the SAME
    # session under the SAME name (fresh member_token), the OLD cookie must fail
    # closed — the cookie is bound to the original token, not just the name.
    admin = {"X-ACP-Token": "secret-token"}
    chief = _create_session_tokenized(tokenized_api_client, "chief", admin)
    worker = tokenized_api_client.post(
        "/sessions/join",
        json={"agent_name": "worker", "join_code": chief["join_code"]},
        headers=admin,
    ).json()

    auth = _auth_member(tokenized_api_client, chief["session_id"], "worker", worker["member_token"])
    assert auth.status_code == 200
    old_cookie = auth.cookies[_MEMBER_COOKIE_NAME]
    assert tokenized_api_client.get(f"/sessions/{chief['session_id']}/detail").status_code == 200

    # Admin disconnects worker; a different agent rejoins under the same name.
    tokenized_api_client.post(
        f"/sessions/{chief['session_id']}/admin/members/worker/disconnect",
        json={},
        headers=admin,
    )
    rejoined = tokenized_api_client.post(
        "/sessions/join",
        json={"agent_name": "worker", "join_code": chief["join_code"]},
        headers=admin,
    ).json()
    assert rejoined["member_token"] != worker["member_token"]

    # Re-set the OLD cookie explicitly (disconnect revoked it server-side; this
    # proves that even a replayed pre-rejoin cookie cannot resolve to the new member).
    tokenized_api_client.cookies.set(_MEMBER_COOKIE_NAME, old_cookie)
    after = tokenized_api_client.get(f"/sessions/{chief['session_id']}/detail")
    assert after.status_code in (401, 403)
    assert after.json().get("session") is None


def test_header_member_token_still_works_backward_compat(api_client: Any) -> None:
    # (f) existing header/query member_token on /detail still returns 200.
    chief = _create_session(api_client, "chief")
    worker = _join_session(api_client, "worker", chief["join_code"])

    via_header = api_client.get(
        f"/sessions/{chief['session_id']}/detail",
        params={"agent_name": "worker"},
        headers={"X-ACP-Member-Token": worker["member_token"]},
    )
    assert via_header.status_code == 200
    assert via_header.json()["session"]["session_id"] == chief["session_id"]

    via_query = api_client.get(
        f"/sessions/{chief['session_id']}/detail",
        params={"agent_name": "worker", "member_token": worker["member_token"]},
    )
    assert via_query.status_code == 200
    assert via_query.json()["session"]["session_id"] == chief["session_id"]


def test_member_session_logout_revokes_cookie(api_client: Any) -> None:
    chief = _create_session(api_client, "chief")
    worker = _join_session(api_client, "worker", chief["join_code"])

    auth = _auth_member(api_client, chief["session_id"], "worker", worker["member_token"])
    assert auth.status_code == 200
    cookie_value = auth.cookies[_MEMBER_COOKIE_NAME]

    # Logout revokes the token server-side (jar sends the cookie automatically).
    logout = api_client.post("/dashboard/session/auth/logout")
    assert logout.status_code == 200

    # Re-set the raw cookie on the jar and confirm it no longer resolves.
    api_client.cookies.set(_MEMBER_COOKIE_NAME, cookie_value)
    after = api_client.get(f"/sessions/{chief['session_id']}/detail")
    assert after.status_code in (401, 403)


def _create_session_tokenized(client: Any, agent_name: str, admin_headers: dict[str, str]) -> dict[str, Any]:
    response = client.post("/sessions", json={"agent_name": agent_name}, headers=admin_headers)
    assert response.status_code == 201
    return response.json()


# --- MemberSessionStore unit test -------------------------------------------------


def test_member_session_store_unit() -> None:
    # (g) create/get/revoke/revoke_for, hash-not-raw, TTL.
    store = MemberSessionStore(ttl_seconds=3600)

    raw = store.create("sess-1", "worker", "member-token-1")
    assert isinstance(raw, str) and raw

    # The cookie value is a random handle, not the member_token, and the dict is
    # keyed by a hash of it — the raw cookie is never a stored key.
    assert raw not in store._sessions  # noqa: SLF001 - unit inspection
    assert raw != "member-token-1"
    hashed = store._hash_token(raw)  # noqa: SLF001
    assert hashed in store._sessions
    assert hashed != raw

    got = store.get(raw)
    assert isinstance(got, MemberSession)
    assert got.session_id == "sess-1"
    assert got.agent_name == "worker"
    # The member_token is held server-side (for per-request re-validation) but
    # carries no admin capability.
    assert got.member_token == "member-token-1"

    # revoke
    store.revoke(raw)
    assert store.get(raw) is None

    # revoke_for by session
    a = store.create("sess-2", "alice", "tok-a")
    b = store.create("sess-2", "bob", "tok-b")
    c = store.create("sess-3", "carol", "tok-c")
    store.revoke_for("sess-2")
    assert store.get(a) is None
    assert store.get(b) is None
    assert store.get(c) is not None

    # revoke_for scoped by agent
    d = store.create("sess-4", "dan", "tok-d")
    e = store.create("sess-4", "eve", "tok-e")
    store.revoke_for("sess-4", agent_name="dan")
    assert store.get(d) is None
    assert store.get(e) is not None

    # get with junk input
    assert store.get(None) is None
    assert store.get("  ") is None
    assert store.get("never-issued") is None


def test_member_session_store_ttl_expiry(monkeypatch: pytest.MonkeyPatch) -> None:
    import acp.hub.dashboard_auth as da

    clock = {"t": 1000.0}
    monkeypatch.setattr(da.time, "monotonic", lambda: clock["t"])

    store = MemberSessionStore(ttl_seconds=10)
    raw = store.create("sess-x", "worker", "member-token-x")
    assert store.get(raw) is not None  # within TTL

    clock["t"] += 11  # advance past TTL
    assert store.get(raw) is None  # expired
    # expired entry purged on access
    assert store.count() == 0
