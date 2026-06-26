"""Protocol models for ACP v0.1 contract validation."""

from __future__ import annotations

import re
from datetime import datetime
from enum import Enum
from typing import Annotated, Literal
from uuid import UUID

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, StrictStr, StringConstraints, field_validator

MAX_PAYLOAD_BYTES = 32 * 1024
AGENT_NAME_PATTERN = r"^[A-Za-z0-9][A-Za-z0-9_.-]{0,63}$"
RFC3339_PATTERN = re.compile(
    r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d+)?(?:Z|[+-]\d{2}:\d{2})$"
)

AgentName = Annotated[
    str,
    StringConstraints(
        strict=True,
        min_length=1,
        max_length=64,
        pattern=AGENT_NAME_PATTERN,
        strip_whitespace=False,
    ),
]
AgentToken = Annotated[str, StringConstraints(strict=True, min_length=1, max_length=512)]


class HelloRole(str, Enum):
    AGENT = "agent"
    OBSERVER = "observer"


class InboundMsgAction(str, Enum):
    TASK = "TASK"
    REPLY = "REPLY"
    INFO = "INFO"


class HelloEnvelope(BaseModel):
    model_config = ConfigDict(extra="forbid")

    type: Literal["HELLO"]
    role: HelloRole
    name: AgentName
    token: AgentToken | None = None


class MsgEnvelope(BaseModel):
    model_config = ConfigDict(extra="forbid", populate_by_name=True)

    type: Literal["MSG"]
    id: UUID
    ts: AwareDatetime
    from_: AgentName = Field(alias="from")
    to: AgentName
    action: InboundMsgAction
    payload: StrictStr
    thread_id: UUID | None = None
    in_reply_to: UUID | None = None

    @field_validator("ts", mode="before")
    @classmethod
    def validate_rfc3339_timestamp(cls, value: object) -> object:
        if not isinstance(value, str):
            raise ValueError("ts must be an RFC3339 string")
        if RFC3339_PATTERN.fullmatch(value) is None:
            raise ValueError("ts must be RFC3339")
        return value

    @property
    def payload_size_bytes(self) -> int:
        return len(self.payload.encode("utf-8"))


class ErrorEnvelope(BaseModel):
    """Hub-generated protocol error envelope."""

    model_config = ConfigDict(extra="forbid", populate_by_name=True)

    type: Literal["MSG"] = "MSG"
    id: UUID
    ts: datetime
    from_: AgentName = Field(alias="from")
    to: AgentName
    action: Literal["ERROR"] = "ERROR"
    payload: StrictStr
    code: StrictStr
    in_reply_to: UUID | None = None
