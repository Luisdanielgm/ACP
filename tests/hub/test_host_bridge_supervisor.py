from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest


ACP_AGENT = Path(__file__).resolve().parents[2] / "ACP_AGENT"
sys.path.insert(0, str(ACP_AGENT))

import host_bridge_supervisor as supervisor_module
from host_bridge_supervisor import BridgeSpec, HostBridgeSupervisor, SupervisorPaths


class FakeProcess:
    def __init__(self, pid: int) -> None:
        self.pid = pid


def build_supervisor(tmp_path: Path, **overrides):
    calls: dict[str, list] = {"spawn": [], "sleep": [], "terminate": [], "probe": []}
    alive = overrides.pop("alive", lambda _pid: False)

    def spawn(spec, log_path):
        calls["spawn"].append((spec, log_path))
        return FakeProcess(9001)

    def probe(url, timeout):
        calls["probe"].append((url, timeout))
        return True

    spec = BridgeSpec("codex", ("python", "bridge.py"), **overrides)
    supervisor = HostBridgeSupervisor(
        spec,
        SupervisorPaths.for_bridge(tmp_path, spec.name),
        process_alive=alive,
        spawn=spawn,
        terminate=lambda pid: calls["terminate"].append(pid) or True,
        health_probe=probe,
        sleep=lambda seconds: calls["sleep"].append(seconds),
    )
    return supervisor, calls


def test_spec_requires_an_explicit_command_and_safe_name():
    with pytest.raises(ValueError):
        BridgeSpec("bad/name", ("python",))
    with pytest.raises(ValueError):
        BridgeSpec("ok", ())


def test_paths_are_scoped_beneath_root(tmp_path):
    paths = SupervisorPaths.for_bridge(tmp_path, "codex")
    assert paths.state_path == tmp_path / "codex.state.json"
    assert paths.log_path == tmp_path / "codex.log"


def test_windows_pid_health_never_uses_os_kill(monkeypatch):
    monkeypatch.setattr(supervisor_module.os, "name", "nt")
    monkeypatch.setattr(supervisor_module, "_windows_process_is_alive", lambda pid: pid == 42)
    monkeypatch.setattr(
        supervisor_module.os, "kill", lambda *_args: pytest.fail("Windows PID health signaled a process")
    )
    assert supervisor_module.process_is_alive(42) is True


def test_windows_termination_uses_bounded_force_fallback(monkeypatch):
    calls: list[list[str]] = []

    def run(command, **_kwargs):
        calls.append(command)
        return subprocess.CompletedProcess(command, 1 if len(calls) == 1 else 0)

    monkeypatch.setattr(supervisor_module.os, "name", "nt")
    monkeypatch.setattr(supervisor_module.subprocess, "run", run)

    assert supervisor_module._terminate_process(55) is True
    assert calls == [
        ["taskkill", "/PID", "55", "/T"],
        ["taskkill", "/PID", "55", "/T", "/F"],
    ]


def test_first_reconcile_starts_bridge_and_writes_atomic_state(tmp_path):
    supervisor, calls = build_supervisor(tmp_path)
    result = supervisor.reconcile()

    assert result["status"] == "running"
    assert result["pid"] == 9001
    assert len(calls["spawn"]) == 1
    assert json.loads(supervisor.paths.state_path.read_text())["restarts"] == 0
    assert not list(tmp_path.glob("*.tmp"))


def test_live_pid_with_explicit_healthy_url_is_adopted(tmp_path):
    supervisor, calls = build_supervisor(
        tmp_path, alive=lambda pid: pid == 41, health_url="http://127.0.0.1:8765/health"
    )
    supervisor.paths.state_path.parent.mkdir(parents=True, exist_ok=True)
    supervisor.paths.state_path.write_text(json.dumps({"pid": 41, "restarts": 0}))

    result = supervisor.reconcile()

    assert result["pid"] == 41
    assert calls["spawn"] == []
    assert calls["probe"] == [("http://127.0.0.1:8765/health", 2.0)]


def test_stale_pid_is_recovered_with_bounded_backoff(tmp_path):
    supervisor, calls = build_supervisor(tmp_path, restart_limit=2, backoff_seconds=0.25)
    supervisor.paths.state_path.parent.mkdir(parents=True, exist_ok=True)
    supervisor.paths.state_path.write_text(json.dumps({"pid": 12, "restarts": 0}))

    result = supervisor.reconcile()

    assert result["status"] == "running"
    assert result["restarts"] == 1
    assert calls["sleep"] == [0.25]


def test_restart_limit_prevents_a_respawn_loop(tmp_path):
    supervisor, calls = build_supervisor(tmp_path, restart_limit=2)
    supervisor.paths.state_path.parent.mkdir(parents=True, exist_ok=True)
    supervisor.paths.state_path.write_text(json.dumps({"pid": 12, "restarts": 2}))

    result = supervisor.reconcile()

    assert result["status"] == "restart_limit"
    assert calls["spawn"] == []


def test_unhealthy_live_bridge_is_stopped_before_restart(tmp_path):
    alive_calls = {"count": 0}
    def alive(pid):
        alive_calls["count"] += 1
        return pid == 77 and alive_calls["count"] == 1
    supervisor, calls = build_supervisor(
        tmp_path, alive=alive, health_url="http://127.0.0.1:8765/health"
    )
    supervisor._health_probe = lambda *_args: False
    supervisor.paths.state_path.parent.mkdir(parents=True, exist_ok=True)
    supervisor.paths.state_path.write_text(json.dumps({"pid": 77, "restarts": 0}))

    result = supervisor.reconcile()

    assert result["pid"] == 9001
    assert calls["terminate"] == [77]


def test_stop_terminates_only_recorded_live_pid_and_clears_state(tmp_path):
    supervisor, calls = build_supervisor(tmp_path, alive=lambda pid: pid == 55)
    supervisor.paths.state_path.parent.mkdir(parents=True, exist_ok=True)
    supervisor.paths.state_path.write_text(json.dumps({"pid": 55, "restarts": 1}))

    result = supervisor.stop()

    assert result == {"status": "stopped", "pid": 55}
    assert calls["terminate"] == [55]
    assert not supervisor.paths.state_path.exists()


def test_shared_explicit_endpoint_fails_closed(tmp_path):
    (tmp_path / "first.state.json").write_text(
        json.dumps({"pid": 44, "endpoint": "ws://127.0.0.1:9000"})
    )
    supervisor, calls = build_supervisor(
        tmp_path,
        endpoint="ws://127.0.0.1:9000",
        alive=lambda pid: pid == 44,
    )
    result = supervisor.reconcile()
    assert result["status"] == "endpoint_collision"
    assert calls["spawn"] == []


def test_failed_termination_does_not_spawn_duplicate(tmp_path):
    supervisor, calls = build_supervisor(tmp_path, alive=lambda _pid: True, health_url="http://127.0.0.1:8765/health")
    supervisor.paths.state_path.write_text(json.dumps({"pid": 77, "restarts": 0}))
    supervisor._terminate = lambda _pid: False
    supervisor._health_probe = lambda *_args: False
    result = supervisor.reconcile()
    assert result["status"] == "restart_blocked"
    assert calls["spawn"] == []


def test_stop_preserves_state_when_termination_fails(tmp_path):
    supervisor, _calls = build_supervisor(tmp_path, alive=lambda _pid: True)
    supervisor.paths.state_path.write_text(json.dumps({"pid": 88, "restarts": 0}))
    supervisor._terminate = lambda _pid: False
    result = supervisor.stop()
    assert result["status"] == "stop_blocked"
    assert supervisor.paths.state_path.exists()
