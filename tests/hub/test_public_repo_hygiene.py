from __future__ import annotations

import re
from pathlib import Path

import pytest


REPO_ROOT = Path(__file__).resolve().parents[2]
PUBLIC_EXTRACTION_SOURCES = (
    REPO_ROOT / "ACP_AGENT",
    REPO_ROOT / "apps" / "hub" / "src" / "acp" / "hub",
    REPO_ROOT / "apps" / "hub" / "src" / "acp" / "protocol",
    # Option Y: the managed workspace layer is open source (public Manager).
    REPO_ROOT / "apps" / "hub" / "src" / "acp_managed",
    # The SPA (public + managed apps) is part of the open Manager.
    REPO_ROOT / "apps" / "hub" / "frontend",
    REPO_ROOT / "tests",
    REPO_ROOT / "OPEN_CORE_MODEL.md",
    REPO_ROOT / "PUBLIC_REPO_BOUNDARY.md",
    REPO_ROOT / "README.md",
    REPO_ROOT / "protocol.md",
)
TEXT_SUFFIXES = {
    ".md",
    ".py",
    ".json",
    ".sql",
    ".txt",
    ".toml",
    ".yml",
    ".yaml",
    ".html",
    ".css",
    ".js",
    ".ts",
    ".vue",
}
FORBIDDEN_MARKERS: dict[str, str] = {}
FORBIDDEN_PATTERNS = {
    re.compile(r"https?://(?:acp|cloud|agents)\.(?!example\.com\b)[a-z0-9-]+\.(?:com|group|io|net|org)\b", re.IGNORECASE):
        "hosted/customer ACP domains must use neutral example hosts",
}
SKIP_PARTS = {"__pycache__", ".pytest_cache", ".planning", ".codex", "downloads", "node_modules", "dist"}
SKIP_FILES = {
    "test_managed_app_smoke.py",
    "test_public_repo_hygiene.py",
}


def _iter_public_text_files() -> list[Path]:
    files: list[Path] = []
    for source in PUBLIC_EXTRACTION_SOURCES:
        if not source.exists():
            continue
        if source.is_file():
            files.append(source)
            continue
        for path in source.rglob("*"):
            if not path.is_file():
                continue
            if any(part in SKIP_PARTS for part in path.parts):
                continue
            if path.name in SKIP_FILES:
                continue
            if path.suffix.lower() not in TEXT_SUFFIXES:
                continue
            files.append(path)
    return sorted(set(files))


def _state_frontmatter() -> dict[str, str]:
    raw = (REPO_ROOT / ".planning" / "STATE.md").read_text(encoding="utf-8")
    parts = raw.split("---", 2)
    if len(parts) < 3:
        raise AssertionError("STATE.md must start with YAML frontmatter")
    metadata: dict[str, str] = {}
    for line in parts[1].splitlines():
        if ":" not in line:
            continue
        key, value = line.split(":", 1)
        metadata[key.strip()] = value.strip().strip('"')
    return metadata


def test_public_extraction_set_is_explicit() -> None:
    # Option Y: the workspace layer (acp_managed) is PUBLIC and must be scanned
    # for private markers, not excluded as it was under the old boundary.
    assert REPO_ROOT / "apps" / "hub" / "src" / "acp_managed" in PUBLIC_EXTRACTION_SOURCES
    assert REPO_ROOT / "apps" / "hub" / "src" / "acp" / "hub" in PUBLIC_EXTRACTION_SOURCES
    assert REPO_ROOT / "apps" / "hub" / "src" / "acp" / "protocol" in PUBLIC_EXTRACTION_SOURCES
    public_files = _iter_public_text_files()
    assert REPO_ROOT / "tests" / "hub" / "test_managed_app_smoke.py" not in public_files
    assert REPO_ROOT / "tests" / "hub" / "test_public_repo_hygiene.py" not in public_files


def test_public_repo_has_no_private_branding_or_private_host_defaults() -> None:
    violations: list[str] = []
    for path in _iter_public_text_files():
        content = path.read_text(encoding="utf-8")
        for marker, reason in FORBIDDEN_MARKERS.items():
            if marker in content:
                violations.append(f"{path.relative_to(REPO_ROOT)} -> {marker} ({reason})")
        for pattern, reason in FORBIDDEN_PATTERNS.items():
            for match in pattern.finditer(content):
                violations.append(f"{path.relative_to(REPO_ROOT)} -> {match.group(0)} ({reason})")
    assert violations == []


def test_public_distribution_defaults_require_explicit_hub_configuration() -> None:
    distribution_path = REPO_ROOT / "ACP_AGENT" / "DISTRIBUTION.json"
    payload = distribution_path.read_text(encoding="utf-8")
    assert '"distribution_id": "acp-community"' in payload
    assert '"default_hub_mode": "explicit"' in payload
    assert '"default_hub_http": null' in payload
    assert '"default_hub_ws": null' in payload
    assert '"default_manifest_url": null' in payload


def test_docker_build_context_includes_agent_bundle_source() -> None:
    dockerfile = (REPO_ROOT / "apps" / "hub" / "Dockerfile").read_text(encoding="utf-8")
    compose = (REPO_ROOT / "apps" / "hub" / "docker-compose.yml").read_text(encoding="utf-8")

    assert "COPY ACP_AGENT ./ACP_AGENT" in dockerfile
    assert "ACP_AGENT_SOURCE_DIR=/app/ACP_AGENT" in dockerfile
    assert "context: ../.." in compose
    assert "dockerfile: apps/hub/Dockerfile" in compose


def test_state_doc_has_no_tbd_and_matches_v03_phase_range() -> None:
    state_path = REPO_ROOT / ".planning" / "STATE.md"
    roadmap_path = REPO_ROOT / ".planning" / "ROADMAP.md"
    if not state_path.exists() or not roadmap_path.exists():
        pytest.skip("internal .planning state docs are not shipped in the public repo")

    state_text = state_path.read_text(encoding="utf-8")
    assert "TBD" not in state_text

    metadata = _state_frontmatter()
    assert metadata["milestone"] == "v0.3"

    phase_range_match = re.search(r"\*\*v0\.3 .*?Phases (\d+)-(\d+)", roadmap_path.read_text(encoding="utf-8"))
    assert phase_range_match is not None
    phase_start, phase_end = (int(value) for value in phase_range_match.groups())

    current_phase = int(metadata["current_phase"])
    assert phase_start <= current_phase <= phase_end
    assert metadata["milestone_phase_span"] == f"{phase_start}-{phase_end}"
