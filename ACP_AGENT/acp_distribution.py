"""Distribution metadata loader for ACP_AGENT bundle flavors."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any


_DEFAULT_DISTRIBUTION_FILE = "DISTRIBUTION.json"


@dataclass(frozen=True)
class AgentDistribution:
    distribution_id: str
    product_name: str
    default_hub_mode: str
    default_hub_label: str
    default_hub_http: str | None
    default_hub_ws: str | None
    default_manifest_url: str | None

    @property
    def has_default_hub(self) -> bool:
        return bool(self.default_hub_http and self.default_hub_ws)


def _clean_optional_string(value: Any, *, strip_trailing_slash: bool = False) -> str | None:
    if not isinstance(value, str):
        return None
    cleaned = value.strip()
    if not cleaned:
        return None
    if strip_trailing_slash:
        cleaned = cleaned.rstrip("/")
    return cleaned or None


def _default_distribution() -> AgentDistribution:
    return AgentDistribution(
        distribution_id="acp-community",
        product_name="ACP",
        default_hub_mode="explicit",
        default_hub_label="default ACP hub",
        default_hub_http=None,
        default_hub_ws=None,
        default_manifest_url=None,
    )


def load_distribution(base_dir: Path | None = None) -> AgentDistribution:
    source_dir = (base_dir or Path(__file__).resolve().parent).resolve()
    payload = _default_distribution()
    distribution_path = source_dir / _DEFAULT_DISTRIBUTION_FILE
    if not distribution_path.is_file():
        return payload

    parsed = json.loads(distribution_path.read_text(encoding="utf-8"))
    if not isinstance(parsed, dict):
        return payload

    distribution_id = _clean_optional_string(parsed.get("distribution_id")) or payload.distribution_id
    product_name = _clean_optional_string(parsed.get("product_name")) or payload.product_name
    default_hub_mode = _clean_optional_string(parsed.get("default_hub_mode")) or payload.default_hub_mode
    if default_hub_mode not in {"official", "explicit"}:
        default_hub_mode = payload.default_hub_mode
    default_hub_label = _clean_optional_string(parsed.get("default_hub_label")) or payload.default_hub_label
    default_hub_http = _clean_optional_string(parsed.get("default_hub_http"), strip_trailing_slash=True)
    default_hub_ws = _clean_optional_string(parsed.get("default_hub_ws"))
    default_manifest_url = _clean_optional_string(parsed.get("default_manifest_url"))

    if default_hub_mode == "official":
        default_hub_http = default_hub_http or payload.default_hub_http
        default_hub_ws = default_hub_ws or payload.default_hub_ws

    return AgentDistribution(
        distribution_id=distribution_id,
        product_name=product_name,
        default_hub_mode=default_hub_mode,
        default_hub_label=default_hub_label,
        default_hub_http=default_hub_http,
        default_hub_ws=default_hub_ws,
        default_manifest_url=default_manifest_url,
    )
