"""Host Bridge adapter for Codex app-server over its official stdio transport."""

from __future__ import annotations

import queue
import subprocess
import threading
from pathlib import Path
from typing import Any, Callable, Mapping

from codex_app_server_adapter import CodexAppServerAdapter
from host_bridge import HostBinding, HostBindingError, HostManifest


ConnectionFactory = Callable[[str], Any]


class _StdioConnection:
    def __init__(self, executable: str) -> None:
        self._process = subprocess.Popen(
            [executable, "app-server", "--stdio"],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            text=True,
            encoding="utf-8",
            bufsize=1,
        )
        if self._process.stdin is None or self._process.stdout is None:
            self.close()
            raise OSError("Codex app-server stdio pipes are unavailable")
        self._input = self._process.stdin
        self._messages: queue.Queue[str | None] = queue.Queue()
        threading.Thread(target=self._read_stdout, daemon=True).start()

    def _read_stdout(self) -> None:
        assert self._process.stdout is not None
        for line in self._process.stdout:
            self._messages.put(line)
        self._messages.put(None)

    def __enter__(self) -> _StdioConnection:
        return self

    def __exit__(self, *_args: Any) -> None:
        self.close()

    def send(self, payload: str) -> None:
        self._input.write(payload + "\n")
        self._input.flush()

    def recv(self, *, timeout: float) -> str:
        try:
            payload = self._messages.get(timeout=timeout)
        except queue.Empty:
            raise TimeoutError from None
        if payload is None:
            raise ConnectionError("Codex app-server stdio closed")
        return payload

    def close(self) -> None:
        if self._process.poll() is not None:
            return
        self._process.terminate()
        try:
            self._process.wait(timeout=1)
        except subprocess.TimeoutExpired:
            self._process.kill()


class CodexAppServerStdioAdapter(CodexAppServerAdapter):
    """Resume an existing Codex thread without opening a loopback listener.

    The HostBridge remains idle on ACP long-poll.  A short-lived Codex
    app-server subprocess is created only after a valid TASK was leased.
    """

    manifest = HostManifest(
        adapter_id="codex_app_server_stdio",
        display_name="Codex app-server stdio",
        capabilities=(
            "existing-session",
            "stdio-delivery",
            "spawn-on-task",
            "client-message-correlation",
            "streaming-terminal-result",
            "cancellation",
        ),
    )

    def __init__(self, *, connection_factory: ConnectionFactory | None = None, **kwargs: Any) -> None:
        self._connection_factory = connection_factory or _StdioConnection
        super().__init__(connect=self._connect_stdio, **kwargs)

    def _connect_stdio(self, executable: str, **_kwargs: Any) -> Any:
        return self._connection_factory(executable)

    def _validated(self, binding: HostBinding) -> tuple[str, str, dict[str, str]]:
        if binding.adapter_id != self.manifest.adapter_id:
            raise HostBindingError("binding targets a different host adapter")
        executable = self._required(binding.values, "executable")
        if not Path(executable).is_absolute():
            raise HostBindingError("Codex app-server stdio executable must be an explicit absolute path")
        if binding.values.get("endpoint"):
            raise HostBindingError("Codex app-server stdio does not accept an endpoint")
        if binding.values.get("directory"):
            raise HostBindingError("Codex app-server stdio does not accept cwd overrides")
        if binding.values.get("credential_ref"):
            raise HostBindingError("Codex app-server stdio uses the local Codex login and does not accept credential_ref")
        return executable, self._required(binding.values, "thread_id"), {}
