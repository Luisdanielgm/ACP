from __future__ import annotations

from pathlib import Path

from acp.hub.bundle_archive import build_bundle_archive
from acp.hub.bundle_release import build_bundle_release_manifest


def test_bundle_release_manifest_falls_back_to_zip_metadata_when_source_is_missing(tmp_path: Path) -> None:
    source_dir = tmp_path / "ACP_AGENT"
    bundle_path = tmp_path / "downloads" / "ACP_AGENT.zip"
    source_dir.mkdir(parents=True)
    (source_dir / "VERSION").write_text("0.3.0\n", encoding="utf-8")
    (source_dir / "CHANGELOG.md").write_text(
        "# ACP_AGENT Changelog\n\n## 0.3.0 - 2026-03-07\n\n- Added release metadata.\n",
        encoding="utf-8",
    )
    (source_dir / "acp.py").write_text("print('ok')\n", encoding="utf-8")

    build_bundle_archive(source_dir=source_dir, bundle_path=bundle_path)
    missing_source_dir = tmp_path / "missing-agent"

    manifest = build_bundle_release_manifest(
        bundle_url="/downloads/ACP_AGENT.zip",
        base_url="https://hub.example/",
        source_dir=missing_source_dir,
        bundle_path=bundle_path,
    )

    assert manifest["version"] == "0.3.0"
    assert manifest["released_at"] == "2026-03-07"
    assert manifest["bundle_url"] == "https://hub.example/downloads/ACP_AGENT.zip"
    assert manifest["manifest_url"] == "https://hub.example/downloads/ACP_AGENT.json"
    assert manifest["downloads_page_url"] == "https://hub.example/downloads"
    assert manifest["brand_name"] == "ACP Hub"
    assert manifest["official_hub_http"] == "https://hub.example"
    assert manifest["official_hub_ws"] == "wss://hub.example/ws"
    assert manifest["agent_update"]["default_policy"] == "notify"
    assert manifest["agent_update"]["safe_update_command"] == "python ACP_AGENT/update_from_release.py --auto-when-idle"
    assert manifest["agent_update"]["preserves"] == ["agents", "inbox", "outbox", "sent"]
    assert manifest["changelog"]


def test_bundle_release_manifest_preserves_bilingual_changelog_notes(tmp_path: Path) -> None:
    source_dir = tmp_path / "ACP_AGENT"
    bundle_path = tmp_path / "downloads" / "ACP_AGENT.zip"
    source_dir.mkdir(parents=True)
    (source_dir / "VERSION").write_text("0.3.4\n", encoding="utf-8")
    (source_dir / "CHANGELOG.md").write_text(
        "# ACP_AGENT Changelog\n\n"
        "## 0.3.4 - 2026-03-08\n\n"
        "- EN: English release note.\n"
        "- ES: Nota de release en espanol.\n",
        encoding="utf-8",
    )
    (source_dir / "acp.py").write_text("print('ok')\n", encoding="utf-8")

    build_bundle_archive(source_dir=source_dir, bundle_path=bundle_path)
    manifest = build_bundle_release_manifest(source_dir=source_dir, bundle_path=bundle_path)

    first_note = manifest["changelog"][0]["notes"][0]
    assert first_note == {
        "en": "English release note.",
        "es": "Nota de release en espanol.",
    }


def test_bundle_release_manifest_prefers_configured_public_hub_http(tmp_path: Path, monkeypatch) -> None:
    source_dir = tmp_path / "ACP_AGENT"
    bundle_path = tmp_path / "downloads" / "ACP_AGENT.zip"
    source_dir.mkdir(parents=True)
    (source_dir / "VERSION").write_text("0.3.10\n", encoding="utf-8")
    (source_dir / "CHANGELOG.md").write_text(
        "# ACP_AGENT Changelog\n\n## 0.3.10 - 2026-05-30\n\n- Release.\n",
        encoding="utf-8",
    )
    (source_dir / "acp.py").write_text("print('ok')\n", encoding="utf-8")
    build_bundle_archive(source_dir=source_dir, bundle_path=bundle_path)

    monkeypatch.setenv("ACP_PUBLIC_HUB_HTTP", "https://acp.example.com")

    manifest = build_bundle_release_manifest(
        base_url="http://internal-service/",
        source_dir=source_dir,
        bundle_path=bundle_path,
    )

    assert manifest["bundle_url"] == "https://acp.example.com/downloads/ACP_AGENT.zip"
    assert manifest["manifest_url"] == "https://acp.example.com/downloads/ACP_AGENT.json"
    assert manifest["agent_guide_url"] == "https://acp.example.com/downloads/ACP_AGENT/AGENT.md"
