from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI
from fastapi.testclient import TestClient

from acp.hub.app import _ImmutableStaticFiles, _register_spa_route


def test_public_spa_shell_revalidates(tmp_path: Path) -> None:
    # The SPA shell must revalidate so a redeploy is picked up instead of
    # 404ing on chunks emptyOutDir already wiped.
    index_html = tmp_path / "index.html"
    index_html.write_text(
        "<!doctype html><html><body><div id='app'>public shell</div></body></html>",
        encoding="utf-8",
    )

    app = FastAPI()
    _register_spa_route(app, "/dashboard", index_html)

    with TestClient(app) as client:
        shell = client.get("/dashboard")
        assert shell.status_code == 200
        assert "public shell" in shell.text
        assert "no-cache" in shell.headers.get("cache-control", "")


def test_public_hashed_assets_cache_immutably(tmp_path: Path) -> None:
    assets_dir = tmp_path / "assets"
    assets_dir.mkdir()
    (assets_dir / "app.js").write_text("console.log('public shell');", encoding="utf-8")

    app = FastAPI()
    app.mount("/assets", _ImmutableStaticFiles(directory=str(assets_dir)), name="public-assets")

    with TestClient(app) as client:
        asset = client.get("/assets/app.js")
        assert asset.status_code == 200
        cache_control = asset.headers.get("cache-control", "")
        assert "immutable" in cache_control
        assert "max-age=31536000" in cache_control
