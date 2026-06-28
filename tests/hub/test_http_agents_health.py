from __future__ import annotations

from acp.hub.app import HubRuntime, create_app
from acp.hub.overlay_example import create_overlay_example_app
from fastapi.testclient import TestClient


def test_get_agents_returns_sorted_connected_agent_names_only(api_client, hub_runtime, websocket_factory) -> None:
    beta_socket = websocket_factory()
    alpha_socket = websocket_factory()

    assert hub_runtime.registry.register_agent(
        session_id="agent-beta-session",
        websocket=beta_socket,
        name="agent_beta",
    )
    assert hub_runtime.registry.register_agent(
        session_id="agent-alpha-session",
        websocket=alpha_socket,
        name="agent_alpha",
    )

    response = api_client.get("/agents")

    assert response.status_code == 200
    body = response.json()
    assert body == {"agents": ["agent_alpha", "agent_beta"]}


def test_get_agents_excludes_observers_and_non_registered(api_client, hub_runtime, observer_socket_factory) -> None:
    observer_socket = observer_socket_factory()
    hub_runtime.registry.register_observer(
        session_id="observer-session",
        websocket=observer_socket,
        name="observer_live",
    )
    assert hub_runtime.registry.enable_observer_live_traces("observer-session")

    response = api_client.get("/agents")

    assert response.status_code == 200
    assert response.json() == {"agents": []}


def test_get_agents_is_deterministic_across_calls(api_client, hub_runtime, websocket_factory) -> None:
    for name in ["agent_delta", "agent_gamma", "agent_beta"]:
        assert hub_runtime.registry.register_agent(
            session_id=f"{name}-session",
            websocket=websocket_factory(),
            name=name,
        )

    first = api_client.get("/agents")
    second = api_client.get("/agents")

    assert first.status_code == 200
    assert second.status_code == 200
    assert first.json() == second.json()
    assert first.json()["agents"] == ["agent_beta", "agent_delta", "agent_gamma"]


def test_get_health_returns_status_ok_only(api_client) -> None:
    response = api_client.get("/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_get_health_contract_stays_minimal(api_client) -> None:
    response = api_client.get("/health")

    assert response.status_code == 200
    body = response.json()
    assert set(body.keys()) == {"status"}
    assert body["status"] == "ok"


def test_root_serves_public_landing_html(api_client) -> None:
    response = api_client.get("/")

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/html")
    assert "ACP Hub" in response.text
    assert "/downloads" in response.text
    assert "release-version" in response.text
    assert "latest change" in response.text or "ultimo cambio" in response.text


def test_download_bundle_is_served_from_hub(api_client) -> None:
    response = api_client.get("/downloads/ACP_AGENT.zip")

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("application/zip")
    assert "attachment; filename=\"ACP_AGENT.zip\"" in response.headers["content-disposition"]
    assert len(response.content) > 0


def test_downloads_page_exposes_release_and_changelog(api_client) -> None:
    response = api_client.get("/downloads")

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/html")
    assert "ACP Agent downloads and changelog" in response.text
    assert "ACP_AGENT/update_from_release.py --check" in response.text
    assert "Recent changelog" in response.text
    assert "lang-toggle" in response.text
    assert "theme-toggle" in response.text
    assert "noteText(note)" in response.text


def test_download_manifest_exposes_release_metadata(api_client) -> None:
    response = api_client.get("/downloads/ACP_AGENT.json")

    assert response.status_code == 200
    body = response.json()
    assert body["product"] == "ACP_AGENT"
    assert body["brand_name"] == "ACP Hub"
    assert body["version"]
    assert body["bundle_url"] == "http://testserver/downloads/ACP_AGENT.zip"
    assert body["manifest_url"] == "http://testserver/downloads/ACP_AGENT.json"
    assert body["downloads_page_url"] == "http://testserver/downloads"
    assert body["official_hub_http"] == "http://testserver"
    assert body["official_hub_ws"] == "ws://testserver/ws"
    assert body["check_command"] == "python ACP_AGENT/acp.py update-check --config ACP_AGENT/agents/<agent>.json"
    assert body["update_command"] == "python ACP_AGENT/acp.py self-update --config ACP_AGENT/agents/<agent>.json --auto-when-idle"
    # X-LEGACY-06: the legacy update_from_release.py manifest hints are retired;
    # the supported path is check_command/update_command (acp.py).
    assert "legacy_check_command" not in body
    assert "legacy_update_command" not in body
    assert body["update_policy"]["recommended_version"] == body["version"]
    assert "minimum_supported_version" in body["update_policy"]
    assert isinstance(body["changelog"], list)
    assert body["changelog"]


def test_runtime_can_disable_public_web_surface() -> None:
    app = create_app(runtime=HubRuntime(public_web_enabled=False))
    with TestClient(app) as client:
        root = client.get("/")
        runtime = client.get("/runtime")
        downloads = client.get("/downloads")

    assert root.status_code == 404
    assert downloads.status_code == 404
    assert runtime.status_code == 200
    assert runtime.json()["runtime"]["public_web_enabled"] is False


def test_overlay_example_can_mount_private_routes_on_top_of_core() -> None:
    app = create_overlay_example_app()
    with TestClient(app) as client:
        root = client.get("/")
        downloads = client.get("/downloads")
        auth_mode = client.get("/managed/auth/mode")
        runtime = client.get("/runtime")

    assert root.status_code == 200
    assert "ACP Cloud Overlay Example" in root.text
    assert downloads.status_code == 200
    assert "Managed Downloads" in downloads.text
    assert auth_mode.status_code == 200
    assert auth_mode.json()["mode"] == "overlay"
    assert runtime.status_code == 200
    assert runtime.json()["runtime"]["public_web_enabled"] is False

def test_get_agents_prunes_stale_sessions_before_response(api_client, hub_runtime, websocket_factory) -> None:
    socket = websocket_factory()
    assert hub_runtime.registry.register_agent(
        session_id="agent-alpha-session",
        websocket=socket,
        name="agent_alpha",
    )

    removed = hub_runtime.registry.unregister_session(
        session_id="agent-alpha-session",
        websocket=socket,
    )
    assert removed is not None

    response = api_client.get("/agents")

    assert response.status_code == 200
    assert response.json() == {"agents": []}


def test_get_agents_response_has_only_expected_contract_key(api_client, hub_runtime, websocket_factory) -> None:
    assert hub_runtime.registry.register_agent(
        session_id="agent-omega-session",
        websocket=websocket_factory(),
        name="agent_omega",
    )

    response = api_client.get("/agents")

    assert response.status_code == 200
    body = response.json()
    assert set(body.keys()) == {"agents"}
    assert body["agents"] == ["agent_omega"]
