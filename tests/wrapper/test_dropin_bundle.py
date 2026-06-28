from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
import zipfile
from io import StringIO
from pathlib import Path
from contextlib import redirect_stdout


def _load_module(module_name: str, path: Path) -> object:
    spec = importlib.util.spec_from_file_location(module_name, path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"unable to load module from {path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    spec.loader.exec_module(module)
    return module


def _copy_bundle_runtime_files(source: Path, target: Path) -> None:
    for name in (
        "acp.py",
        "acp_distribution.py",
        "DISTRIBUTION.json",
        "install_from_bundle.py",
        "requirements.txt",
        "VERSION",
        "CHANGELOG.md",
        "update_from_release.py",
    ):
        (target / name).write_text((source / name).read_text(encoding="utf-8"), encoding="utf-8")
    (target / "skills" / "acp-session-coordinator" / "SKILL.md").write_text(
        (source / "skills" / "acp-session-coordinator" / "SKILL.md").read_text(encoding="utf-8"),
        encoding="utf-8",
    )


def test_dropin_bundle_tracks_runtime_and_skill_sources() -> None:
    module = _load_module("acp_dropin_runtime", Path("ACP_AGENT/acp.py"))
    parser = module.build_parser()
    subcommands = set(parser._subparsers._group_actions[0].choices.keys())
    assert {"run", "send", "create-session", "join-session", "wait", "listen", "status", "heartbeat", "session-info", "leave-session"} <= subcommands
    distribution = json.loads(Path("ACP_AGENT/DISTRIBUTION.json").read_text(encoding="utf-8"))
    assert distribution["distribution_id"] == "acp-community"
    assert distribution["default_hub_mode"] == "explicit"
    assert distribution["default_hub_http"] is None
    assert distribution["default_hub_ws"] is None
    assert distribution["default_manifest_url"] is None
    requirements = Path("ACP_AGENT/requirements.txt").read_text(encoding="utf-8")
    assert "websockets" in requirements
    assert Path("ACP_AGENT/update_from_release.py").exists()
    assert Path("ACP_AGENT/acp_distribution.py").exists()
    assert Path("ACP_AGENT/VERSION").read_text(encoding="utf-8").strip()
    assert "0.3.0" in Path("ACP_AGENT/CHANGELOG.md").read_text(encoding="utf-8")

    # The bundled skill is the source of truth in the public repo. When the
    # internal authoring source (.codex/skills) is present (private/dev tree),
    # assert the bundle tracks it; in the public repo that source is absent.
    skill_source_path = Path(".codex/skills/acp-session-coordinator/SKILL.md")
    bundle_skill = Path("ACP_AGENT/skills/acp-session-coordinator/SKILL.md").read_text(encoding="utf-8")
    assert bundle_skill.strip()
    assert len(bundle_skill.splitlines()) <= 180
    assert "coordinate --agent <agent>" in bundle_skill
    assert "connect --role auto" in bundle_skill
    assert "listen --stop-after-message --timeout-seconds 300" in bundle_skill
    assert "runner start" in bundle_skill
    if skill_source_path.exists():
        assert bundle_skill == skill_source_path.read_text(encoding="utf-8")


def test_agent_bootstrap_docs_are_clean_and_session_aligned() -> None:
    agent_doc = Path("ACP_AGENT/AGENT.md").read_text(encoding="utf-8")
    protocol_doc = Path("protocol.md").read_text(encoding="utf-8")

    assert "\ufffd" not in agent_doc
    assert "install_from_bundle.py --force" in agent_doc
    assert "create-session" in agent_doc
    assert "join-session" in agent_doc
    assert "wait" in agent_doc
    assert "listen" in agent_doc
    assert "session_dashboard_url" in agent_doc
    assert "shareable_session_access" in agent_doc
    assert "sesion murio" in agent_doc
    assert "update_from_release.py --check" in agent_doc
    assert "downloads/ACP_AGENT.zip" in agent_doc
    assert "requirements.txt" in agent_doc
    assert "python -m pip install -r ACP_AGENT/requirements.txt" in agent_doc
    assert "/sessions" in protocol_doc
    assert "/sessions/join" in protocol_doc
    assert "/sessions/wait" in protocol_doc
    assert "/sessions/status" in protocol_doc
    assert "/sessions/send" in protocol_doc
    assert "session_dashboard_url_template" in protocol_doc
    assert "active sessions do not survive Hub restart or redeploy" in protocol_doc
    assert "Markdown Memory Contract" not in protocol_doc


def test_dropin_installer_creates_skill_and_agent_folder(tmp_path: Path) -> None:
    installer = _load_module("acp_dropin_installer", Path("ACP_AGENT/install_from_bundle.py"))
    skill_home = tmp_path / "skills-home"
    acp_root = tmp_path / "ACP_AGENT"
    acp_root.mkdir(parents=True)
    (acp_root / "acp.py").write_text(Path("ACP_AGENT/acp.py").read_text(encoding="utf-8"), encoding="utf-8")
    (acp_root / "acp_distribution.py").write_text(
        Path("ACP_AGENT/acp_distribution.py").read_text(encoding="utf-8"),
        encoding="utf-8",
    )
    (acp_root / "DISTRIBUTION.json").write_text(
        Path("ACP_AGENT/DISTRIBUTION.json").read_text(encoding="utf-8"),
        encoding="utf-8",
    )

    skill_path = installer.install_skill(skill_home=skill_home, force=True)
    acp_path = installer.initialize_agent_folder(
        acp_root=acp_root,
        hub_mode="custom",
        hub_http="http://hub.example",
        hub_ws="ws://hub.example/ws",
        agent_names=["codex-chief", "claude-review"],
        token="shared-token",
        force=True,
    )

    assert skill_path == skill_home / "acp-session-coordinator"
    assert (skill_path / "SKILL.md").exists()
    assert acp_path == acp_root
    assert (acp_path / "acp.py").exists()
    assert (acp_path / "acp_distribution.py").exists()
    assert (acp_path / "DISTRIBUTION.json").exists()
    assert (acp_path / "VERSION").exists()
    assert (acp_path / "CHANGELOG.md").exists()
    assert (acp_path / "update_from_release.py").exists()
    assert (acp_path / "agents" / "codex-chief.json").exists()
    assert (acp_path / "agents" / "claude-review.json").exists()

    config = json.loads((acp_path / "agents" / "codex-chief.json").read_text(encoding="utf-8"))
    assert config["agent_name"] == "codex-chief"
    assert config["hub_mode"] == "custom"
    assert config["hub_http"] == "http://hub.example"
    assert config["hub_ws"] == "ws://hub.example/ws"
    assert config["token"] == "shared-token"


def test_dropin_installer_resolves_codex_and_claude_skill_homes(tmp_path: Path) -> None:
    installer = _load_module("acp_dropin_installer_skill_homes", Path("ACP_AGENT/install_from_bundle.py"))

    homes = installer.resolve_skill_homes(
        type(
            "_Args",
            (),
            {
                "skill_home": None,
                "claude_skill_home": str(tmp_path / "claude-skills"),
            },
        )()
    )

    assert Path.home() / ".codex" / "skills" in homes
    assert tmp_path / "claude-skills" in homes


def test_dropin_installer_requires_custom_hub_urls_when_bundle_has_no_default(tmp_path: Path) -> None:
    source = Path("ACP_AGENT")
    target = tmp_path / "ACP_AGENT"
    (target / "skills" / "acp-session-coordinator").mkdir(parents=True)
    _copy_bundle_runtime_files(source, target)

    result = subprocess.run(
        [
            sys.executable,
            str(target / "install_from_bundle.py"),
            "--agent",
            "codex-chief",
            "--skip-install-deps",
            "--force",
        ],
        cwd=tmp_path,
        text=True,
        input="",
        capture_output=True,
        check=False,
    )

    assert result.returncode != 0
    assert "Custom Hub HTTP URL is required in non-interactive mode." in (result.stderr or result.stdout)
    assert not (target / "agents" / "codex-chief.json").exists()


def test_dropin_installer_non_interactive_requires_agent_names(tmp_path: Path) -> None:
    source = Path("ACP_AGENT")
    target = tmp_path / "ACP_AGENT"
    (target / "skills" / "acp-session-coordinator").mkdir(parents=True)
    _copy_bundle_runtime_files(source, target)

    result = subprocess.run(
        [
            sys.executable,
            str(target / "install_from_bundle.py"),
            "--hub-mode",
            "custom",
            "--hub-http",
            "http://hub.example",
            "--skip-install-deps",
            "--non-interactive",
            "--force",
        ],
        cwd=tmp_path,
        text=True,
        input="",
        capture_output=True,
        check=False,
    )

    assert result.returncode != 0
    assert "Agent names are required in non-interactive mode." in (result.stderr or result.stdout)


def test_dropin_installer_official_mode_honors_explicit_hub_flags(tmp_path: Path) -> None:
    source = Path("ACP_AGENT")
    target = tmp_path / "ACP_AGENT"
    (target / "skills" / "acp-session-coordinator").mkdir(parents=True)
    _copy_bundle_runtime_files(source, target)

    skill_home = tmp_path / "skill-home"
    result = subprocess.run(
        [
            sys.executable,
            str(target / "install_from_bundle.py"),
            "--hub-mode",
            "official",
            "--hub-http",
            "https://hub.example",
            "--agent",
            "codex-chief",
            "--skill-home",
            str(skill_home),
            "--skip-install-deps",
            "--non-interactive",
            "--force",
        ],
        cwd=tmp_path,
        text=True,
        input="",
        capture_output=True,
        check=False,
    )

    assert result.returncode == 0, result.stderr or result.stdout
    config = json.loads((target / "agents" / "codex-chief.json").read_text(encoding="utf-8"))
    assert config["hub_mode"] == "official"
    assert config["hub_http"] == "https://hub.example"
    assert config["hub_ws"] == "wss://hub.example/ws"


def test_dropin_installer_main_works_in_place_without_prompting_for_optional_token(tmp_path: Path) -> None:
    source = Path("ACP_AGENT")
    target = tmp_path / "ACP_AGENT"
    (target / "skills" / "acp-session-coordinator").mkdir(parents=True)
    _copy_bundle_runtime_files(source, target)

    skill_home = tmp_path / "skill-home"
    result = subprocess.run(
        [
            sys.executable,
            str(target / "install_from_bundle.py"),
            "--hub-http",
            "http://hub.example",
            "--hub-ws",
            "ws://hub.example/ws",
            "--agent",
            "codex-chief",
            "--skill-home",
            str(skill_home),
            "--skip-install-deps",
            "--force",
        ],
        cwd=tmp_path,
        text=True,
        input="",
        capture_output=True,
        check=False,
    )

    assert result.returncode == 0, result.stderr or result.stdout
    config = json.loads((target / "agents" / "codex-chief.json").read_text(encoding="utf-8"))
    assert config["hub_http"] == "http://hub.example"
    assert config["hub_ws"] == "ws://hub.example/ws"
    assert config["hub_mode"] == "custom"
    assert "token" not in config
    assert (target / "requirements.txt").exists()
    bundle_info = json.loads((target / "BUNDLE_INFO.json").read_text(encoding="utf-8"))
    assert bundle_info["installed_version"] == Path("ACP_AGENT/VERSION").read_text(encoding="utf-8").strip()
    assert bundle_info["installed_at"]


def test_runtime_settings_require_hub_ws_when_config_has_no_urls(tmp_path: Path) -> None:
    module = _load_module("acp_dropin_runtime_default_hub", Path("ACP_AGENT/acp.py"))
    config_path = tmp_path / "codex-chief.json"
    config_path.write_text(json.dumps({"agent_name": "codex-chief"}), encoding="utf-8")

    try:
        module.resolve_runtime_settings(
            module.build_parser().parse_args(["run", "--config", str(config_path)])
        )
    except ValueError as exc:
        assert "hub websocket URL is required" in str(exc)
    else:
        raise AssertionError("resolve_runtime_settings should require hub_ws when the bundle has no default hub")


def test_hub_agent_settings_require_hub_http_when_config_has_no_urls(tmp_path: Path) -> None:
    module = _load_module("acp_dropin_runtime_default_http", Path("ACP_AGENT/acp.py"))
    config_path = tmp_path / "codex-chief.json"
    config_path.write_text(json.dumps({"agent_name": "codex-chief"}), encoding="utf-8")

    try:
        module.resolve_hub_agent_settings(
            module.build_parser().parse_args(["session-info", "--config", str(config_path)])
        )
    except ValueError as exc:
        assert "hub_http is required" in str(exc)
    else:
        raise AssertionError("resolve_hub_agent_settings should require hub_http when the bundle has no default hub")


def test_session_commands_return_shareable_dashboard_access_metadata(tmp_path: Path) -> None:
    module = _load_module("acp_dropin_runtime_access", Path("ACP_AGENT/acp.py"))
    config_path = tmp_path / "codex-chief.json"
    config_path.write_text(
        json.dumps(
            {
                "agent_name": "codex-chief",
                "hub_http": "http://hub.example",
                "hub_ws": "ws://hub.example/ws",
            }
        ),
        encoding="utf-8",
    )
    calls: list[tuple[str, dict[str, object]]] = []

    def fake_post_json(*, hub_http: str, route: str, payload: dict[str, object], token: str | None = None) -> dict[str, object]:
        calls.append((route, payload))
        if route == "/sessions":
            return {
                "status": "ok",
                "session_id": "session-123",
                "join_code": "JOIN42",
                "member_token": "chief-token",
                "member_role": "chief",
            }
        if route == "/sessions/join":
            return {
                "status": "ok",
                "session_id": "session-123",
                "join_code": "JOIN42",
                "member_token": "worker-token",
                "member_role": "collaborator",
            }
        if route == "/sessions/status":
            return {"status": "ok"}
        raise AssertionError(route)

    def fake_get_json(*, hub_http: str, route: str, token: str | None = None) -> dict[str, object]:
        return {
            "status": "ok",
            "session": {
                "session_id": "session-123",
                "join_code": "JOIN42",
                "members": [
                    {
                        "agent_name": "codex-chief",
                        "role": "chief",
                    }
                ],
            },
        }

    module.post_json = fake_post_json
    module.get_json = fake_get_json

    created = module.create_session_from_args(
        module.build_parser().parse_args(
            ["create-session", "--config", str(config_path), "--title", "Auth Refactor"]
        )
    )
    assert created["session_dashboard_url"] == (
        "http://hub.example/dashboard/session?session_id=session-123&agent_name=codex-chief#member_token=chief-token"
    )
    assert created["shareable_session_access"]["join_code"] == "JOIN42"
    assert created["shareable_session_access"]["hub_ws"] == "ws://hub.example/ws"
    assert "join-session" in created["shareable_session_access"]["join_command_example"]
    assert "wait" in created["shareable_session_access"]["wait_command_example"]
    assert "listen" in created["shareable_session_access"]["listen_command_example"]
    assert "heartbeat" in created["shareable_session_access"]["heartbeat_command_example"]
    assert "heartbeat-window-minutes" in created["shareable_session_access"]["busy_hold_command_example"]
    assert "[busy-hold:30]" in created["shareable_session_access"]["long_task_payload_convention"]
    assert created["operational_status"] == "waiting"
    assert "listen" in created["recommended_next_step"].lower()
    assert "listen" in created["listen_command_example"]
    assert calls[1] == (
        "/sessions/status",
        {
            "session_id": "session-123",
            "agent_name": "codex-chief",
            "member_token": "chief-token",
            "status": "waiting",
            "status_text": "waiting for session activity",
        },
    )

    collaborator_config = tmp_path / "claude-review.json"
    collaborator_config.write_text(
        json.dumps(
            {
                "agent_name": "claude-review",
                "hub_http": "http://hub.example",
                "hub_ws": "ws://hub.example/ws",
            }
        ),
        encoding="utf-8",
    )
    joined = module.join_session_from_args(
        module.build_parser().parse_args(
            ["join-session", "--config", str(collaborator_config), "--code", "JOIN42"]
        )
    )
    assert "member_token=worker-token" in joined["session_dashboard_url"]
    assert "agent_name=%3Cagent_name%3E" in joined["session_dashboard_url_template"]
    assert joined["operational_status"] == "waiting"
    assert calls[3] == (
        "/sessions/status",
        {
            "session_id": "session-123",
            "agent_name": "claude-review",
            "member_token": "worker-token",
            "status": "waiting",
            "status_text": "waiting for session activity",
        },
    )

    info = module.fetch_session_info(
        module.build_parser().parse_args(["session-info", "--config", str(config_path)])
    )
    assert info["session_dashboard_url"].endswith("member_token=chief-token")
    assert info["shareable_session_access"]["session_id"] == "session-123"


def test_join_session_refuses_reusing_live_chief_config(tmp_path: Path) -> None:
    module = _load_module("acp_dropin_runtime_join_reuse_guard", Path("ACP_AGENT/acp.py"))
    config_path = tmp_path / "codex-chief.json"
    config_path.write_text(
        json.dumps(
            {
                "agent_name": "codex-chief",
                "hub_http": "http://hub.example",
                "hub_ws": "ws://hub.example/ws",
                "session_id": "session-123",
                "member_token": "chief-token",
                "member_role": "chief",
            }
        ),
        encoding="utf-8",
    )

    def fake_get_json(*, hub_http: str, route: str, token: str | None = None) -> dict[str, object]:
        return {
            "status": "ok",
            "session": {
                "session_id": "session-123",
                "members": [
                    {
                        "agent_name": "codex-chief",
                        "role": "chief",
                    }
                ],
            },
        }

    module.get_json = fake_get_json

    try:
        module.join_session_from_args(
            module.build_parser().parse_args(
                ["join-session", "--config", str(config_path), "--code", "JOIN42"]
            )
        )
    except ValueError as exc:
        assert "already attached to active session" in str(exc)
        assert "chief" in str(exc)
    else:
        raise AssertionError("join-session should refuse a config that is already bound to a live session")


def test_join_session_clears_stale_local_binding_before_rejoin(tmp_path: Path) -> None:
    module = _load_module("acp_dropin_runtime_join_stale_rebind", Path("ACP_AGENT/acp.py"))
    config_path = tmp_path / "claude-review.json"
    config_path.write_text(
        json.dumps(
            {
                "agent_name": "claude-review",
                "hub_http": "http://hub.example",
                "hub_ws": "ws://hub.example/ws",
                "session_id": "stale-session",
                "member_token": "stale-token",
                "member_role": "collaborator",
            }
        ),
        encoding="utf-8",
    )

    def fake_get_json(*, hub_http: str, route: str, token: str | None = None) -> dict[str, object]:
        raise ValueError('hub HTTP 403: {"status":"error","message":"session does not exist."}')

    def fake_post_json(*, hub_http: str, route: str, payload: dict[str, object], token: str | None = None) -> dict[str, object]:
        if route == "/sessions/join":
            return {
                "status": "ok",
                "session_id": "session-456",
                "join_code": "JOIN99",
                "member_token": "worker-token",
                "member_role": "collaborator",
            }
        if route == "/sessions/status":
            return {"status": "ok"}
        raise AssertionError(route)

    module.get_json = fake_get_json
    module.post_json = fake_post_json

    payload = module.join_session_from_args(
        module.build_parser().parse_args(
            ["join-session", "--config", str(config_path), "--code", "JOIN99"]
        )
    )

    assert payload["session_id"] == "session-456"
    updated = json.loads(config_path.read_text(encoding="utf-8"))
    assert updated["session_id"] == "session-456"
    assert updated["member_role"] == "collaborator"


def test_listen_renews_wait_until_message_arrives(tmp_path: Path) -> None:
    module = _load_module("acp_dropin_runtime_listen", Path("ACP_AGENT/acp.py"))
    config_path = tmp_path / "codex-chief.json"
    config_path.write_text(
        json.dumps(
            {
                "agent_name": "codex-chief",
                "hub_http": "http://hub.example",
                "hub_ws": "ws://hub.example/ws",
                "session_id": "session-123",
                "member_token": "chief-token",
            }
        ),
        encoding="utf-8",
    )
    calls: list[str] = []

    def fake_post_json(*, hub_http: str, route: str, payload: dict[str, object], token: str | None = None) -> dict[str, object]:
        calls.append(route)
        if len(calls) < 3:
            return {"status": "timeout"}
        return {
            "status": "message",
            "message": {
                "type": "MSG",
                "from": "worker",
                "to": "codex-chief",
                "action": "REPLY",
                "payload": "done",
            },
        }

    module.post_json = fake_post_json
    args = module.build_parser().parse_args(
        [
            "listen",
            "--config",
            str(config_path),
            "--timeout-seconds",
            "10",
            "--retry-delay-seconds",
            "0.01",
            "--stop-after-message",
        ]
    )
    payload = module.listen_for_session_message(args)

    assert calls == ["/sessions/status", "/sessions/wait", "/sessions/wait"]
    assert payload["status"] == "message"
    assert payload["message"]["action"] == "REPLY"
    assert payload["listener_mode"] == "persistent"


def test_listen_main_emits_single_json_line_with_stop_after_message(tmp_path: Path) -> None:
    module = _load_module("acp_dropin_runtime_listen_main", Path("ACP_AGENT/acp.py"))
    config_path = tmp_path / "codex-chief.json"
    config_path.write_text(
        json.dumps(
            {
                "agent_name": "codex-chief",
                "hub_http": "http://hub.example",
                "hub_ws": "ws://hub.example/ws",
                "session_id": "session-123",
                "member_token": "chief-token",
            }
        ),
        encoding="utf-8",
    )

    def fake_post_json(*, hub_http: str, route: str, payload: dict[str, object], token: str | None = None) -> dict[str, object]:
        if route == "/sessions/status":
            return {"status": "ok"}
        return {
            "status": "message",
            "message": {
                "type": "MSG",
                "from": "worker",
                "to": "codex-chief",
                "action": "REPLY",
                "payload": "done",
            },
        }

    module.post_json = fake_post_json
    stdout = StringIO()
    with redirect_stdout(stdout):
        exit_code = module.main(
            ["listen", "--config", str(config_path), "--stop-after-message"]
        )

    lines = [line for line in stdout.getvalue().splitlines() if line.strip()]
    assert exit_code == 0
    assert len(lines) == 1
    assert json.loads(lines[0])["status"] == "message"


def test_listen_clears_local_session_on_system_disconnect_notice(tmp_path: Path) -> None:
    module = _load_module("acp_dropin_runtime_system_notice", Path("ACP_AGENT/acp.py"))
    config_path = tmp_path / "codex-chief.json"
    config_path.write_text(
        json.dumps(
            {
                "agent_name": "codex-chief",
                "hub_http": "http://hub.example",
                "hub_ws": "ws://hub.example/ws",
                "session_id": "session-123",
                "member_token": "chief-token",
                "join_code": "ABC123",
                "member_role": "chief",
            }
        ),
        encoding="utf-8",
    )

    def fake_post_json(*, hub_http: str, route: str, payload: dict[str, object], token: str | None = None) -> dict[str, object]:
        if route == "/sessions/status":
            return {"status": "ok"}
        return {
            "status": "message",
            "message": {
                "type": "MSG",
                "from": "system",
                "to": "codex-chief",
                "action": "INFO",
                "payload": "session closed by admin",
                "session_id": "session-123",
                "system_event": "SESSION_CLOSED",
                "session_closed": True,
                "forced": True,
                "removed_by": "admin",
            },
        }

    module.post_json = fake_post_json

    payload = module.listen_for_session_message(
        module.build_parser().parse_args(
            [
                "listen",
                "--config",
                str(config_path),
            ]
        )
    )

    updated = json.loads(config_path.read_text(encoding="utf-8"))
    assert payload["session_credentials_cleared"] is True
    assert payload["session_notice"]["system_event"] == "SESSION_CLOSED"
    assert "session_id" not in updated
    assert "member_token" not in updated
    assert "join_code" not in updated
    assert "member_role" not in updated


def test_update_from_release_replaces_core_files_and_preserves_runtime_state(tmp_path: Path) -> None:
    module = _load_module("acp_dropin_updater", Path("ACP_AGENT/update_from_release.py"))
    target = tmp_path / "ACP_AGENT"
    target.mkdir()
    (target / "VERSION").write_text("0.1.0\n", encoding="utf-8")
    (target / "acp.py").write_text("old-client\n", encoding="utf-8")
    (target / "agents").mkdir()
    (target / "agents" / "codex-chief.json").write_text('{"agent_name":"codex-chief"}\n', encoding="utf-8")
    (target / "inbox").mkdir()
    (target / "inbox" / "keep.txt").write_text("preserve\n", encoding="utf-8")

    release_dir = tmp_path / "release"
    release_dir.mkdir()
    (release_dir / "VERSION").write_text("9.9.9\n", encoding="utf-8")
    (release_dir / "CHANGELOG.md").write_text("# ACP_AGENT Changelog\n\n## 9.9.9 - 2026-03-07\n\n- test release\n", encoding="utf-8")
    (release_dir / "acp.py").write_text("new-client\n", encoding="utf-8")
    (release_dir / "update_from_release.py").write_text("new-updater\n", encoding="utf-8")

    zip_path = tmp_path / "ACP_AGENT.zip"
    with zipfile.ZipFile(zip_path, "w") as archive:
        for file_path in release_dir.iterdir():
            archive.write(file_path, arcname=file_path.name)

    manifest_path = tmp_path / "ACP_AGENT.json"
    manifest_payload = {
        "product": "ACP_AGENT",
        "version": "9.9.9",
        "bundle_url": zip_path.as_uri(),
        "manifest_url": manifest_path.as_uri(),
        "downloads_page_url": "https://hub.example/downloads",
        "sha256": module._sha256_bytes(zip_path.read_bytes()),
        "changelog": [{"version": "9.9.9", "date": "2026-03-07", "notes": ["test release"]}],
    }
    manifest_path.write_text(json.dumps(manifest_payload), encoding="utf-8")

    result = module.update_from_manifest(target_dir=target, manifest_url=manifest_path.as_uri(), force=False)

    assert result["status"] == "updated"
    assert result["updated_version"] == "9.9.9"
    assert result["bundle_info"]["installed_version"] == "9.9.9"
    assert (target / "VERSION").read_text(encoding="utf-8").strip() == "9.9.9"
    assert (target / "acp.py").read_text(encoding="utf-8") == "new-client\n"
    bundle_info = json.loads((target / "BUNDLE_INFO.json").read_text(encoding="utf-8"))
    assert bundle_info["installed_version"] == "9.9.9"
    assert bundle_info["release_date"] == "2026-03-07"
    assert (target / "agents" / "codex-chief.json").exists()
    assert (target / "inbox" / "keep.txt").read_text(encoding="utf-8") == "preserve\n"


def test_update_check_reports_policy_status(tmp_path: Path) -> None:
    module = _load_module("acp_dropin_updater_policy", Path("ACP_AGENT/update_from_release.py"))
    target = tmp_path / "ACP_AGENT"
    target.mkdir()
    (target / "VERSION").write_text("0.1.0\n", encoding="utf-8")

    manifest_path = tmp_path / "ACP_AGENT.json"
    manifest_payload = {
        "product": "ACP_AGENT",
        "version": "0.3.0",
        "bundle_url": "https://hub.example/downloads/ACP_AGENT.zip",
        "update_policy": {
            "recommended_version": "0.3.0",
            "minimum_supported_version": "0.2.0",
            "policy_url": "https://hub.example/downloads",
        },
    }
    manifest_path.write_text(json.dumps(manifest_payload), encoding="utf-8")

    comparison = module.check_for_update(target_dir=target, manifest_url=manifest_path.as_uri())

    assert comparison["status"] == "update_available"
    assert comparison["policy_status"] == "required"
    assert comparison["update_required"] is True
    assert comparison["update_recommended"] is True


def test_update_from_manifest_refreshes_project_and_global_skills(tmp_path: Path) -> None:
    module = _load_module("acp_dropin_updater_skills", Path("ACP_AGENT/update_from_release.py"))
    target = tmp_path / "ACP_AGENT"
    target.mkdir()
    (target / "VERSION").write_text("0.1.0\n", encoding="utf-8")

    release_dir = tmp_path / "release"
    release_dir.mkdir()
    (release_dir / "VERSION").write_text("9.9.9\n", encoding="utf-8")
    (release_dir / "CHANGELOG.md").write_text("# ACP_AGENT Changelog\n\n## 9.9.9 - 2026-03-08\n\n- skill refresh\n", encoding="utf-8")
    (release_dir / "acp.py").write_text("new-client\n", encoding="utf-8")
    (release_dir / "update_from_release.py").write_text("new-updater\n", encoding="utf-8")
    skill_dir = release_dir / "skills" / "acp-session-coordinator"
    skill_dir.mkdir(parents=True)
    (skill_dir / "SKILL.md").write_text("fresh skill\n", encoding="utf-8")

    zip_path = tmp_path / "ACP_AGENT.zip"
    with zipfile.ZipFile(zip_path, "w") as archive:
        for file_path in release_dir.rglob("*"):
            archive.write(file_path, arcname=file_path.relative_to(release_dir))

    manifest_path = tmp_path / "ACP_AGENT.json"
    manifest_payload = {
        "product": "ACP_AGENT",
        "version": "9.9.9",
        "bundle_url": zip_path.as_uri(),
        "manifest_url": manifest_path.as_uri(),
        "sha256": module._sha256_bytes(zip_path.read_bytes()),
        "changelog": [{"version": "9.9.9", "date": "2026-03-08", "notes": ["skill refresh"]}],
    }
    manifest_path.write_text(json.dumps(manifest_payload), encoding="utf-8")

    project_skill_home = tmp_path / ".codex" / "skills"
    global_skill_home = tmp_path / "global-home" / ".codex" / "skills"

    result = module.update_from_manifest(
        target_dir=target,
        manifest_url=manifest_path.as_uri(),
        force=False,
        project_skill_home=project_skill_home,
        global_skill_home=global_skill_home,
    )

    assert result["status"] == "updated"
    assert (project_skill_home / "acp-session-coordinator" / "SKILL.md").read_text(encoding="utf-8") == "fresh skill\n"
    assert (global_skill_home / "acp-session-coordinator" / "SKILL.md").read_text(encoding="utf-8") == "fresh skill\n"
    assert len(result["updated_skills"]) == 2


def test_sync_skill_installs_can_refresh_claude_skill_home(tmp_path: Path) -> None:
    module = _load_module("acp_dropin_updater_claude_skills", Path("ACP_AGENT/update_from_release.py"))
    target = tmp_path / "ACP_AGENT"
    skill_dir = target / "skills" / "acp-session-coordinator"
    skill_dir.mkdir(parents=True)
    (skill_dir / "SKILL.md").write_text("fresh skill\n", encoding="utf-8")

    updated = module.sync_skill_installs(
        target_dir=target,
        project_skill_home=tmp_path / ".codex" / "skills",
        global_skill_home=tmp_path / "home" / ".codex" / "skills",
        claude_skill_home=tmp_path / "home" / ".claude" / "skills",
    )

    assert (tmp_path / "home" / ".claude" / "skills" / "acp-session-coordinator" / "SKILL.md").read_text(
        encoding="utf-8"
    ) == "fresh skill\n"
    assert len(updated) == 3


def test_status_can_hold_busy_with_periodic_heartbeats(tmp_path: Path) -> None:
    module = _load_module("acp_dropin_runtime_status_hold", Path("ACP_AGENT/acp.py"))
    config_path = tmp_path / "codex-chief.json"
    config_path.write_text(
        json.dumps(
            {
                "agent_name": "codex-chief",
                "hub_http": "http://hub.example",
                "hub_ws": "ws://hub.example/ws",
                "session_id": "session-123",
                "member_token": "chief-token",
            }
        ),
        encoding="utf-8",
    )

    calls: list[str] = []

    def fake_post_json(*, hub_http: str, route: str, payload: dict[str, object], token: str | None = None) -> dict[str, object]:
        calls.append(route)
        if route == "/sessions/status":
            return {"status": "ok", "member": {"status": "busy"}}
        if route == "/sessions/heartbeat":
            return {"status": "ok", "member": {"status": "busy", "status_text": payload.get("detail")}}
        raise AssertionError(route)

    monotonic_values = iter([0.0, 0.0, 20.0, 20.0, 40.0, 40.0, 61.0])

    module.post_json = fake_post_json
    original_sleep = module.time.sleep
    original_monotonic = module.time.monotonic
    try:
        module.time.sleep = lambda _: None
        module.time.monotonic = lambda: next(monotonic_values)

        payload = module.update_session_status(
            module.build_parser().parse_args(
                [
                    "status",
                    "--config",
                    str(config_path),
                    "--state",
                    "busy",
                    "--text",
                    "implementing auth flow",
                    "--heartbeat-window-minutes",
                    "1",
                    "--heartbeat-interval-seconds",
                    "20",
                ]
            )
        )
    finally:
        module.time.sleep = original_sleep
        module.time.monotonic = original_monotonic

    assert calls == ["/sessions/status", "/sessions/heartbeat", "/sessions/heartbeat"]
    assert payload["heartbeat_count"] == 2
    assert payload["heartbeat_failures"] == 0
    assert payload["member"]["status_text"] == "implementing auth flow"


def test_wait_window_can_auto_start_busy_hold_for_marked_task(tmp_path: Path) -> None:
    module = _load_module("acp_dropin_runtime_wait_window_auto_busy", Path("ACP_AGENT/acp.py"))
    config_path = tmp_path / "codex-chief.json"
    config_path.write_text(
        json.dumps(
            {
                "agent_name": "codex-chief",
                "hub_http": "http://hub.example",
                "hub_ws": "ws://hub.example/ws",
                "session_id": "session-123",
                "member_token": "chief-token",
            }
        ),
        encoding="utf-8",
    )

    calls: list[str] = []

    def fake_post_json(*, hub_http: str, route: str, payload: dict[str, object], token: str | None = None) -> dict[str, object]:
        calls.append(route)
        if route == "/sessions/status":
            return {"status": "ok"}
        if route == "/sessions/wait":
            return {
                "status": "message",
                "message": {
                    "type": "MSG",
                    "from": "chief",
                    "to": "codex-chief",
                    "action": "TASK",
                    "payload": "[busy-hold:15] Implement auth hardening",
                },
            }
        raise AssertionError(route)

    launched: dict[str, object] = {}

    def fake_auto_busy(**kwargs: object) -> dict[str, object]:
        launched.update(kwargs)
        return {"status": "started", "window_minutes": 15.0}

    module.post_json = fake_post_json
    module.maybe_start_auto_busy_hold = fake_auto_busy

    payload = module.wait_window_for_session_message(
        module.build_parser().parse_args(
            [
                "wait-window",
                "--config",
                str(config_path),
                "--window-minutes",
                "20",
                "--auto-busy-heartbeat-minutes",
                "30",
            ]
        )
    )

    assert calls == ["/sessions/status", "/sessions/wait"]
    assert payload["auto_busy_hold"]["status"] == "started"
    assert launched["default_window_minutes"] == 30.0
    assert launched["interval_seconds"] == 45.0


def test_listen_stop_after_message_can_auto_start_busy_hold_for_marked_task(tmp_path: Path) -> None:
    module = _load_module("acp_dropin_runtime_listen_auto_busy", Path("ACP_AGENT/acp.py"))
    config_path = tmp_path / "codex-chief.json"
    config_path.write_text(
        json.dumps(
            {
                "agent_name": "codex-chief",
                "hub_http": "http://hub.example",
                "hub_ws": "ws://hub.example/ws",
                "session_id": "session-123",
                "member_token": "chief-token",
            }
        ),
        encoding="utf-8",
    )

    def fake_post_json(*, hub_http: str, route: str, payload: dict[str, object], token: str | None = None) -> dict[str, object]:
        if route == "/sessions/status":
            return {"status": "ok"}
        return {
            "status": "message",
            "message": {
                "type": "MSG",
                "from": "chief",
                "to": "codex-chief",
                "action": "TASK",
                "payload": "[long] Review the auth migration plan",
            },
        }

    launched: dict[str, object] = {}

    def fake_auto_busy(**kwargs: object) -> dict[str, object]:
        launched.update(kwargs)
        return {"status": "started", "window_minutes": 25.0}

    module.post_json = fake_post_json
    module.maybe_start_auto_busy_hold = fake_auto_busy

    payload = module.listen_for_session_message(
        module.build_parser().parse_args(
            [
                "listen",
                "--config",
                str(config_path),
                "--stop-after-message",
                "--auto-busy-heartbeat-minutes",
                "25",
            ]
        )
    )

    assert payload["auto_busy_hold"]["status"] == "started"
    assert launched["default_window_minutes"] == 25.0


def test_listen_auto_busy_requires_stop_after_message(tmp_path: Path) -> None:
    module = _load_module("acp_dropin_runtime_listen_auto_busy_guard", Path("ACP_AGENT/acp.py"))
    config_path = tmp_path / "codex-chief.json"
    config_path.write_text(
        json.dumps(
            {
                "agent_name": "codex-chief",
                "hub_http": "http://hub.example",
                "hub_ws": "ws://hub.example/ws",
                "session_id": "session-123",
                "member_token": "chief-token",
            }
        ),
        encoding="utf-8",
    )

    try:
        module.listen_for_session_message(
            module.build_parser().parse_args(
                [
                    "listen",
                    "--config",
                    str(config_path),
                    "--auto-busy-heartbeat-minutes",
                    "10",
                ]
            )
        )
    except ValueError as exc:
        assert "--stop-after-message" in str(exc)
    else:
        raise AssertionError("listen should require stop-after-message for auto busy hold")


def test_listen_fails_fast_on_auth_error(tmp_path: Path) -> None:
    module = _load_module("acp_dropin_runtime_listen_auth", Path("ACP_AGENT/acp.py"))
    config_path = tmp_path / "codex-chief.json"
    config_path.write_text(
        json.dumps(
            {
                "agent_name": "codex-chief",
                "hub_http": "http://hub.example",
                "hub_ws": "ws://hub.example/ws",
                "session_id": "session-123",
                "member_token": "chief-token",
            }
        ),
        encoding="utf-8",
    )

    def fake_post_json(*, hub_http: str, route: str, payload: dict[str, object], token: str | None = None) -> dict[str, object]:
        raise ValueError("hub HTTP 401: {\"status\":\"error\",\"code\":\"AUTH_REQUIRED\"}")

    module.post_json = fake_post_json
    args = module.build_parser().parse_args(["listen", "--config", str(config_path)])

    try:
        module.listen_for_session_message(args)
    except ValueError as exc:
        assert "AUTH_REQUIRED" in str(exc)
    else:
        raise AssertionError("listen should fail fast on auth errors")
