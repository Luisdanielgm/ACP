from __future__ import annotations

import re
import hashlib
import subprocess
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
    REPO_ROOT / "HANDOFF-sala-viva.md",
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
# Fingerprints avoid publishing customer/project names in the guard itself.
# These are regression checks, not encryption or a general secret scanner.
PRIVATE_MARKER_FINGERPRINTS = {
    (10, "aac62148e0cfed01d656aae9a829b0374b210aecca9e033f8d43136af7691276"),
    (10, "238cb8066630a04e653b22c12aecc2407baad258409d4d8bf05f582365008514"),
    (5, "ce4919b6de0785ec716757dccb058b8d4ababb7fc1048603400b899b2c67b459"),
    (11, "2fa89a954fceb94e4902d575903f90f844540993366d56ee2bce6ffea0634a66"),
    (7, "61bcd4e590465c3b63200090464aa85c25771c1997a49355d6debcc0fa402dc0"),
    (6, "73ef041995e94147c83239e6e779dbe02b12ebb3792f0bd70f9827b3ba88231a"),
}

def _contains_private_marker(content: str) -> bool:
    # Preserve substring matching within the marker alphabet.
    tokens = set(re.findall(r"[a-z0-9-]+", content.lower()))
    for length, digest in PRIVATE_MARKER_FINGERPRINTS:
        for token in tokens:
            for offset in range(len(token) - length + 1):
                if hashlib.sha256(token[offset:offset + length].encode()).hexdigest() == digest:
                    return True
    return False


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
        content_lower = content.lower()
        if _contains_private_marker(content_lower):
            violations.append(f"{path.relative_to(REPO_ROOT)} -> private identifier")
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


def test_private_marker_detection_preserves_substrings(monkeypatch) -> None:
    marker = "synthetic-private-id"
    monkeypatch.setitem(globals(), "PRIVATE_MARKER_FINGERPRINTS", {
        (len(marker), hashlib.sha256(marker.encode()).hexdigest()),
    })
    assert _contains_private_marker("prefixSYNTHETIC-PRIVATE-IDsuffix")
    assert not _contains_private_marker("neutral-example")


def test_environment_files_are_ignored() -> None:
    paths = [".env", ".env.local", "apps/hub/.env", "apps/hub/.env.production"]
    result = subprocess.run(
        ["git", "check-ignore", "--no-index", "--stdin"],
        input=("\n".join(paths) + "\n").encode(), capture_output=True,
        cwd=REPO_ROOT, check=False,
    )
    assert set(result.stdout.decode().splitlines()) == set(paths)


def test_environment_templates_remain_trackable() -> None:
    result = subprocess.run(
        ["git", "check-ignore", "--no-index", "--stdin"],
        input=b".env.example\napps/hub/.env.example\n",
        capture_output=True, cwd=REPO_ROOT, check=False,
    )
    assert result.returncode == 1
