from __future__ import annotations

from pathlib import Path
from zipfile import ZipFile

from acp.hub.bundle_archive import (
    _discover_downloads_dir,
    build_bundle_archive,
    bundle_is_stale,
    ensure_bundle_archive,
)


REPO_ROOT = Path(__file__).resolve().parents[2]


def test_build_bundle_archive_writes_skill_tree(tmp_path: Path) -> None:
    source_dir = tmp_path / "ACP_AGENT"
    bundle_path = tmp_path / "downloads" / "ACP_AGENT.zip"
    skill_dir = source_dir / "skills" / "acp-session-coordinator"
    skill_dir.mkdir(parents=True)
    (source_dir / "acp.py").write_text("print('ok')\n", encoding="utf-8")
    (skill_dir / "SKILL.md").write_text("# ACP\n", encoding="utf-8")

    result = build_bundle_archive(source_dir=source_dir, bundle_path=bundle_path)

    assert result == bundle_path
    assert bundle_path.is_file()
    with ZipFile(bundle_path) as archive:
        assert sorted(archive.namelist()) == ["acp.py", "skills/acp-session-coordinator/SKILL.md"]


def test_ensure_bundle_archive_rebuilds_when_source_changes(tmp_path: Path) -> None:
    source_dir = tmp_path / "ACP_AGENT"
    bundle_path = tmp_path / "downloads" / "ACP_AGENT.zip"
    source_dir.mkdir(parents=True)
    tracked_file = source_dir / "AGENT.md"
    tracked_file.write_text("v1\n", encoding="utf-8")

    ensure_bundle_archive(source_dir=source_dir, bundle_path=bundle_path)
    assert bundle_is_stale(source_dir=source_dir, bundle_path=bundle_path) is False

    tracked_file.write_text("v2\n", encoding="utf-8")

    assert bundle_is_stale(source_dir=source_dir, bundle_path=bundle_path) is True
    ensure_bundle_archive(source_dir=source_dir, bundle_path=bundle_path)
    with ZipFile(bundle_path) as archive:
        assert archive.read("AGENT.md").decode("utf-8").strip() == "v2"


def test_discover_downloads_dir_falls_back_to_process_cwd(monkeypatch, tmp_path: Path) -> None:
    downloads_dir = tmp_path / "downloads"
    downloads_dir.mkdir()
    monkeypatch.chdir(tmp_path)

    assert _discover_downloads_dir() == downloads_dir.resolve()


def test_project_and_bundle_session_coordinator_skills_are_synchronized() -> None:
    bundled = REPO_ROOT / "ACP_AGENT" / "skills" / "acp-session-coordinator" / "SKILL.md"
    project = REPO_ROOT / ".codex" / "skills" / "acp-session-coordinator" / "SKILL.md"

    assert project.is_file()
    assert project.read_bytes() == bundled.read_bytes()
