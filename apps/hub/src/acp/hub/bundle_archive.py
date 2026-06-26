"""Utilities to keep the distributable ACP bundle synchronized."""

from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
from tempfile import NamedTemporaryFile
from zipfile import BadZipFile, ZIP_DEFLATED, ZipFile

_MODULE_PATH = Path(__file__).resolve()
_FINGERPRINT_COMMENT_PREFIX = b"ACP_AGENT_FINGERPRINT:"


def _discover_source_dir() -> Path:
    configured = os.getenv("ACP_AGENT_SOURCE_DIR")
    if isinstance(configured, str) and configured.strip():
        return Path(configured).expanduser().resolve()

    for parent in _MODULE_PATH.parents:
        candidate = parent / "ACP_AGENT"
        if (candidate / "acp.py").is_file():
            return candidate

    cwd_candidate = Path.cwd() / "ACP_AGENT"
    if (cwd_candidate / "acp.py").is_file():
        return cwd_candidate.resolve()

    return (Path.cwd() / "ACP_AGENT").resolve()


def _discover_downloads_dir() -> Path:
    configured = os.getenv("ACP_DOWNLOADS_DIR")
    if isinstance(configured, str) and configured.strip():
        return Path(configured).expanduser().resolve()

    cwd_candidate = Path.cwd() / "downloads"
    if cwd_candidate.exists():
        return cwd_candidate.resolve()

    for parent in _MODULE_PATH.parents:
        candidate = parent / "downloads"
        if candidate.exists():
            return candidate

    parent_chain = _MODULE_PATH.parents
    if len(parent_chain) > 3:
        return parent_chain[3] / "downloads"
    return (Path.cwd() / "downloads").resolve()


ACP_AGENT_SOURCE_DIR = _discover_source_dir()
ACP_DOWNLOADS_DIR = _discover_downloads_dir()
ACP_AGENT_BUNDLE_PATH = ACP_DOWNLOADS_DIR / "ACP_AGENT.zip"


def _iter_source_files(source_dir: Path) -> list[Path]:
    return sorted(
        path
        for path in source_dir.rglob("*")
        if path.is_file() and "__pycache__" not in path.parts
    )


def _latest_source_mtime_ns(source_dir: Path) -> int:
    files = _iter_source_files(source_dir)
    if not files:
        return 0
    return max(path.stat().st_mtime_ns for path in files)


def _source_fingerprint(source_dir: Path, files: list[Path] | None = None) -> str:
    digest = hashlib.sha256()
    for file_path in files or _iter_source_files(source_dir):
        relative_path = file_path.relative_to(source_dir).as_posix()
        file_stat = file_path.stat()
        digest.update(relative_path.encode("utf-8"))
        digest.update(b"\0")
        digest.update(str(file_stat.st_size).encode("ascii"))
        digest.update(b"\0")
        with file_path.open("rb") as handle:
            for chunk in iter(lambda: handle.read(1024 * 1024), b""):
                digest.update(chunk)
        digest.update(b"\0")
    return digest.hexdigest()


def _fingerprint_comment(fingerprint: str) -> bytes:
    payload = json.dumps({"version": 1, "fingerprint": fingerprint}, sort_keys=True).encode("utf-8")
    return _FINGERPRINT_COMMENT_PREFIX + payload


def _archive_fingerprint(bundle_path: Path) -> str | None:
    try:
        with ZipFile(bundle_path) as archive:
            comment = archive.comment
    except (BadZipFile, OSError):
        return None

    if not comment.startswith(_FINGERPRINT_COMMENT_PREFIX):
        return None
    raw_payload = comment[len(_FINGERPRINT_COMMENT_PREFIX) :]
    try:
        payload = json.loads(raw_payload.decode("utf-8"))
    except (json.JSONDecodeError, UnicodeDecodeError):
        return None
    fingerprint = payload.get("fingerprint")
    return fingerprint if isinstance(fingerprint, str) and fingerprint else None


def bundle_is_stale(
    *,
    source_dir: Path = ACP_AGENT_SOURCE_DIR,
    bundle_path: Path = ACP_AGENT_BUNDLE_PATH,
) -> bool:
    if not source_dir.is_dir():
        return False
    if not bundle_path.is_file():
        return True
    archive_fingerprint = _archive_fingerprint(bundle_path)
    if archive_fingerprint is None:
        return True
    return _source_fingerprint(source_dir) != archive_fingerprint


def build_bundle_archive(
    *,
    source_dir: Path = ACP_AGENT_SOURCE_DIR,
    bundle_path: Path = ACP_AGENT_BUNDLE_PATH,
) -> Path:
    if not source_dir.is_dir():
        raise FileNotFoundError(f"ACP agent source directory is missing: {source_dir}")

    bundle_path.parent.mkdir(parents=True, exist_ok=True)
    files = _iter_source_files(source_dir)
    if not files:
        raise FileNotFoundError(f"ACP agent source directory has no files: {source_dir}")
    latest_source_mtime_ns = max(path.stat().st_mtime_ns for path in files)
    fingerprint = _source_fingerprint(source_dir, files)

    with NamedTemporaryFile(delete=False, suffix=".zip", dir=bundle_path.parent) as temp_file:
        temp_path = Path(temp_file.name)

    try:
        with ZipFile(temp_path, mode="w", compression=ZIP_DEFLATED) as archive:
            for file_path in files:
                archive.write(file_path, arcname=file_path.relative_to(source_dir))
            archive.comment = _fingerprint_comment(fingerprint)
        temp_path.replace(bundle_path)
        os.utime(bundle_path, ns=(latest_source_mtime_ns, latest_source_mtime_ns))
    finally:
        if temp_path.exists():
            temp_path.unlink()

    return bundle_path


def ensure_bundle_archive(
    *,
    source_dir: Path = ACP_AGENT_SOURCE_DIR,
    bundle_path: Path = ACP_AGENT_BUNDLE_PATH,
) -> Path:
    if source_dir.is_dir() and bundle_is_stale(source_dir=source_dir, bundle_path=bundle_path):
        return build_bundle_archive(source_dir=source_dir, bundle_path=bundle_path)
    return bundle_path
