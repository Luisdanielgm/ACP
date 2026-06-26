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

# apps/hub — the directory that contains src/. Keep this anchored to the package
# location so it does not depend on the process working directory.
_HUB_DIR = Path(__file__).resolve().parents[3]

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
    return HTMLResponse(content=content)


def _register_managed_vue_spa(app: FastAPI) -> None:
    """Mount managed Vue SPA assets."""
    managed_static_dir = _managed_static_dir()
    if managed_static_dir is None:
        return
    assets_dir = managed_static_dir / "assets"
    if assets_dir.is_dir():
        app.mount("/managed/assets", StaticFiles(directory=str(assets_dir)), name="managed-assets")
