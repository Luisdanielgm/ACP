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


def test_default_distribution_id_is_acp_community(tmp_path: Path) -> None:
    # X-LEGACY-07: the fallback distribution_id must not be the legacy placeholder.
    # tmp_path has no DISTRIBUTION.json, so load_distribution returns the built-in
    # default, which must already read as the community flavor.
    distribution = acp_distribution.load_distribution(base_dir=tmp_path)
    assert distribution.distribution_id == "acp-community"
