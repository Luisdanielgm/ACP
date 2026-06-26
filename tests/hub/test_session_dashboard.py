from __future__ import annotations

from typing import Any


def test_session_dashboard_route_returns_html(api_client: Any) -> None:
    response = api_client.get("/dashboard/session", follow_redirects=False)
    assert response.status_code == 307
    assert response.headers["location"] == "/managed/login"
