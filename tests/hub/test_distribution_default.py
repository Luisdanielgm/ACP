from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

repo_root = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(repo_root / "ACP_AGENT"))
_SPEC = importlib.util.spec_from_file_location(
    "acp_distribution_under_test", repo_root / "ACP_AGENT" / "acp_distribution.py"
)
assert _SPEC is not None and _SPEC.loader is not None
acp_distribution = importlib.util.module_from_spec(_SPEC)
sys.modules[_SPEC.name] = acp_distribution
_SPEC.loader.exec_module(acp_distribution)
from host_bridge import default_registry  # noqa: E402


def test_default_distribution_id_is_acp_community(tmp_path: Path) -> None:
    # X-LEGACY-07: the fallback distribution_id must not be the legacy placeholder.
    # tmp_path has no DISTRIBUTION.json, so load_distribution returns the built-in
    # default, which must already read as the community flavor.
    distribution = acp_distribution.load_distribution(base_dir=tmp_path)
    assert distribution.distribution_id == "acp-community"


def test_distribution_declares_all_host_bridge_adapters_and_capabilities() -> None:
    distribution = acp_distribution.load_distribution(base_dir=repo_root / "ACP_AGENT")
    declarations = {item.adapter_id: set(item.capabilities) for item in distribution.host_adapters}

    assert set(declarations) == {
        "opencode_server",
        "kilo_serve",
        "codex_app_server",
        "codex_app_server_stdio",
        "codex_cli",
        "claude_code_cli",
        "claude_desktop",
    }
    assert {"existing-session", "http-delivery"} <= declarations["opencode_server"]
    assert {"existing-session", "directory-context"} <= declarations["kilo_serve"]
    assert {"existing-session", "websocket-delivery", "cancellation", "endpoint-serialized"} <= declarations["codex_app_server"]
    assert {"existing-session", "stdio-delivery", "spawn-on-task", "cancellation"} <= declarations["codex_app_server_stdio"]
    assert {"existing-session", "cli-resume", "fail-closed-retry"} <= declarations["codex_cli"]
    assert {"existing-session", "cli-resume", "fail-closed-retry"} <= declarations["claude_code_cli"]
    assert declarations["claude_desktop"] == {"unsupported-pending-official-interface"}
    registered = {manifest.adapter_id: set(manifest.capabilities) for manifest in default_registry().manifests()}
    assert registered == declarations
