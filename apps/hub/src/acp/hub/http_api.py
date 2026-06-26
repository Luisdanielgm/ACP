"""HTTP compatibility API for ACP hub operator flows."""

from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from typing import Any, Mapping
from uuid import UUID, uuid4

from fastapi import APIRouter, Cookie, Header, HTTPException, Query, Request, Response
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse

from acp.hub.auth_service import PermissiveAuthService, ScopeDecision
from acp.hub.coordination_service import (
    SessionAccessError,
    SessionConflictError,
    SessionDashboardAccessError,
    SessionNotFoundError,
)
from acp.hub.event_store import ReplayFilters, StoredEvent
from acp.hub.journal import (
    INGRESS_HTTP,
    append_delivery_failed,
    append_received,
    append_rejected,
    append_routed,
)
from acp.hub.routing_service import (
    ROUTE_STATUS_DELIVERY_FAILED,
    ROUTE_STATUS_DESTINATION_NOT_FOUND,
    route_validated_msg,
)
from acp.hub.trace import emit_trace_authz, emit_trace_error, emit_trace_route
from acp.protocol.errors import (
    AUTH_FORBIDDEN,
    AUTH_INVALID,
    AUTH_REQUIRED,
    INVALID_FIELD,
    ProtocolValidationError,
    SESSION_NOT_FOUND,
    WAIT_ALREADY_ACTIVE,
    build_error,
)
from acp.protocol.models import AGENT_NAME_PATTERN
from acp.protocol.validators import parse_raw_envelope, validate_envelope

_REPLAY_ALLOWED_PARAMS = {
    "from",
    "to",
    "actor",
    "event_type",
    "message_id",
    "thread_id",
    "order",
    "limit",
    "cursor",
}
_REPLAY_ALLOWED_EVENT_TYPES = {"received", "routed", "rejected", "delivery_failed"}
_REPLAY_DEFAULT_LIMIT = 50
_REPLAY_MAX_LIMIT = 200
_SAFE_AGENT_NAME = re.compile(AGENT_NAME_PATTERN)
_SAFE_CAPABILITY = re.compile(r"^[a-z0-9][a-z0-9_.:-]{0,63}$")
_SESSION_ALLOWED_STATUS = {"idle", "waiting", "busy"}
_SESSION_ALLOWED_DELIVERY_MODES = {"attached", "runner"}
_RUNNER_ALLOWED_EVENTS = {"RUN_STARTED", "RUN_LOG", "RUN_FINISHED", "RUN_REPLY_SENT", "RUN_INTERRUPTED"}
_DASHBOARD_COOKIE_NAME = "acp_dashboard_session"
_BROADCAST_DESTINATIONS = {"all", "*"}
_SESSION_JOIN_OPENAPI_EXTRA = {
    "requestBody": {
        "required": True,
        "content": {
            "application/json": {
                "schema": {
                    "type": "object",
                    "required": ["agent_name", "join_code"],
                    "properties": {
                        "agent_name": {"type": "string"},
                        "join_code": {"type": "string"},
                        "token": {"type": "string"},
                        "delivery_mode": {"type": "string", "enum": ["attached", "runner"]},
                        "provider": {"type": "string"},
                        "workspace_path": {"type": "string"},
                        "capabilities": {
                            "oneOf": [
                                {"type": "array", "items": {"type": "string"}},
                                {"type": "string", "description": "Comma-separated capability tags."},
                            ]
                        },
                    },
                }
            }
        },
    }
}
_SESSION_WAIT_OPENAPI_EXTRA = {
    "requestBody": {
        "required": True,
        "content": {
            "application/json": {
                "schema": {
                    "type": "object",
                    "required": ["session_id", "agent_name"],
                    "properties": {
                        "session_id": {"type": "string"},
                        "agent_name": {"type": "string"},
                        "member_token": {
                            "type": "string",
                            "description": "Optional when X-ACP-Member-Token header is provided.",
                        },
                        "timeout_seconds": {"type": "number", "minimum": 0, "maximum": 300, "default": 30},
                    },
                }
            }
        },
    }
}
_SESSION_SEND_OPENAPI_EXTRA = {
    "requestBody": {
        "required": True,
        "content": {
            "application/json": {
                "schema": {
                    "type": "object",
                    "required": ["session_id", "agent_name", "to", "action", "payload"],
                    "properties": {
                        "session_id": {"type": "string"},
                        "agent_name": {"type": "string"},
                        "member_token": {
                            "type": "string",
                            "description": "Optional when X-ACP-Member-Token header is provided.",
                        },
                        "to": {
                            "type": "string",
                            "description": "Member agent name, or all/* to broadcast to every other member.",
                        },
                        "action": {"type": "string", "enum": ["TASK", "REPLY", "INFO"]},
                        "payload": {"oneOf": [{"type": "string"}, {"type": "object"}, {"type": "array"}]},
                        "thread_id": {"type": "string"},
                        "in_reply_to": {"type": "string"},
                    },
                }
            }
        },
    }
}


def _error_status_code(reason: ProtocolValidationError) -> int:
    if reason.code == AUTH_FORBIDDEN:
        return 403
    if reason.code in {AUTH_REQUIRED, AUTH_INVALID}:
        return 401
    if reason.code == "PAYLOAD_TOO_LARGE":
        return 413
    return 400


def _safe_error_payload(
    reason: ProtocolValidationError,
    *,
    in_reply_to: str | None = None,
) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "status": "error",
        "code": reason.code,
        "message": reason.message,
    }
    if reason.field is not None:
        payload["field"] = reason.field
    if reason.details:
        payload["details"] = reason.details
    if in_reply_to is not None:
        payload["in_reply_to"] = in_reply_to
    return payload


def _persistence_unavailable_response(
    *,
    in_reply_to: str | None = None,
) -> JSONResponse:
    reason = build_error(
        INVALID_FIELD,
        field="id",
        message="message persistence is temporarily unavailable.",
    )
    return JSONResponse(
        status_code=503,
        content=_safe_error_payload(reason, in_reply_to=in_reply_to),
    )


def _canonical_rfc3339(value: str, *, field: str) -> str:
    cleaned = value.strip()
    if not cleaned:
        raise ValueError(f"{field} must be RFC3339")
    candidate = cleaned[:-1] + "+00:00" if cleaned.endswith("Z") else cleaned
    try:
        parsed = datetime.fromisoformat(candidate)
    except ValueError as exc:
        raise ValueError(f"{field} must be RFC3339") from exc
    if parsed.tzinfo is None:
        raise ValueError(f"{field} must include timezone offset")
    return parsed.astimezone(timezone.utc).isoformat(timespec="microseconds").replace("+00:00", "Z")


def _canonical_uuid(value: str, *, field: str) -> str:
    cleaned = value.strip()
    if not cleaned:
        raise ValueError(f"{field} must be UUID")
    try:
        return str(UUID(cleaned))
    except ValueError as exc:
        raise ValueError(f"{field} must be UUID") from exc


def _serialize_event(event: StoredEvent) -> dict[str, Any]:
    return {
        "event_id": event.event_id,
        "event_type": event.event_type,
        "created_at": event.ts,
        "payload": event.payload,
    }


async def _send_json(websocket: Any, payload: Mapping[str, Any]) -> None:
    if hasattr(websocket, "send_json"):
        await websocket.send_json(dict(payload))
        return
    if hasattr(websocket, "send_text"):
        import json

        await websocket.send_text(json.dumps(dict(payload)))
        return
    raise TypeError("observer websocket must implement send_json() or send_text()")


async def _broadcast_trace(runtime: Any, *, event: dict[str, Any]) -> None:
    for observer in runtime.registry.observer_sessions(live_only=True):
        try:
            await _send_json(observer.websocket, event)
        except Exception:
            continue


async def _emit_authz_trace(
    runtime: Any,
    *,
    session_id: str,
    decision: ScopeDecision,
) -> None:
    event = emit_trace_authz(
        runtime.trace_sink,
        session_id=session_id,
        principal=decision.principal,
        scope=decision.scope,
        surface=decision.surface,
        decision=decision.decision,
        reason_code=decision.reason_code,
    )
    await _broadcast_trace(runtime, event=event)


def _normalize_http_body(parsed: dict[str, Any]) -> tuple[dict[str, Any], str | None]:
    body = dict(parsed)
    token_value = body.pop("token", None)
    token = token_value if isinstance(token_value, str) and token_value else None
    if "type" not in body:
        body["type"] = "MSG"
    return body, token


async def _load_json_object(request: Request) -> dict[str, Any] | None:
    try:
        parsed = await request.json()
    except Exception:
        return None
    if not isinstance(parsed, dict):
        return None
    return parsed


def _normalize_agent_name(value: Any, *, field: str = "agent_name") -> str:
    if not isinstance(value, str):
        raise ValueError(f"{field} must be a string.")
    cleaned = value.strip()
    if not cleaned or _SAFE_AGENT_NAME.fullmatch(cleaned) is None:
        raise ValueError(f"{field} is invalid.")
    return cleaned


def _normalize_optional_string(value: Any, *, field: str, max_length: int = 160) -> str | None:
    if value is None:
        return None
    if not isinstance(value, str):
        raise ValueError(f"{field} must be a string.")
    cleaned = value.strip()
    if not cleaned:
        return None
    return cleaned[:max_length]


def _normalize_member_token(value: Any) -> str:
    if not isinstance(value, str):
        raise ValueError("member_token must be a string.")
    cleaned = value.strip()
    if not cleaned:
        raise ValueError("member_token is required.")
    return cleaned


def _member_token_candidate(parsed: Mapping[str, Any], header_value: str | None) -> Any:
    body_value = parsed.get("member_token")
    if isinstance(body_value, str) and body_value.strip():
        return body_value
    return header_value


def _is_missing_required_value(value: Any) -> bool:
    if value is None:
        return True
    if isinstance(value, str) and not value.strip():
        return True
    return False


def _missing_required_fields(parsed: Mapping[str, Any], fields: tuple[str, ...]) -> list[str]:
    return [field for field in fields if _is_missing_required_value(parsed.get(field))]


def _missing_required_fields_response(fields: list[str]) -> JSONResponse:
    reason = build_error(
        INVALID_FIELD,
        field="body",
        message=f"missing required fields: {', '.join(fields)}.",
        details={"missing_fields": fields},
    )
    return JSONResponse(status_code=400, content=_safe_error_payload(reason))


def _normalize_message_destination(value: Any) -> str:
    if isinstance(value, str) and value.strip().lower() in _BROADCAST_DESTINATIONS:
        return "all"
    return _normalize_agent_name(value, field="to")


def _normalize_session_status(value: Any) -> str:
    if not isinstance(value, str):
        raise ValueError("status must be a string.")
    cleaned = value.strip().lower()
    if cleaned not in _SESSION_ALLOWED_STATUS:
        raise ValueError("status must be one of: idle, waiting, busy.")
    return cleaned


def _normalize_delivery_mode(value: Any) -> str | None:
    if value is None:
        return None
    if not isinstance(value, str):
        raise ValueError("delivery_mode must be a string.")
    cleaned = value.strip().lower()
    if cleaned not in _SESSION_ALLOWED_DELIVERY_MODES:
        raise ValueError("delivery_mode must be attached or runner.")
    return cleaned


def _normalize_workspace_path(value: Any) -> str | None:
    return _normalize_optional_string(value, field="workspace_path", max_length=512)


def _normalize_capabilities(value: Any) -> list[str] | None:
    if value is None:
        return None
    raw_items: list[Any]
    if isinstance(value, str):
        raw_items = [item.strip() for item in value.split(",")]
    elif isinstance(value, list):
        raw_items = value
    else:
        raise ValueError("capabilities must be an array of strings or a comma-separated string.")
    seen: set[str] = set()
    capabilities: list[str] = []
    for item in raw_items:
        if not isinstance(item, str):
            raise ValueError("capabilities entries must be strings.")
        cleaned = item.strip().lower()
        if not cleaned:
            continue
        if _SAFE_CAPABILITY.fullmatch(cleaned) is None:
            raise ValueError("capabilities entries may contain lowercase letters, numbers, _, ., :, or -.")
        if cleaned not in seen:
            seen.add(cleaned)
            capabilities.append(cleaned)
    return capabilities


def _normalize_runner_event(value: Any) -> str:
    if not isinstance(value, str):
        raise ValueError("event must be a string.")
    cleaned = value.strip().upper()
    if cleaned not in _RUNNER_ALLOWED_EVENTS:
        raise ValueError("event must be one of RUN_STARTED, RUN_LOG, RUN_FINISHED, RUN_REPLY_SENT, RUN_INTERRUPTED.")
    return cleaned


def _normalize_task_payload(value: Any) -> str | None:
    if value is None:
        return None
    if isinstance(value, str):
        return _normalize_optional_string(value, field="payload", max_length=32768)
    if isinstance(value, (dict, list)):
        encoded = json.dumps(value, ensure_ascii=True, separators=(",", ":"))
        return _normalize_optional_string(encoded, field="payload", max_length=32768)
    raise ValueError("payload must be a string, object, or array.")


def _get_auth_service(runtime: Any) -> Any:
    auth_service = getattr(runtime, "auth_service", None)
    if auth_service is None:
        auth_service = PermissiveAuthService(required_token=getattr(runtime, "required_token", None))
    return auth_service


def _authorize_dashboard_request(
    runtime: Any,
    *,
    authorization: str | None,
    x_acp_token: str | None,
    query_token: str | None,
) -> ProtocolValidationError | None:
    auth_service = _get_auth_service(runtime)
    return auth_service.authorize_http_send(
        authorization=authorization,
        x_acp_token=x_acp_token,
        body_token=query_token,
    )


def _resolve_dashboard_session(runtime: Any, dashboard_session_id: str | None) -> Any | None:
    store = getattr(runtime, "dashboard_sessions", None)
    if store is None:
        return None
    return store.get(dashboard_session_id)


def _authorize_managed_admin_session(
    runtime: Any,
    *,
    session_id: str,
    acp_managed_session: str | None,
) -> bool:
    authorizer = getattr(runtime, "managed_session_authorizer", None)
    if authorizer is None:
        return False
    try:
        return bool(authorizer(session_id=session_id, acp_managed_session=acp_managed_session))
    except HTTPException as exc:
        if exc.status_code in {401, 403, 404}:
            return False
        raise


def _request_is_secure(request: Request) -> bool:
    forwarded_proto = request.headers.get("x-forwarded-proto")
    if isinstance(forwarded_proto, str) and forwarded_proto.strip():
        first_hop = forwarded_proto.split(",")[0].strip().lower()
        if first_hop in {"http", "https"}:
            return first_hop == "https"
    return request.url.scheme == "https"


def build_http_router(runtime: Any, *, legacy_dashboard_enabled: bool = True) -> APIRouter:
    router = APIRouter()

    @router.get("/health")
    async def get_health() -> dict[str, str]:
        return {"status": "ok"}

    @router.get("/agents")
    async def get_agents() -> dict[str, list[str]]:
        return {"agents": runtime.registry.snapshot_agents()}

    @router.get("/dashboard", response_class=HTMLResponse)
    async def get_dashboard() -> RedirectResponse:
        return RedirectResponse(url="/managed/login", status_code=307)

    @router.get("/dashboard/session", response_class=HTMLResponse)
    async def get_session_dashboard() -> RedirectResponse:
        return RedirectResponse(url="/managed/login", status_code=307)

    @router.post("/dashboard/auth/login")
    async def post_dashboard_login(
        request: Request,
        response: Response,
        authorization: str | None = Header(default=None),
        x_acp_token: str | None = Header(default=None, alias="X-ACP-Token"),
    ) -> JSONResponse:
        if not legacy_dashboard_enabled:
            raise HTTPException(status_code=404, detail="legacy dashboard is disabled")
        parsed = await _load_json_object(request)
        body_token = parsed.get("token") if isinstance(parsed, dict) and isinstance(parsed.get("token"), str) else None
        auth_error = _authorize_dashboard_request(
            runtime,
            authorization=authorization,
            x_acp_token=x_acp_token,
            query_token=body_token,
        )
        if auth_error is not None:
            return JSONResponse(status_code=_error_status_code(auth_error), content=_safe_error_payload(auth_error))

        session = runtime.dashboard_sessions.create()
        dashboard_store = getattr(runtime, "dashboard_sessions", None)
        max_age = getattr(dashboard_store, "ttl_seconds", None)
        result = JSONResponse(status_code=200, content={"status": "ok", "dashboard_session": session.as_payload()})
        result.set_cookie(
            key=_DASHBOARD_COOKIE_NAME,
            value=session.session_id,
            httponly=True,
            samesite="lax",
            secure=_request_is_secure(request),
            path="/",
            max_age=max_age if isinstance(max_age, int) and max_age > 0 else None,
        )
        return result

    @router.post("/dashboard/auth/logout")
    async def post_dashboard_logout(
        response: Response,
        dashboard_session_id: str | None = Cookie(default=None, alias=_DASHBOARD_COOKIE_NAME),
    ) -> JSONResponse:
        if not legacy_dashboard_enabled:
            raise HTTPException(status_code=404, detail="legacy dashboard is disabled")
        runtime.dashboard_sessions.revoke(dashboard_session_id)
        result = JSONResponse(status_code=200, content={"status": "ok"})
        result.delete_cookie(key=_DASHBOARD_COOKIE_NAME, path="/")
        return result

    @router.get("/dashboard/auth/session")
    async def get_dashboard_auth_session(
        dashboard_session_id: str | None = Cookie(default=None, alias=_DASHBOARD_COOKIE_NAME),
    ) -> JSONResponse:
        if not legacy_dashboard_enabled:
            raise HTTPException(status_code=404, detail="legacy dashboard is disabled")
        session = _resolve_dashboard_session(runtime, dashboard_session_id)
        if session is None:
            return JSONResponse(
                status_code=200,
                content={
                    "status": "anonymous",
                    "authenticated": False,
                    "token_required": getattr(runtime, "required_token", None) is not None,
                },
            )
        return JSONResponse(
            status_code=200,
            content={
                "status": "ok",
                "authenticated": True,
                "token_required": getattr(runtime, "required_token", None) is not None,
                "dashboard_session": session.as_payload(),
            },
        )

    @router.get("/dashboard/overview")
    async def get_dashboard_overview(
        authorization: str | None = Header(default=None),
        x_acp_token: str | None = Header(default=None, alias="X-ACP-Token"),
        token: str | None = Query(default=None),
        dashboard_session_id: str | None = Cookie(default=None, alias=_DASHBOARD_COOKIE_NAME),
    ) -> JSONResponse:
        if not legacy_dashboard_enabled:
            raise HTTPException(status_code=404, detail="legacy dashboard is disabled")
        dashboard_session = _resolve_dashboard_session(runtime, dashboard_session_id)
        if dashboard_session is None:
            auth_error = _authorize_dashboard_request(
                runtime,
                authorization=authorization,
                x_acp_token=x_acp_token,
                query_token=token,
            )
            if auth_error is not None:
                return JSONResponse(status_code=_error_status_code(auth_error), content=_safe_error_payload(auth_error))

        overview = await runtime.coordination.dashboard_snapshot()
        return JSONResponse(
            status_code=200,
            content={
                "status": "ok",
                "hub": runtime.as_status_payload(),
                "connected_agents": runtime.registry.snapshot_agents(),
                "traces": list(runtime.trace_sink[-120:]),
                "overview": overview,
            },
        )

    @router.post("/sessions")
    async def post_create_session(
        request: Request,
        authorization: str | None = Header(default=None),
        x_acp_token: str | None = Header(default=None, alias="X-ACP-Token"),
    ) -> JSONResponse:
        parsed = await _load_json_object(request)
        if parsed is None:
            reason = build_error(INVALID_FIELD, field="body", message="body must be a JSON object.")
            return JSONResponse(status_code=400, content=_safe_error_payload(reason))

        auth_service = getattr(runtime, "auth_service", None)
        if auth_service is None:
            auth_service = PermissiveAuthService(required_token=getattr(runtime, "required_token", None))
        auth_error = auth_service.authorize_http_send(
            authorization=authorization,
            x_acp_token=x_acp_token,
            body_token=parsed.get("token") if isinstance(parsed.get("token"), str) else None,
        )
        if auth_error is not None:
            return JSONResponse(status_code=_error_status_code(auth_error), content=_safe_error_payload(auth_error))

        try:
            agent_name = _normalize_agent_name(parsed.get("agent_name"))
            title = _normalize_optional_string(parsed.get("title"), field="title")
            project = _normalize_optional_string(parsed.get("project"), field="project")
            delivery_mode = _normalize_delivery_mode(parsed.get("delivery_mode")) or "attached"
            provider = _normalize_optional_string(parsed.get("provider"), field="provider")
            workspace_path = _normalize_workspace_path(parsed.get("workspace_path"))
            capabilities = _normalize_capabilities(parsed.get("capabilities")) or []
        except ValueError as exc:
            reason = build_error(INVALID_FIELD, field="body", message=str(exc))
            return JSONResponse(status_code=400, content=_safe_error_payload(reason))

        try:
            created = await runtime.coordination.create_session(
                owner_agent=agent_name,
                title=title,
                project=project,
                capabilities=capabilities,
                delivery_mode=delivery_mode,
                provider=provider,
                workspace_path=workspace_path,
            )
        except SessionAccessError as exc:
            reason = build_error(INVALID_FIELD, field="agent_name", message=str(exc))
            return JSONResponse(status_code=409, content=_safe_error_payload(reason))

        return JSONResponse(status_code=201, content={"status": "ok", **created})

    @router.post("/sessions/join", openapi_extra=_SESSION_JOIN_OPENAPI_EXTRA)
    async def post_join_session(
        request: Request,
        authorization: str | None = Header(default=None),
        x_acp_token: str | None = Header(default=None, alias="X-ACP-Token"),
    ) -> JSONResponse:
        parsed = await _load_json_object(request)
        if parsed is None:
            reason = build_error(INVALID_FIELD, field="body", message="body must be a JSON object.")
            return JSONResponse(status_code=400, content=_safe_error_payload(reason))
        missing = _missing_required_fields(parsed, ("agent_name", "join_code"))
        if missing:
            return _missing_required_fields_response(missing)

        auth_service = getattr(runtime, "auth_service", None)
        if auth_service is None:
            auth_service = PermissiveAuthService(required_token=getattr(runtime, "required_token", None))
        auth_error = auth_service.authorize_http_send(
            authorization=authorization,
            x_acp_token=x_acp_token,
            body_token=parsed.get("token") if isinstance(parsed.get("token"), str) else None,
        )
        if auth_error is not None:
            return JSONResponse(status_code=_error_status_code(auth_error), content=_safe_error_payload(auth_error))

        try:
            agent_name = _normalize_agent_name(parsed.get("agent_name"))
            join_code = _normalize_optional_string(parsed.get("join_code"), field="join_code", max_length=24)
            if join_code is None:
                raise ValueError("join_code is required.")
            delivery_mode = _normalize_delivery_mode(parsed.get("delivery_mode")) or "attached"
            provider = _normalize_optional_string(parsed.get("provider"), field="provider")
            workspace_path = _normalize_workspace_path(parsed.get("workspace_path"))
            capabilities = _normalize_capabilities(parsed.get("capabilities")) or []
        except ValueError as exc:
            reason = build_error(INVALID_FIELD, field="body", message=str(exc))
            return JSONResponse(status_code=400, content=_safe_error_payload(reason))

        try:
            joined = await runtime.coordination.join_session(
                join_code=join_code,
                agent_name=agent_name,
                capabilities=capabilities,
                delivery_mode=delivery_mode,
                provider=provider,
                workspace_path=workspace_path,
            )
        except SessionAccessError as exc:
            reason = build_error(INVALID_FIELD, field="join_code", message=str(exc))
            return JSONResponse(status_code=409, content=_safe_error_payload(reason))

        return JSONResponse(status_code=200, content={"status": "ok", **joined})

    @router.get("/sessions/{session_id}")
    async def get_session_snapshot(
        session_id: str,
        agent_name: str = Query(...),
        member_token: str | None = Query(default=None),
        x_acp_member_token: str | None = Header(default=None, alias="X-ACP-Member-Token"),
    ) -> JSONResponse:
        try:
            normalized_agent = _normalize_agent_name(agent_name)
            normalized_token = _normalize_member_token(member_token or x_acp_member_token)
        except ValueError as exc:
            reason = build_error(INVALID_FIELD, field="member_token", message=str(exc))
            return JSONResponse(status_code=400, content=_safe_error_payload(reason))

        try:
            payload = await runtime.coordination.session_snapshot(
                session_id=session_id,
                agent_name=normalized_agent,
                member_token=normalized_token,
            )
        except SessionNotFoundError as exc:
            reason = build_error(SESSION_NOT_FOUND, field="session_id", message=str(exc))
            return JSONResponse(status_code=404, content=_safe_error_payload(reason))
        except SessionAccessError as exc:
            reason = build_error(INVALID_FIELD, field="session_id", message=str(exc))
            return JSONResponse(status_code=403, content=_safe_error_payload(reason))

        return JSONResponse(status_code=200, content={"status": "ok", "session": payload})

    @router.get("/sessions/{session_id}/detail")
    async def get_session_detail(
        session_id: str,
        agent_name: str | None = Query(default=None),
        member_token: str | None = Query(default=None),
        x_acp_member_token: str | None = Header(default=None, alias="X-ACP-Member-Token"),
        authorization: str | None = Header(default=None),
        x_acp_token: str | None = Header(default=None, alias="X-ACP-Token"),
        token: str | None = Query(default=None),
        dashboard_session_id: str | None = Cookie(default=None, alias=_DASHBOARD_COOKIE_NAME),
        acp_managed_session: str | None = Cookie(default=None),
    ) -> JSONResponse:
        admin_authorized = _resolve_dashboard_session(runtime, dashboard_session_id) is not None
        if not admin_authorized:
            admin_authorized = _authorize_managed_admin_session(
                runtime,
                session_id=session_id,
                acp_managed_session=acp_managed_session,
            )
        requested_admin_access = any(
            isinstance(value, str) and value.strip()
            for value in (authorization, x_acp_token, token)
        )
        if not admin_authorized and requested_admin_access:
            auth_error = _authorize_dashboard_request(
                runtime,
                authorization=authorization,
                x_acp_token=x_acp_token,
                query_token=token,
            )
            if auth_error is None:
                admin_authorized = True
            elif agent_name is None or member_token is None:
                return JSONResponse(status_code=_error_status_code(auth_error), content=_safe_error_payload(auth_error))

        normalized_agent: str | None = None
        normalized_member_token: str | None = None
        effective_member_token = member_token or x_acp_member_token
        if not admin_authorized and (agent_name is not None or effective_member_token is not None):
            try:
                if agent_name is None or effective_member_token is None:
                    raise ValueError("agent_name and member_token are required together.")
                normalized_agent = _normalize_agent_name(agent_name)
                normalized_member_token = _normalize_member_token(effective_member_token)
            except ValueError as exc:
                reason = build_error(INVALID_FIELD, field="member_token", message=str(exc))
                return JSONResponse(status_code=400, content=_safe_error_payload(reason))

        if not admin_authorized and (normalized_agent is None or normalized_member_token is None):
            reason = build_error(
                AUTH_REQUIRED,
                field="member_token",
                message="member credentials or an admin token are required for session detail.",
            )
            return JSONResponse(status_code=_error_status_code(reason), content=_safe_error_payload(reason))

        try:
            payload = await runtime.coordination.session_detail(
                session_id=session_id,
                agent_name=None if admin_authorized else normalized_agent,
                member_token=None if admin_authorized else normalized_member_token,
                include_join_code=True,
            )
        except SessionDashboardAccessError as exc:
            reason = build_error(INVALID_FIELD, field="member_token", message=str(exc))
            return JSONResponse(status_code=400, content=_safe_error_payload(reason))
        except SessionNotFoundError as exc:
            reason = build_error(SESSION_NOT_FOUND, field="session_id", message=str(exc))
            return JSONResponse(status_code=404, content=_safe_error_payload(reason))
        except SessionAccessError as exc:
            reason = build_error(INVALID_FIELD, field="session_id", message=str(exc))
            return JSONResponse(status_code=403, content=_safe_error_payload(reason))

        return JSONResponse(status_code=200, content={"status": "ok", "session": payload})

    @router.post("/sessions/{session_id}/admin/close")
    async def post_admin_close_session(
        session_id: str,
        request: Request,
        authorization: str | None = Header(default=None),
        x_acp_token: str | None = Header(default=None, alias="X-ACP-Token"),
        token: str | None = Query(default=None),
        dashboard_session_id: str | None = Cookie(default=None, alias=_DASHBOARD_COOKIE_NAME),
        acp_managed_session: str | None = Cookie(default=None),
    ) -> JSONResponse:
        parsed = await _load_json_object(request)
        if parsed is None:
            reason = build_error(INVALID_FIELD, field="body", message="body must be a JSON object.")
            return JSONResponse(status_code=400, content=_safe_error_payload(reason))

        admin_authorized = _resolve_dashboard_session(runtime, dashboard_session_id) is not None
        if not admin_authorized:
            admin_authorized = _authorize_managed_admin_session(
                runtime,
                session_id=session_id,
                acp_managed_session=acp_managed_session,
            )
        if not admin_authorized:
            auth_error = _authorize_dashboard_request(
                runtime,
                authorization=authorization,
                x_acp_token=x_acp_token,
                query_token=token,
            )
            if auth_error is not None:
                return JSONResponse(status_code=_error_status_code(auth_error), content=_safe_error_payload(auth_error))

        try:
            detail = _normalize_optional_string(parsed.get("detail"), field="detail", max_length=240)
            payload = await runtime.coordination.admin_close_session(
                session_id=session_id,
                actor="admin",
                detail=detail,
            )
        except SessionNotFoundError as exc:
            reason = build_error(SESSION_NOT_FOUND, field="session_id", message=str(exc))
            return JSONResponse(status_code=404, content=_safe_error_payload(reason))
        except SessionAccessError as exc:
            reason = build_error(INVALID_FIELD, field="session_id", message=str(exc))
            return JSONResponse(status_code=403, content=_safe_error_payload(reason))
        except ValueError as exc:
            reason = build_error(INVALID_FIELD, field="detail", message=str(exc))
            return JSONResponse(status_code=400, content=_safe_error_payload(reason))

        return JSONResponse(status_code=200, content={"status": "ok", **payload})

    @router.post("/sessions/{session_id}/admin/members/{agent_name}/disconnect")
    async def post_admin_disconnect_session_member(
        session_id: str,
        agent_name: str,
        request: Request,
        authorization: str | None = Header(default=None),
        x_acp_token: str | None = Header(default=None, alias="X-ACP-Token"),
        token: str | None = Query(default=None),
        dashboard_session_id: str | None = Cookie(default=None, alias=_DASHBOARD_COOKIE_NAME),
        acp_managed_session: str | None = Cookie(default=None),
    ) -> JSONResponse:
        parsed = await _load_json_object(request)
        if parsed is None:
            reason = build_error(INVALID_FIELD, field="body", message="body must be a JSON object.")
            return JSONResponse(status_code=400, content=_safe_error_payload(reason))

        admin_authorized = _resolve_dashboard_session(runtime, dashboard_session_id) is not None
        if not admin_authorized:
            admin_authorized = _authorize_managed_admin_session(
                runtime,
                session_id=session_id,
                acp_managed_session=acp_managed_session,
            )
        if not admin_authorized:
            auth_error = _authorize_dashboard_request(
                runtime,
                authorization=authorization,
                x_acp_token=x_acp_token,
                query_token=token,
            )
            if auth_error is not None:
                return JSONResponse(status_code=_error_status_code(auth_error), content=_safe_error_payload(auth_error))

        try:
            normalized_agent = _normalize_agent_name(agent_name)
            detail = _normalize_optional_string(parsed.get("detail"), field="detail", max_length=240)
            payload = await runtime.coordination.admin_remove_member(
                session_id=session_id,
                agent_name=normalized_agent,
                actor="admin",
                detail=detail,
            )
        except SessionNotFoundError as exc:
            reason = build_error(SESSION_NOT_FOUND, field="session_id", message=str(exc))
            return JSONResponse(status_code=404, content=_safe_error_payload(reason))
        except SessionAccessError as exc:
            reason = build_error(INVALID_FIELD, field="session_id", message=str(exc))
            return JSONResponse(status_code=403, content=_safe_error_payload(reason))
        except ValueError as exc:
            reason = build_error(INVALID_FIELD, field="agent_name", message=str(exc))
            return JSONResponse(status_code=400, content=_safe_error_payload(reason))

        return JSONResponse(status_code=200, content={"status": "ok", **payload})

    @router.post("/sessions/status")
    async def post_session_status(
        request: Request,
        x_acp_member_token: str | None = Header(default=None, alias="X-ACP-Member-Token"),
    ) -> JSONResponse:
        parsed = await _load_json_object(request)
        if parsed is None:
            reason = build_error(INVALID_FIELD, field="body", message="body must be a JSON object.")
            return JSONResponse(status_code=400, content=_safe_error_payload(reason))
        required = ["session_id", "agent_name"]
        if _is_missing_required_value(_member_token_candidate(parsed, x_acp_member_token)):
            required.append("member_token")
        missing = _missing_required_fields(parsed, tuple(required))
        if "member_token" in missing and not _is_missing_required_value(x_acp_member_token):
            missing.remove("member_token")
        if missing:
            return _missing_required_fields_response(missing)

        try:
            session_id = _normalize_optional_string(parsed.get("session_id"), field="session_id", max_length=64)
            if session_id is None:
                raise ValueError("session_id is required.")
            agent_name = _normalize_agent_name(parsed.get("agent_name"))
            member_token = _normalize_member_token(_member_token_candidate(parsed, x_acp_member_token))
            status = _normalize_session_status(parsed.get("status"))
            status_text = _normalize_optional_string(parsed.get("status_text"), field="status_text")
            delivery_mode = _normalize_delivery_mode(parsed.get("delivery_mode"))
            provider = _normalize_optional_string(parsed.get("provider"), field="provider")
            workspace_path = _normalize_workspace_path(parsed.get("workspace_path"))
            capabilities = _normalize_capabilities(parsed.get("capabilities"))
        except ValueError as exc:
            reason = build_error(INVALID_FIELD, field="status", message=str(exc))
            return JSONResponse(status_code=400, content=_safe_error_payload(reason))

        try:
            payload = await runtime.coordination.update_status(
                session_id=session_id,
                agent_name=agent_name,
                member_token=member_token,
                status=status,
                status_text=status_text,
                capabilities=capabilities,
                delivery_mode=delivery_mode,
                provider=provider,
                workspace_path=workspace_path,
            )
        except SessionNotFoundError as exc:
            reason = build_error(SESSION_NOT_FOUND, field="session_id", message=str(exc))
            return JSONResponse(status_code=404, content=_safe_error_payload(reason))
        except SessionAccessError as exc:
            reason = build_error(INVALID_FIELD, field="session_id", message=str(exc))
            return JSONResponse(status_code=403, content=_safe_error_payload(reason))

        return JSONResponse(status_code=200, content={"status": "ok", "member": payload})

    @router.post("/sessions/leave")
    async def post_session_leave(
        request: Request,
        x_acp_member_token: str | None = Header(default=None, alias="X-ACP-Member-Token"),
    ) -> JSONResponse:
        parsed = await _load_json_object(request)
        if parsed is None:
            reason = build_error(INVALID_FIELD, field="body", message="body must be a JSON object.")
            return JSONResponse(status_code=400, content=_safe_error_payload(reason))
        required = ["session_id", "agent_name"]
        if _is_missing_required_value(_member_token_candidate(parsed, x_acp_member_token)):
            required.append("member_token")
        missing = _missing_required_fields(parsed, tuple(required))
        if "member_token" in missing and not _is_missing_required_value(x_acp_member_token):
            missing.remove("member_token")
        if missing:
            return _missing_required_fields_response(missing)

        try:
            session_id = _normalize_optional_string(parsed.get("session_id"), field="session_id", max_length=64)
            if session_id is None:
                raise ValueError("session_id is required.")
            agent_name = _normalize_agent_name(parsed.get("agent_name"))
            member_token = _normalize_member_token(_member_token_candidate(parsed, x_acp_member_token))
        except ValueError as exc:
            reason = build_error(INVALID_FIELD, field="session_id", message=str(exc))
            return JSONResponse(status_code=400, content=_safe_error_payload(reason))

        try:
            payload = await runtime.coordination.leave_session(
                session_id=session_id,
                agent_name=agent_name,
                member_token=member_token,
            )
        except SessionNotFoundError as exc:
            reason = build_error(SESSION_NOT_FOUND, field="session_id", message=str(exc))
            return JSONResponse(status_code=404, content=_safe_error_payload(reason))
        except SessionAccessError as exc:
            reason = build_error(INVALID_FIELD, field="session_id", message=str(exc))
            return JSONResponse(status_code=403, content=_safe_error_payload(reason))

        return JSONResponse(status_code=200, content={"status": "ok", **payload})

    @router.post("/sessions/heartbeat")
    async def post_session_heartbeat(
        request: Request,
        x_acp_member_token: str | None = Header(default=None, alias="X-ACP-Member-Token"),
    ) -> JSONResponse:
        parsed = await _load_json_object(request)
        if parsed is None:
            reason = build_error(INVALID_FIELD, field="body", message="body must be a JSON object.")
            return JSONResponse(status_code=400, content=_safe_error_payload(reason))
        required = ["session_id", "agent_name"]
        if _is_missing_required_value(_member_token_candidate(parsed, x_acp_member_token)):
            required.append("member_token")
        missing = _missing_required_fields(parsed, tuple(required))
        if missing:
            return _missing_required_fields_response(missing)

        try:
            session_id = _normalize_optional_string(parsed.get("session_id"), field="session_id", max_length=64)
            if session_id is None:
                raise ValueError("session_id is required.")
            agent_name = _normalize_agent_name(parsed.get("agent_name"))
            member_token = _normalize_member_token(_member_token_candidate(parsed, x_acp_member_token))
            detail = _normalize_optional_string(parsed.get("detail"), field="detail")
            delivery_mode = _normalize_delivery_mode(parsed.get("delivery_mode"))
            provider = _normalize_optional_string(parsed.get("provider"), field="provider")
            workspace_path = _normalize_workspace_path(parsed.get("workspace_path"))
            capabilities = _normalize_capabilities(parsed.get("capabilities"))
        except ValueError as exc:
            reason = build_error(INVALID_FIELD, field="session_id", message=str(exc))
            return JSONResponse(status_code=400, content=_safe_error_payload(reason))

        try:
            payload = await runtime.coordination.heartbeat(
                session_id=session_id,
                agent_name=agent_name,
                member_token=member_token,
                detail=detail,
                capabilities=capabilities,
                delivery_mode=delivery_mode,
                provider=provider,
                workspace_path=workspace_path,
            )
        except SessionNotFoundError as exc:
            reason = build_error(SESSION_NOT_FOUND, field="session_id", message=str(exc))
            return JSONResponse(status_code=404, content=_safe_error_payload(reason))
        except SessionAccessError as exc:
            reason = build_error(INVALID_FIELD, field="session_id", message=str(exc))
            return JSONResponse(status_code=403, content=_safe_error_payload(reason))

        return JSONResponse(status_code=200, content={"status": "ok", "member": payload})

    @router.post("/sessions/wait", openapi_extra=_SESSION_WAIT_OPENAPI_EXTRA)
    async def post_session_wait(
        request: Request,
        x_acp_member_token: str | None = Header(default=None, alias="X-ACP-Member-Token"),
    ) -> JSONResponse:
        parsed = await _load_json_object(request)
        if parsed is None:
            reason = build_error(INVALID_FIELD, field="body", message="body must be a JSON object.")
            return JSONResponse(status_code=400, content=_safe_error_payload(reason))
        required = ["session_id", "agent_name"]
        if _is_missing_required_value(_member_token_candidate(parsed, x_acp_member_token)):
            required.append("member_token")
        missing = _missing_required_fields(parsed, tuple(required))
        if missing:
            return _missing_required_fields_response(missing)

        try:
            session_id = _normalize_optional_string(parsed.get("session_id"), field="session_id", max_length=64)
            if session_id is None:
                raise ValueError("session_id is required.")
            agent_name = _normalize_agent_name(parsed.get("agent_name"))
            member_token = _normalize_member_token(_member_token_candidate(parsed, x_acp_member_token))
            timeout_seconds_raw = parsed.get("timeout_seconds", 30.0)
            timeout_seconds = float(timeout_seconds_raw)
            if timeout_seconds <= 0 or timeout_seconds > 300:
                raise ValueError("timeout_seconds must be between 0 and 300.")
        except ValueError as exc:
            reason = build_error(INVALID_FIELD, field="timeout_seconds", message=str(exc))
            return JSONResponse(status_code=400, content=_safe_error_payload(reason))

        try:
            message = await runtime.coordination.wait_for_message(
                session_id=session_id,
                agent_name=agent_name,
                member_token=member_token,
                timeout_seconds=timeout_seconds,
            )
        except SessionConflictError as exc:
            details = {
                "recommended_command": "python ACP_AGENT/acp.py listen --config ACP_AGENT/agents/<agent>.json --stop-after-message --timeout-seconds 300",
                "do_not_run_concurrent_waits": True,
                "turn_based_agent_flow": [
                    "Stop the existing managed-join/listen/wait process if it is still running.",
                    "Run listen --stop-after-message --timeout-seconds 300.",
                    "Process exactly one message.",
                    "Send REPLY or INFO.",
                    "Publish waiting and repeat the one-message listen.",
                ],
            }
            details.update(getattr(exc, "details", {}))
            reason = build_error(
                WAIT_ALREADY_ACTIVE,
                field="agent_name",
                message=str(exc),
                details=details,
            )
            return JSONResponse(status_code=409, content=_safe_error_payload(reason))
        except SessionNotFoundError as exc:
            reason = build_error(SESSION_NOT_FOUND, field="session_id", message=str(exc))
            return JSONResponse(status_code=404, content=_safe_error_payload(reason))
        except SessionAccessError as exc:
            reason = build_error(INVALID_FIELD, field="session_id", message=str(exc))
            return JSONResponse(status_code=403, content=_safe_error_payload(reason))

        if message is None:
            return JSONResponse(status_code=200, content={"status": "timeout"})
        return JSONResponse(status_code=200, content={"status": "message", "message": message})

    @router.post("/sessions/cancel-wait", openapi_extra=_SESSION_WAIT_OPENAPI_EXTRA)
    async def post_session_cancel_wait(
        request: Request,
        x_acp_member_token: str | None = Header(default=None, alias="X-ACP-Member-Token"),
    ) -> JSONResponse:
        parsed = await _load_json_object(request)
        if parsed is None:
            reason = build_error(INVALID_FIELD, field="body", message="body must be a JSON object.")
            return JSONResponse(status_code=400, content=_safe_error_payload(reason))
        required = ["session_id", "agent_name"]
        if _is_missing_required_value(_member_token_candidate(parsed, x_acp_member_token)):
            required.append("member_token")
        missing = _missing_required_fields(parsed, tuple(required))
        if missing:
            return _missing_required_fields_response(missing)

        try:
            session_id = _normalize_optional_string(parsed.get("session_id"), field="session_id", max_length=64)
            if session_id is None:
                raise ValueError("session_id is required.")
            agent_name = _normalize_agent_name(parsed.get("agent_name"))
            member_token = _normalize_member_token(_member_token_candidate(parsed, x_acp_member_token))
        except ValueError as exc:
            reason = build_error(INVALID_FIELD, field="body", message=str(exc))
            return JSONResponse(status_code=400, content=_safe_error_payload(reason))

        try:
            payload = await runtime.coordination.cancel_wait(
                session_id=session_id,
                agent_name=agent_name,
                member_token=member_token,
            )
        except SessionNotFoundError as exc:
            reason = build_error(SESSION_NOT_FOUND, field="session_id", message=str(exc))
            return JSONResponse(status_code=404, content=_safe_error_payload(reason))
        except SessionAccessError as exc:
            reason = build_error(INVALID_FIELD, field="session_id", message=str(exc))
            return JSONResponse(status_code=403, content=_safe_error_payload(reason))
        return JSONResponse(status_code=200, content=payload)

    @router.post("/sessions/send", openapi_extra=_SESSION_SEND_OPENAPI_EXTRA)
    async def post_session_send(
        request: Request,
        x_acp_member_token: str | None = Header(default=None, alias="X-ACP-Member-Token"),
    ) -> JSONResponse:
        parsed = await _load_json_object(request)
        if parsed is None:
            reason = build_error(INVALID_FIELD, field="body", message="body must be a JSON object.")
            return JSONResponse(status_code=400, content=_safe_error_payload(reason))
        required = ["session_id", "agent_name", "to", "action", "payload"]
        if _is_missing_required_value(_member_token_candidate(parsed, x_acp_member_token)):
            required.append("member_token")
        missing = _missing_required_fields(parsed, tuple(required))
        if missing:
            return _missing_required_fields_response(missing)

        try:
            session_id = _normalize_optional_string(parsed.get("session_id"), field="session_id", max_length=64)
            if session_id is None:
                raise ValueError("session_id is required.")
            agent_name = _normalize_agent_name(parsed.get("agent_name"))
            member_token = _normalize_member_token(_member_token_candidate(parsed, x_acp_member_token))
            destination = _normalize_message_destination(parsed.get("to"))
            action = _normalize_optional_string(parsed.get("action"), field="action", max_length=32)
            if action not in {"TASK", "REPLY", "INFO"}:
                raise ValueError("action must be TASK, REPLY, or INFO.")
            payload_text = _normalize_task_payload(parsed.get("payload"))
            if payload_text is None:
                raise ValueError("payload is required.")
            thread_id = _normalize_optional_string(parsed.get("thread_id"), field="thread_id", max_length=64)
            in_reply_to = _normalize_optional_string(parsed.get("in_reply_to"), field="in_reply_to", max_length=64)
            # Optional client-supplied idempotency key: a retried send reusing the
            # same id is deduped per recipient (C-REL-06). Defaults to a fresh id.
            raw_message_id = parsed.get("id")
            message_id = (
                _canonical_uuid(raw_message_id, field="id")
                if isinstance(raw_message_id, str) and raw_message_id.strip()
                else str(uuid4())
            )
        except ValueError as exc:
            reason = build_error(INVALID_FIELD, field="payload", message=str(exc))
            return JSONResponse(status_code=400, content=_safe_error_payload(reason))

        envelope = {
            "type": "MSG",
            "id": message_id,
            "ts": datetime.now(timezone.utc).isoformat(timespec="microseconds").replace("+00:00", "Z"),
            "from": agent_name,
            "to": destination,
            "action": action,
            "payload": payload_text,
            "thread_id": thread_id,
            "in_reply_to": in_reply_to,
            "session_id": session_id,
        }

        try:
            queued = await runtime.coordination.send_message(
                session_id=session_id,
                agent_name=agent_name,
                member_token=member_token,
                payload=envelope,
            )
        except SessionNotFoundError as exc:
            reason = build_error(SESSION_NOT_FOUND, field="session_id", message=str(exc))
            return JSONResponse(status_code=404, content=_safe_error_payload(reason))
        except SessionAccessError as exc:
            reason = build_error(INVALID_FIELD, field="session_id", message=str(exc))
            return JSONResponse(status_code=403, content=_safe_error_payload(reason))

        return JSONResponse(status_code=200, content=queued)

    @router.post("/sessions/runs/events")
    async def post_session_run_event(
        request: Request,
        x_acp_member_token: str | None = Header(default=None, alias="X-ACP-Member-Token"),
    ) -> JSONResponse:
        parsed = await _load_json_object(request)
        if parsed is None:
            reason = build_error(INVALID_FIELD, field="body", message="body must be a JSON object.")
            return JSONResponse(status_code=400, content=_safe_error_payload(reason))

        try:
            session_id = _normalize_optional_string(parsed.get("session_id"), field="session_id", max_length=64)
            if session_id is None:
                raise ValueError("session_id is required.")
            agent_name = _normalize_agent_name(parsed.get("agent_name"))
            member_token = _normalize_member_token(_member_token_candidate(parsed, x_acp_member_token))
            event = _normalize_runner_event(parsed.get("event"))
            run_id = _normalize_optional_string(parsed.get("run_id"), field="run_id", max_length=128)
            if run_id is None:
                raise ValueError("run_id is required.")
            detail = _normalize_optional_string(parsed.get("detail"), field="detail", max_length=512)
            status_text = _normalize_optional_string(parsed.get("status_text"), field="status_text", max_length=240)
            provider = _normalize_optional_string(parsed.get("provider"), field="provider")
            workspace_path = _normalize_workspace_path(parsed.get("workspace_path"))
            task_id = _normalize_optional_string(parsed.get("task_id"), field="task_id", max_length=128)
            outcome = _normalize_optional_string(parsed.get("outcome"), field="outcome", max_length=64)
            summary = _normalize_optional_string(parsed.get("summary"), field="summary", max_length=512)
            log_chunk = _normalize_optional_string(parsed.get("log_chunk"), field="log_chunk", max_length=4096)
            metadata_value = parsed.get("metadata")
            metadata = dict(metadata_value) if isinstance(metadata_value, dict) else None
            capabilities = _normalize_capabilities(parsed.get("capabilities"))
        except ValueError as exc:
            reason = build_error(INVALID_FIELD, field="body", message=str(exc))
            return JSONResponse(status_code=400, content=_safe_error_payload(reason))

        try:
            member = await runtime.coordination.record_runner_event(
                session_id=session_id,
                agent_name=agent_name,
                member_token=member_token,
                event=event,
                run_id=run_id,
                detail=detail,
                status_text=status_text,
                provider=provider,
                workspace_path=workspace_path,
                task_id=task_id,
                outcome=outcome,
                summary=summary,
                log_chunk=log_chunk,
                metadata=metadata,
                capabilities=capabilities,
            )
        except SessionNotFoundError as exc:
            reason = build_error(SESSION_NOT_FOUND, field="session_id", message=str(exc))
            return JSONResponse(status_code=404, content=_safe_error_payload(reason))
        except SessionAccessError as exc:
            reason = build_error(INVALID_FIELD, field="session_id", message=str(exc))
            return JSONResponse(status_code=403, content=_safe_error_payload(reason))

        return JSONResponse(status_code=200, content={"status": "ok", "member": member})

    @router.get("/replay/events")
    async def get_replay_events(
        request: Request,
        x_acp_principal: str | None = Header(default=None, alias="X-ACP-Principal"),
        from_ts: str | None = Query(default=None, alias="from"),
        to_ts: str | None = Query(default=None, alias="to"),
        actor: str | None = Query(default=None),
        event_type: str | None = Query(default=None),
        message_id: str | None = Query(default=None),
        thread_id: str | None = Query(default=None),
        order: str = Query(default="desc"),
        limit: int = Query(default=_REPLAY_DEFAULT_LIMIT),
        cursor: str | None = Query(default=None),
    ) -> JSONResponse:
        auth_service = getattr(runtime, "auth_service", None)
        if auth_service is None:
            auth_service = PermissiveAuthService(required_token=getattr(runtime, "required_token", None))
        if hasattr(auth_service, "evaluate_scope"):
            decision = auth_service.evaluate_scope(
                scope="replay",
                principal=x_acp_principal.strip() if isinstance(x_acp_principal, str) and x_acp_principal.strip() else None,
                surface="http_replay",
            )
            await _emit_authz_trace(runtime, session_id="http:replay", decision=decision)
            if decision.decision == "deny":
                deny_reason = auth_service.deny_error(decision=decision, field="principal")
                error_event = emit_trace_error(
                    runtime.trace_sink,
                    session_id="http:replay",
                    reason_code=decision.reason_code,
                    requested_to=None,
                    in_reply_to=None,
                )
                await _broadcast_trace(runtime, event=error_event)
                return JSONResponse(
                    status_code=_error_status_code(deny_reason),
                    content=_safe_error_payload(deny_reason),
                )

        unknown = sorted(set(request.query_params.keys()) - _REPLAY_ALLOWED_PARAMS)
        if unknown:
            reason = build_error(
                INVALID_FIELD,
                field=unknown[0],
                message="unknown replay filter parameter.",
            )
            return JSONResponse(status_code=400, content=_safe_error_payload(reason))

        normalized_order = order.strip().lower()
        if normalized_order not in {"asc", "desc"}:
            reason = build_error(INVALID_FIELD, field="order", message="order must be asc or desc.")
            return JSONResponse(status_code=400, content=_safe_error_payload(reason))

        if limit <= 0:
            reason = build_error(INVALID_FIELD, field="limit", message="limit must be > 0.")
            return JSONResponse(status_code=400, content=_safe_error_payload(reason))
        normalized_limit = min(limit, _REPLAY_MAX_LIMIT)

        try:
            normalized_from = _canonical_rfc3339(from_ts, field="from") if from_ts is not None else None
            normalized_to = _canonical_rfc3339(to_ts, field="to") if to_ts is not None else None
        except ValueError as exc:
            field = "from" if "from" in str(exc) else "to"
            reason = build_error(INVALID_FIELD, field=field, message=str(exc))
            return JSONResponse(status_code=400, content=_safe_error_payload(reason))

        if normalized_from is not None and normalized_to is not None and normalized_from > normalized_to:
            reason = build_error(
                INVALID_FIELD,
                field="from",
                message="from must be less than or equal to to.",
            )
            return JSONResponse(status_code=400, content=_safe_error_payload(reason))

        normalized_actor: str | None = None
        if actor is not None:
            candidate = actor.strip()
            if _SAFE_AGENT_NAME.fullmatch(candidate) is None:
                reason = build_error(INVALID_FIELD, field="actor", message="actor must be a valid agent name.")
                return JSONResponse(status_code=400, content=_safe_error_payload(reason))
            normalized_actor = candidate

        normalized_event_type: str | None = None
        if event_type is not None:
            candidate = event_type.strip().lower()
            if candidate not in _REPLAY_ALLOWED_EVENT_TYPES:
                reason = build_error(
                    INVALID_FIELD,
                    field="event_type",
                    message="event_type must be one of received,routed,rejected,delivery_failed.",
                )
                return JSONResponse(status_code=400, content=_safe_error_payload(reason))
            normalized_event_type = candidate

        try:
            normalized_message_id = (
                _canonical_uuid(message_id, field="message_id") if message_id is not None else None
            )
            normalized_thread_id = _canonical_uuid(thread_id, field="thread_id") if thread_id is not None else None
        except ValueError as exc:
            field = "message_id" if "message_id" in str(exc) else "thread_id"
            reason = build_error(INVALID_FIELD, field=field, message=str(exc))
            return JSONResponse(status_code=400, content=_safe_error_payload(reason))

        filters = ReplayFilters(
            from_ts=normalized_from,
            to_ts=normalized_to,
            actor=normalized_actor,
            event_type=normalized_event_type,
            message_id=normalized_message_id,
            thread_id=normalized_thread_id,
        )
        store = getattr(runtime, "event_store", None)
        if store is None or not hasattr(store, "query_events"):
            reason = build_error(INVALID_FIELD, field="storage", message="replay read path is unavailable.")
            return JSONResponse(status_code=503, content=_safe_error_payload(reason))

        try:
            page = store.query_events(
                filters=filters,
                order=normalized_order,
                limit=normalized_limit,
                cursor=cursor,
            )
        except ValueError as exc:
            reason = build_error(INVALID_FIELD, field="cursor", message=str(exc))
            return JSONResponse(status_code=400, content=_safe_error_payload(reason))

        return JSONResponse(
            status_code=200,
            content={
                "events": [_serialize_event(event) for event in page.events],
                "next_cursor": page.next_cursor,
                "order": page.order,
                "limit": page.limit,
            },
        )

    @router.get("/replay/messages/{message_id}")
    async def get_message_timeline(
        message_id: str,
        x_acp_principal: str | None = Header(default=None, alias="X-ACP-Principal"),
    ) -> JSONResponse:
        auth_service = getattr(runtime, "auth_service", None)
        if auth_service is None:
            auth_service = PermissiveAuthService(required_token=getattr(runtime, "required_token", None))
        if hasattr(auth_service, "evaluate_scope"):
            decision = auth_service.evaluate_scope(
                scope="replay",
                principal=x_acp_principal.strip() if isinstance(x_acp_principal, str) and x_acp_principal.strip() else None,
                surface="http_replay",
            )
            await _emit_authz_trace(runtime, session_id="http:replay", decision=decision)
            if decision.decision == "deny":
                deny_reason = auth_service.deny_error(decision=decision, field="principal")
                error_event = emit_trace_error(
                    runtime.trace_sink,
                    session_id="http:replay",
                    reason_code=decision.reason_code,
                    requested_to=None,
                    in_reply_to=None,
                )
                await _broadcast_trace(runtime, event=error_event)
                return JSONResponse(
                    status_code=_error_status_code(deny_reason),
                    content=_safe_error_payload(deny_reason),
                )

        try:
            normalized_message_id = _canonical_uuid(message_id, field="message_id")
        except ValueError as exc:
            reason = build_error(INVALID_FIELD, field="message_id", message=str(exc))
            return JSONResponse(status_code=400, content=_safe_error_payload(reason))

        store = getattr(runtime, "event_store", None)
        if store is None or not hasattr(store, "query_message_timeline"):
            reason = build_error(INVALID_FIELD, field="storage", message="replay read path is unavailable.")
            return JSONResponse(status_code=503, content=_safe_error_payload(reason))

        timeline = store.query_message_timeline(message_id=normalized_message_id)
        if timeline is None:
            reason = build_error(INVALID_FIELD, field="message_id", message="message timeline not found.")
            return JSONResponse(status_code=404, content=_safe_error_payload(reason))

        return JSONResponse(
            status_code=200,
            content={
                "metadata": {
                    "message_id": timeline.message_id,
                    "timeline_status": timeline.timeline_status,
                },
                "events": [_serialize_event(event) for event in timeline.events],
            },
        )

    @router.post("/send")
    async def post_send(
        request: Request,
        authorization: str | None = Header(default=None),
        x_acp_token: str | None = Header(default=None, alias="X-ACP-Token"),
        x_acp_principal: str | None = Header(default=None, alias="X-ACP-Principal"),
    ) -> JSONResponse:
        event_store = getattr(runtime, "event_store", None)
        persistence_strict = bool(getattr(runtime, "persistence_strict", False))
        raw_body = await request.body()
        parsed, parse_error = parse_raw_envelope(raw_body)
        if parse_error is not None:
            if event_store is not None:
                try:
                    append_rejected(
                        event_store=event_store,
                        ingress=INGRESS_HTTP,
                        reason_code=f"HTTP_{parse_error.code}",
                    )
                except Exception:
                    if persistence_strict:
                        return _persistence_unavailable_response()
            return JSONResponse(
                status_code=_error_status_code(parse_error),
                content=_safe_error_payload(parse_error),
            )
        if parsed is None:
            reason = build_error("INVALID_SCHEMA")
            return JSONResponse(status_code=400, content=_safe_error_payload(reason))

        normalized, body_token = _normalize_http_body(parsed)
        auth_service = getattr(runtime, "auth_service", None)
        if auth_service is None:
            auth_service = PermissiveAuthService(required_token=getattr(runtime, "required_token", None))
        auth_error = auth_service.authorize_http_send(
            authorization=authorization,
            x_acp_token=x_acp_token,
            body_token=body_token,
        )
        if auth_error is not None:
            if event_store is not None:
                try:
                    append_rejected(
                        event_store=event_store,
                        ingress=INGRESS_HTTP,
                        reason_code=f"HTTP_{auth_error.code}",
                        message=normalized,
                        sender_fallback=normalized.get("from") if isinstance(normalized.get("from"), str) else None,
                    )
                except Exception:
                    if persistence_strict:
                        return _persistence_unavailable_response(
                            in_reply_to=normalized.get("id") if isinstance(normalized.get("id"), str) else None
                        )
            return JSONResponse(
                status_code=_error_status_code(auth_error),
                content=_safe_error_payload(auth_error),
            )

        result = validate_envelope(normalized, max_payload_bytes=runtime.max_payload_bytes)
        if not result.ok:
            reason = result.error or build_error("INVALID_SCHEMA")
            if event_store is not None:
                try:
                    append_rejected(
                        event_store=event_store,
                        ingress=INGRESS_HTTP,
                        reason_code=f"HTTP_{reason.code}",
                        message=normalized,
                        sender_fallback=normalized.get("from") if isinstance(normalized.get("from"), str) else None,
                    )
                except Exception:
                    if persistence_strict:
                        return _persistence_unavailable_response(
                            in_reply_to=normalized.get("id") if isinstance(normalized.get("id"), str) else None
                        )
            return JSONResponse(
                status_code=_error_status_code(reason),
                content=_safe_error_payload(reason),
            )

        if result.message_type != "MSG" or result.data is None:
            reason = build_error(INVALID_FIELD, field="type", message="/send expects MSG payload")
            if event_store is not None:
                try:
                    append_rejected(
                        event_store=event_store,
                        ingress=INGRESS_HTTP,
                        reason_code="HTTP_INVALID_TYPE",
                        message=normalized,
                        sender_fallback=normalized.get("from") if isinstance(normalized.get("from"), str) else None,
                    )
                except Exception:
                    if persistence_strict:
                        return _persistence_unavailable_response(
                            in_reply_to=normalized.get("id") if isinstance(normalized.get("id"), str) else None
                        )
            return JSONResponse(status_code=400, content=_safe_error_payload(reason))

        payload = result.data
        session_id = f"http:{payload.get('from', 'unknown')}"
        header_principal = (
            x_acp_principal.strip() if isinstance(x_acp_principal, str) and x_acp_principal.strip() else None
        )
        if bool(getattr(runtime, "auth_enforce", False)):
            principal = header_principal
        else:
            principal = header_principal or (
                payload.get("from") if isinstance(payload.get("from"), str) else None
            )
        if hasattr(auth_service, "evaluate_identity_binding"):
            binding_decision = auth_service.evaluate_identity_binding(
                principal=principal,
                claimed_sender=payload.get("from") if isinstance(payload.get("from"), str) else None,
                surface="http_send",
            )
            await _emit_authz_trace(runtime, session_id=session_id, decision=binding_decision)
            if binding_decision.decision == "deny":
                deny_reason = auth_service.deny_error(decision=binding_decision, field="from")
                if event_store is not None:
                    try:
                        append_rejected(
                            event_store=event_store,
                            ingress=INGRESS_HTTP,
                            reason_code=binding_decision.reason_code,
                            message=payload,
                            sender_fallback=payload.get("from"),
                        )
                    except Exception:
                        if persistence_strict:
                            return _persistence_unavailable_response(
                                in_reply_to=payload.get("id"),
                            )
                error_event = emit_trace_error(
                    runtime.trace_sink,
                    session_id=session_id,
                    reason_code=binding_decision.reason_code,
                    requested_to=payload.get("to"),
                    in_reply_to=payload.get("id"),
                )
                await _broadcast_trace(runtime, event=error_event)
                return JSONResponse(
                    status_code=_error_status_code(deny_reason),
                    content=_safe_error_payload(deny_reason, in_reply_to=payload.get("id")),
                )

        if hasattr(auth_service, "evaluate_scope"):
            send_decision = auth_service.evaluate_scope(
                scope="send",
                principal=principal,
                surface="http_send",
            )
            await _emit_authz_trace(runtime, session_id=session_id, decision=send_decision)
            if send_decision.decision == "deny":
                deny_reason = auth_service.deny_error(decision=send_decision, field="principal")
                if event_store is not None:
                    try:
                        append_rejected(
                            event_store=event_store,
                            ingress=INGRESS_HTTP,
                            reason_code=send_decision.reason_code,
                            message=payload,
                            sender_fallback=payload.get("from"),
                        )
                    except Exception:
                        if persistence_strict:
                            return _persistence_unavailable_response(
                                in_reply_to=payload.get("id"),
                            )
                error_event = emit_trace_error(
                    runtime.trace_sink,
                    session_id=session_id,
                    reason_code=send_decision.reason_code,
                    requested_to=payload.get("to"),
                    in_reply_to=payload.get("id"),
                )
                await _broadcast_trace(runtime, event=error_event)
                return JSONResponse(
                    status_code=_error_status_code(deny_reason),
                    content=_safe_error_payload(deny_reason, in_reply_to=payload.get("id")),
                )
        if hasattr(auth_service, "evaluate_acl"):
            acl_decision = auth_service.evaluate_acl(
                principal=principal,
                sender=payload.get("from") if isinstance(payload.get("from"), str) else None,
                recipient=payload.get("to") if isinstance(payload.get("to"), str) else None,
                action=payload.get("action") if isinstance(payload.get("action"), str) else None,
                surface="http_send",
            )
            await _emit_authz_trace(runtime, session_id=session_id, decision=acl_decision)
            if acl_decision.decision == "deny":
                deny_reason = auth_service.deny_error(decision=acl_decision, field="to")
                if event_store is not None:
                    try:
                        append_rejected(
                            event_store=event_store,
                            ingress=INGRESS_HTTP,
                            reason_code=acl_decision.reason_code,
                            message=payload,
                            sender_fallback=payload.get("from"),
                        )
                    except Exception:
                        if persistence_strict:
                            return _persistence_unavailable_response(
                                in_reply_to=payload.get("id"),
                            )
                error_event = emit_trace_error(
                    runtime.trace_sink,
                    session_id=session_id,
                    reason_code=acl_decision.reason_code,
                    requested_to=payload.get("to"),
                    in_reply_to=payload.get("id"),
                )
                await _broadcast_trace(runtime, event=error_event)
                return JSONResponse(
                    status_code=_error_status_code(deny_reason),
                    content=_safe_error_payload(deny_reason, in_reply_to=payload.get("id")),
                )
        if event_store is not None:
            try:
                append_received(
                    event_store=event_store,
                    ingress=INGRESS_HTTP,
                    message=payload,
                    sender_fallback=payload.get("from"),
                )
            except Exception:
                error_event = emit_trace_error(
                    runtime.trace_sink,
                    session_id=session_id,
                    reason_code="PERSISTENCE_RECEIVED_FAILED",
                    requested_to=payload.get("to"),
                    in_reply_to=payload.get("id"),
                )
                await _broadcast_trace(runtime, event=error_event)
                reason = build_error(
                    INVALID_FIELD,
                    field="id",
                    message="message persistence is temporarily unavailable.",
                )
                return JSONResponse(
                    status_code=503,
                    content=_safe_error_payload(reason, in_reply_to=payload.get("id")),
                )

        route_result = await route_validated_msg(payload=payload, active_agents=runtime.active_agents)

        if route_result.status == ROUTE_STATUS_DESTINATION_NOT_FOUND:
            if event_store is not None:
                try:
                    append_rejected(
                        event_store=event_store,
                        ingress=INGRESS_HTTP,
                        reason_code=route_result.reason_code or "DESTINATION_NOT_FOUND",
                        message=payload,
                        sender_fallback=payload.get("from"),
                    )
                except Exception:
                    persistence_error_event = emit_trace_error(
                        runtime.trace_sink,
                        session_id=session_id,
                        reason_code="PERSISTENCE_REJECTED_FAILED",
                        requested_to=payload.get("to"),
                        in_reply_to=payload.get("id"),
                    )
                    await _broadcast_trace(runtime, event=persistence_error_event)
                    if persistence_strict:
                        return _persistence_unavailable_response(
                            in_reply_to=payload.get("id"),
                        )
            error_event = emit_trace_error(
                runtime.trace_sink,
                session_id=session_id,
                reason_code=route_result.reason_code or "DESTINATION_NOT_FOUND",
                requested_to=payload.get("to"),
                in_reply_to=payload.get("id"),
            )
            await _broadcast_trace(runtime, event=error_event)

            reason = build_error(
                route_result.code or INVALID_FIELD,
                field=route_result.field,
                message=route_result.message,
            )
            return JSONResponse(
                status_code=404,
                content=_safe_error_payload(reason, in_reply_to=payload.get("id")),
            )

        if route_result.status == ROUTE_STATUS_DELIVERY_FAILED:
            if event_store is not None:
                try:
                    append_delivery_failed(
                        event_store=event_store,
                        ingress=INGRESS_HTTP,
                        reason_code=route_result.reason_code or "DESTINATION_DELIVERY_FAILED",
                        message=payload,
                        sender_fallback=payload.get("from"),
                    )
                except Exception:
                    persistence_error_event = emit_trace_error(
                        runtime.trace_sink,
                        session_id=session_id,
                        reason_code="PERSISTENCE_DELIVERY_FAILED",
                        requested_to=payload.get("to"),
                        in_reply_to=payload.get("id"),
                    )
                    await _broadcast_trace(runtime, event=persistence_error_event)
                    if persistence_strict:
                        return _persistence_unavailable_response(
                            in_reply_to=payload.get("id"),
                        )
            error_event = emit_trace_error(
                runtime.trace_sink,
                session_id=session_id,
                reason_code=route_result.reason_code or "DESTINATION_DELIVERY_FAILED",
                requested_to=payload.get("to"),
                in_reply_to=payload.get("id"),
            )
            await _broadcast_trace(runtime, event=error_event)

            reason = build_error(
                route_result.code or INVALID_FIELD,
                field=route_result.field,
                message=route_result.message,
            )
            return JSONResponse(
                status_code=503,
                content=_safe_error_payload(reason, in_reply_to=payload.get("id")),
            )

        if event_store is not None:
            try:
                append_routed(
                    event_store=event_store,
                    ingress=INGRESS_HTTP,
                    message=payload,
                    sender_fallback=payload.get("from"),
                )
            except Exception:
                persistence_error_event = emit_trace_error(
                    runtime.trace_sink,
                    session_id=session_id,
                    reason_code="PERSISTENCE_ROUTED_FAILED",
                    requested_to=payload.get("to"),
                    in_reply_to=payload.get("id"),
                )
                await _broadcast_trace(runtime, event=persistence_error_event)
                # Routing already succeeded and destination delivery already happened.
                # Keep sender success semantics stable to avoid false-negative 503.

        route_event = emit_trace_route(
            runtime.trace_sink,
            session_id=session_id,
            msg_id=payload.get("id"),
            from_name=payload.get("from"),
            to_name=payload.get("to"),
            action=payload.get("action"),
            thread_id=payload.get("thread_id"),
        )
        await _broadcast_trace(runtime, event=route_event)

        return JSONResponse(status_code=200, content={"status": "ok", "id": payload["id"]})

    return router
