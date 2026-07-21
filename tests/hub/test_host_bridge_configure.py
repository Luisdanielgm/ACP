from __future__ import annotations

import argparse
import importlib.util
import json
import sys
from pathlib import Path
from typing import Any

import pytest


repo_root = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(repo_root / "ACP_AGENT"))
_ACP_SPEC = importlib.util.spec_from_file_location("acp_agent_host_bridge_configure", repo_root / "ACP_AGENT" / "acp.py")
assert _ACP_SPEC is not None and _ACP_SPEC.loader is not None
acp_cli = importlib.util.module_from_spec(_ACP_SPEC)
sys.modules[_ACP_SPEC.name] = acp_cli
_ACP_SPEC.loader.exec_module(acp_cli)

from host_bridge import HostBindingError, HostDelivery  # noqa: E402


def _delivery(*, sender: str, reply_to: str | None = None) -> HostDelivery:
    return HostDelivery(
        message_id="m1", correlation_id="c1", sender=sender, instructions="do", reply_to=reply_to
    )


def _base_config(**overrides: Any) -> dict[str, Any]:
    config = {
        "agent_name": "codex-task-code",
        "hub_http": "https://hub.example",
        "session_id": "coordination-session",
        "member_token": "SECRET-member-token",
        "token": "SECRET-acp-token",
        "custom_unknown_field": {"nested": "preserved"},
    }
    config.update(overrides)
    return config


def test_worker_profile_routes_task_results_directly_to_configured_coordinator() -> None:
    config, summary = acp_cli.build_host_bridge_profile(
        _base_config(),
        agent_name="codex-task-code",
        role="worker",
        adapter_id="codex_app_server_stdio",
        host_session_id="thread-code-1",
        executable=r"C:\Tools\codex.exe",
        coordinator="codex-chief",
    )

    assert config["host_bridge_reply_to"] == "codex-chief"
    assert config["host_bridge_allowed_senders"] == ["codex-chief"]
    assert config["host_bridge_accepted_actions"] == ["TASK", "REPLY", "INFO"]
    assert config["host_bridge_thread_id"] == "thread-code-1"
    assert config["host_bridge_adapter_id"] == "codex_app_server_stdio"
    assert config["host_bridge_executable"] == r"C:\Tools\codex.exe"
    assert config["host_profile_schema_version"] == acp_cli.HOST_PROFILE_SCHEMA_VERSION
    assert summary["reply_to"] == "codex-chief"
    assert summary["role"] == "worker"


def test_generic_member_profile_uses_explicit_senders_without_named_topology() -> None:
    config, summary = acp_cli.build_host_bridge_profile(
        _base_config(agent_name="codex-chief"),
        agent_name="codex-chief",
        role="member",
        adapter_id="codex_app_server_stdio",
        host_session_id="thread-chief-1",
        executable=r"C:\Tools\codex.exe",
        extra_allowed_senders=("worker-a", "worker-b"),
    )

    assert config["host_bridge_allowed_senders"] == ["worker-a", "worker-b"]
    assert config["host_bridge_accepted_actions"] == ["TASK", "REPLY", "INFO"]
    assert "host_bridge_reply_to" not in config
    assert summary["reply_to"] is None


def test_member_profile_preserves_an_explicit_generic_reply_target() -> None:
    config, summary = acp_cli.build_host_bridge_profile(
        _base_config(agent_name="agent-a"),
        agent_name="agent-a",
        role="member",
        adapter_id="codex_app_server_stdio",
        host_session_id="thread-chief-1",
        executable=r"C:\Tools\codex.exe",
        reply_to="agent-b",
        extra_allowed_senders=("agent-b",),
    )

    assert config["host_bridge_reply_to"] == "agent-b"
    assert summary["reply_to"] == "agent-b"


def test_migrates_legacy_codex_session_id_to_thread_id_and_stamps_version() -> None:
    legacy = _base_config(
        host_bridge_adapter_id="codex_app_server",
        host_bridge_endpoint="ws://127.0.0.1:4500",
        host_bridge_session_id="legacy-thread-id",  # old key, no schema version
    )
    assert "host_profile_schema_version" not in legacy

    config, summary = acp_cli.build_host_bridge_profile(
        legacy,
        agent_name="codex-task-code",
        role="worker",
        adapter_id="codex_app_server",
        endpoint="ws://127.0.0.1:4500",
        coordinator="codex-chief",
    )

    assert config["host_bridge_thread_id"] == "legacy-thread-id"
    assert "host_bridge_session_id" not in config
    assert config["host_profile_schema_version"] == acp_cli.HOST_PROFILE_SCHEMA_VERSION
    assert summary["prior_schema_version"] is None
    assert any("host_bridge_session_id -> host_bridge_thread_id" in note for note in summary["migrated"])


def test_migrates_task_only_worker_to_direct_multi_action_ingress() -> None:
    legacy = _base_config(
        host_bridge_wait_action="TASK",
        host_bridge_reply_to="old-result-router",
        host_bridge_allowed_senders=["coordinator"],
    )

    config, summary = acp_cli.build_host_bridge_profile(
        legacy,
        agent_name="worker-a",
        role="worker",
        adapter_id="codex_app_server_stdio",
        host_session_id="thread-worker-a",
        executable=r"C:\Tools\codex.exe",
        coordinator="coordinator",
        accepted_actions=("TASK", "REPLY", "INFO"),
    )

    assert "host_bridge_wait_action" not in config
    assert config["host_bridge_accepted_actions"] == ["TASK", "REPLY", "INFO"]
    assert config["host_bridge_reply_to"] == "coordinator"
    assert summary["schema_version"] == 2


def test_preserves_secrets_and_unknown_keys() -> None:
    config, _summary = acp_cli.build_host_bridge_profile(
        _base_config(),
        agent_name="codex-task-code",
        role="worker",
        adapter_id="codex_cli",
        host_session_id="session-code-1",
        executable="/usr/local/bin/codex",
        coordinator="codex-chief",
    )

    assert config["member_token"] == "SECRET-member-token"
    assert config["token"] == "SECRET-acp-token"
    assert config["session_id"] == "coordination-session"
    assert config["custom_unknown_field"] == {"nested": "preserved"}


def test_listener_config_is_explicit_and_kept_separate_from_host_binding() -> None:
    config, summary = acp_cli.build_host_bridge_profile(
        _base_config(),
        agent_name="codex-task-code",
        role="member",
        adapter_id="codex_app_server_stdio",
        host_session_id="thread-code-1",
        executable=r"C:\Tools\codex.exe",
        listener_config="agents/coordinator-listener.json",
        extra_allowed_senders=("codex-chief",),
    )

    assert config["host_bridge_listener_config"] == "agents/coordinator-listener.json"
    assert summary["listener_config"] == "agents/coordinator-listener.json"
    assert summary["host_id"] == "thread-code-1"


def test_configure_is_idempotent() -> None:
    kwargs = dict(
        agent_name="codex-task-code",
        role="worker",
        adapter_id="codex_app_server_stdio",
        host_session_id="thread-code-1",
        executable=r"C:\Tools\codex.exe",
        coordinator="codex-chief",
    )
    first, _ = acp_cli.build_host_bridge_profile(_base_config(), **kwargs)
    second, _ = acp_cli.build_host_bridge_profile(dict(first), **kwargs)

    assert first == second
    # Allowlist is not duplicated across repeated runs.
    assert second["host_bridge_allowed_senders"] == ["codex-chief"]


def test_extra_allow_senders_merge_without_duplicates() -> None:
    config, _ = acp_cli.build_host_bridge_profile(
        _base_config(host_bridge_allowed_senders=["codex-chief", "auditor"]),
        agent_name="codex-task-code",
        role="worker",
        adapter_id="codex_app_server_stdio",
        host_session_id="thread-code-1",
        executable=r"C:\Tools\codex.exe",
        coordinator="codex-chief",
        extra_allowed_senders=("auditor", "reviewer"),
    )

    assert config["host_bridge_allowed_senders"] == ["codex-chief", "auditor", "reviewer"]


def test_member_reply_to_cannot_equal_own_identity() -> None:
    with pytest.raises(HostBindingError, match="differ from the bridge member identity"):
        acp_cli.build_host_bridge_profile(
            _base_config(agent_name="agent-a"),
            agent_name="agent-a",
            role="member",
            adapter_id="codex_app_server_stdio",
            host_session_id="thread-1",
            executable=r"C:\Tools\codex.exe",
            reply_to="agent-a",
            extra_allowed_senders=("agent-b",),
        )


def test_worker_requires_coordinator() -> None:
    with pytest.raises(HostBindingError, match="requires --coordinator"):
        acp_cli.build_host_bridge_profile(
            _base_config(),
            agent_name="codex-task-code",
            role="worker",
            adapter_id="codex_app_server_stdio",
            host_session_id="thread-1",
            executable=r"C:\Tools\codex.exe",
        )


def test_claude_desktop_cannot_be_configured() -> None:
    with pytest.raises(HostBindingError, match="UNSUPPORTED_PENDING_OFFICIAL_INTERFACE"):
        acp_cli.build_host_bridge_profile(
            _base_config(),
            agent_name="codex-task-code",
            role="worker",
            adapter_id="claude_desktop",
            host_session_id="thread-1",
            coordinator="codex-chief",
        )


def test_cli_adapter_requires_absolute_executable() -> None:
    with pytest.raises(HostBindingError, match="absolute path"):
        acp_cli.build_host_bridge_profile(
            _base_config(),
            agent_name="codex-task-code",
            role="worker",
            adapter_id="codex_cli",
            host_session_id="session-1",
            executable="codex",
            coordinator="codex-chief",
        )


def test_codex_app_server_rejects_directory() -> None:
    with pytest.raises(HostBindingError, match="does not accept directory"):
        acp_cli.build_host_bridge_profile(
            _base_config(),
            agent_name="codex-task-code",
            role="worker",
            adapter_id="codex_app_server",
            endpoint="ws://127.0.0.1:4500",
            host_session_id="thread-1",
            directory="C:/repo",
            coordinator="codex-chief",
        )


def test_worker_coordinator_flow_has_no_collector_or_reply_loop() -> None:
    worker_cfg, _ = acp_cli.build_host_bridge_profile(
        _base_config(agent_name="codex-task-code"),
        agent_name="codex-task-code",
        role="worker",
        adapter_id="codex_app_server_stdio",
        host_session_id="thread-code-1",
        executable=r"C:\Tools\codex.exe",
        coordinator="codex-chief",
    )
    coordinator_cfg, _ = acp_cli.build_host_bridge_profile(
        _base_config(agent_name="codex-chief"),
        agent_name="codex-chief",
        role="coordinator",
        adapter_id="codex_app_server_stdio",
        host_session_id="thread-chief-1",
        executable=r"C:\Tools\codex.exe",
        extra_allowed_senders=("codex-task-code",),
    )

    # Worker handling a plain TASK from the coordinator replies directly to it.
    worker_target = acp_cli._host_bridge_reply_target(
        _delivery(sender="codex-chief"), worker_cfg.get("host_bridge_reply_to")
    )
    assert worker_target == "codex-chief"

    assert coordinator_cfg["host_bridge_allowed_senders"] == ["codex-task-code"]
    assert coordinator_cfg["host_bridge_accepted_actions"] == ["TASK", "REPLY", "INFO"]


def _configure_args(config_path: Path, **overrides: Any) -> argparse.Namespace:
    namespace = argparse.Namespace(
        command="host-bridge",
        host_bridge_command="configure",
        config=str(config_path),
        agent=None,
        role="worker",
        adapter_id="codex_app_server_stdio",
        host_session_id="thread-code-1",
        endpoint=None,
        host_executable=r"C:\Tools\codex.exe",
        directory=None,
        credential_ref=None,
        member_token_ref=None,
        reply_collector=None,
        reply_to=None,
        accepted_actions=None,
        coordinator="codex-chief",
        bridge_allowed_senders=None,
        state_path=None,
        check=False,
    )
    for key, value in overrides.items():
        setattr(namespace, key, value)
    return namespace


def test_configure_command_writes_atomically_and_is_idempotent(tmp_path: Path) -> None:
    config_path = tmp_path / "codex-task-code.json"
    config_path.write_text(json.dumps(_base_config()), encoding="utf-8")

    first = acp_cli.host_bridge_configure_command(_configure_args(config_path))
    assert first["status"] == "configured"
    assert first["written"] is True
    written = json.loads(config_path.read_text(encoding="utf-8"))
    assert written["host_bridge_reply_to"] == "codex-chief"
    assert written["member_token"] == "SECRET-member-token"

    acp_cli.host_bridge_configure_command(_configure_args(config_path))
    rewritten = json.loads(config_path.read_text(encoding="utf-8"))
    assert rewritten == written


def test_configure_command_persists_listener_member_token_reference_without_secret(
    tmp_path: Path,
) -> None:
    config_path = tmp_path / "coordinator-listener.json"
    config_path.write_text(json.dumps(_base_config(member_token=None)), encoding="utf-8")

    result = acp_cli.host_bridge_configure_command(
        _configure_args(
            config_path,
            role="member",
            agent="coordinator-listener",
            member_token_ref="env:ACP_COORDINATOR_LISTENER_TOKEN",
            coordinator=None,
            bridge_allowed_senders=["codex-pilot-coordinator"],
        )
    )

    written = json.loads(config_path.read_text(encoding="utf-8"))
    assert result["member_token_ref"] == "env:ACP_COORDINATOR_LISTENER_TOKEN"
    assert written["member_token_ref"] == "env:ACP_COORDINATOR_LISTENER_TOKEN"
    assert written.get("member_token") in {None, ""}


def test_configure_check_mode_does_not_write(tmp_path: Path) -> None:
    config_path = tmp_path / "codex-task-code.json"
    original = _base_config()
    config_path.write_text(json.dumps(original), encoding="utf-8")

    result = acp_cli.host_bridge_configure_command(_configure_args(config_path, check=True))

    assert result["status"] == "checked"
    assert result["written"] is False
    assert json.loads(config_path.read_text(encoding="utf-8")) == original


def test_configure_summary_never_contains_secret_values(tmp_path: Path) -> None:
    config_path = tmp_path / "codex-task-code.json"
    config_path.write_text(json.dumps(_base_config()), encoding="utf-8")

    result = acp_cli.host_bridge_configure_command(
        _configure_args(config_path, credential_ref="env:CODEX_CREDENTIAL")
    )

    serialized = json.dumps(result)
    assert "SECRET-member-token" not in serialized
    assert "SECRET-acp-token" not in serialized
    assert result["credential_ref"] == "env:CODEX_CREDENTIAL"  # env reference, not the value


def test_configure_cli_parser_accepts_role_and_adapter() -> None:
    parser = acp_cli.build_parser()
    args = parser.parse_args(
        [
            "host-bridge",
            "configure",
            "--config",
            "ACP_AGENT/agents/codex-task-code.json",
            "--role",
            "worker",
            "--adapter-id",
            "codex_app_server_stdio",
            "--host-thread-id",
            "thread-code-1",
            "--host-executable",
            r"C:\Tools\codex.exe",
            "--coordinator",
            "codex-chief",
        ]
    )

    assert args.role == "worker"
    assert args.adapter_id == "codex_app_server_stdio"
    assert args.host_session_id == "thread-code-1"
    assert args.coordinator == "codex-chief"
