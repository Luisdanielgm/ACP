"""--agent-token / --join-code accept env, file and stdin sources (ACP_AGENT)."""

from __future__ import annotations

import importlib.util
import io
import sys
from pathlib import Path
from typing import Any

import pytest

repo_root = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(repo_root / "ACP_AGENT"))
_SPEC = importlib.util.spec_from_file_location("acp_agent_secret_sources", repo_root / "ACP_AGENT" / "acp.py")
assert _SPEC is not None and _SPEC.loader is not None
acp = importlib.util.module_from_spec(_SPEC)
sys.modules[_SPEC.name] = acp
_SPEC.loader.exec_module(acp)

TOKEN = "workspaceTOKENsecret1234567890"
CODE = "A1B2C3D4"


def _parse(*argv: str):
    parser = acp.build_parser()
    args = parser.parse_args(list(argv))
    acp.resolve_secret_sources(args)
    return args


@pytest.mark.parametrize(
    "command",
    [
        ["managed-join", "--session-id", "s1"],
        ["managed-start"],
        ["managed-sessions"],
        ["coordinate"],
        ["connect"],
        ["onboard"],
        ["verify-approval", "--approval-id", "a1"],
    ],
)
def test_agent_token_from_env_file_and_stdin(command: list[str], tmp_path: Path, monkeypatch: Any) -> None:
    monkeypatch.setenv("ACP_TEST_TOKEN", f"  {TOKEN}\n")
    assert _parse(*command, "--agent-token-env", "ACP_TEST_TOKEN").agent_token == TOKEN

    token_file = tmp_path / "token.txt"
    token_file.write_text(f"{TOKEN}\n", encoding="utf-8")
    assert _parse(*command, "--agent-token-file", str(token_file)).agent_token == TOKEN

    monkeypatch.setattr(sys, "stdin", io.StringIO(f"{TOKEN}\n"))
    assert _parse(*command, "--agent-token-stdin").agent_token == TOKEN

    monkeypatch.setattr(sys, "stdin", io.StringIO(f"{TOKEN}\n"))
    assert _parse(*command, "--agent-token", "-").agent_token == TOKEN


def test_agent_token_sources_are_mutually_exclusive_and_errors_hide_the_value(monkeypatch: Any) -> None:
    monkeypatch.setenv("ACP_TEST_TOKEN", TOKEN)
    with pytest.raises(ValueError, match="choose only one agent token source") as excinfo:
        _parse("managed-sessions", "--agent-token", TOKEN, "--agent-token-env", "ACP_TEST_TOKEN")
    assert TOKEN not in str(excinfo.value)


def test_agent_token_env_errors(monkeypatch: Any) -> None:
    monkeypatch.delenv("ACP_MISSING", raising=False)
    with pytest.raises(ValueError, match="ACP_MISSING is not set"):
        _parse("managed-sessions", "--agent-token-env", "ACP_MISSING")
    with pytest.raises(ValueError, match="environment variable name"):
        _parse("managed-sessions", "--agent-token-env", "not a name")
    with pytest.raises(ValueError, match="could not read"):
        _parse("managed-sessions", "--agent-token-file", "/nonexistent/token.txt")


def test_plain_agent_token_still_works_and_absent_sources_change_nothing() -> None:
    assert _parse("managed-sessions", "--agent-token", TOKEN).agent_token == TOKEN
    assert _parse("managed-sessions").agent_token is None


def test_runner_join_code_from_env_file_and_stdin(tmp_path: Path, monkeypatch: Any) -> None:
    monkeypatch.setenv("ACP_TEST_CODE", f"{CODE}\n")
    for sub in ("start", "once"):
        assert _parse("runner", sub, "--join-code-env", "ACP_TEST_CODE").join_code == CODE

    code_file = tmp_path / "code.txt"
    code_file.write_text(CODE, encoding="utf-8")
    assert _parse("runner", "start", "--join-code-file", str(code_file)).join_code == CODE

    monkeypatch.setattr(sys, "stdin", io.StringIO(f"{CODE}\n"))
    assert _parse("runner", "start", "--join-code-stdin").join_code == CODE


def test_runner_join_code_from_env_is_format_checked_without_echoing_it(monkeypatch: Any) -> None:
    monkeypatch.setenv("ACP_TEST_CODE", '"A1B2C3D4"')
    with pytest.raises(ValueError, match="malformed") as excinfo:
        _parse("runner", "start", "--join-code-env", "ACP_TEST_CODE")
    assert "A1B2C3D4" not in str(excinfo.value)


def test_only_one_secret_may_use_stdin(monkeypatch: Any) -> None:
    monkeypatch.setattr(sys, "stdin", io.StringIO(f"{CODE}\n"))
    with pytest.raises(ValueError, match="only one secret"):
        # No shipped command takes both today; exercise the guard directly.
        import argparse

        acp.resolve_secret_sources(
            argparse.Namespace(
                agent_token=None, agent_token_env=None, agent_token_file=None, agent_token_stdin=True,
                join_code=None, join_code_env=None, join_code_file=None, join_code_stdin=True,
            )
        )
