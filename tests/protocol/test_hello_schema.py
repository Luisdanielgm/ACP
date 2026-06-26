from __future__ import annotations

import sys
from pathlib import Path

import pytest
from pydantic import ValidationError

repo_root = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(repo_root / "apps" / "hub" / "src"))

from acp.protocol.models import HelloEnvelope
from acp.protocol.validators import validate_envelope


def test_hello_accepts_agent_and_observer_roles() -> None:
    hello = HelloEnvelope.model_validate({"type": "HELLO", "role": "agent", "name": "worker_1"})
    observer = HelloEnvelope.model_validate(
        {"type": "HELLO", "role": "observer", "name": "watcher-1"}
    )

    assert hello.role.value == "agent"
    assert observer.role.value == "observer"


def test_hello_rejects_invalid_role() -> None:
    with pytest.raises(ValidationError):
        HelloEnvelope.model_validate({"type": "HELLO", "role": "AGENT", "name": "worker_1"})


def test_hello_rejects_unsafe_name_chars() -> None:
    with pytest.raises(ValidationError):
        HelloEnvelope.model_validate({"type": "HELLO", "role": "agent", "name": "agente_á"})


def test_hello_rejects_empty_token_when_provided() -> None:
    with pytest.raises(ValidationError):
        HelloEnvelope.model_validate(
            {"type": "HELLO", "role": "agent", "name": "worker_1", "token": ""}
        )


def test_hello_requires_token_when_toggle_enabled() -> None:
    result = validate_envelope(
        {"type": "HELLO", "role": "agent", "name": "worker_1"},
        required_token="secret",
    )

    assert result.ok is False
    assert result.error is not None
    assert result.error.field == "token"


def test_hello_rejects_wrong_token_when_toggle_enabled() -> None:
    result = validate_envelope(
        {"type": "HELLO", "role": "agent", "name": "worker_1", "token": "wrong"},
        required_token="secret",
    )

    assert result.ok is False
    assert result.error is not None
    assert result.error.field == "token"


def test_hello_accepts_matching_token_when_toggle_enabled() -> None:
    result = validate_envelope(
        {"type": "HELLO", "role": "agent", "name": "worker_1", "token": "secret"},
        required_token="secret",
    )

    assert result.ok is True
    assert result.error is None

