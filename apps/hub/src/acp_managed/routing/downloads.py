"""Bundle download routes (ACP_AGENT manifest/zip/docs) — de-tangle slice 2a.

These routes serve the public ACP_AGENT distribution artifacts. They are
anonymous (no auth), so they take the deps bundle only to keep a uniform
build_*_router(deps) factory signature.

The bundle symbols (``ensure_bundle_archive``, ``ACP_AGENT_SOURCE_DIR``) are
imported at this module's level so they resolve as module globals at request
time — tests monkeypatch them on ``acp_managed.routing.downloads``.
"""

from __future__ import annotations

from pathlib import Path
from zipfile import BadZipFile, ZipFile

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import FileResponse, JSONResponse, Response

from acp.hub.bundle_archive import ACP_AGENT_SOURCE_DIR, ensure_bundle_archive
from acp.hub.bundle_release import build_bundle_release_manifest

from acp_managed.routing import ManagedRouterDeps


def build_downloads_router(deps: ManagedRouterDeps) -> APIRouter:
    router = APIRouter()

    @router.get("/downloads/ACP_AGENT.json")
    async def managed_download_manifest(request: Request) -> JSONResponse:
        return JSONResponse(content=build_bundle_release_manifest(base_url=str(request.base_url)))

    @router.get("/downloads/ACP_AGENT.zip")
    async def managed_download_bundle() -> FileResponse:
        bundle_path = ensure_bundle_archive()
        if not bundle_path.is_file():
            raise HTTPException(status_code=404, detail="ACP_AGENT.zip is not available.")
        return FileResponse(
            path=bundle_path,
            media_type="application/zip",
            filename="ACP_AGENT.zip",
        )

    @router.get("/downloads/ACP_AGENT/AGENT.md")
    async def managed_download_agent_guide() -> Response:
        guide_path = ACP_AGENT_SOURCE_DIR / "AGENT.md"
        return _agent_markdown_download(
            source_path=guide_path,
            archive_member="AGENT.md",
            filename="AGENT.md",
            missing_detail="ACP_AGENT/AGENT.md is not available.",
        )

    @router.get("/downloads/ACP_AGENT/skills/acp-session-coordinator/SKILL.md")
    async def managed_download_agent_skill() -> Response:
        skill_path = ACP_AGENT_SOURCE_DIR / "skills" / "acp-session-coordinator" / "SKILL.md"
        return _agent_markdown_download(
            source_path=skill_path,
            archive_member="skills/acp-session-coordinator/SKILL.md",
            filename="SKILL.md",
            missing_detail="ACP_AGENT/skills/acp-session-coordinator/SKILL.md is not available.",
        )

    return router


def _agent_markdown_download(
    *,
    source_path: Path,
    archive_member: str,
    filename: str,
    missing_detail: str,
) -> Response:
    if source_path.is_file():
        return FileResponse(
            path=source_path,
            media_type="text/markdown; charset=utf-8",
            filename=filename,
        )

    bundle_path = ensure_bundle_archive()
    if bundle_path.is_file():
        try:
            with ZipFile(bundle_path) as archive:
                content = archive.read(archive_member).decode("utf-8")
        except (BadZipFile, KeyError, OSError, UnicodeDecodeError):
            content = ""
        if content:
            return Response(
                content=content,
                media_type="text/markdown; charset=utf-8",
                headers={"content-disposition": f'attachment; filename="{filename}"'},
            )

    raise HTTPException(status_code=404, detail=missing_detail)
