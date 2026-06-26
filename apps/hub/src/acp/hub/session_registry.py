"""Session registry primitives for hub websocket lifecycle and routing state."""

from __future__ import annotations

from dataclasses import dataclass
from collections.abc import MutableMapping
from typing import Any, Literal

SessionRole = Literal["agent", "observer"]


@dataclass(frozen=True)
class SessionRecord:
    session_id: str
    websocket: Any
    role: SessionRole
    name: str
    live_trace_enabled: bool


class SessionRegistry:
    """In-memory registry with deterministic snapshots and duplicate checks."""

    def __init__(self, *, active_agents: MutableMapping[str, Any] | None = None) -> None:
        self._active_agents = active_agents if active_agents is not None else {}
        self._sessions: dict[str, SessionRecord] = {}
        self._agents_by_name: dict[str, str] = {}
        self._observer_session_ids: set[str] = set()

    def get_session(self, session_id: str) -> SessionRecord | None:
        return self._sessions.get(session_id)

    def register_agent(self, *, session_id: str, websocket: Any, name: str) -> bool:
        existing_session_id = self._agents_by_name.get(name)
        if existing_session_id is not None and existing_session_id != session_id:
            return False

        existing_socket = self._active_agents.get(name)
        if existing_socket is not None and existing_socket is not websocket:
            return False

        self._replace_existing_session(session_id)

        record = SessionRecord(
            session_id=session_id,
            websocket=websocket,
            role="agent",
            name=name,
            live_trace_enabled=True,
        )
        self._sessions[session_id] = record
        self._agents_by_name[name] = session_id
        self._active_agents[name] = websocket
        return True

    def register_observer(self, *, session_id: str, websocket: Any, name: str) -> SessionRecord:
        self._replace_existing_session(session_id)

        record = SessionRecord(
            session_id=session_id,
            websocket=websocket,
            role="observer",
            name=name,
            live_trace_enabled=False,
        )
        self._sessions[session_id] = record
        self._observer_session_ids.add(session_id)
        return record

    def enable_observer_live_traces(self, session_id: str) -> bool:
        record = self._sessions.get(session_id)
        if record is None or record.role != "observer":
            return False
        if record.live_trace_enabled:
            return True

        self._sessions[session_id] = SessionRecord(
            session_id=record.session_id,
            websocket=record.websocket,
            role=record.role,
            name=record.name,
            live_trace_enabled=True,
        )
        return True

    def unregister_session(self, *, session_id: str, websocket: Any | None = None) -> SessionRecord | None:
        record = self._sessions.get(session_id)
        if record is None:
            return None
        if websocket is not None and record.websocket is not websocket:
            return None

        self._sessions.pop(session_id, None)
        self._remove_indexes(record)
        return record

    def snapshot_agents(self) -> list[str]:
        for name, session_id in list(self._agents_by_name.items()):
            record = self._sessions.get(session_id)
            if record is None or record.role != "agent":
                self._agents_by_name.pop(name, None)
                self._active_agents.pop(name, None)
        return sorted(self._agents_by_name.keys())

    def observer_sessions(self, *, live_only: bool = True) -> list[SessionRecord]:
        sessions: list[SessionRecord] = []
        for session_id in sorted(self._observer_session_ids):
            record = self._sessions.get(session_id)
            if record is None or record.role != "observer":
                self._observer_session_ids.discard(session_id)
                continue
            if live_only and not record.live_trace_enabled:
                continue
            sessions.append(record)
        return sessions

    def _replace_existing_session(self, session_id: str) -> None:
        existing = self._sessions.get(session_id)
        if existing is None:
            return
        self._remove_indexes(existing)

    def _remove_indexes(self, record: SessionRecord) -> None:
        if record.role == "agent":
            if self._agents_by_name.get(record.name) == record.session_id:
                self._agents_by_name.pop(record.name, None)
            if self._active_agents.get(record.name) is record.websocket:
                self._active_agents.pop(record.name, None)
            return

        if record.role == "observer":
            self._observer_session_ids.discard(record.session_id)
