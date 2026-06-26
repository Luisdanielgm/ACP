from __future__ import annotations

from acp_managed.routing.downloads import _agent_markdown_download, build_downloads_router


def test_build_downloads_router_exposes_the_four_download_routes() -> None:
    router = build_downloads_router(None)

    paths = {route.path for route in router.routes}

    assert paths == {
        "/downloads/ACP_AGENT.json",
        "/downloads/ACP_AGENT.zip",
        "/downloads/ACP_AGENT/AGENT.md",
        "/downloads/ACP_AGENT/skills/acp-session-coordinator/SKILL.md",
    }


def test_agent_markdown_download_helper_lives_in_downloads_module() -> None:
    assert callable(_agent_markdown_download)
