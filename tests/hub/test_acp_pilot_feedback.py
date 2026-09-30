"""Client-side behavior added from the pilot feedback report (ACP_AGENT)."""

from __future__ import annotations

import argparse
import importlib.util
import io
import json
import os
import re
import sys
import urllib.error
from pathlib import Path
from typing import Any

import pytest

repo_root = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(repo_root / "ACP_AGENT"))
_SPEC = importlib.util.spec_from_file_location("acp_agent_pilot_feedback", repo_root / "ACP_AGENT" / "acp.py")
assert _SPEC is not None and _SPEC.loader is not None
acp = importlib.util.module_from_spec(_SPEC)
sys.modules[_SPEC.name] = acp
_SPEC.loader.exec_module(acp)

CODE = "A1B2C3D4"
MEMBER_TOKEN = "membertokenSECRET1234567890"


def _ns(**kwargs: Any) -> argparse.Namespace:
    defaults: dict[str, Any] = {"code": None, "code_env": None, "code_file": None, "code_stdin": False}
    defaults.update(kwargs)
    return argparse.Namespace(**defaults)


# --- B5 / D13: join code sources and pre-validation -------------------------------------------


def test_join_code_from_env_file_stdin_and_dash(tmp_path: Path, monkeypatch: Any) -> None:
    monkeypatch.setenv("ACP_TEST_CODE", f"  {CODE}\n")
    assert acp.resolve_join_code_from_args(_ns(code_env="ACP_TEST_CODE")) == CODE

    code_file = tmp_path / "code.txt"
    code_file.write_text(f"{CODE}\n", encoding="utf-8")
    assert acp.resolve_join_code_from_args(_ns(code_file=str(code_file))) == CODE

    monkeypatch.setattr(sys, "stdin", io.StringIO(f"{CODE}\n"))
    assert acp.resolve_join_code_from_args(_ns(code_stdin=True)) == CODE
    monkeypatch.setattr(sys, "stdin", io.StringIO(f"{CODE}\n"))
    assert acp.resolve_join_code_from_args(_ns(code="-")) == CODE
    monkeypatch.setattr(sys, "stdin", io.StringIO(f"{CODE}\n"))
    assert acp.resolve_join_code_from_args(_ns(code_file="-")) == CODE
    assert acp.resolve_join_code_from_args(_ns(code=CODE)) == CODE


def test_join_code_sources_are_mutually_exclusive_and_required(monkeypatch: Any) -> None:
    monkeypatch.setenv("ACP_TEST_CODE", CODE)
    with pytest.raises(ValueError, match="only one join code source"):
        acp.resolve_join_code_from_args(_ns(code=CODE, code_env="ACP_TEST_CODE"))
    with pytest.raises(ValueError, match="only one join code source"):
        acp.resolve_join_code_from_args(_ns(code_env="ACP_TEST_CODE", code_stdin=True))
    with pytest.raises(ValueError, match="join code is required"):
        acp.resolve_join_code_from_args(_ns())
    monkeypatch.delenv("ACP_TEST_CODE")
    with pytest.raises(ValueError, match="ACP_TEST_CODE is not set"):
        acp.resolve_join_code_from_args(_ns(code_env="ACP_TEST_CODE"))
    with pytest.raises(ValueError, match="could not read --code-file"):
        acp.resolve_join_code_from_args(_ns(code_file="/nonexistent/acp-code"))


def test_join_code_format_errors_report_counts_and_never_the_code() -> None:
    secret = "Z9Y8X7W6V5"
    cases = {
        f'"{CODE}"': ["1 leading quote character", "1 trailing quote character"],
        f" {CODE} ": ["2 leading/trailing whitespace characters"],
        f"{CODE}AB": ["length is 10 but join codes have 8 characters"],
        secret: ["length is 10", "outside 0-9 and A-F"],
        "": ["the code is empty"],
    }
    for raw, expected in cases.items():
        with pytest.raises(ValueError) as excinfo:
            acp.validate_join_code_format(raw)
        message = str(excinfo.value)
        for fragment in expected:
            assert fragment in message, (raw, message)
        if raw:
            assert raw.strip("\"' ") not in message
    assert acp.validate_join_code_format(CODE.lower()) == CODE.lower()


def test_join_session_rejects_quoted_code_before_calling_the_hub(tmp_path: Path, monkeypatch: Any) -> None:
    calls: list[str] = []
    monkeypatch.setattr(acp, "post_json", lambda **kwargs: calls.append(kwargs["route"]) or {})
    args = acp.build_parser().parse_args(
        ["join-session", "--config", str(tmp_path / "w.json"), "--agent", "w", "--hub-http", "https://hub.example", "--code", f"'{CODE}'"]
    )
    with pytest.raises(ValueError, match="1 leading quote character"):
        acp.join_session_from_args(args)
    assert calls == []


def test_join_session_uses_code_env_and_shows_hub_reason(tmp_path: Path, monkeypatch: Any) -> None:
    monkeypatch.setenv("ACP_TEST_CODE", CODE)
    sent: list[dict[str, Any]] = []

    def fake_post_json(*, hub_http: str, route: str, payload: dict[str, Any], token: str | None = None, **_: Any) -> dict[str, Any]:
        if route == "/sessions/join":
            sent.append(payload)
            body = json.dumps(
                {
                    "error": {"code": "INVALID_FIELD", "message": "join code is invalid: the session was closed. Ask for a new invitation."},
                    "reason": "session_closed",
                }
            )
            raise ValueError(f"hub HTTP 409: {body}")
        return {"status": "ok"}

    monkeypatch.setattr(acp, "post_json", fake_post_json)
    args = acp.build_parser().parse_args(
        ["join-session", "--config", str(tmp_path / "w.json"), "--agent", "w", "--hub-http", "https://hub.example", "--code-env", "ACP_TEST_CODE"]
    )
    with pytest.raises(ValueError) as excinfo:
        acp.join_session_from_args(args)
    assert sent[0]["join_code"] == CODE
    message = str(excinfo.value)
    assert "reason: session_closed" in message
    assert "the session was closed" in message
    assert CODE not in message


def test_explain_join_rejection_handles_legacy_and_format_messages() -> None:
    legacy = acp.explain_join_rejection(ValueError('hub HTTP 409: {"detail":"join code is invalid"}'))
    assert legacy is not None and "join code is invalid" in str(legacy) and "unspecified" in str(legacy)
    body = json.dumps(
        {"error": {"message": "join code is invalid: expected 8 characters (0-9, A-F), got 10."}, "reason": "invalid_format"}
    )
    fmt = acp.explain_join_rejection(ValueError(f"hub HTTP 409: {body}"))
    assert fmt is not None and "expected 8 characters" in str(fmt) and "invalid_format" in str(fmt)
    assert acp.explain_join_rejection(ValueError("hub HTTP 500: boom")) is None


# --- B6: masking --------------------------------------------------------------------------


def _session_payload() -> dict[str, Any]:
    return {
        "session_id": "s-1",
        "member_token": MEMBER_TOKEN,
        "join_code": CODE,
        "managed_agent_token": "agenttokenSECRET999",
        "session_dashboard_url": f"https://hub.example/dashboard/session?session_id=s-1#member_token={MEMBER_TOKEN}",
        "shareable_session_access": {"join_code": CODE, "note": f"code {CODE}"},
    }


def test_mask_session_output_masks_tokens_codes_and_url_fragments() -> None:
    masked = acp.mask_session_output(_session_payload(), mask_join_code=True)
    text = json.dumps(masked)
    assert MEMBER_TOKEN not in text and CODE not in text and "agenttokenSECRET999" not in text
    assert masked["member_token"] == "memb****"
    assert masked["join_code"] == "A1B2****"
    assert masked["session_dashboard_url"].endswith("#member_token=memb****")
    assert masked["session_id"] == "s-1"
    assert masked["secrets_masked"] is True


def test_mask_session_output_can_keep_join_code_for_sharing() -> None:
    masked = acp.mask_session_output(_session_payload(), mask_join_code=False)
    assert masked["join_code"] == CODE
    assert MEMBER_TOKEN not in json.dumps(masked)


def test_join_session_prints_masked_output_unless_show_secrets(tmp_path: Path, monkeypatch: Any, capsys: Any) -> None:
    monkeypatch.setattr(acp, "join_session_from_args", lambda args: _session_payload())
    base = ["join-session", "--config", str(tmp_path / "w.json"), "--agent", "w", "--hub-http", "https://hub.example", "--code", CODE]
    assert acp.main(base) == 0
    masked_out = capsys.readouterr()
    assert MEMBER_TOKEN not in masked_out.out and CODE not in masked_out.out
    assert "--show-secrets" in masked_out.err
    assert acp.main([*base, "--show-secrets"]) == 0
    revealed = json.loads(capsys.readouterr().out)
    assert revealed["member_token"] == MEMBER_TOKEN and revealed["join_code"] == CODE


def test_masking_does_not_touch_saved_config(tmp_path: Path, monkeypatch: Any, capsys: Any) -> None:
    calls: list[str] = []

    def fake_post_json(*, hub_http: str, route: str, payload: dict[str, Any], token: str | None = None, **_: Any) -> dict[str, Any]:
        calls.append(route)
        if route == "/sessions/join":
            return {"session_id": "s-1", "member_token": MEMBER_TOKEN, "member_role": "collaborator", "join_code": CODE}
        return {"status": "ok"}

    monkeypatch.setattr(acp, "post_json", fake_post_json)
    config = tmp_path / "w.json"
    code = acp.main(["join-session", "--config", str(config), "--hub-http", "https://hub.example", "--agent", "w", "--code", CODE])
    assert code == 0
    assert json.loads(config.read_text(encoding="utf-8"))["member_token"] == MEMBER_TOKEN
    assert MEMBER_TOKEN not in capsys.readouterr().out


# --- B7: configs and git ---------------------------------------------------------------------


def test_warns_when_config_is_inside_a_git_worktree(tmp_path: Path, capsys: Any, monkeypatch: Any) -> None:
    monkeypatch.setattr(acp, "_GIT_WORKTREE_WARNED", set())
    repo = tmp_path / "repo"
    (repo / ".git").mkdir(parents=True)
    config = repo / "agents" / "w.json"
    assert acp.warn_if_config_in_git_worktree(config) is True
    err = capsys.readouterr().err
    assert "WARNING" in err and "git work tree" in err
    assert acp.warn_if_config_in_git_worktree(config) is False  # once per path
    outside = tmp_path / "elsewhere" / "w.json"
    assert acp.warn_if_config_in_git_worktree(outside) is False
    assert capsys.readouterr().err == ""


def test_explicit_config_in_git_still_works_with_only_a_warning(tmp_path: Path, capsys: Any, monkeypatch: Any) -> None:
    monkeypatch.setattr(acp, "_GIT_WORKTREE_WARNED", set())
    repo = tmp_path / "repo"
    (repo / ".git").mkdir(parents=True)
    config = repo / "w.json"
    resolved = acp.resolve_cli_config_path(config_path=str(config), command_name="listen")
    assert resolved == config.resolve()
    assert "WARNING" in capsys.readouterr().err


def test_default_agents_dir_avoids_git_worktrees(tmp_path: Path, monkeypatch: Any) -> None:
    monkeypatch.delenv("ACP_AGENTS_DIR", raising=False)
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "xdg"))
    repo = tmp_path / "repo"
    (repo / ".git").mkdir(parents=True)
    (repo / "ACP_AGENT").mkdir()
    monkeypatch.setattr(acp, "ACP_ROOT", repo / "ACP_AGENT")
    assert acp._default_agents_dir() == (tmp_path / "xdg" / "acp" / "agents").resolve()
    # an already-existing bundled directory keeps working (backward compatible)
    (repo / "ACP_AGENT" / "agents").mkdir()
    assert acp._default_agents_dir() == (repo / "ACP_AGENT" / "agents").resolve()
    # outside git the bundled directory is the default
    plain = tmp_path / "plain" / "ACP_AGENT"
    plain.mkdir(parents=True)
    monkeypatch.setattr(acp, "ACP_ROOT", plain)
    assert acp._default_agents_dir() == (plain / "agents").resolve()
    monkeypatch.setenv("ACP_AGENTS_DIR", str(tmp_path / "custom"))
    assert acp._default_agents_dir() == (tmp_path / "custom").resolve()


_TOKEN_LIKE = [
    re.compile(r"\b(?:sk|pk|ghp|gho|xox[bp]|acpm|acpt)[-_][A-Za-z0-9_-]{16,}"),
    re.compile(r"(?i)[\"']?(?:member_token|managed_agent_token|agent_token|token)[\"']?\s*[:=]\s*[\"'][A-Za-z0-9_\-]{24,}[\"']"),
    re.compile(r"(?i)(?:member_token|agent-token|--token)[= ]\s*[A-Za-z0-9_\-]{24,}\b"),
    re.compile(r"eyJ[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}"),
]


def test_shipped_agent_bundle_contains_no_token_like_values() -> None:
    offenders: list[str] = []
    for path in sorted((repo_root / "ACP_AGENT").rglob("*")):
        if not path.is_file() or "__pycache__" in path.parts or path.suffix in {".pyc", ".zip"}:
            continue
        if "agents" in path.relative_to(repo_root / "ACP_AGENT").parts[:1]:
            offenders.append(f"{path}: agent configs must not ship in the bundle")
            continue
        try:
            text = path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            continue
        for pattern in _TOKEN_LIKE:
            for match in pattern.finditer(text):
                offenders.append(f"{path.relative_to(repo_root)}: {match.group(0)[:40]}")
    assert not offenders, offenders


# --- B8: verify-approval ------------------------------------------------------------------------


def _verify_args(tmp_path: Path, **extra: str) -> list[str]:
    return [
        "verify-approval", "--hub-http", "https://hub.example", "--agent-token", "agent-secret-token-value",
        "--session-id", "sess-1", "--approval-id", "appr-9", *[part for k, v in extra.items() for part in (f"--{k}", v)],
    ]


def test_verify_approval_valid_uses_bearer_agent_token(tmp_path: Path, monkeypatch: Any, capsys: Any) -> None:
    seen: dict[str, Any] = {}

    def fake_request_json(**kwargs: Any) -> dict[str, Any]:
        seen.update(kwargs)
        return {"valid": True, "approval_id": "appr-9", "text": "go ahead", "created_at": "2026-01-01T00:00:00Z"}

    monkeypatch.setattr(acp, "request_json", fake_request_json)
    assert acp.main(_verify_args(tmp_path)) == 0
    assert seen["method"] == "GET"
    assert seen["url"] == "https://hub.example/managed/agent/sessions/sess-1/operator-approvals/appr-9"
    assert seen["headers"]["Authorization"] == "Bearer agent-secret-token-value"
    out = json.loads(capsys.readouterr().out)
    assert out["valid"] is True and out["text"] == "go ahead"


def test_verify_approval_unknown_id_exits_nonzero(tmp_path: Path, monkeypatch: Any, capsys: Any) -> None:
    def fake_request_json(**kwargs: Any) -> dict[str, Any]:
        raise ValueError('hub HTTP 404: {"detail":"not found"}')

    monkeypatch.setattr(acp, "request_json", fake_request_json)
    assert acp.main(_verify_args(tmp_path)) == 1
    out = json.loads(capsys.readouterr().out)
    assert out["valid"] is False and "NOT approved" in out["detail"]


def test_verify_approval_defaults_session_from_config_and_honors_workspace(tmp_path: Path, monkeypatch: Any) -> None:
    config = tmp_path / "w.json"
    config.write_text(
        json.dumps({"agent_name": "w", "hub_http": "https://hub.example", "session_id": "cfg-sess", "managed_agent_token": "cfgtoken-value"}),
        encoding="utf-8",
    )
    urls: list[str] = []
    monkeypatch.setattr(acp, "request_json", lambda **kw: urls.append(kw["url"]) or {"valid": True, "approval_id": "a"})
    args = acp.build_parser().parse_args(["verify-approval", "--config", str(config), "--approval-id", "a", "--workspace", "acme"])
    assert acp.verify_approval_from_args(args)["valid"] is True
    assert urls == ["https://hub.example/managed/agent/workspaces/acme/sessions/cfg-sess/operator-approvals/a"]


def test_verify_approval_transport_errors_are_not_reported_as_invalid(tmp_path: Path, monkeypatch: Any) -> None:
    monkeypatch.setattr(acp, "request_json", lambda **kw: (_ for _ in ()).throw(ValueError("hub HTTP 401: bad token")))
    with pytest.raises(SystemExit) as excinfo:
        acp.main(_verify_args(tmp_path))
    assert excinfo.value.code == 2


# --- C10: modes ---------------------------------------------------------------------------------


def test_modes_table_matches_real_adapters_and_providers(capsys: Any) -> None:
    assert acp.main(["modes"]) == 0
    data = json.loads(capsys.readouterr().out)
    assert data["runner_providers"] == ["codex_local", "claude_local"]
    assert set(data["host_bridge_adapters"]) == set(acp.HOST_BRIDGE_SUPPORTED_ADAPTERS)
    listed = " ".join(entry["mode"] for entry in data["modes"])
    for adapter in acp.HOST_BRIDGE_SUPPORTED_ADAPTERS:
        assert adapter in listed
    desktop = next(entry for entry in data["modes"] if entry["mode"] == "claude_desktop")
    assert desktop["wakes_idle_agent"] is False


def test_unknown_modes_are_rejected_listing_valid_ones(tmp_path: Path, capsys: Any) -> None:
    with pytest.raises(SystemExit):
        acp.main(["runner", "once", "--config", str(tmp_path / "w.json"), "--provider", "codex_cloud"])
    err = capsys.readouterr().err
    assert "codex_cloud" in err and "codex_local" in err and "claude_local" in err
    with pytest.raises(SystemExit):
        acp.main(["host-bridge", "configure", "--adapter-id", "nope", "--role", "member"])
    assert "opencode_server" in capsys.readouterr().err

    config = tmp_path / "cfg.json"
    config.write_text(
        json.dumps({"agent_name": "w", "hub_http": "https://hub.example", "session_id": "s", "member_token": "tok", "runner_provider": "codex_cloud"}),
        encoding="utf-8",
    )
    with pytest.raises(ValueError) as excinfo:
        acp.resolve_runner_profile(acp.build_parser().parse_args(["runner", "once", "--config", str(config)]))
    assert "codex_cloud" in str(excinfo.value) and "codex_local, claude_local" in str(excinfo.value)


# --- C11: listen --to-file / --exec ------------------------------------------------------------


def _settings(tmp_path: Path) -> Any:
    return acp.HubAgentSettings(
        config_path=tmp_path / "w.json", config={}, base_dir=tmp_path, agent_name="w", hub_http="https://hub.example",
        hub_ws=None, token=None, session_id="s-1", member_token="member-secret", dashboard_session_path="/dashboard/session",
    )


def _message(**extra: Any) -> dict[str, Any]:
    return {"id": "11111111-1111-4111-8111-111111111111", "from": "chief", "to": "w", "action": "TASK", "payload": "hi", **extra}


def test_append_message_to_file_writes_one_json_line_each(tmp_path: Path) -> None:
    target = tmp_path / "nested" / "inbox.jsonl"
    acp.append_message_to_file(target, _message(payload="line1\nline2"))
    acp.append_message_to_file(target, _message(id="22222222-2222-4222-8222-222222222222"))
    lines = target.read_text(encoding="utf-8").splitlines()
    assert len(lines) == 2
    assert json.loads(lines[0])["payload"] == "line1\nline2"


def test_exec_receives_message_on_stdin_and_ids_in_env_without_a_shell(tmp_path: Path, monkeypatch: Any) -> None:
    monkeypatch.setattr(acp, "post_json", lambda **kw: {})
    out = tmp_path / "out.json"
    script = tmp_path / "handler.py"
    script.write_text(
        "import json, os, sys\n"
        "data = json.load(sys.stdin)\n"
        "json.dump({'payload': data['payload'], 'id': os.environ['ACP_MESSAGE_ID'], 'from': os.environ['ACP_MESSAGE_FROM'],\n"
        "  'action': os.environ['ACP_MESSAGE_ACTION'], 'session': os.environ['ACP_SESSION_ID'],\n"
        "  'leaked': [k for k in os.environ if 'TOKEN' in k and k.startswith('ACP_')], 'argv': sys.argv[1:]},\n"
        "  open(sys.argv[1], 'w'))\n",
        encoding="utf-8",
    )
    marker = tmp_path / "pwned"
    argv = acp.parse_exec_command(f'"{sys.executable}" "{script}" "{out}"')
    hostile = f"$(touch {marker}); `touch {marker}`; touch {marker}"
    result = acp.run_exec_for_message(
        settings=_settings(tmp_path), argv=argv, message=_message(payload=hostile), inbox_path="/x/y.json", timeout_seconds=30
    )
    assert result["status"] == "exec_ok", result
    recorded = json.loads(out.read_text(encoding="utf-8"))
    assert recorded["payload"] == hostile
    assert recorded["id"] == "11111111-1111-4111-8111-111111111111"
    assert recorded["from"] == "chief" and recorded["action"] == "TASK" and recorded["session"] == "s-1"
    assert recorded["leaked"] == []
    assert hostile not in " ".join(recorded["argv"])
    assert not marker.exists()


def test_exec_reports_failures_and_timeouts(tmp_path: Path, monkeypatch: Any) -> None:
    monkeypatch.setattr(acp, "post_json", lambda **kw: {})
    settings = _settings(tmp_path)
    failed = acp.run_exec_for_message(
        settings=settings, argv=[sys.executable, "-c", "import sys; sys.stderr.write('boom'); sys.exit(3)"],
        message=_message(), inbox_path=None, timeout_seconds=30,
    )
    assert failed["status"] == "exec_failed" and failed["returncode"] == 3 and "boom" in failed["stderr_tail"]
    missing = acp.run_exec_for_message(
        settings=settings, argv=["/nonexistent/acp-handler"], message=_message(), inbox_path=None, timeout_seconds=5
    )
    assert missing["status"] == "exec_failed" and "could not start" in missing["detail"]
    slow = acp.run_exec_for_message(
        settings=settings, argv=[sys.executable, "-c", "import time; time.sleep(30)"],
        message=_message(), inbox_path=None, timeout_seconds=1,
    )
    assert slow["status"] == "exec_failed" and "killed" in slow["detail"]


def test_exec_sends_heartbeats_while_running(tmp_path: Path, monkeypatch: Any) -> None:
    routes: list[str] = []
    monkeypatch.setattr(acp, "post_json", lambda **kw: routes.append(kw["route"]) or {})
    result = acp.run_exec_for_message(
        settings=_settings(tmp_path), argv=[sys.executable, "-c", "import time; time.sleep(1.2)"],
        message=_message(), inbox_path=None, timeout_seconds=30, heartbeat_interval_seconds=0.3,
    )
    assert result["status"] == "exec_ok"
    assert routes.count("/sessions/heartbeat") >= 2


def test_parse_exec_command_rejects_empty() -> None:
    with pytest.raises(ValueError):
        acp.parse_exec_command("   ")
    assert acp.parse_exec_command("python -c 'print(1)'") == ["python", "-c", "print(1)"] or os.name == "nt"


def _listen_args(tmp_path: Path, *extra: str) -> argparse.Namespace:
    config = tmp_path / "w.json"
    config.write_text(
        json.dumps({"agent_name": "w", "hub_http": "https://hub.example", "session_id": "s-1", "member_token": "tok"}),
        encoding="utf-8",
    )
    args = acp.build_parser().parse_args(["listen", "--config", str(config), "--retry-delay-seconds", "0.1", *extra])
    args.emit = False
    return args


def test_listen_to_file_and_exec_survive_transport_errors(tmp_path: Path, monkeypatch: Any) -> None:
    sink = tmp_path / "msgs.jsonl"
    marker = tmp_path / "handled.txt"
    script = tmp_path / "h.py"
    script.write_text(
        "import os, sys\nopen(sys.argv[1], 'a').write(os.environ['ACP_MESSAGE_ID'] + '\\n')\n", encoding="utf-8"
    )
    waits = iter(
        [
            ValueError("hub HTTP 503: unavailable"),
            ValueError("hub connection failed (URLError: refused)."),
            {"status": "message", "message": _message(), "delivery": {"ack_required": True, "message_id": _message()["id"], "receipt_handle": "rh"}},
            {"status": "message", "message": _message(id="33333333-3333-4333-8333-333333333333", payload="second"), "delivery": {"ack_required": True, "message_id": "33333333-3333-4333-8333-333333333333", "receipt_handle": "rh2"}},
        ]
    )
    sleeps: list[float] = []

    def fake_post_json(*, hub_http: str, route: str, payload: dict[str, Any], **_: Any) -> dict[str, Any]:
        if route == "/sessions/wait":
            item = next(waits, None)
            if item is None:
                raise RuntimeError("scripted waits exhausted")
            if isinstance(item, Exception):
                raise item
            return item
        return {"status": "ok"}

    monkeypatch.setattr(acp, "post_json", fake_post_json)
    monkeypatch.setattr(acp.time, "sleep", lambda seconds: sleeps.append(seconds))

    real_append = acp.append_message_to_file
    count = {"n": 0}

    def stopping_append(path: Path, message: dict[str, Any]) -> None:
        real_append(path, message)
        count["n"] += 1

    monkeypatch.setattr(acp, "append_message_to_file", stopping_append)
    args = _listen_args(
        tmp_path, "--to-file", str(sink), "--exec", f'"{sys.executable}" "{script}" "{marker}"'
    )
    # the scripted waits run out -> RuntimeError ends the persistent loop deterministically
    with pytest.raises(RuntimeError):
        acp.listen_for_session_message(args)
    ids = [json.loads(line)["id"] for line in sink.read_text(encoding="utf-8").splitlines()]
    assert ids == ["11111111-1111-4111-8111-111111111111", "33333333-3333-4333-8333-333333333333"]
    assert marker.read_text(encoding="utf-8").split() == ids
    assert len(sleeps) == 2 and sleeps[1] >= sleeps[0] / 2  # backoff grows (with jitter) across consecutive failures
    assert count["n"] == 2


# --- D14: dependency check -------------------------------------------------------------------


def test_missing_websockets_fails_early_with_actionable_message(monkeypatch: Any, capsys: Any) -> None:
    monkeypatch.setattr(acp, "_missing_dependencies", lambda: ["websockets>=15,<16"])
    for command in (["listen"], ["join-session", "--code", CODE], ["managed-join", "--session-id", "s"]):
        assert acp.main(command) == 3
        err = capsys.readouterr().err
        assert "websockets" in err and "pip install -r" in err and "requirements.txt" in err
    # diagnostics still work without the package
    monkeypatch.setattr(acp, "cmd_doctor", lambda args: {"status": "fail", "checks": []})
    assert acp.main(["doctor", "--hub-http", "https://hub.example"]) == 1


def test_missing_dependencies_helper_detects_absent_module(monkeypatch: Any) -> None:
    monkeypatch.setattr(acp, "REQUIRED_DEPENDENCIES", (("acp_module_that_does_not_exist", "acp-missing>=1"),))
    assert acp._missing_dependencies() == ["acp-missing>=1"]
    monkeypatch.setattr(acp, "REQUIRED_DEPENDENCIES", (("json", "json"),))
    assert acp._missing_dependencies() == []


# --- Extra: retry with backoff and idempotency ---------------------------------------------------


class _Resp:
    def __init__(self, body: bytes = b'{"status":"ok"}') -> None:
        self._body = body

    def __enter__(self) -> "_Resp":
        return self

    def __exit__(self, *_: object) -> None:
        return None

    def read(self) -> bytes:
        return self._body


def _http_error(code: int) -> urllib.error.HTTPError:
    return urllib.error.HTTPError("https://hub.example/x", code, "err", {}, io.BytesIO(b'{"detail":"gateway"}'))  # type: ignore[arg-type]


def _script_urlopen(monkeypatch: Any, outcomes: list[Any]) -> list[Any]:
    calls: list[Any] = []

    def fake_urlopen(request: Any, timeout: float) -> Any:
        calls.append(request)
        outcome = outcomes.pop(0)
        if isinstance(outcome, BaseException):
            raise outcome
        return outcome

    monkeypatch.setattr(acp.urllib.request, "urlopen", fake_urlopen)
    return calls


@pytest.mark.parametrize("code", [502, 503, 504, 524])
def test_idempotent_calls_retry_transient_gateway_statuses(monkeypatch: Any, code: int) -> None:
    sleeps: list[float] = []
    monkeypatch.setattr(acp.time, "sleep", sleeps.append)
    calls = _script_urlopen(monkeypatch, [_http_error(code), _http_error(code), _Resp()])
    assert acp.get_json(hub_http="https://hub.example", route="/health") == {"status": "ok"}
    assert len(calls) == 3 and len(sleeps) == 2


def test_connection_errors_retry_then_raise_a_clear_value_error(monkeypatch: Any) -> None:
    sleeps: list[float] = []
    monkeypatch.setattr(acp.time, "sleep", sleeps.append)
    monkeypatch.delenv(acp.RETRY_ATTEMPTS_ENV, raising=False)
    calls = _script_urlopen(monkeypatch, [urllib.error.URLError("refused")] * 4)
    with pytest.raises(ValueError, match="hub connection failed") as excinfo:
        acp.get_json(hub_http="https://hub.example", route="/health")
    assert len(calls) == 4 and len(sleeps) == 3
    assert "ACP_HTTP_RETRIES" in str(excinfo.value)


def test_backoff_is_exponential_bounded_and_jittered(monkeypatch: Any) -> None:
    monkeypatch.setenv(acp.RETRY_ATTEMPTS_ENV, "5")
    monkeypatch.setenv(acp.RETRY_BASE_DELAY_ENV, "1")
    schedule = acp.default_retry_backoff()
    assert schedule == (1.0, 2.0, 4.0, 8.0, 16.0)
    monkeypatch.setenv(acp.RETRY_ATTEMPTS_ENV, "999")
    assert len(acp.default_retry_backoff()) == acp.RETRY_MAX_ATTEMPTS_LIMIT
    monkeypatch.setenv(acp.RETRY_ATTEMPTS_ENV, "0")
    assert acp.default_retry_backoff() == ()
    for _ in range(50):
        assert 1.0 <= acp._jittered_delay(2.0) <= 2.0


def test_retry_count_is_configurable_by_env_and_flag(monkeypatch: Any) -> None:
    monkeypatch.setattr(acp.time, "sleep", lambda _: None)
    monkeypatch.setenv(acp.RETRY_ATTEMPTS_ENV, "1")
    calls = _script_urlopen(monkeypatch, [_http_error(503)] * 5)
    with pytest.raises(ValueError, match="hub HTTP 503"):
        acp.get_json(hub_http="https://hub.example", route="/health")
    assert len(calls) == 2
    monkeypatch.delenv(acp.RETRY_ATTEMPTS_ENV)
    with pytest.raises(SystemExit):
        acp.main(["--http-retries", "99", "modes"])
    assert acp.main(["--http-retries", "0", "modes"]) == 0
    assert os.environ[acp.RETRY_ATTEMPTS_ENV] == "0"
    monkeypatch.delenv(acp.RETRY_ATTEMPTS_ENV)


def test_send_without_idempotency_key_is_not_retried_and_fails_clearly(monkeypatch: Any) -> None:
    monkeypatch.setattr(acp.time, "sleep", lambda _: None)
    calls = _script_urlopen(monkeypatch, [_http_error(503), _Resp()])
    with pytest.raises(ValueError) as excinfo:
        acp.post_json(hub_http="https://hub.example", route="/sessions/send", payload={"to": "x", "payload": "p"})
    assert len(calls) == 1
    assert "NOT retried" in str(excinfo.value) and "hub HTTP 503" in str(excinfo.value)


def test_send_with_idempotency_key_is_retried_with_the_same_id(monkeypatch: Any) -> None:
    monkeypatch.setattr(acp.time, "sleep", lambda _: None)
    calls = _script_urlopen(monkeypatch, [_http_error(502), urllib.error.URLError("reset"), _Resp()])
    payload = {"to": "x", "payload": "p", "id": "44444444-4444-4444-8444-444444444444"}
    assert acp.post_json(hub_http="https://hub.example", route="/sessions/send", payload=payload) == {"status": "ok"}
    assert len(calls) == 3
    assert {json.loads(call.data)["id"] for call in calls} == {payload["id"]}


def test_cli_send_payload_carries_a_fresh_idempotency_key(tmp_path: Path) -> None:
    config = tmp_path / "w.json"
    config.write_text(
        json.dumps({"agent_name": "w", "hub_http": "https://hub.example", "session_id": "s-1", "member_token": "tok"}),
        encoding="utf-8",
    )
    args = acp.build_parser().parse_args(["send", "--config", str(config), "--to", "chief", "--action", "INFO", "--payload", "hi"])
    settings = acp.resolve_hub_agent_settings(args)
    first = acp.build_session_send_payload(args, settings)
    second = acp.build_session_send_payload(args, settings)
    assert re.fullmatch(r"[0-9a-f-]{36}", first["id"]) and first["id"] != second["id"]


def test_non_transient_http_errors_are_never_retried(monkeypatch: Any) -> None:
    monkeypatch.setattr(acp.time, "sleep", lambda _: None)
    calls = _script_urlopen(monkeypatch, [_http_error(404), _Resp()])
    with pytest.raises(ValueError, match="hub HTTP 404"):
        acp.get_json(hub_http="https://hub.example", route="/health")
    assert len(calls) == 1
