"""Stable and safe protocol validation errors."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

INVALID_JSON = "INVALID_JSON"
INVALID_SCHEMA = "INVALID_SCHEMA"
INVALID_FIELD = "INVALID_FIELD"
UNSUPPORTED_TYPE = "UNSUPPORTED_TYPE"
PAYLOAD_TOO_LARGE = "PAYLOAD_TOO_LARGE"
AUTH_REQUIRED = "AUTH_REQUIRED"
AUTH_INVALID = "AUTH_INVALID"
AUTH_FORBIDDEN = "AUTH_FORBIDDEN"
WAIT_ALREADY_ACTIVE = "WAIT_ALREADY_ACTIVE"
SESSION_NOT_FOUND = "SESSION_NOT_FOUND"

ERROR_MESSAGES: dict[str, str] = {
    INVALID_JSON: "Request body must be valid JSON.",
    INVALID_SCHEMA: "Message does not match ACP schema.",
    INVALID_FIELD: "One or more fields are invalid.",
    UNSUPPORTED_TYPE: "Unsupported message type.",
    PAYLOAD_TOO_LARGE: "Payload exceeds maximum allowed size.",
    AUTH_REQUIRED: "Authentication token is required.",
    AUTH_INVALID: "Authentication token is invalid.",
    AUTH_FORBIDDEN: "Operation is forbidden by policy.",
    WAIT_ALREADY_ACTIVE: "This member already has an active wait request.",
    SESSION_NOT_FOUND: "The coordination session no longer exists.",
}


@dataclass(frozen=True)
class ProtocolValidationError:
    code: str
    message: str
    field: str | None = None
    details: dict[str, Any] | None = None

    def to_dict(self) -> dict[str, Any]:
        data: dict[str, Any] = {"code": self.code, "message": self.message}
        if self.field is not None:
            data["field"] = self.field
        if self.details:
            data["details"] = self.details
        return data


def build_error(
    code: str,
    *,
    field: str | None = None,
    message: str | None = None,
    details: dict[str, Any] | None = None,
) -> ProtocolValidationError:
    if code not in ERROR_MESSAGES:
        raise ValueError(f"Unsupported protocol error code: {code}")
    return ProtocolValidationError(
        code=code,
        message=message or ERROR_MESSAGES[code],
        field=field,
        details=details,
    )
