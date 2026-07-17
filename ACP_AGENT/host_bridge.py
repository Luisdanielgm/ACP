"""Portable ACP delivery bridge for already-running coding hosts."""

from __future__ import annotations

import base64
import hashlib
import json
import math
import tempfile
import time
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass, field
from pathlib import Path
from types import MappingProxyType
from typing import Any, Callable, Mapping, Protocol
from uuid import NAMESPACE_URL, uuid5


class HostBindingError(ValueError):
    """Raised when a host binding is unsafe or incomplete."""


class HostDeliveryError(RuntimeError):
    """Raised when a host did not durably accept a delivery."""


@dataclass(frozen=True)
class HostManifest:
    adapter_id: str
    display_name: str
    capabilities: tuple[str, ...]


@dataclass(frozen=True)
class HostBinding:
    adapter_id: str
    values: Mapping[str, str]

    def __post_init__(self) -> None:
        values_are_strings = all(
            isinstance(key, str) and isinstance(value, str)
            for key, value in self.values.items()
        )
        if not self.adapter_id.strip() or not values_are_strings:
            raise HostBindingError("host binding must use non-empty adapter and string values")
        object.__setattr__(self, "values", MappingProxyType(dict(self.values)))
        if any(_is_secret_key(key) for key in self.values):
            raise HostBindingError("host binding contains a secret-bearing field")
        endpoint = self.values.get("endpoint")
        if isinstance(endpoint, str):
            parsed = urllib.parse.urlparse(endpoint)
            if parsed.username or parsed.password or parsed.query or parsed.fragment:
                raise HostBindingError("host endpoint cannot contain credentials, query, or fragment")

    def fingerprint(self) -> str:
        encoded = json.dumps(
            {"adapter_id": self.adapter_id, "values": dict(self.values)},
            ensure_ascii=True,
            sort_keys=True,
            separators=(",", ":"),
        ).encode()
        return hashlib.sha256(encoded).hexdigest()

    def safe_descriptor(self) -> dict[str, str]:
        return {"adapter_id": self.adapter_id, "binding_fingerprint": self.fingerprint()}


@dataclass(frozen=True)
class HostDelivery:
    message_id: str
    correlation_id: str
    sender: str
    instructions: str
    task_id: str | None = None

    def host_message_id(self) -> str:
        digest = hashlib.sha256(self.message_id.encode()).hexdigest()[:24]
        return f"msg_acp_{digest}"


@dataclass(frozen=True)
class HostResult:
    outcome: str
    summary: str
    metadata: Mapping[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class HostCredential:
    username: str
    password: str


class HostAdapter(Protocol):
    manifest: HostManifest

    def deliver(self, binding: HostBinding, delivery: HostDelivery) -> HostResult: ...


class AdapterRegistry:
    def __init__(self) -> None:
        self._adapters: dict[str, HostAdapter] = {}

    def register(self, adapter: HostAdapter) -> None:
        adapter_id = adapter.manifest.adapter_id
        if adapter_id in self._adapters:
            raise ValueError(f"host adapter already registered: {adapter_id}")
        self._adapters[adapter_id] = adapter

    def get(self, adapter_id: str) -> HostAdapter:
        try:
            return self._adapters[adapter_id]
        except KeyError as exc:
            raise HostBindingError("configured host adapter is not registered") from exc


CredentialResolver = Callable[[str], HostCredential | None]


class _HttpSessionAdapter:
    manifest: HostManifest

    def __init__(
        self,
        *,
        request_timeout_seconds: float = 1800.0,
        credential_resolver: CredentialResolver | None = None,
    ) -> None:
        self.request_timeout_seconds = request_timeout_seconds
        self.credential_resolver = credential_resolver

    def deliver(self, binding: HostBinding, delivery: HostDelivery) -> HostResult:
        endpoint, session_id, directory, credential_ref = self._validated(binding)
        query = urllib.parse.urlencode({"directory": directory}) if directory else ""
        url = f"{endpoint}/session/{urllib.parse.quote(session_id, safe='')}/message"
        if query:
            url = f"{url}?{query}"
        headers = self._headers(credential_ref)
        message_id = delivery.host_message_id()
        history = self._request_json(url=url, method="GET", headers=headers)
        recovered = _correlated_result(
            history,
            message_id=message_id,
            session_id=session_id,
            history=True,
        )
        if recovered is not None:
            return recovered
        if _history_contains(history, message_id=message_id):
            deadline = time.monotonic() + self.request_timeout_seconds
            while time.monotonic() < deadline:
                time.sleep(min(0.25, max(0.0, deadline - time.monotonic())))
                history = self._request_json(url=url, method="GET", headers=headers)
                recovered = _correlated_result(
                    history,
                    message_id=message_id,
                    session_id=session_id,
                    history=True,
                )
                if recovered is not None:
                    return recovered
            raise HostDeliveryError("existing host delivery did not reach a valid correlated result")
        body = json.dumps(
            {
                "messageID": message_id,
                "parts": [{"type": "text", "text": delivery.instructions}],
            },
            ensure_ascii=True,
        ).encode()
        payload = self._request_json(url=url, method="POST", headers=headers, body=body)
        result = _correlated_result(
            payload,
            message_id=message_id,
            session_id=session_id,
            history=False,
        )
        if result is None:
            raise HostDeliveryError("host did not return a valid correlated result")
        return result

    def _headers(self, credential_ref: str | None) -> dict[str, str]:
        headers = {"Content-Type": "application/json", "Accept": "application/json"}
        if credential_ref:
            try:
                credential = self.credential_resolver(credential_ref) if self.credential_resolver else None
            except Exception:
                raise HostBindingError("host credential reference cannot be resolved") from None
            if credential is None:
                raise HostBindingError("host credential reference cannot be resolved")
            raw = f"{credential.username}:{credential.password}".encode()
            headers["Authorization"] = f"Basic {base64.b64encode(raw).decode()}"
        return headers

    def _request_json(
        self,
        *,
        url: str,
        method: str,
        headers: Mapping[str, str],
        body: bytes | None = None,
    ) -> Any:
        request = urllib.request.Request(url, data=body, headers=dict(headers), method=method)
        try:
            with urllib.request.urlopen(request, timeout=self.request_timeout_seconds) as response:
                return json.loads(response.read().decode() or "{}")
        except urllib.error.HTTPError as exc:
            raise HostDeliveryError(f"host rejected delivery with HTTP {exc.code}") from None
        except (urllib.error.URLError, TimeoutError, OSError, ValueError, json.JSONDecodeError):
            raise HostDeliveryError("host delivery failed before a valid result was received") from None

    def _validated(self, binding: HostBinding) -> tuple[str, str, str | None, str | None]:
        if binding.adapter_id != self.manifest.adapter_id:
            raise HostBindingError("binding targets a different host adapter")
        endpoint = _required_value(binding.values, "endpoint")
        session_id = _required_value(binding.values, "session_id")
        parsed = urllib.parse.urlparse(endpoint)
        if parsed.scheme not in {"http", "https"} or not parsed.hostname:
            raise HostBindingError("host endpoint must be an explicit HTTP URL")
        if parsed.hostname not in {"localhost", "127.0.0.1", "::1"}:
            raise HostBindingError("first-slice host endpoints must be loopback addresses")
        base_path = parsed.path.rstrip("/")
        normalized = urllib.parse.urlunparse((parsed.scheme, parsed.netloc, base_path, "", "", ""))
        directory = _optional_value(binding.values, "directory")
        credential_ref = _optional_value(binding.values, "credential_ref")
        return normalized, session_id, directory, credential_ref


class OpenCodeServerAdapter(_HttpSessionAdapter):
    manifest = HostManifest(
        adapter_id="opencode_server",
        display_name="OpenCode server",
        capabilities=("existing-session", "http-delivery", "correlated-result"),
    )


class KiloServeAdapter(_HttpSessionAdapter):
    manifest = HostManifest(
        adapter_id="kilo_serve",
        display_name="Kilo Code serve",
        capabilities=("existing-session", "http-delivery", "correlated-result", "directory-context"),
    )


class JsonBridgeStore:
    def __init__(self, path: Path) -> None:
        self.path = path

    def get(self, key: str) -> dict[str, Any]:
        return dict(self._load()["deliveries"].get(key) or {})

    def put(self, key: str, record: Mapping[str, Any]) -> None:
        state = self._load()
        state["deliveries"][key] = dict(record)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with tempfile.NamedTemporaryFile(
            "w",
            delete=False,
            encoding="utf-8",
            dir=self.path.parent,
            suffix=".tmp",
        ) as handle:
            json.dump(state, handle, ensure_ascii=True, indent=2, sort_keys=True)
            handle.write("\n")
            temporary = Path(handle.name)
        temporary.replace(self.path)

    def _load(self) -> dict[str, Any]:
        if not self.path.exists():
            return {"version": 1, "deliveries": {}}
        try:
            loaded = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, ValueError, json.JSONDecodeError) as exc:
            raise HostDeliveryError("host bridge state is unreadable") from exc
        if not isinstance(loaded, dict) or not isinstance(loaded.get("deliveries"), dict):
            raise HostDeliveryError("host bridge state has an invalid format")
        return loaded


class HostBridge:
    def __init__(
        self,
        *,
        registry: AdapterRegistry,
        binding: HostBinding,
        store: JsonBridgeStore,
        allowed_senders: tuple[str, ...],
    ) -> None:
        if not allowed_senders:
            raise ValueError("host bridge requires at least one trusted sender")
        self.registry = registry
        self.binding = binding
        self.store = store
        self.allowed_senders = allowed_senders

    def poll_once(
        self,
        *,
        receive: Callable[[], Mapping[str, Any]],
        acknowledge: Callable[[Mapping[str, Any]], Any],
        reply: Callable[[HostDelivery, HostResult, str], Any],
    ) -> dict[str, Any]:
        """Wait through the injected ACP transport, then process at most one delivery."""
        return self.handle(receive(), acknowledge=acknowledge, reply=reply)

    def handle(
        self,
        response: Mapping[str, Any],
        *,
        acknowledge: Callable[[Mapping[str, Any]], Any],
        reply: Callable[[HostDelivery, HostResult, str], Any],
    ) -> dict[str, Any]:
        if not isinstance(response, Mapping):
            raise HostDeliveryError("ACP receive returned an invalid response")
        status = response.get("status")
        if status == "timeout":
            return {"status": "idle"}
        if status != "message":
            raise HostDeliveryError("ACP receive returned an invalid status")
        message, _delivery = _validated_envelope(response, self.allowed_senders)
        host_delivery = _host_delivery(message)
        key = hashlib.sha256(f"{message.get('session_id', '')}:{host_delivery.message_id}".encode()).hexdigest()
        record = self.store.get(key)
        binding_descriptor = self.binding.safe_descriptor()
        if record and record.get("binding") != binding_descriptor:
            raise HostBindingError("durable delivery binding changed")
        adapter = self.registry.get(self.binding.adapter_id)
        duplicate = record.get("status") == "completed"
        if duplicate:
            result = HostResult(outcome=str(record["outcome"]), summary=str(record["summary"]))
        else:
            record = {
                "status": "received",
                "message_id": host_delivery.message_id,
                "correlation_id": host_delivery.correlation_id,
                "sender": host_delivery.sender,
                "binding": binding_descriptor,
            }
            self.store.put(key, record)
            try:
                result = adapter.deliver(self.binding, host_delivery)
            except (HostBindingError, HostDeliveryError):
                record["last_error"] = "host delivery was not accepted"
                self.store.put(key, record)
                raise
            record.update({"status": "completed", "outcome": result.outcome, "summary": result.summary})
            self.store.put(key, record)

        reply_id = str(uuid5(NAMESPACE_URL, f"acp-host-bridge-reply:{host_delivery.correlation_id}"))
        if not record.get("replied"):
            reply(host_delivery, result, reply_id)
            record["replied"] = True
            self.store.put(key, record)
        if not record.get("acked"):
            acknowledge(response)
            record["acked"] = True
            self.store.put(key, record)
        return {"status": "duplicate" if duplicate else "completed", "outcome": result.outcome}


def default_registry(
    *,
    request_timeout_seconds: float = 1800.0,
    credential_resolver: CredentialResolver | None = None,
) -> AdapterRegistry:
    registry = AdapterRegistry()
    registry.register(
        OpenCodeServerAdapter(
            request_timeout_seconds=request_timeout_seconds,
            credential_resolver=credential_resolver,
        )
    )
    registry.register(
        KiloServeAdapter(
            request_timeout_seconds=request_timeout_seconds,
            credential_resolver=credential_resolver,
        )
    )
    return registry


def _required_value(values: Mapping[str, str], key: str) -> str:
    value = values.get(key)
    if not isinstance(value, str) or not value.strip():
        raise HostBindingError(f"host binding requires {key}")
    return value.strip()


def _optional_value(values: Mapping[str, str], key: str) -> str | None:
    value = values.get(key)
    return value.strip() if isinstance(value, str) and value.strip() else None


def _response_text(payload: Any) -> str:
    if not isinstance(payload, dict) or not isinstance(payload.get("parts"), list):
        return ""
    return "\n".join(
        part["text"].strip()
        for part in payload["parts"]
        if isinstance(part, dict)
        and part.get("type") == "text"
        and isinstance(part.get("text"), str)
        and part["text"].strip()
    )


def _correlated_result(
    payload: Any,
    *,
    message_id: str,
    session_id: str,
    history: bool,
) -> HostResult | None:
    if history:
        if not isinstance(payload, list):
            raise HostDeliveryError("host history has an invalid format")
        items = payload
    else:
        if not isinstance(payload, dict):
            raise HostDeliveryError("host did not return a valid correlated result")
        items = [payload]
    if not all(isinstance(item, dict) for item in items):
        raise HostDeliveryError(
            "host history has an invalid format"
            if history
            else "host did not return a valid correlated result"
        )
    for item in items:
        info = item.get("info")
        parts = item.get("parts")
        if not isinstance(info, dict) or not isinstance(parts, list):
            continue
        if info.get("role") != "assistant" or info.get("parentID") != message_id:
            continue
        if not isinstance(info.get("id"), str) or not info["id"].strip():
            continue
        if info.get("sessionID") != session_id or info.get("error") is not None:
            continue
        completed_at = info.get("time", {}).get("completed") if isinstance(info.get("time"), dict) else None
        completed = (
            isinstance(completed_at, (int, float))
            and not isinstance(completed_at, bool)
            and math.isfinite(completed_at)
            and completed_at > 0
        )
        if not completed:
            continue
        summary = _response_text(item)
        return HostResult(outcome="success", summary=summary or "Host completed without a text response")
    if history:
        return None
    raise HostDeliveryError("host did not return a valid correlated result")


def _history_contains(payload: Any, *, message_id: str) -> bool:
    return isinstance(payload, list) and any(
        isinstance(item, dict)
        and isinstance(item.get("info"), dict)
        and (
            item["info"].get("id") == message_id
            or item["info"].get("parentID") == message_id
        )
        for item in payload
    )


def _is_secret_key(key: str) -> bool:
    normalized = key.lower().replace("-", "_")
    if normalized == "credential_ref":
        return False
    return any(
        marker in normalized
        for marker in (
            "api_key",
            "apikey",
            "auth",
            "bearer",
            "cookie",
            "credential",
            "password",
            "private_key",
            "secret",
            "signing_key",
            "token",
        )
    )


def _validated_envelope(
    response: Mapping[str, Any],
    allowed_senders: tuple[str, ...],
) -> tuple[dict[str, Any], dict[str, Any]]:
    message = response.get("message")
    delivery = response.get("delivery")
    if not isinstance(message, dict) or not isinstance(delivery, dict) or delivery.get("ack_required") is not True:
        raise HostDeliveryError("host bridge requires an explicit leased ACP delivery")
    message_id = message.get("id")
    receipt_handle = delivery.get("receipt_handle")
    if (
        not isinstance(message_id, str)
        or delivery.get("message_id") != message_id
        or not isinstance(receipt_handle, str)
        or not receipt_handle.strip()
    ):
        raise HostDeliveryError("ACP delivery identity is invalid")
    if message.get("action") != "TASK" or message.get("from") not in allowed_senders:
        raise HostDeliveryError("ACP delivery is not an authorized TASK")
    return message, delivery


def _host_delivery(message: Mapping[str, Any]) -> HostDelivery:
    payload = message.get("payload")
    task_id: str | None = None
    instructions: str | None = None
    if isinstance(payload, str):
        try:
            parsed = json.loads(payload)
        except (ValueError, json.JSONDecodeError):
            parsed = None
        if isinstance(parsed, dict):
            if isinstance(parsed.get("task_id"), str):
                task_id = parsed["task_id"].strip() or None
            if isinstance(parsed.get("instructions"), str):
                instructions = parsed["instructions"].strip() or None
        elif payload.strip():
            instructions = payload.strip()
    if instructions is None:
        raise HostDeliveryError("ACP TASK does not contain instructions")
    message_id = str(message["id"])
    return HostDelivery(
        message_id=message_id,
        correlation_id=message_id,
        sender=str(message["from"]),
        instructions=instructions,
        task_id=task_id,
    )
