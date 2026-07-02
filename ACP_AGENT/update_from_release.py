"""Update an installed ACP_AGENT folder from a distribution release channel."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import shutil
import subprocess
import sys
import urllib.parse
import urllib.request
import zipfile
from datetime import datetime, timezone
from io import BytesIO
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Any

ACP_ROOT = Path(__file__).resolve().parent
if str(ACP_ROOT) not in sys.path:
    sys.path.insert(0, str(ACP_ROOT))

from acp_distribution import load_distribution

_DISTRIBUTION = load_distribution(ACP_ROOT)
DEFAULT_MANIFEST_URL = _DISTRIBUTION.default_manifest_url
PRESERVE_NAMES = {"agents", "inbox", "outbox", "sent", "__pycache__"}
LEGACY_REMOVE = {"wrapper.py", "markdown_client.py", "thin_client.py", "enqueue_message.py", "send.py", "src"}
BUNDLE_INFO_NAME = "BUNDLE_INFO.json"
SKILL_NAME = "acp-session-coordinator"


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Update the local ACP_AGENT folder from a release manifest")
    parser.add_argument("--manifest-url", default=DEFAULT_MANIFEST_URL, help="Release manifest URL")
    parser.add_argument("--target", default=str(ACP_ROOT), help="Target ACP_AGENT directory to update in place")
    parser.add_argument("--check", action="store_true", help="Only compare local and remote versions")
    parser.add_argument("--force", action="store_true", help="Apply the update even when versions match")
    parser.add_argument(
        "--auto-when-idle",
        action="store_true",
        help="Apply only when the target is safe for autonomous idle updates; otherwise report update_blocked",
    )
    parser.add_argument(
        "--allow-tracked-repo",
        action="store_true",
        help="Allow autonomous updates even when ACP_AGENT files are tracked by git",
    )
    return parser


def _read_text(path: Path) -> str | None:
    if not path.is_file():
        return None
    return path.read_text(encoding="utf-8").strip() or None


def local_version(target_dir: Path) -> str | None:
    return _read_text(target_dir / "VERSION")


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def write_bundle_info(*, target_dir: Path, manifest: dict[str, Any], source: str) -> dict[str, Any]:
    release_date = manifest.get("released_at")
    if release_date is None:
        changelog = manifest.get("changelog")
        if isinstance(changelog, list) and changelog:
            first_entry = changelog[0]
            if isinstance(first_entry, dict):
                release_date = first_entry.get("date")
    payload = {
        "installed_at": _utc_now_iso(),
        "installed_version": local_version(target_dir),
        "release_date": release_date,
        "source": source,
        "release_manifest_url": manifest.get("manifest_url"),
        "distribution_id": _DISTRIBUTION.distribution_id,
    }
    (target_dir / BUNDLE_INFO_NAME).write_text(json.dumps(payload, indent=2, ensure_ascii=True) + "\n", encoding="utf-8")
    return payload


def _release_request(url: str) -> urllib.request.Request:
    return urllib.request.Request(
        url,
        headers={
            "Accept": "application/json, application/zip, application/octet-stream, */*",
            "User-Agent": f"ACP_AGENT/{local_version(ACP_ROOT)}",
        },
    )


def fetch_json(url: str) -> dict[str, Any]:
    with urllib.request.urlopen(_release_request(url), timeout=30) as response:
        payload = json.loads(response.read().decode("utf-8"))
    if not isinstance(payload, dict):
        raise ValueError("release manifest must be a JSON object")
    return payload


def fetch_bytes(url: str) -> bytes:
    with urllib.request.urlopen(_release_request(url), timeout=120) as response:
        return response.read()


def _sha256_bytes(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def _version_key(value: str | None) -> tuple[tuple[int, str], ...]:
    if not isinstance(value, str) or not value.strip():
        return tuple()
    parts = re.split(r"[.\-_]+", value.strip())
    normalized: list[tuple[int, str]] = []
    for part in parts:
        if not part:
            continue
        if part.isdigit():
            normalized.append((0, f"{int(part):09d}"))
        else:
            normalized.append((1, part.lower()))
    return tuple(normalized)


def _compare_versions(left: str | None, right: str | None) -> int:
    left_key = _version_key(left)
    right_key = _version_key(right)
    if left_key == right_key:
        return 0
    max_len = max(len(left_key), len(right_key))
    padded_left = left_key + (((0, "000000000"),) * (max_len - len(left_key)))
    padded_right = right_key + (((0, "000000000"),) * (max_len - len(right_key)))
    if padded_left < padded_right:
        return -1
    return 1


def _run_git(*, cwd: Path, args: list[str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["git", *args],
        cwd=str(cwd),
        text=True,
        capture_output=True,
        check=False,
    )


def _git_root_for(path: Path) -> Path | None:
    current = path.resolve()
    probe = current if current.is_dir() else current.parent
    result = _run_git(cwd=probe, args=["rev-parse", "--show-toplevel"])
    if result.returncode != 0:
        return None
    root = result.stdout.strip()
    if not root:
        return None
    return Path(root).resolve()


def target_has_tracked_files(target_dir: Path) -> bool:
    """Return true when this ACP_AGENT install is tracked by the surrounding git repo."""

    git_root = _git_root_for(target_dir)
    if git_root is None:
        return False
    try:
        relative_target = target_dir.resolve().relative_to(git_root)
    except ValueError:
        return False
    result = _run_git(cwd=git_root, args=["ls-files", "--", relative_target.as_posix()])
    return result.returncode == 0 and bool(result.stdout.strip())


def auto_update_safety(*, target_dir: Path, allow_tracked_repo: bool = False) -> dict[str, Any]:
    tracked = target_has_tracked_files(target_dir)
    if tracked and not allow_tracked_repo:
        return {
            "safe": False,
            "reason": "target_is_git_tracked",
            "detail": "ACP_AGENT files are tracked by git; autonomous updates would mutate the user's repository.",
            "manual_command": "python ACP_AGENT/update_from_release.py",
        }
    return {
        "safe": True,
        "reason": "safe_untracked_install" if not tracked else "tracked_repo_allowed",
        "detail": "Target can be updated autonomously while the agent is idle.",
    }


def resolve_policy_status(*, local_version_value: str | None, manifest: dict[str, Any]) -> str:
    policy = manifest.get("update_policy")
    if not isinstance(policy, dict):
        return "unknown"
    minimum_supported_version = policy.get("minimum_supported_version")
    if isinstance(minimum_supported_version, str) and minimum_supported_version.strip():
        if _compare_versions(local_version_value, minimum_supported_version.strip()) < 0:
            return "required"
    recommended_version = policy.get("recommended_version")
    if isinstance(recommended_version, str) and recommended_version.strip():
        if _compare_versions(local_version_value, recommended_version.strip()) < 0:
            return "recommended"
    if isinstance(local_version_value, str) and local_version_value.strip():
        return "current"
    return "unknown"


def _remove_path(path: Path) -> None:
    if path.is_dir():
        shutil.rmtree(path)
    elif path.exists():
        path.unlink()


def _copy_tree(source: Path, destination: Path) -> None:
    if source.is_dir():
        shutil.copytree(source, destination, dirs_exist_ok=True)
    else:
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, destination)


def _replace_tree(source: Path, destination: Path) -> None:
    if destination.exists():
        shutil.rmtree(destination)
    destination.parent.mkdir(parents=True, exist_ok=True)
    shutil.copytree(source, destination)


def sync_skill_installs(
    *,
    target_dir: Path,
    project_skill_home: Path | None = None,
    global_skill_home: Path | None = None,
    claude_skill_home: Path | None = None,
) -> list[str]:
    source_skill = target_dir / "skills" / SKILL_NAME
    if not source_skill.is_dir():
        return []

    destinations: list[Path] = []
    use_default_homes = project_skill_home is None and global_skill_home is None and claude_skill_home is None
    if project_skill_home is None:
        project_skill_home = target_dir.parent / ".codex" / "skills"
    if global_skill_home is None:
        global_skill_home = Path.home() / ".codex" / "skills"
    if claude_skill_home is None and use_default_homes:
        claude_skill_home = Path.home() / ".claude" / "skills"

    seen: set[str] = set()
    for skill_home in (project_skill_home, global_skill_home, claude_skill_home):
        if skill_home is None:
            continue
        destination = (skill_home / SKILL_NAME).resolve()
        normalized = str(destination).lower()
        if normalized in seen:
            continue
        seen.add(normalized)
        _replace_tree(source_skill, destination)
        destinations.append(destination)
    return [str(path) for path in destinations]


def apply_bundle_update(*, target_dir: Path, archive_bytes: bytes) -> None:
    target_dir.mkdir(parents=True, exist_ok=True)
    with TemporaryDirectory(prefix="acp-agent-update-") as temp_dir_value:
        temp_dir = Path(temp_dir_value)
        with zipfile.ZipFile(BytesIO(archive_bytes)) as archive:
            archive.extractall(temp_dir)

        extracted_items = list(temp_dir.iterdir())
        if not extracted_items:
            raise ValueError("release archive is empty")

        for legacy_name in LEGACY_REMOVE:
            _remove_path(target_dir / legacy_name)

        for existing in list(target_dir.iterdir()):
            if existing.name in PRESERVE_NAMES:
                continue
            _remove_path(existing)

        for extracted in extracted_items:
            if extracted.name in PRESERVE_NAMES:
                continue
            _copy_tree(extracted, target_dir / extracted.name)


def check_for_update(*, target_dir: Path, manifest_url: str) -> dict[str, Any]:
    manifest = fetch_json(manifest_url)
    remote_version = str(manifest.get("version") or "").strip() or None
    bundle_url_value = str(manifest.get("bundle_url") or "").strip() or None
    if remote_version is None:
        raise ValueError("release manifest is missing version")
    if bundle_url_value is None:
        raise ValueError("release manifest is missing bundle_url")
    bundle_url = urllib.parse.urljoin(manifest_url, bundle_url_value)
    current_version = local_version(target_dir)
    policy_status = resolve_policy_status(local_version_value=current_version, manifest=manifest)
    safety = auto_update_safety(target_dir=target_dir)
    return {
        "status": "current" if current_version == remote_version else "update_available",
        "local_version": current_version,
        "remote_version": remote_version,
        "bundle_url": bundle_url,
        "policy_status": policy_status,
        "update_required": policy_status == "required",
        "update_recommended": policy_status in {"required", "recommended"},
        "auto_update": {
            "safe": safety["safe"],
            "reason": safety["reason"],
            "policy": manifest.get("agent_update", {}),
            "command": "python ACP_AGENT/update_from_release.py --auto-when-idle",
        },
        "manifest": manifest,
    }


def update_from_manifest(
    *,
    target_dir: Path,
    manifest_url: str,
    force: bool,
    auto_when_idle: bool = False,
    allow_tracked_repo: bool = False,
    project_skill_home: Path | None = None,
    global_skill_home: Path | None = None,
    claude_skill_home: Path | None = None,
) -> dict[str, Any]:
    comparison = check_for_update(target_dir=target_dir, manifest_url=manifest_url)
    manifest = dict(comparison["manifest"])
    manifest.setdefault("manifest_url", manifest_url)
    if comparison["status"] == "current" and not force:
        return {
            "status": "current",
            "local_version": comparison["local_version"],
            "remote_version": comparison["remote_version"],
            "bundle_url": comparison["bundle_url"],
        }

    if auto_when_idle:
        safety = auto_update_safety(target_dir=target_dir, allow_tracked_repo=allow_tracked_repo)
        if not safety["safe"]:
            return {
                "status": "update_blocked",
                "local_version": comparison["local_version"],
                "remote_version": comparison["remote_version"],
                "bundle_url": comparison["bundle_url"],
                "safety": safety,
            }

    bundle_url = str(comparison["bundle_url"])
    archive_bytes = fetch_bytes(bundle_url)
    expected_sha256 = str(manifest.get("sha256") or "").strip()
    archive_sha256 = _sha256_bytes(archive_bytes)
    if expected_sha256 and archive_sha256 != expected_sha256:
        raise ValueError("release archive sha256 does not match the manifest")

    apply_bundle_update(target_dir=target_dir, archive_bytes=archive_bytes)
    updated_skills = sync_skill_installs(
        target_dir=target_dir,
        project_skill_home=project_skill_home,
        global_skill_home=global_skill_home,
        claude_skill_home=claude_skill_home,
    )
    bundle_info = write_bundle_info(target_dir=target_dir, manifest=manifest, source="update_from_release")
    updated_version = local_version(target_dir)
    return {
        "status": "updated",
        "local_version": comparison["local_version"],
        "remote_version": comparison["remote_version"],
        "updated_version": updated_version,
        "bundle_info": bundle_info,
        "bundle_url": bundle_url,
        "sha256": archive_sha256,
        "preserved": sorted(PRESERVE_NAMES - {"__pycache__"}),
        "updated_skills": updated_skills,
    }


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    target_dir = Path(args.target).expanduser().resolve()
    if not isinstance(args.manifest_url, str) or not args.manifest_url.strip():
        raise SystemExit("A release manifest URL is required. Pass --manifest-url explicitly for this distribution.")
    if args.check:
        print(json.dumps(check_for_update(target_dir=target_dir, manifest_url=args.manifest_url), ensure_ascii=True))
        return 0
    print(
        json.dumps(
            update_from_manifest(
                target_dir=target_dir,
                manifest_url=args.manifest_url,
                force=bool(args.force),
                auto_when_idle=bool(args.auto_when_idle),
                allow_tracked_repo=bool(args.allow_tracked_repo),
            ),
            ensure_ascii=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
