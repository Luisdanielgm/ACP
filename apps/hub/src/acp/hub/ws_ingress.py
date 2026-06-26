"""WebSocket ingress loop with safe reject semantics."""

from __future__ import annotations

from collections.abc import MutableMapping
from typing import Any

from acp.hub.auth_service import AuthService, PermissiveAuthService, ScopeDecision
from acp.hub.event_store import EventStore, InMemoryEventStore
from acp.hub.journal import (
    INGRESS_WS,
    append_delivery_failed,
    append_received,
    append_rejected,
    append_routed,
)
from acp.hub.reject import reject_and_trace, send_runtime_error
from acp.hub.routing_service import (
    ROUTE_STATUS_DELIVERY_FAILED,
    ROUTE_STATUS_DESTINATION_NOT_FOUND,
    route_validated_msg,
)
from acp.hub.session_registry import SessionRegistry
from acp.hub.trace import (
    emit_trace_authz,
    emit_trace_connect,
    emit_trace_disconnect,
    emit_trace_error,
    emit_trace_route,
)
from acp.protocol.errors import AUTH_FORBIDDEN, INVALID_FIELD, ProtocolValidationError, build_error
from acp.protocol.models import MAX_PAYLOAD_BYTES
from acp.protocol.validators import validate_envelope


async def _safe_close(websocket: Any, *, code: int, reason: str) -> None:
    close_fn = getattr(websocket, "close", None)
    if close_fn is None:
        return
    try:
        await close_fn(code=code, reason=reason)
    except Exception:
        # Close failures should never bubble to the hub loop.
        return


async def _send_json(websocket: Any, payload: dict[str, Any]) -> None:
    if hasattr(websocket, "send_json"):
        await websocket.send_json(payload)
        return
    if hasattr(websocket, "send_text"):
        import json

        await websocket.send_text(json.dumps(payload))
        return
    raise TypeError("websocket must implement send_json() or send_text()")


async def _broadcast_trace_to_live_observers(
    registry: SessionRegistry,
    *,
    event: dict[str, Any],
    exclude_websocket: Any | None = None,
) -> None:
    for observer in registry.observer_sessions(live_only=True):
        if exclude_websocket is not None and observer.websocket is exclude_websocket:
            continue
        try:
            await _send_json(observer.websocket, event)
        except Exception:
            # Broadcast failures should not break ingress handling.
            continue


async def _reject_sender_identity(
    *,
    websocket: Any,
    trace_sink: Any,
    session_id: str,
    payload: dict[str, Any],
    sender_name: str | None,
    registry: SessionRegistry,
    reason: ProtocolValidationError | None = None,
) -> None:
    _, trace_event = await reject_and_trace(
        websocket=websocket,
        reason=reason
        or build_error(
            INVALID_FIELD,
            field="from",
            message="sender identity must match registered agent session.",
        ),
        trace_sink=trace_sink,
        session_id=session_id,
        raw_message=payload,
        sender_name=sender_name,
    )
    await _broadcast_trace_to_live_observers(registry, event=trace_event, exclude_websocket=websocket)


async def _emit_authz_decision(
    *,
    trace_sink: Any,
    registry: SessionRegistry,
    session_id: str,
    decision: ScopeDecision,
    exclude_websocket: Any | None = None,
) -> None:
    authz_event = emit_trace_authz(
        trace_sink,
        session_id=session_id,
        principal=decision.principal,
        scope=decision.scope,
        surface=decision.surface,
        decision=decision.decision,
        reason_code=decision.reason_code,
    )
    await _broadcast_trace_to_live_observers(
        registry,
        event=authz_event,
        exclude_websocket=exclude_websocket,
    )


async def _handle_persistence_failure(
    *,
    websocket: Any,
    trace_sink: Any,
    registry: SessionRegistry,
    session_id: str,
    reason_code: str,
    requested_to: Any,
    raw_message: Any,
    sender_name: str | None,
    persistence_strict: bool,
) -> None:
    if not persistence_strict:
        return
    await send_runtime_error(
        websocket=websocket,
        code=INVALID_FIELD,
        field="id",
        message="message persistence is temporarily unavailable.",
        session_id=session_id,
        raw_message=raw_message,
        sender_name=sender_name,
    )
    persistence_error = emit_trace_error(
        trace_sink,
        session_id=session_id,
        reason_code=reason_code,
        requested_to=requested_to,
        in_reply_to=raw_message.get("id") if isinstance(raw_message, dict) else None,
    )
    await _broadcast_trace_to_live_observers(registry, event=persistence_error)


async def _handle_msg(
    *,
    websocket: Any,
    payload: dict[str, Any],
    session_id: str,
    active_agents: MutableMapping[str, Any],
    trace_sink: Any,
    registry: SessionRegistry,
    auth_service: AuthService,
    event_store: EventStore,
    persistence_strict: bool,
) -> None:
    session = registry.get_session(session_id)
    session_name = session.name if session and session.role == "agent" else None

    sender_error = auth_service.authorize_ws_message(
        session_name=session_name,
        claimed_sender=payload.get("from"),
    )
    if sender_error is not None:
        try:
            append_rejected(
                event_store=event_store,
                ingress=INGRESS_WS,
                reason_code=f"WS_{sender_error.code}",
                message=payload,
                sender_fallback=session_name,
            )
        except Exception:
            pass
        await _reject_sender_identity(
            websocket=websocket,
            trace_sink=trace_sink,
            session_id=session_id,
            payload=payload,
            sender_name=session_name,
            registry=registry,
            reason=sender_error,
        )
        return

    if hasattr(auth_service, "evaluate_scope"):
        scope_decision = auth_service.evaluate_scope(
            scope="send",
            principal=session_name,
            surface="ws_msg",
        )
        await _emit_authz_decision(
            trace_sink=trace_sink,
            registry=registry,
            session_id=session_id,
            decision=scope_decision,
        )
        if scope_decision.decision == "deny":
            try:
                append_rejected(
                    event_store=event_store,
                    ingress=INGRESS_WS,
                    reason_code=scope_decision.reason_code,
                    message=payload,
                    sender_fallback=session_name,
                )
            except Exception:
                await _handle_persistence_failure(
                    websocket=websocket,
                    trace_sink=trace_sink,
                    registry=registry,
                    session_id=session_id,
                    reason_code="PERSISTENCE_REJECTED_FAILED",
                    requested_to=payload.get("to"),
                    raw_message=payload,
                    sender_name=session_name,
                    persistence_strict=persistence_strict,
                )
                if persistence_strict:
                    return
            await send_runtime_error(
                websocket=websocket,
                code=AUTH_FORBIDDEN,
                field="principal",
                message="operation denied by policy.",
                details={"reason_code": scope_decision.reason_code},
                session_id=session_id,
                raw_message=payload,
                sender_name=session_name,
            )
            deny_trace = emit_trace_error(
                trace_sink,
                session_id=session_id,
                reason_code=scope_decision.reason_code,
                requested_to=payload.get("to"),
                in_reply_to=payload.get("id"),
            )
            await _broadcast_trace_to_live_observers(registry, event=deny_trace)
            return
    if hasattr(auth_service, "evaluate_acl"):
        acl_decision = auth_service.evaluate_acl(
            principal=session_name,
            sender=payload.get("from") if isinstance(payload.get("from"), str) else None,
            recipient=payload.get("to") if isinstance(payload.get("to"), str) else None,
            action=payload.get("action") if isinstance(payload.get("action"), str) else None,
            surface="ws_msg",
        )
        await _emit_authz_decision(
            trace_sink=trace_sink,
            registry=registry,
            session_id=session_id,
            decision=acl_decision,
        )
        if acl_decision.decision == "deny":
            try:
                append_rejected(
                    event_store=event_store,
                    ingress=INGRESS_WS,
                    reason_code=acl_decision.reason_code,
                    message=payload,
                    sender_fallback=session_name,
                )
            except Exception:
                await _handle_persistence_failure(
                    websocket=websocket,
                    trace_sink=trace_sink,
                    registry=registry,
                    session_id=session_id,
                    reason_code="PERSISTENCE_REJECTED_FAILED",
                    requested_to=payload.get("to"),
                    raw_message=payload,
                    sender_name=session_name,
                    persistence_strict=persistence_strict,
                )
                if persistence_strict:
                    return
            await send_runtime_error(
                websocket=websocket,
                code=AUTH_FORBIDDEN,
                field="to",
                message="operation denied by policy.",
                details={"reason_code": acl_decision.reason_code},
                session_id=session_id,
                raw_message=payload,
                sender_name=session_name,
            )
            deny_trace = emit_trace_error(
                trace_sink,
                session_id=session_id,
                reason_code=acl_decision.reason_code,
                requested_to=payload.get("to"),
                in_reply_to=payload.get("id"),
            )
            await _broadcast_trace_to_live_observers(registry, event=deny_trace)
            return

    if session is None or session.role != "agent":
        return

    try:
        append_received(
            event_store=event_store,
            ingress=INGRESS_WS,
            message=payload,
            sender_fallback=session_name,
        )
    except Exception:
        await send_runtime_error(
            websocket=websocket,
            code=INVALID_FIELD,
            field="id",
            message="message persistence is temporarily unavailable.",
            session_id=session_id,
            raw_message=payload,
            sender_name=session_name,
        )
        persistence_error = emit_trace_error(
            trace_sink,
            session_id=session_id,
            reason_code="PERSISTENCE_RECEIVED_FAILED",
            requested_to=payload.get("to"),
            in_reply_to=payload.get("id"),
        )
        await _broadcast_trace_to_live_observers(registry, event=persistence_error)
        return

    route_result = await route_validated_msg(payload=payload, active_agents=active_agents)

    if route_result.status == ROUTE_STATUS_DESTINATION_NOT_FOUND:
        try:
            append_rejected(
                event_store=event_store,
                ingress=INGRESS_WS,
                reason_code=route_result.reason_code or "DESTINATION_NOT_FOUND",
                message=payload,
                sender_fallback=session_name,
            )
        except Exception:
            persistence_error = emit_trace_error(
                trace_sink,
                session_id=session_id,
                reason_code="PERSISTENCE_REJECTED_FAILED",
                requested_to=payload.get("to"),
                in_reply_to=payload.get("id"),
            )
            await _broadcast_trace_to_live_observers(registry, event=persistence_error)
            if persistence_strict:
                await send_runtime_error(
                    websocket=websocket,
                    code=INVALID_FIELD,
                    field="id",
                    message="message persistence is temporarily unavailable.",
                    session_id=session_id,
                    raw_message=payload,
                    sender_name=session_name,
                )
                return
        await send_runtime_error(
            websocket=websocket,
            code=route_result.code or INVALID_FIELD,
            field=route_result.field,
            message=route_result.message,
            session_id=session_id,
            raw_message=payload,
            sender_name=session_name,
        )
        error_event = emit_trace_error(
            trace_sink,
            session_id=session_id,
            reason_code=route_result.reason_code or "DESTINATION_NOT_FOUND",
            requested_to=payload.get("to"),
            in_reply_to=payload.get("id"),
        )
        await _broadcast_trace_to_live_observers(registry, event=error_event)
        return

    if route_result.status == ROUTE_STATUS_DELIVERY_FAILED:
        try:
            append_delivery_failed(
                event_store=event_store,
                ingress=INGRESS_WS,
                reason_code=route_result.reason_code or "DESTINATION_DELIVERY_FAILED",
                message=payload,
                sender_fallback=session_name,
            )
        except Exception:
            persistence_error = emit_trace_error(
                trace_sink,
                session_id=session_id,
                reason_code="PERSISTENCE_DELIVERY_FAILED",
                requested_to=payload.get("to"),
                in_reply_to=payload.get("id"),
            )
            await _broadcast_trace_to_live_observers(registry, event=persistence_error)
            if persistence_strict:
                await send_runtime_error(
                    websocket=websocket,
                    code=INVALID_FIELD,
                    field="id",
                    message="message persistence is temporarily unavailable.",
                    session_id=session_id,
                    raw_message=payload,
                    sender_name=session_name,
                )
                return
        # Existing behavior: destination socket failures are non-fatal and silent
        # to sender, preserving ingress stability under transient disconnects.
        return

    try:
        append_routed(
            event_store=event_store,
            ingress=INGRESS_WS,
            message=payload,
            sender_fallback=session_name,
        )
    except Exception:
        persistence_error = emit_trace_error(
            trace_sink,
            session_id=session_id,
            reason_code="PERSISTENCE_ROUTED_FAILED",
            requested_to=payload.get("to"),
            in_reply_to=payload.get("id"),
        )
        await _broadcast_trace_to_live_observers(registry, event=persistence_error)
        # Routing already succeeded and destination delivery already happened.
        # Avoid late runtime errors after successful delivery.

    route_event = emit_trace_route(
        trace_sink,
        session_id=session_id,
        msg_id=payload.get("id"),
        from_name=payload.get("from"),
        to_name=payload.get("to"),
        action=payload.get("action"),
        thread_id=payload.get("thread_id"),
    )
    await _broadcast_trace_to_live_observers(registry, event=route_event)


async def run_ws_ingress(
    websocket: Any,
    *,
    session_id: str,
    active_agents: MutableMapping[str, Any],
    trace_sink: Any,
    session_registry: SessionRegistry | None = None,
    auth_service: AuthService | None = None,
    event_store: EventStore | None = None,
    max_payload_bytes: int = MAX_PAYLOAD_BYTES,
    required_token: str | None = None,
    persistence_strict: bool = False,
) -> None:
    registry = session_registry or SessionRegistry(active_agents=active_agents)
    auth = auth_service or PermissiveAuthService(required_token=required_token)
    store = event_store or InMemoryEventStore()

    try:
        while True:
            try:
                raw_frame = await websocket.receive_text()
            except (StopAsyncIteration, EOFError):
                break
            except Exception:
                break

            result = validate_envelope(
                raw_frame,
                max_payload_bytes=max_payload_bytes,
            )
            if not result.ok:
                session = registry.get_session(session_id)
                _, trace_event = await reject_and_trace(
                    websocket=websocket,
                    reason=result.error or build_error(INVALID_FIELD),
                    trace_sink=trace_sink,
                    session_id=session_id,
                    raw_message=raw_frame,
                    sender_name=session.name if session and session.role == "agent" else None,
                )
                await _broadcast_trace_to_live_observers(
                    registry,
                    event=trace_event,
                    exclude_websocket=websocket,
                )
                try:
                    append_rejected(
                        event_store=store,
                        ingress=INGRESS_WS,
                        reason_code=f"WS_{(result.error or build_error(INVALID_FIELD)).code}",
                        message=None,
                        sender_fallback=session.name if session and session.role == "agent" else None,
                    )
                except Exception:
                    await _handle_persistence_failure(
                        websocket=websocket,
                        trace_sink=trace_sink,
                        registry=registry,
                        session_id=session_id,
                        reason_code="PERSISTENCE_REJECTED_FAILED",
                        requested_to=None,
                        raw_message=raw_frame,
                        sender_name=session.name if session and session.role == "agent" else None,
                        persistence_strict=persistence_strict,
                    )
                    if persistence_strict:
                        break
                continue

            payload = result.data or {}
            if result.message_type == "HELLO":
                hello_error = auth.authorize_ws_hello(token=payload.get("token"))
                if hello_error is not None:
                    session = registry.get_session(session_id)
                    _, trace_event = await reject_and_trace(
                        websocket=websocket,
                        reason=hello_error,
                        trace_sink=trace_sink,
                        session_id=session_id,
                        raw_message=payload,
                        sender_name=session.name if session and session.role == "agent" else None,
                    )
                    await _broadcast_trace_to_live_observers(
                        registry,
                        event=trace_event,
                        exclude_websocket=websocket,
                    )
                    try:
                        append_rejected(
                            event_store=store,
                            ingress=INGRESS_WS,
                            reason_code=f"WS_{hello_error.code}",
                            message=payload,
                            sender_fallback=session.name if session and session.role == "agent" else None,
                        )
                    except Exception:
                        await _handle_persistence_failure(
                            websocket=websocket,
                            trace_sink=trace_sink,
                            registry=registry,
                            session_id=session_id,
                            reason_code="PERSISTENCE_REJECTED_FAILED",
                            requested_to=None,
                            raw_message=payload,
                            sender_name=session.name if session and session.role == "agent" else None,
                            persistence_strict=persistence_strict,
                        )
                        if persistence_strict:
                            break
                    continue

                role = payload.get("role")
                name = payload.get("name")

                if role == "agent" and isinstance(name, str):
                    if hasattr(auth, "evaluate_scope"):
                        scope_decision = auth.evaluate_scope(
                            scope="connect",
                            principal=name,
                            surface="ws_hello",
                        )
                        await _emit_authz_decision(
                            trace_sink=trace_sink,
                            registry=registry,
                            session_id=session_id,
                            decision=scope_decision,
                            exclude_websocket=websocket,
                        )
                        if scope_decision.decision == "deny":
                            try:
                                append_rejected(
                                    event_store=store,
                                    ingress=INGRESS_WS,
                                    reason_code=scope_decision.reason_code,
                                    message=payload,
                                )
                            except Exception:
                                await _handle_persistence_failure(
                                    websocket=websocket,
                                    trace_sink=trace_sink,
                                    registry=registry,
                                    session_id=session_id,
                                    reason_code="PERSISTENCE_REJECTED_FAILED",
                                    requested_to=name,
                                    raw_message=payload,
                                    sender_name=None,
                                    persistence_strict=persistence_strict,
                                )
                                if persistence_strict:
                                    break
                            await send_runtime_error(
                                websocket=websocket,
                                code=AUTH_FORBIDDEN,
                                field="name",
                                message="operation denied by policy.",
                                details={"reason_code": scope_decision.reason_code},
                                session_id=session_id,
                                raw_message=payload,
                                sender_name=None,
                            )
                            deny_trace = emit_trace_error(
                                trace_sink,
                                session_id=session_id,
                                reason_code=scope_decision.reason_code,
                                requested_to=name,
                                in_reply_to=payload.get("id"),
                            )
                            await _broadcast_trace_to_live_observers(
                                registry,
                                event=deny_trace,
                                exclude_websocket=websocket,
                            )
                            await _safe_close(websocket, code=1008, reason="scope-denied")
                            break
                    registered = registry.register_agent(
                        session_id=session_id,
                        websocket=websocket,
                        name=name,
                    )
                    if not registered:
                        duplicate = build_error(
                            INVALID_FIELD,
                            field="name",
                            message="agent name is already connected.",
                        )
                        _, trace_event = await reject_and_trace(
                            websocket=websocket,
                            reason=duplicate,
                            trace_sink=trace_sink,
                            session_id=session_id,
                            raw_message=payload,
                            sender_name=None,
                        )
                        await _broadcast_trace_to_live_observers(
                            registry,
                            event=trace_event,
                            exclude_websocket=websocket,
                        )
                        try:
                            append_rejected(
                                event_store=store,
                                ingress=INGRESS_WS,
                                reason_code="WS_DUPLICATE_AGENT_NAME",
                                message=payload,
                            )
                        except Exception:
                            await _handle_persistence_failure(
                                websocket=websocket,
                                trace_sink=trace_sink,
                                registry=registry,
                                session_id=session_id,
                                reason_code="PERSISTENCE_REJECTED_FAILED",
                                requested_to=name,
                                raw_message=payload,
                                sender_name=None,
                                persistence_strict=persistence_strict,
                            )
                            if persistence_strict:
                                break
                        await _safe_close(websocket, code=1008, reason="duplicate-agent-name")
                        break
                    connect_event = emit_trace_connect(
                        trace_sink,
                        session_id=session_id,
                        role="agent",
                        name=name,
                    )
                    await _broadcast_trace_to_live_observers(registry, event=connect_event)

                elif role == "observer" and isinstance(name, str):
                    if hasattr(auth, "evaluate_scope"):
                        scope_decision = auth.evaluate_scope(
                            scope="observe",
                            principal=name,
                            surface="ws_hello",
                        )
                        await _emit_authz_decision(
                            trace_sink=trace_sink,
                            registry=registry,
                            session_id=session_id,
                            decision=scope_decision,
                            exclude_websocket=websocket,
                        )
                        if scope_decision.decision == "deny":
                            try:
                                append_rejected(
                                    event_store=store,
                                    ingress=INGRESS_WS,
                                    reason_code=scope_decision.reason_code,
                                    message=payload,
                                )
                            except Exception:
                                await _handle_persistence_failure(
                                    websocket=websocket,
                                    trace_sink=trace_sink,
                                    registry=registry,
                                    session_id=session_id,
                                    reason_code="PERSISTENCE_REJECTED_FAILED",
                                    requested_to=name,
                                    raw_message=payload,
                                    sender_name=None,
                                    persistence_strict=persistence_strict,
                                )
                                if persistence_strict:
                                    break
                            await send_runtime_error(
                                websocket=websocket,
                                code=AUTH_FORBIDDEN,
                                field="name",
                                message="operation denied by policy.",
                                details={"reason_code": scope_decision.reason_code},
                                session_id=session_id,
                                raw_message=payload,
                                sender_name=None,
                            )
                            deny_trace = emit_trace_error(
                                trace_sink,
                                session_id=session_id,
                                reason_code=scope_decision.reason_code,
                                requested_to=name,
                                in_reply_to=payload.get("id"),
                            )
                            await _broadcast_trace_to_live_observers(
                                registry,
                                event=deny_trace,
                                exclude_websocket=websocket,
                            )
                            await _safe_close(websocket, code=1008, reason="scope-denied")
                            break
                    registry.register_observer(
                        session_id=session_id,
                        websocket=websocket,
                        name=name,
                    )
                    await _send_json(
                        websocket,
                        {
                            "type": "SNAPSHOT",
                            "agents": registry.snapshot_agents(),
                        },
                    )
                    registry.enable_observer_live_traces(session_id)
                    connect_event = emit_trace_connect(
                        trace_sink,
                        session_id=session_id,
                        role="observer",
                        name=name,
                    )
                    await _broadcast_trace_to_live_observers(registry, event=connect_event)

                continue

            if result.message_type == "MSG":
                await _handle_msg(
                    websocket=websocket,
                    payload=payload,
                    session_id=session_id,
                    active_agents=active_agents,
                    trace_sink=trace_sink,
                    registry=registry,
                    auth_service=auth,
                    event_store=store,
                    persistence_strict=persistence_strict,
                )
                continue
    finally:
        removed_session = registry.unregister_session(session_id=session_id, websocket=websocket)
        should_emit_disconnect = (
            removed_session is not None
            and not (removed_session.role == "observer" and not removed_session.live_trace_enabled)
        )
        if should_emit_disconnect and removed_session is not None:
            disconnect_event = emit_trace_disconnect(
                trace_sink,
                session_id=removed_session.session_id,
                role=removed_session.role,
                name=removed_session.name,
            )
            await _broadcast_trace_to_live_observers(registry, event=disconnect_event)
