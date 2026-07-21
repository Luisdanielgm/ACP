"""Host Bridge adapter for an explicitly bound Codex app-server thread."""

from __future__ import annotations

import json
import math
import time
import urllib.parse
from typing import Any, Callable, Mapping

from websockets.sync.client import connect as websocket_connect

from host_bridge import (
    CredentialResolver,
    HostBinding,
    HostBindingError,
    HostDelivery,
    HostDeliveryError,
    HostManifest,
    HostNotAcceptedError,
    HostQuarantineError,
    HostResult,
    HostTerminalFailureError,
)


Connect = Callable[..., Any]
_MAX_SUMMARY_CHARS = 16_000


class CodexAppServerAdapter:
    manifest = HostManifest(
        adapter_id="codex_app_server",
        display_name="Codex app-server",
        capabilities=(
            "existing-session",
            "websocket-delivery",
            "client-message-correlation",
            "streaming-terminal-result",
            "cancellation",
            "endpoint-serialized",
        ),
    )

    def __init__(
        self,
        *,
        request_timeout_seconds: float = 1800.0,
        deadline_monotonic: float | None = None,
        credential_resolver: CredentialResolver | None = None,
        connect: Connect = websocket_connect,
    ) -> None:
        self.request_timeout_seconds = request_timeout_seconds
        self.deadline_monotonic = deadline_monotonic
        self.credential_resolver = credential_resolver
        self.connect = connect

    def deliver(self, binding: HostBinding, delivery: HostDelivery) -> HostResult:
        return self._run(binding, delivery, reconcile_only=False)

    def reconcile(self, binding: HostBinding, delivery: HostDelivery) -> HostResult:
        """Recover an earlier accepted turn, but never submit a second prompt."""
        return self._run(binding, delivery, reconcile_only=True)

    def _run(self, binding: HostBinding, delivery: HostDelivery, *, reconcile_only: bool) -> HostResult:
        endpoint, thread_id, headers = self._validated(binding)
        deadline = time.monotonic() + self.request_timeout_seconds
        if self.deadline_monotonic is not None:
            deadline = min(deadline, self.deadline_monotonic)
        connection: Any = None
        turn_id: str | None = None
        try:
            connection = self.connect(
                endpoint,
                open_timeout=self._remaining(deadline),
                close_timeout=1,
                max_size=None,
                proxy=None,
                additional_headers=headers or None,
            )
            with connection:
                initialized, _ = self._request(
                    connection,
                    request_id=0,
                    method="initialize",
                    params={
                        "clientInfo": {
                            "name": "acp_host_bridge",
                            "title": "ACP Host Bridge",
                            "version": "0.3",
                        }
                    },
                    deadline=deadline,
                )
                if not isinstance(initialized.get("userAgent"), str):
                    raise HostDeliveryError("Codex initialize returned an invalid response")
                self._send(connection, {"method": "initialized", "params": {}})

                resumed, pending = self._request(
                    connection,
                    request_id=1,
                    method="thread/resume",
                    params={"threadId": thread_id},
                    deadline=deadline,
                )
                thread = resumed.get("thread")
                if not isinstance(thread, dict) or thread.get("id") != thread_id:
                    raise HostDeliveryError("Codex thread/resume returned a different thread")
                turns = thread.get("turns")
                if not isinstance(turns, list):
                    raise HostDeliveryError("Codex thread/resume omitted durable turn history")
                recovered = self._find_correlated_turn(turns, delivery)
                if recovered is not None:
                    turn_id, status, summary = recovered
                    if status == "completed":
                        return HostResult(outcome="success", summary=summary or "Codex completed without a text response")
                    if status == "inProgress":
                        return self._wait_for_terminal(connection, thread_id, turn_id, pending, deadline)
                    # The correlated turn exists but reached a terminal non-success
                    # state (failed/interrupted). This is proof no retry can recover
                    # or duplicate it, so quarantine instead of retrying forever.
                    raise HostTerminalFailureError(
                        "Codex correlated turn reached a terminal non-success state; refusing duplicate turn",
                        reason=f"codex_turn_{status}",
                    )
                if reconcile_only:
                    # The thread resumed and its durable history has no turn for
                    # this client message id: the delivery was provably never
                    # accepted, so signal quarantine instead of retrying forever.
                    raise HostNotAcceptedError(
                        "Codex thread resumed but never accepted this delivery; refusing duplicate turn"
                    )

                started, pending = self._request(
                    connection,
                    request_id=2,
                    method="turn/start",
                    params={
                        "threadId": thread_id,
                        "clientUserMessageId": delivery.host_message_id(),
                        "input": [{"type": "text", "text": delivery.instructions}],
                    },
                    deadline=deadline,
                )
                turn = started.get("turn")
                turn_id = turn.get("id") if isinstance(turn, dict) else None
                if not isinstance(turn_id, str) or not turn_id:
                    raise HostDeliveryError("Codex turn/start returned an invalid turn")
                return self._wait_for_terminal(connection, thread_id, turn_id, pending, deadline)
        except HostBindingError:
            raise
        except HostQuarantineError:
            # Proven terminal state: no in-flight turn of ours to interrupt, and
            # any correlated turn already reached a terminal state on the host.
            raise
        except HostDeliveryError:
            self._interrupt_best_effort(connection, thread_id, turn_id, deadline)
            raise
        except TimeoutError:
            self._interrupt_best_effort(connection, thread_id, turn_id, deadline)
            raise HostDeliveryError("Codex turn exceeded its completion deadline") from None
        except Exception:
            self._interrupt_best_effort(connection, thread_id, turn_id, deadline)
            raise HostDeliveryError("Codex app-server disconnected before terminal completion") from None

    def _wait_for_terminal(
        self,
        connection: Any,
        thread_id: str,
        turn_id: str,
        pending: list[dict[str, Any]],
        deadline: float,
    ) -> HostResult:
        final_text = ""
        messages = list(pending)
        while True:
            message = messages.pop(0) if messages else self._receive(connection, deadline)
            method = message.get("method")
            params = message.get("params")
            if not isinstance(params, dict):
                continue
            if params.get("threadId") != thread_id:
                continue
            event_turn_id = params.get("turnId")
            if method == "item/completed" and event_turn_id == turn_id:
                item = params.get("item")
                if isinstance(item, dict) and item.get("type") == "agentMessage":
                    text = item.get("text")
                    if isinstance(text, str) and text.strip():
                        final_text = text.strip()
                continue
            if method != "turn/completed":
                continue
            turn = params.get("turn")
            if not isinstance(turn, dict) or turn.get("id") != turn_id:
                continue
            if turn.get("status") != "completed":
                raise HostDeliveryError("Codex turn did not complete successfully")
            if not final_text:
                final_text = self._final_agent_text(turn.get("items"))
            return HostResult(
                outcome="success",
                summary=self._summary(final_text or "Codex completed without a text response"),
            )

    def _find_correlated_turn(
        self,
        turns: list[Any],
        delivery: HostDelivery,
    ) -> tuple[str, str, str] | None:
        matches: list[tuple[str, str, str]] = []
        for turn in turns:
            if not isinstance(turn, dict) or not isinstance(turn.get("items"), list):
                continue
            correlated = [
                item
                for item in turn["items"]
                if isinstance(item, dict)
                and item.get("type") == "userMessage"
                and item.get("clientId") == delivery.host_message_id()
            ]
            if not correlated:
                continue
            if len(correlated) != 1 or self._user_text(correlated[0].get("content")) != delivery.instructions:
                raise HostDeliveryError("Codex client message correlation is ambiguous")
            turn_id = turn.get("id")
            status = turn.get("status")
            if not isinstance(turn_id, str) or status not in {"completed", "inProgress", "failed", "interrupted"}:
                raise HostDeliveryError("Codex correlated turn has an invalid state")
            matches.append((turn_id, status, self._final_agent_text(turn["items"])))
        if len(matches) > 1:
            raise HostDeliveryError("Codex client message correlation is ambiguous")
        return matches[0] if matches else None

    def _request(
        self,
        connection: Any,
        *,
        request_id: int,
        method: str,
        params: Mapping[str, Any],
        deadline: float,
    ) -> tuple[dict[str, Any], list[dict[str, Any]]]:
        self._send(connection, {"id": request_id, "method": method, "params": dict(params)})
        pending: list[dict[str, Any]] = []
        while True:
            message = self._receive(connection, deadline)
            if message.get("id") != request_id:
                pending.append(message)
                continue
            if "error" in message:
                raise HostDeliveryError(f"Codex {method} was rejected")
            result = message.get("result")
            if not isinstance(result, dict):
                raise HostDeliveryError(f"Codex {method} returned an invalid response")
            return result, pending

    def _validated(self, binding: HostBinding) -> tuple[str, str, dict[str, str]]:
        if binding.adapter_id != self.manifest.adapter_id:
            raise HostBindingError("binding targets a different host adapter")
        endpoint = self._required(binding.values, "endpoint")
        thread_id = self._required(binding.values, "thread_id")
        if binding.values.get("directory"):
            raise HostBindingError("Codex app-server binding does not accept cwd overrides")
        parsed = urllib.parse.urlparse(endpoint)
        try:
            port = parsed.port
        except ValueError:
            raise HostBindingError("Codex app-server endpoint is invalid") from None
        if (
            parsed.scheme not in {"ws", "wss"}
            or parsed.hostname not in {"localhost", "127.0.0.1", "::1"}
            or port is None
            or parsed.path not in {"", "/"}
        ):
            raise HostBindingError("Codex app-server requires an explicit loopback WebSocket endpoint")
        headers: dict[str, str] = {}
        credential_ref = binding.values.get("credential_ref")
        if credential_ref:
            try:
                credential = self.credential_resolver(credential_ref) if self.credential_resolver else None
            except Exception:
                credential = None
            bearer = credential.bearer_token if credential is not None else None
            if not isinstance(bearer, str) or not bearer:
                raise HostBindingError("Codex credential reference cannot be resolved")
            headers["Authorization"] = f"Bearer {bearer}"
        normalized = urllib.parse.urlunparse((parsed.scheme, parsed.netloc, parsed.path, "", "", ""))
        return normalized, thread_id, headers

    def _interrupt_best_effort(
        self,
        connection: Any,
        thread_id: str,
        turn_id: str | None,
        deadline: float,
    ) -> None:
        if connection is None or not turn_id:
            return
        try:
            self._request(
                connection,
                request_id=3,
                method="turn/interrupt",
                params={"threadId": thread_id, "turnId": turn_id},
                deadline=max(deadline, time.monotonic() + 0.05),
            )
        except Exception:
            return

    @staticmethod
    def _send(connection: Any, message: Mapping[str, Any]) -> None:
        connection.send(json.dumps(dict(message), ensure_ascii=True, separators=(",", ":")))

    @staticmethod
    def _remaining(deadline: float) -> float:
        remaining = deadline - time.monotonic()
        if remaining <= 0 or not math.isfinite(remaining):
            raise TimeoutError
        return remaining

    def _receive(self, connection: Any, deadline: float) -> dict[str, Any]:
        raw = connection.recv(timeout=self._remaining(deadline))
        try:
            message = json.loads(raw)
        except (TypeError, ValueError, json.JSONDecodeError):
            raise HostDeliveryError("Codex app-server returned invalid JSON") from None
        if not isinstance(message, dict):
            raise HostDeliveryError("Codex app-server returned an invalid message")
        return message

    @staticmethod
    def _required(values: Mapping[str, str], key: str) -> str:
        value = values.get(key)
        if not isinstance(value, str) or not value.strip():
            raise HostBindingError(f"Codex app-server binding requires {key}")
        return value.strip()

    @classmethod
    def _summary(cls, text: str) -> str:
        return text.strip()[:_MAX_SUMMARY_CHARS]

    @classmethod
    def _final_agent_text(cls, items: Any) -> str:
        if not isinstance(items, list):
            return ""
        messages = [
            item.get("text", "").strip()
            for item in items
            if isinstance(item, dict)
            and item.get("type") == "agentMessage"
            and isinstance(item.get("text"), str)
            and item["text"].strip()
        ]
        return cls._summary(messages[-1]) if messages else ""

    @staticmethod
    def _user_text(content: Any) -> str:
        if not isinstance(content, list):
            return ""
        return "\n".join(
            item["text"]
            for item in content
            if isinstance(item, dict) and item.get("type") == "text" and isinstance(item.get("text"), str)
        ).strip()
