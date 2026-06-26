"""Release metadata helpers for the distributable ACP agent bundle."""

from __future__ import annotations

import hashlib
import os
import re
import urllib.parse
from pathlib import Path
from typing import Any
from zipfile import ZipFile

from acp.hub.bundle_archive import ACP_AGENT_BUNDLE_PATH, ACP_AGENT_SOURCE_DIR, ensure_bundle_archive
from acp.hub.hub_branding import load_hub_branding


def _read_text(path: Path) -> str:
    if not path.is_file():
        return ""
    return path.read_text(encoding="utf-8").strip()


def read_bundle_version(source_dir: Path = ACP_AGENT_SOURCE_DIR) -> str:
    version = _read_text(source_dir / "VERSION")
    return version or "0.0.0"


def _parse_changelog_text(content: str) -> list[dict[str, Any]]:
    if not content:
        return []

    entries: list[dict[str, Any]] = []
    current: dict[str, Any] | None = None
    for raw_line in content.splitlines():
        line = raw_line.strip()
        if line.startswith("## "):
            if current is not None:
                entries.append(current)
            heading = line[3:].strip()
            version, _, date = heading.partition(" - ")
            current = {
                "version": version.strip(),
                "date": date.strip() or None,
                "notes": [],
            }
            continue
        if current is not None and line.startswith("- "):
            note_text = line[2:].strip()
            localized_match = re.match(r"(?i)(en|es):\s*(.+)$", note_text)
            if localized_match is None:
                current["notes"].append(note_text)
                continue
            language = localized_match.group(1).lower()
            message = localized_match.group(2).strip()
            notes = current["notes"]
            if notes and isinstance(notes[-1], dict) and not notes[-1].get(language):
                notes[-1][language] = message
            else:
                notes.append({language: message})
    if current is not None:
        entries.append(current)
    return _normalize_changelog_entries(entries)


def _normalize_changelog_entries(entries: list[dict[str, Any]]) -> list[dict[str, Any]]:
    normalized: list[dict[str, Any]] = []
    for entry in entries:
        notes: list[Any] = []
        for note in entry.get("notes", []):
            if isinstance(note, dict):
                english = str(note.get("en") or "").strip()
                spanish = str(note.get("es") or "").strip()
                if not english and not spanish:
                    continue
                if not english:
                    english = spanish
                if not spanish:
                    spanish = english
                notes.append({"en": english, "es": spanish})
                continue
            text = str(note).strip()
            if text:
                notes.append(text)
        normalized.append(
            {
                "version": entry.get("version"),
                "date": entry.get("date"),
                "notes": notes,
            }
        )
    return normalized


def _parse_changelog(source_dir: Path = ACP_AGENT_SOURCE_DIR) -> list[dict[str, Any]]:
    return _parse_changelog_text(_read_text(source_dir / "CHANGELOG.md"))


def _read_archive_text(bundle_path: Path, member_name: str) -> str:
    if not bundle_path.is_file():
        return ""
    try:
        with ZipFile(bundle_path) as archive:
            with archive.open(member_name) as handle:
                return handle.read().decode("utf-8").strip()
    except (KeyError, OSError, UnicodeDecodeError):
        return ""


def _bundle_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _env_value(name: str) -> str | None:
    value = os.getenv(name)
    if not isinstance(value, str):
        return None
    cleaned = value.strip()
    return cleaned or None


def _valid_version_or_none(value: str | None) -> str | None:
    if value is None:
        return None
    if re.fullmatch(r"[0-9A-Za-z][0-9A-Za-z.\-_]*", value) is None:
        return None
    return value


def _build_update_policy(*, current_version: str) -> dict[str, Any]:
    recommended_version = _valid_version_or_none(_env_value("ACP_AGENT_RECOMMENDED_VERSION")) or current_version
    minimum_supported_version = _valid_version_or_none(_env_value("ACP_AGENT_MIN_SUPPORTED_VERSION"))
    channel = _env_value("ACP_AGENT_RELEASE_CHANNEL") or "stable"
    return {
        "channel": channel,
        "recommended_version": recommended_version,
        "minimum_supported_version": minimum_supported_version,
        "policy_url": "/downloads",
    }


def _env_flag(name: str, *, default: bool = False) -> bool:
    value = _env_value(name)
    if value is None:
        return default
    return value.lower() in {"1", "true", "yes", "y", "on"}


def _build_agent_update_policy() -> dict[str, Any]:
    auto_when_idle = _env_flag("ACP_AGENT_AUTO_UPDATE_WHEN_IDLE", default=False)
    default_policy = _env_value("ACP_AGENT_DEFAULT_UPDATE_POLICY")
    if default_policy not in {"off", "notify", "auto_when_idle"}:
        default_policy = "auto_when_idle" if auto_when_idle else "notify"
    return {
        "default_policy": default_policy,
        "auto_update_when_idle": auto_when_idle,
        "tracked_repo_default": "notify",
        "untracked_install_default": "auto_when_idle" if auto_when_idle else "notify",
        "safe_update_command": "python ACP_AGENT/update_from_release.py --auto-when-idle",
        "check_command": "python ACP_AGENT/update_from_release.py --check",
        "preserves": ["agents", "inbox", "outbox", "sent"],
        "safety": "Autonomous updates are blocked when ACP_AGENT files are tracked by git unless explicitly allowed.",
    }


def _absolute_url(base_url: str | None, path: str) -> str:
    if not isinstance(base_url, str) or not base_url.strip():
        return path
    return urllib.parse.urljoin(base_url.rstrip("/") + "/", path.lstrip("/"))


def build_bundle_release_manifest(
    *,
    bundle_url: str = "/downloads/ACP_AGENT.zip",
    base_url: str | None = None,
    source_dir: Path = ACP_AGENT_SOURCE_DIR,
    bundle_path: Path | None = None,
) -> dict[str, Any]:
    branding = load_hub_branding(base_url=base_url)
    effective_bundle_path = ensure_bundle_archive(
        source_dir=source_dir,
        bundle_path=bundle_path or ACP_AGENT_BUNDLE_PATH,
    )
    changelog = _parse_changelog(source_dir=source_dir)
    version = read_bundle_version(source_dir=source_dir)
    if not changelog:
        changelog = _parse_changelog_text(_read_archive_text(effective_bundle_path, "CHANGELOG.md"))
    if version == "0.0.0":
        archive_version = _read_archive_text(effective_bundle_path, "VERSION")
        if archive_version:
            version = archive_version
    if version == "0.0.0" and changelog:
        fallback_version = str(changelog[0].get("version") or "").strip()
        if fallback_version:
            version = fallback_version
    latest_entry = changelog[0] if changelog else {"version": version, "date": None, "notes": []}
    size_bytes = effective_bundle_path.stat().st_size if effective_bundle_path.is_file() else 0
    bundle_url_value = _absolute_url(base_url, bundle_url)
    manifest_url = _absolute_url(base_url, "/downloads/ACP_AGENT.json")
    downloads_page_url = _absolute_url(base_url, "/downloads")
    landing_page_url = _absolute_url(base_url, "/")
    runtime_url = _absolute_url(base_url, "/runtime")
    health_url = _absolute_url(base_url, "/health")
    guide_url = _absolute_url(base_url, "/downloads/ACP_AGENT/AGENT.md")
    skill_url = _absolute_url(base_url, "/downloads/ACP_AGENT/skills/acp-session-coordinator/SKILL.md")
    policy = _build_update_policy(current_version=version)
    policy["policy_url"] = downloads_page_url
    agent_update = _build_agent_update_policy()
    return {
        "product": "ACP_AGENT",
        "brand_name": branding.brand_name,
        "version": version,
        "released_at": latest_entry.get("date"),
        "bundle_url": bundle_url_value,
        "manifest_url": manifest_url,
        "downloads_page_url": downloads_page_url,
        "landing_page_url": landing_page_url,
        "runtime_url": runtime_url,
        "health_url": health_url,
        "agent_guide_url": guide_url,
        "skill_url": skill_url,
        "sha256": _bundle_sha256(effective_bundle_path) if effective_bundle_path.is_file() else "",
        "size_bytes": size_bytes,
        "size_mb": round(size_bytes / (1024 * 1024), 2) if size_bytes else 0,
        "check_command": "python ACP_AGENT/acp.py update-check --config ACP_AGENT/agents/<agent>.json",
        "update_command": "python ACP_AGENT/acp.py self-update --config ACP_AGENT/agents/<agent>.json --auto-when-idle",
        "official_hub_http": branding.official_hub_http,
        "official_hub_ws": branding.official_hub_ws,
        "update_policy": policy,
        "agent_update": agent_update,
        "agent_bootstrap": {
            "start_here": [
                manifest_url,
                guide_url,
                skill_url,
                downloads_page_url,
            ],
            "read_order": [
                "manifest",
                "agent_guide",
                "skill",
                "downloads_page",
            ],
            "notes": [
                "Use the manifest to discover the current version, bundle URL, and changelog.",
                "Read AGENT.md for the human and agent bootstrap contract.",
                "Read the ACP session coordinator skill before operating live ACP sessions.",
                "Use runtime and health endpoints to validate that the hub is online before attempting websocket coordination.",
            ],
        },
        "changelog": changelog,
    }
