"""Small process supervisor for explicitly configured ACP host bridges."""

from __future__ import annotations

import ctypes
import hashlib
import json
import os
import re
import signal
import subprocess
import time
import urllib.parse
import urllib.request
from ctypes import wintypes
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable
from uuid import uuid4

from config_reservation import reserve_config


@dataclass(frozen=True)
class BridgeSpec:
    name: str
    command: tuple[str, ...]
    cwd: Path | None = None
    endpoint: str | None = None
    health_url: str | None = None
    restart_limit: int = 3
    backoff_seconds: float = 1.0
    health_timeout_seconds: float = 2.0

    def __post_init__(self) -> None:
        if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,63}", self.name):
            raise ValueError("bridge name must be a safe file name")
        if not self.command or not all(isinstance(part, str) and part for part in self.command):
            raise ValueError("bridge command must be explicit and non-empty")
        if self.restart_limit < 0 or self.backoff_seconds < 0 or self.health_timeout_seconds <= 0:
            raise ValueError("bridge restart and health settings are invalid")
        if self.health_url:
            parsed = urllib.parse.urlparse(self.health_url)
            if parsed.scheme not in {"http", "https"} or parsed.username or parsed.password:
                raise ValueError("health URL must be credential-free HTTP(S)")
            if parsed.hostname not in {"127.0.0.1", "localhost", "::1"}:
                raise ValueError("health URL must be loopback")
        if self.endpoint:
            parsed = urllib.parse.urlparse(self.endpoint)
            if parsed.scheme not in {"ws", "wss", "http", "https"} or parsed.username or parsed.password:
                raise ValueError("endpoint must be an explicit credential-free URL")
            if parsed.hostname not in {"127.0.0.1", "localhost", "::1"}:
                raise ValueError("host bridge endpoint must be loopback")


@dataclass(frozen=True)
class SupervisorPaths:
    state_path: Path
    log_path: Path
    endpoint_lock_path: Path | None = None

    @classmethod
    def for_bridge(cls, root: Path, name: str) -> "SupervisorPaths":
        if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,63}", name):
            raise ValueError("bridge name must be a safe file name")
        root = root.resolve()
        return cls(root / f"{name}.state.json", root / f"{name}.log")

    def endpoint_lock(self, endpoint: str) -> Path:
        digest = hashlib.sha256(endpoint.encode("utf-8")).hexdigest()[:24]
        return self.state_path.parent / f"endpoint-{digest}.lock"


def _windows_process_is_alive(pid: int) -> bool:
    query = 0x1000  # PROCESS_QUERY_LIMITED_INFORMATION
    still_active = 259
    invalid_parameter = 87
    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel32.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
    kernel32.OpenProcess.restype = wintypes.HANDLE
    kernel32.GetExitCodeProcess.argtypes = [wintypes.HANDLE, ctypes.POINTER(wintypes.DWORD)]
    kernel32.GetExitCodeProcess.restype = wintypes.BOOL
    kernel32.CloseHandle.argtypes = [wintypes.HANDLE]
    kernel32.CloseHandle.restype = wintypes.BOOL
    handle = kernel32.OpenProcess(query, False, pid)
    if not handle:
        # Access denied proves the PID exists; only INVALID_PARAMETER proves it stale.
        return ctypes.get_last_error() != invalid_parameter
    try:
        exit_code = wintypes.DWORD()
        if not kernel32.GetExitCodeProcess(handle, ctypes.byref(exit_code)):
            return True
        return exit_code.value == still_active
    finally:
        kernel32.CloseHandle(handle)


def process_is_alive(pid: int) -> bool:
    """Check PID health without signaling a process on Windows."""
    if not isinstance(pid, int) or pid <= 0:
        return False
    if os.name == "nt":
        return _windows_process_is_alive(pid)
    try:
        os.kill(pid, 0)
    except OSError:
        return False
    return True


def _terminate_process(pid: int) -> bool:
    try:
        if os.name != "nt":
            os.kill(pid, signal.SIGTERM)
            return True
        # Ask Windows to close the full child tree gracefully; no force flag.
        completed = subprocess.run(
            ["taskkill", "/PID", str(pid), "/T"],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            check=False,
        )
        return completed.returncode == 0
    except OSError:
        return False


def _probe_health(url: str, timeout: float) -> bool:
    try:
        request = urllib.request.Request(url, method="GET")
        with urllib.request.urlopen(request, timeout=timeout) as response:
            return 200 <= response.status < 300
    except Exception:
        return False


def _spawn_bridge(spec: BridgeSpec, log_path: Path) -> subprocess.Popen[bytes]:
    log_path.parent.mkdir(parents=True, exist_ok=True)
    creationflags = 0
    startupinfo = None
    if os.name == "nt":
        creationflags = subprocess.CREATE_NEW_PROCESS_GROUP | subprocess.DETACHED_PROCESS
        startupinfo = subprocess.STARTUPINFO()
        startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
        startupinfo.wShowWindow = subprocess.SW_HIDE
    with log_path.open("ab", buffering=0) as log:
        return subprocess.Popen(
            spec.command,
            cwd=str(spec.cwd) if spec.cwd else None,
            stdin=subprocess.DEVNULL,
            stdout=log,
            stderr=subprocess.STDOUT,
            creationflags=creationflags,
            startupinfo=startupinfo,
        )


class HostBridgeSupervisor:
    def __init__(
        self,
        spec: BridgeSpec,
        paths: SupervisorPaths,
        *,
        process_alive: Callable[[int], bool] = process_is_alive,
        spawn: Callable[[BridgeSpec, Path], Any] = _spawn_bridge,
        terminate: Callable[[int], bool] = _terminate_process,
        health_probe: Callable[[str, float], bool] = _probe_health,
        sleep: Callable[[float], None] = time.sleep,
    ) -> None:
        self.spec, self.paths = spec, paths
        self._process_alive, self._spawn = process_alive, spawn
        self._terminate, self._health_probe, self._sleep = terminate, health_probe, sleep

    def _read_state(self) -> dict[str, Any]:
        try:
            value = json.loads(self.paths.state_path.read_text(encoding="utf-8"))
            return value if isinstance(value, dict) else {}
        except (FileNotFoundError, OSError, json.JSONDecodeError):
            return {}

    def _write_state(self, state: dict[str, Any]) -> None:
        self.paths.state_path.parent.mkdir(parents=True, exist_ok=True)
        temporary = self.paths.state_path.with_name(f".{self.paths.state_path.name}.{uuid4().hex}.tmp")
        try:
            temporary.write_text(json.dumps(state, sort_keys=True) + "\n", encoding="utf-8")
            os.replace(temporary, self.paths.state_path)
        finally:
            try:
                temporary.unlink()
            except FileNotFoundError:
                pass

    def reconcile(self) -> dict[str, Any]:
        """Adopt a healthy bridge or restart it within its persisted limit."""
        endpoint_lock = self.paths.endpoint_lock(self.spec.endpoint) if self.spec.endpoint else None
        state_lock = reserve_config(self.paths.state_path)
        endpoint_context = reserve_config(endpoint_lock) if endpoint_lock else None
        with state_lock:
            if endpoint_context is not None:
                endpoint_context.__enter__()
            try:
                return self._reconcile_locked()
            finally:
                if endpoint_context is not None:
                    endpoint_context.__exit__(None, None, None)

    def _reconcile_locked(self) -> dict[str, Any]:
            state = self._read_state()
            if self.spec.endpoint:
                for candidate in self.paths.state_path.parent.glob("*.state.json"):
                    if candidate == self.paths.state_path:
                        continue
                    try:
                        other = json.loads(candidate.read_text(encoding="utf-8"))
                    except (OSError, json.JSONDecodeError):
                        continue
                    other_pid = other.get("pid") if isinstance(other, dict) else None
                    if isinstance(other, dict) and other.get("endpoint") == self.spec.endpoint and isinstance(other_pid, int) and self._process_alive(other_pid):
                        return {"status": "endpoint_collision", "endpoint": self.spec.endpoint}
            pid = state.get("pid")
            alive = isinstance(pid, int) and self._process_alive(pid)
            healthy = alive and (
                not self.spec.health_url
                or self._health_probe(self.spec.health_url, self.spec.health_timeout_seconds)
            )
            if healthy:
                try:
                    restart_count = max(0, int(state.get("restarts", 0)))
                except (TypeError, ValueError):
                    restart_count = 0
                return {"status": "running", "pid": pid, "restarts": restart_count}
            if alive:
                if not self._terminate(pid):
                    return {"status": "restart_blocked", "pid": pid, "reason": "process did not accept termination"}
                for _ in range(5):
                    if not self._process_alive(pid):
                        break
                    self._sleep(0.05)
                else:
                    return {"status": "restart_blocked", "pid": pid, "reason": "process is still alive"}

            had_previous_process = isinstance(pid, int)
            try:
                previous_restarts = int(state.get("restarts", 0))
            except (TypeError, ValueError):
                previous_restarts = 0
            restarts = max(0, previous_restarts) + (1 if had_previous_process else 0)
            if had_previous_process and restarts > self.spec.restart_limit:
                result = {"status": "restart_limit", "pid": pid, "restarts": restarts - 1}
                self._write_state(result)
                return result
            if had_previous_process and self.spec.backoff_seconds:
                self._sleep(min(30.0, self.spec.backoff_seconds * (2 ** max(0, restarts - 1))))
            process = self._spawn(self.spec, self.paths.log_path)
            result = {"status": "running", "pid": int(process.pid), "restarts": restarts}
            if self.spec.endpoint:
                result["endpoint"] = self.spec.endpoint
            self._write_state(result)
            return result

    def stop(self) -> dict[str, Any]:
        """Stop the recorded bridge, without installing a service or scheduled task."""
        with reserve_config(self.paths.state_path):
            state = self._read_state()
            pid = state.get("pid")
            terminated = True
            if isinstance(pid, int) and self._process_alive(pid):
                terminated = self._terminate(pid)
            if not terminated:
                return {"status": "stop_blocked", "pid": pid}
            try:
                self.paths.state_path.unlink()
            except FileNotFoundError:
                pass
            return {"status": "stopped", "pid": pid if isinstance(pid, int) else None}
