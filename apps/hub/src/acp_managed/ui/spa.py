"""Managed Vue SPA / static-asset serving.

Extracted from acp_managed/app.py (de-tangle slice 1). Behavior-preserving:
the static-dir candidates resolve to the same `apps/hub` base as before. This
file lives one directory deeper than the old app.py, so it uses parents[3]
(spa.py -> ui -> acp_managed -> src -> hub) where app.py used parent.parent.parent.
"""

from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from starlette.types import Scope

# apps/hub — the directory that contains src/. Keep this anchored to the package
# location so it does not depend on the process working directory.
_HUB_DIR = Path(__file__).resolve().parents[3]

# Hashed Vite chunks are content-addressed: the filename changes when the bytes
# change, so they are safe to cache forever. Serving them immutably stops the
# browser (and Cloudflare) from revalidating on every load.
_IMMUTABLE_CACHE_CONTROL = "public, max-age=31536000, immutable"
# index.html is the pointer to the current hashed chunks. It must always be
# revalidated so a redeploy (which wipes old chunks via emptyOutDir) is picked
# up immediately instead of serving a stale shell that 404s on gone chunks.
_NO_CACHE_CONTROL = "no-cache"


class _ImmutableStaticFiles(StaticFiles):
    """StaticFiles that tags successful responses as immutable, cache-forever."""

    async def get_response(self, path: str, scope: Scope):
        response = await super().get_response(path, scope)
        if response.status_code == 200:
            response.headers["Cache-Control"] = _IMMUTABLE_CACHE_CONTROL
        return response

_MANAGED_STATIC_DIR_CANDIDATES = (
    _HUB_DIR / "static" / "managed",
    _HUB_DIR / "frontend" / "packages" / "managed-app" / "dist",
)


def _managed_static_dir() -> Path | None:
    for candidate in (*_MANAGED_STATIC_DIR_CANDIDATES, Path.cwd() / "static" / "managed"):
        if (candidate / "index.html").is_file():
            return candidate
    return None


def _managed_spa_index() -> str | None:
    managed_static_dir = _managed_static_dir()
    if managed_static_dir is None:
        return None
    index_html = managed_static_dir / "index.html"
    if index_html.is_file():
        return index_html.read_text(encoding="utf-8")
    return None


def _managed_spa_response() -> HTMLResponse:
    content = _managed_spa_index()
    if content is None:
        raise HTTPException(status_code=503, detail="managed frontend not built")
    return HTMLResponse(content=content, headers={"Cache-Control": _NO_CACHE_CONTROL})


def _register_managed_vue_spa(app: FastAPI) -> None:
    """Mount managed Vue SPA assets."""
    managed_static_dir = _managed_static_dir()
    if managed_static_dir is None:
        return
    assets_dir = managed_static_dir / "assets"
    if assets_dir.is_dir():
        app.mount(
            "/managed/assets",
            _ImmutableStaticFiles(directory=str(assets_dir)),
            name="managed-assets",
        )
