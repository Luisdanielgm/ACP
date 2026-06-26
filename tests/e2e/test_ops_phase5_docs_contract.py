from __future__ import annotations

from pathlib import Path


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def test_readme_contract() -> None:
    content = _read(Path("README.md"))

    required_snippets = [
        "docker compose up -d",
        "python ACP_AGENT/acp.py run --hub ws://localhost:8000/ws --name \"Claude-Back\"",
        "python ACP_AGENT/acp.py send --config ACP_AGENT/agents/codex-chief.json",
        "python ACP_AGENT/acp.py listen --config ACP_AGENT/agents/claude-review.json",
        "http://localhost:8000/dashboard",
        "/dashboard/overview",
        "/dashboard/session",
        "ACP_TOKEN",
        "ACP_PORT",
        "MVP Limitations",
    ]

    for snippet in required_snippets:
        assert snippet in content


def test_protocol_doc_contract() -> None:
    content = _read(Path("protocol.md"))

    required_snippets = [
        "HELLO",
        "MSG",
        "TRACE",
        "SNAPSHOT",
        "TASK | REPLY | INFO",
        "POST /send",
        "GET /agents",
        "GET /health",
        "GET /dashboard",
        "GET /dashboard/overview",
        "GET /sessions/{session_id}/detail",
        "listen",
    ]

    for snippet in required_snippets:
        assert snippet in content
