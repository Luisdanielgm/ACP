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
_ACP_SPEC = importlib.util.spec_from_file_location("acp_agent_host_supervisor_generate", repo_root / "ACP_AGENT" / "acp.py")
assert _ACP_SPEC is not None and _ACP_SPEC.loader is not None
acp_cli = importlib.util.module_from_spec(_ACP_SPEC)
sys.modules[_ACP_SPEC.name] = acp_cli
_ACP_SPEC.loader.exec_module(acp_cli)


def _write_agent(dir_path: Path, name: str, **fields: Any) -> Path:
    config = {"agent_name": name, "hub_http": "https://hub.example", "session_id": "s", "member_token": "t"}
    config.update(fields)
    path = dir_path / f"{name}.json"
    path.write_text(json.dumps(config), encoding="utf-8")
    return path


def _generate_args(**overrides: Any) -> argparse.Namespace:
    namespace = argparse.Namespace(
        command="host-supervisor",
        action="generate",
        config=None,
        state_dir=None,
        max_cycles=None,
        output=None,
        coordinator=None,
        workers=None,
        reply_collector=None,
        python_executable="/usr/bin/python3",
        acp_script="/opt/acp/ACP_AGENT/acp.py",
        check=False,
    )
    for key, value in overrides.items():
        setattr(namespace, key, value)
    return namespace


def test_generate_keeps_optional_legacy_result_router_compatible(tmp_path: Path) -> None:
    chief = _write_agent(
        tmp_path, "codex-chief",
        host_bridge_adapter_id="codex_app_server", host_bridge_endpoint="ws://127.0.0.1:4500",
    )
    code = _write_agent(tmp_path, "codex-task-code", host_bridge_adapter_id="codex_app_server_stdio")
    collector = _write_agent(tmp_path, "result-router")
    output = tmp_path / "supervisor.json"

    result = acp_cli.host_supervisor_generate_command(
        _generate_args(
            output=str(output),
            coordinator=str(chief),
            workers=[str(code)],
            reply_collector=str(collector),
        )
    )

    assert result["status"] == "generated"
    assert result["written"] is True
    assert result["autostart"] == "not_installed"
    assert result["bridges"] == ["codex-chief", "codex-task-code", "result-router"]

    written = json.loads(output.read_text(encoding="utf-8"))
    bridges = {entry["name"]: entry for entry in written["host_supervisor_bridges"]}
    assert bridges["codex-chief"]["command"][2:4] == ["host-bridge", "start"]
    assert bridges["codex-chief"]["endpoint"] == "ws://127.0.0.1:4500"  # endpoint-serialized adapter
    assert "endpoint" not in bridges["codex-task-code"]  # stdio has no endpoint lock
    collector_command = bridges["result-router"]["command"]
    assert collector_command[2:4] == ["reply-collector", "start"]
    assert "--forward-to" in collector_command
    assert collector_command[collector_command.index("--forward-to") + 1] == "codex-chief"
    assert collector_command[-2:] == ["--forward-action", "TASK"]


def test_generate_defaults_to_only_generic_host_bridges(tmp_path: Path) -> None:
    coordinator = _write_agent(tmp_path, "coordinator", host_bridge_adapter_id="codex_app_server_stdio")
    worker = _write_agent(tmp_path, "worker-a", host_bridge_adapter_id="codex_app_server_stdio")
    output = tmp_path / "supervisor.json"

    result = acp_cli.host_supervisor_generate_command(
        _generate_args(output=str(output), coordinator=str(coordinator), workers=[str(worker)])
    )

    assert result["bridges"] == ["coordinator", "worker-a"]
    written = json.loads(output.read_text(encoding="utf-8"))
    assert all(spec["command"][2:4] == ["host-bridge", "start"] for spec in written["host_supervisor_bridges"])


def test_generate_check_mode_does_not_write(tmp_path: Path) -> None:
    chief = _write_agent(tmp_path, "codex-chief", host_bridge_adapter_id="codex_app_server_stdio")
    collector = _write_agent(tmp_path, "result-router")
    output = tmp_path / "supervisor.json"

    result = acp_cli.host_supervisor_generate_command(
        _generate_args(output=str(output), coordinator=str(chief), reply_collector=str(collector), check=True)
    )

    assert result["status"] == "checked"
    assert result["written"] is False
    assert not output.exists()


def test_generate_reuses_existing_supervisor_specs(tmp_path: Path) -> None:
    """The generated config is consumable by the existing _supervisor_specs parser."""
    chief = _write_agent(tmp_path, "codex-chief", host_bridge_adapter_id="codex_app_server_stdio")
    collector = _write_agent(tmp_path, "result-router")
    output = tmp_path / "supervisor.json"

    acp_cli.host_supervisor_generate_command(
        _generate_args(output=str(output), coordinator=str(chief), reply_collector=str(collector))
    )

    specs = acp_cli._supervisor_specs(output)
    assert tuple(spec["name"] for spec in specs) == ("codex-chief", "result-router")
    for spec in specs:
        assert isinstance(spec["command"], list) and all(isinstance(part, str) for part in spec["command"])


def test_generate_rejects_duplicate_names(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="duplicate supervisor bridge name"):
        acp_cli.build_supervisor_bridges(
            [
                {"name": "dup", "config_path": "a.json", "kind": "host_bridge"},
                {"name": "dup", "config_path": "b.json", "kind": "host_bridge"},
            ],
            python_executable="python",
            acp_script="acp.py",
        )


def test_generate_requires_output_and_coordinator(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="requires --output"):
        acp_cli.host_supervisor_generate_command(_generate_args(coordinator="codex-chief"))


def test_supervisor_once_keeps_other_bridges_alive_when_one_config_is_reserved(
    tmp_path: Path, monkeypatch: Any
) -> None:
    config = tmp_path / "supervisor.json"
    config.write_text(
        json.dumps(
            {
                "host_supervisor_bridges": [
                    {"name": "coordinator", "command": ["python", "bridge.py"]},
                    {"name": "worker", "command": ["python", "bridge.py"]},
                ]
            }
        ),
        encoding="utf-8",
    )

    class FakeSupervisor:
        def __init__(self, spec: Any, _paths: Any) -> None:
            self.spec = spec

        def reconcile(self) -> dict[str, Any]:
            if self.spec.name == "coordinator":
                raise ValueError("config coordinator.json is reserved by another process")
            return {"status": "running", "pid": 42}

    monkeypatch.setattr(acp_cli, "HostBridgeSupervisor", FakeSupervisor)
    result = acp_cli.host_supervisor_command(
        argparse.Namespace(
            action="once",
            config=str(config),
            state_dir=str(tmp_path / "state"),
            max_cycles=None,
        )
    )

    assert result["status"] == "ok"
    assert result["bridges"] == [
        {"status": "reserved", "reason": "config reserved by another process"},
        {"status": "running", "pid": 42},
    ]
