"""Shared transport-agnostic ACP v0.1 validation entrypoints."""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any, Mapping

from pydantic import ValidationError

from acp.protocol.errors import (
    INVALID_FIELD,
    INVALID_JSON,
    INVALID_SCHEMA,
    PAYLOAD_TOO_LARGE,
    UNSUPPORTED_TYPE,
    ProtocolValidationError,
    build_error,
)
from acp.protocol.models import HelloEnvelope, MAX_PAYLOAD_BYTES, MsgEnvelope


@dataclass(frozen=True)
class ValidationResult:
    ok: bool
    message_type: str | None = None
    data: dict[str, Any] | None = None
    error: ProtocolValidationError | None = None


def _field_from_validation_error(exc: ValidationError) -> str | None:
    first = exc.errors()[0] if exc.errors() else None
    if not first:
        return None
    loc = first.get("loc", ())
    if not loc:
        return None
    return ".".join(str(part) for part in loc)


def _map_validation_error(exc: ValidationError) -> ProtocolValidationError:
    field = _field_from_validation_error(exc)
    if field:
        return build_error(INVALID_FIELD, field=field)
    return build_error(INVALID_SCHEMA)


def parse_raw_envelope(raw: str | bytes | Mapping[str, Any]) -> tuple[dict[str, Any] | None, ProtocolValidationError | None]:
    if isinstance(raw, Mapping):
        return dict(raw), None

    if isinstance(raw, bytes):
        try:
            raw = raw.decode("utf-8")
        except UnicodeDecodeError:
            return None, build_error(INVALID_JSON, message="Request body must be UTF-8 JSON text.")

    if not isinstance(raw, str):
        return None, build_error(INVALID_JSON, message="Request body must be JSON text or object.")

    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError:
        return None, build_error(INVALID_JSON)

    if not isinstance(parsed, dict):
        return None, build_error(INVALID_SCHEMA, message="Top-level message must be a JSON object.")

    return parsed, None


def _validate_hello(data: Mapping[str, Any], *, required_token: str | None) -> ValidationResult:
    try:
        hello = HelloEnvelope.model_validate(data)
    except ValidationError as exc:
        return ValidationResult(ok=False, error=_map_validation_error(exc))

    if required_token is not None:
        if hello.token is None:
            return ValidationResult(
                ok=False, error=build_error(INVALID_FIELD, field="token", message="token is required.")
            )
        if hello.token != required_token:
            return ValidationResult(
                ok=False, error=build_error(INVALID_FIELD, field="token", message="token is invalid.")
            )

    return ValidationResult(
        ok=True,
        message_type="HELLO",
        data=hello.model_dump(mode="json"),
    )


def _validate_msg(data: Mapping[str, Any], *, max_payload_bytes: int) -> ValidationResult:
    try:
        message = MsgEnvelope.model_validate(data)
    except ValidationError as exc:
        return ValidationResult(ok=False, error=_map_validation_error(exc))

    payload_size = message.payload_size_bytes
    if payload_size > max_payload_bytes:
        return ValidationResult(
            ok=False,
            error=build_error(
                PAYLOAD_TOO_LARGE,
                field="payload",
                details={"max_bytes": max_payload_bytes, "actual_bytes": payload_size},
            ),
        )

    return ValidationResult(
        ok=True,
        message_type="MSG",
        data=message.model_dump(by_alias=True, mode="json"),
    )


def validate_envelope(
    raw: str | bytes | Mapping[str, Any],
    *,
    required_token: str | None = None,
    max_payload_bytes: int = MAX_PAYLOAD_BYTES,
) -> ValidationResult:
    data, parse_error = parse_raw_envelope(raw)
    if parse_error is not None:
        return ValidationResult(ok=False, error=parse_error)
    if data is None:
        return ValidationResult(ok=False, error=build_error(INVALID_SCHEMA))

    message_type = data.get("type")
    if message_type == "HELLO":
        return _validate_hello(data, required_token=required_token)
    if message_type == "MSG":
        return _validate_msg(data, max_payload_bytes=max_payload_bytes)

    return ValidationResult(ok=False, error=build_error(UNSUPPORTED_TYPE, field="type"))
