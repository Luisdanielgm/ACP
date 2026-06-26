"""Public hub branding and endpoint defaults."""

from __future__ import annotations

import os
import urllib.parse
from dataclasses import dataclass


def _clean_env(name: str) -> str | None:
    value = os.getenv(name)
    if not isinstance(value, str):
        return None
    cleaned = value.strip()
    return cleaned or None


def _origin_from_base_url(base_url: str | None) -> str | None:
    if not isinstance(base_url, str) or not base_url.strip():
        return None
    try:
        parsed = urllib.parse.urlparse(base_url)
    except ValueError:
        return None
    if not parsed.scheme or not parsed.netloc:
        return None
    return f"{parsed.scheme}://{parsed.netloc}"


def _ws_from_http_origin(http_origin: str | None) -> str | None:
    if not isinstance(http_origin, str) or not http_origin.strip():
        return None
    try:
        parsed = urllib.parse.urlparse(http_origin)
    except ValueError:
        return None
    if not parsed.scheme or not parsed.netloc:
        return None
    ws_scheme = "wss" if parsed.scheme == "https" else "ws"
    return urllib.parse.urlunparse((ws_scheme, parsed.netloc, "/ws", "", "", ""))


@dataclass(frozen=True)
class HubBranding:
    brand_name: str
    official_hub_http: str | None
    official_hub_ws: str | None


def load_hub_branding(*, base_url: str | None = None) -> HubBranding:
    brand_name = _clean_env("ACP_PUBLIC_BRAND_NAME") or "ACP Hub"
    official_hub_http = _clean_env("ACP_PUBLIC_HUB_HTTP") or _origin_from_base_url(base_url)
    official_hub_ws = _clean_env("ACP_PUBLIC_HUB_WS") or _ws_from_http_origin(official_hub_http)
    return HubBranding(
        brand_name=brand_name,
        official_hub_http=official_hub_http,
        official_hub_ws=official_hub_ws,
    )
