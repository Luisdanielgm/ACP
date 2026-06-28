"""Handler-free helpers extracted from acp_managed.app (A-DETANGLE-01).

Pure-ish helpers (sanitizers, slug allocation, request origin, replay filter,
agent bootstrap payload, dashboard URLs) with no FastAPI route handlers. They are
re-exported from acp_managed.app for backward compatibility, since the route
closures reference them as module globals.
"""

from __future__ import annotations

import re
import time
import unicodedata
import urllib.parse

from fastapi import Request

from acp_managed.auth.sqlite_store import (
    ManagedAgentTokenRecord,
    ManagedRoomWallPostRecord,
    ManagedWorkspace,
    ManagedWorkspaceAdminInvitationRecord,
    ManagedWorkspaceMembership,
    ManagedWorkspaceSessionRecord,
    SqliteManagedPrincipalStore,
)
from acp_managed.auth.whitelist import ManagedPrincipal


def _sanitize_principal(principal: ManagedPrincipal) -> dict[str, str]:
    return {
        "email": principal.email,
        "role": principal.role,
        "status": principal.status,
    }


def _sanitize_workspace(workspace: ManagedWorkspace) -> dict[str, str]:
    return {
        "workspace_id": workspace.workspace_id,
        "slug": workspace.slug,
        "name": workspace.name,
        "status": workspace.status,
        "created_by": workspace.created_by,
    }


def _sanitize_membership(membership: ManagedWorkspaceMembership) -> dict[str, str]:
    return {
        "workspace_id": membership.workspace_id,
        "email": membership.email,
        "role": membership.role,
        "status": membership.status,
    }


def _sanitize_workspace_session(
    record: ManagedWorkspaceSessionRecord,
    *,
    include_owner_member_token: bool = False,
) -> dict[str, str | None]:
    payload: dict[str, str | None] = {
        "session_id": record.session_id,
        "workspace_id": record.workspace_id,
        "created_by_email": record.created_by_email,
        "owner_agent_name": record.owner_agent_name,
        "title": record.title,
        "project": record.project,
        "prompt": record.prompt,
        "created_at": record.created_at,
    }
    # The owner member token lets the holder operate the session as the chief
    # (send/wait/leave). It is only ever surfaced behind require_workspace_admin_access,
    # which is the same trust boundary the server-side /live redirect already uses.
    # It MUST stay out of agent-token (Bearer) responses so a collaborator token
    # cannot read the chief's member token for another session.
    if include_owner_member_token:
        payload["owner_member_token"] = record.owner_member_token
    return payload


def _sanitize_room_wall_post(record: ManagedRoomWallPostRecord) -> dict[str, str | bool]:
    return {
        "post_id": record.post_id,
        "session_id": record.session_id,
        "workspace_id": record.workspace_id,
        "author_type": record.author_type,
        "author_name": record.author_name,
        "body": record.body,
        "pinned": record.pinned,
        "created_at": record.created_at,
    }


def _managed_session_aliases(
    *,
    record: ManagedWorkspaceSessionRecord,
    acp_session: dict[str, object] | None = None,
) -> dict[str, object]:
    aliases: dict[str, object] = {
        "session_id": record.session_id,
        "owner_agent_name": record.owner_agent_name,
        "title": record.title,
        "project": record.project,
        "created_at": record.created_at,
    }
    if isinstance(acp_session, dict):
        for key in ("join_code", "member_token", "member_role", "current_member_dashboard_url"):
            value = acp_session.get(key)
            if value is not None:
                aliases[key] = value
        session_payload = acp_session.get("session")
        if isinstance(session_payload, dict):
            aliases["session"] = session_payload
            if session_payload.get("members") is not None:
                aliases["members"] = session_payload.get("members")
    return aliases


def _managed_replay_event_from_history(*, session_id: str, item: dict[str, object]) -> dict[str, object]:
    payload = dict(item)
    payload["session_id"] = session_id
    return {
        "event_id": str(item.get("event_id") or ""),
        "event_type": str(item.get("event") or "").lower(),
        "created_at": str(item.get("ts") or ""),
        "payload": payload,
    }


def _filter_managed_replay_history(
    *,
    session_id: str,
    history: list[object],
    actor: str | None,
    action: str | None,
    event_type: str | None,
    order: str,
    limit: int,
) -> list[dict[str, object]]:
    events: list[dict[str, object]] = []
    for raw_item in history:
        if not isinstance(raw_item, dict):
            continue
        if actor is not None and raw_item.get("actor") != actor:
            continue
        if action is not None and str(raw_item.get("action") or "").upper() != action:
            continue
        if event_type is not None and str(raw_item.get("event") or "").lower() != event_type:
            continue
        events.append(_managed_replay_event_from_history(session_id=session_id, item=raw_item))
    if order == "desc":
        events.reverse()
    return events[:limit]


def _sanitize_agent_token(record: ManagedAgentTokenRecord) -> dict[str, str | int | None]:
    return {
        "token_id": record.token_id,
        "workspace_id": record.workspace_id,
        "label": record.label,
        "agent_name": record.agent_name,
        "token_hint": record.token_hint,
        "status": record.status,
        "created_by_email": record.created_by_email,
        "created_at": record.created_at,
        "last_used_at": record.last_used_at,
    }


def _sanitize_workspace_admin_invitation(
    record: ManagedWorkspaceAdminInvitationRecord,
) -> dict[str, str | int | None]:
    return {
        "invitation_id": record.invitation_id,
        "workspace_id": record.workspace_id,
        "email": record.email,
        "status": record.status,
        "created_by_email": record.created_by_email,
        "created_at": record.created_at,
        "expires_at": record.expires_at,
        "accepted_at": record.accepted_at,
        "revoked_at": record.revoked_at,
    }


def _slugify_workspace_name(value: str) -> str:
    normalized = unicodedata.normalize("NFKD", value or "")
    ascii_only = normalized.encode("ascii", "ignore").decode("ascii")
    lowered = ascii_only.strip().lower()
    compact = re.sub(r"[^a-z0-9]+", "-", lowered).strip("-")
    return compact or "espacio"


def _allocate_workspace_slug(
    store: SqliteManagedPrincipalStore,
    *,
    name: str,
    preferred_slug: str | None = None,
) -> str:
    base_slug = _slugify_workspace_name(preferred_slug or name)
    candidate = base_slug
    suffix = 2
    while store.get_workspace_by_slug(candidate) is not None:
        candidate = f"{base_slug}-{suffix}"
        suffix += 1
    return candidate



def _default_agent_token_label(*, workspace: ManagedWorkspace, agent_name: str | None) -> str:
    if isinstance(agent_name, str) and agent_name.strip():
        return _slugify_workspace_name(f"{workspace.slug}-{agent_name.strip()}")[:64]
    return f"{workspace.slug}-agent-{int(time.time())}"[:64]


def _request_scheme(request: Request) -> str:
    forwarded_proto = request.headers.get("x-forwarded-proto", "").split(",")[0].strip()
    return forwarded_proto or request.url.scheme


def _request_is_secure(request: Request) -> bool:
    return _request_scheme(request).lower() == "https"


def _request_origin(request: Request) -> str:
    forwarded_host = request.headers.get("x-forwarded-host", "").split(",")[0].strip()
    host = forwarded_host or request.headers.get("host", "").strip()
    scheme = _request_scheme(request)
    if host:
        return f"{scheme}://{host}"
    return str(request.base_url).rstrip("/")


def _request_ws_origin(request: Request) -> str:
    forwarded_proto = request.headers.get("x-forwarded-proto", "").split(",")[0].strip()
    forwarded_host = request.headers.get("x-forwarded-host", "").split(",")[0].strip()
    host = forwarded_host or request.headers.get("host", "").strip()
    scheme = "wss" if (forwarded_proto or request.url.scheme) == "https" else "ws"
    if host:
        return f"{scheme}://{host}"
    return f"{scheme}://{request.base_url.netloc}"


def _managed_agent_bootstrap_payload(
    *,
    request: Request,
    workspace: ManagedWorkspace,
    token_record: ManagedAgentTokenRecord,
    raw_token: str | None = None,
) -> dict[str, object]:
    origin = _request_origin(request)
    hub_ws = f"{_request_ws_origin(request)}/ws"
    token_value = raw_token if isinstance(raw_token, str) and raw_token.strip() else "<MANAGED_AGENT_TOKEN>"
    token_scope = "agent" if isinstance(token_record.agent_name, str) and token_record.agent_name.strip() else "workspace"
    preferred_agent_name = token_record.agent_name.strip() if token_scope == "agent" else "codex-chief"
    share_prompt = "\n".join(
        [
            f"Usa ACP Managed para operar en {origin}.",
            f"Hub HTTP: {origin}",
            f"Hub WS: {hub_ws}",
            "Este es un token managed de workspace. No lo uses como ACP_TOKEN global del hub.",
            "El workspace se detecta automaticamente desde el token; no necesitas memorizar el slug para operar.",
            f"Workspace: {workspace.slug}",
            f"Token managed: {token_value}",
            "Antes de operar, instala o actualiza ACP_AGENT si hace falta usando estas guias:",
            f"- {origin}/downloads/ACP_AGENT.json",
            f"- {origin}/downloads/ACP_AGENT/AGENT.md",
            f"- {origin}/downloads/ACP_AGENT/skills/acp-session-coordinator/SKILL.md",
            "Usa un agent name distinto por proceso/config. No reutilices el mismo agente en dos sesiones vivas.",
            "Comandos utiles:",
            f"- python ACP_AGENT/acp.py managed-sessions --agent {preferred_agent_name} --agent-token {token_value}",
            f"- python ACP_AGENT/acp.py managed-start --agent {preferred_agent_name} --agent-token {token_value} --title \"Short task\"",
            f"- python ACP_AGENT/acp.py managed-join --agent {preferred_agent_name} --agent-token {token_value} --session-id SESSION_ID",
            f"- python ACP_AGENT/acp.py replay --agent {preferred_agent_name} --agent-token {token_value} --session-id SESSION_ID --actor worker-1 --action REPLY --limit 20",
            f"- python ACP_AGENT/acp.py managed-close --agent {preferred_agent_name} --agent-token {token_value} --session-id SESSION_ID",
            f"- python ACP_AGENT/acp.py connect --role worker --agent {preferred_agent_name} --agent-token {token_value} --project PROJECT_ID --workspace /path/to/project --capabilities backend,python",
            f"- python ACP_AGENT/acp.py invite --role worker --agent worker-1 --capabilities backend,python --session-id SESSION_ID --project PROJECT_ID",
            f"- python ACP_AGENT/acp.py onboard-help --agent {preferred_agent_name} --project PROJECT_ID",
            f"- python ACP_AGENT/acp.py onboard --agent {preferred_agent_name} --agent-token {token_value} --project PROJECT_ID --workspace /path/to/project --capabilities backend,python",
            f"- python ACP_AGENT/acp.py chief start --agent {preferred_agent_name} --backlog-dir coord/backlog --provider claude_local --workspace /path/to/project",
            f"- python ACP_AGENT/acp.py runner start --agent {preferred_agent_name} --hub-http {origin} --session-id SESSION_ID --member-token MEMBER_TOKEN --provider claude_local --workspace /path/to/project",
            "Para unirte a una sala existente, pide el SESSION_ID de esa sala y usa managed-join. Para onboarding autonomo de worker, usa connect u onboard: valida el token, encuentra la sala por project, se une, avisa READY al chief y deja el runner preparado.",
            "Para crear una sala nueva, usa managed-start. Para coordinar backlog autonomo, usa chief start con una cola local coord/backlog; las tareas JSON pueden incluir required_capabilities/tags para dispatch por capacidad, verify_command para reencolar con feedback cuando una entrega reportada como exitosa no verifica, y acceptance_criteria/verify_prompt para juez LLM con max_attempts. El chief despacha maximo una tarea por worker por tick, infiere task_id si hay una sola asignacion en vuelo y se auto-recupera de WAIT_ALREADY_ACTIVE propio. Para cerrar y limpiar una sala managed, usa managed-close.",
            "Para replies manuales, usa send/task/reply --task-id y --reply-to/--in-reply-to en vez de meter IDs en texto libre. El chief tambien reencola asignaciones vencidas por TTL para que no queden pegadas en assigned/.",
            "Para tareas largas, prefija instrucciones con [long] o [busy-hold:30]; el runner detecta el marcador dentro del payload JSON de TASK y mantiene busy heartbeat automaticamente.",
            "Daemon headless: puedes hacer join REST/managed, guardar o pasar session_id + member_token, y correr runner start para escuchar sin gastar tokens mientras esta idle.",
            "Si no puedes instalar ACP_AGENT, usa REST directo: crea con POST /managed/agent/sessions; une con POST /managed/agent/sessions/{session_id}/join; cierra con POST /managed/agent/sessions/{session_id}/close; envia con POST /sessions/send; recibe con POST /sessions/wait.",
            "En REST directo, manda el member token por X-ACP-Member-Token o member_token. El payload de mensajes va en payload, action debe ser TASK, REPLY o INFO, y to acepta un miembro real o all/* para broadcast a los otros miembros (excluye al emisor).",
            f"Si solo quieres validar el token o descubrir contexto, consulta {origin}/managed/agent/bootstrap con Authorization: Bearer <token>.",
        ]
    )
    return {
        "hub_http": origin,
        "hub_ws": hub_ws,
        "requires_workspace_slug": False,
        "workspace": _sanitize_workspace(workspace),
        "agent_token": _sanitize_agent_token(token_record),
        "token_scope": token_scope,
        "bootstrap_url": f"{origin}/managed/agent/bootstrap",
        "managed_routes": {
            "sessions": f"{origin}/managed/agent/sessions",
            "session_detail_template": f"{origin}/managed/agent/sessions/{{session_id}}",
            "session_join_template": f"{origin}/managed/agent/sessions/{{session_id}}/join",
            "session_close_template": f"{origin}/managed/agent/sessions/{{session_id}}/close",
            "session_replay_template": f"{origin}/managed/agent/sessions/{{session_id}}/replay",
        },
        "command_examples": {
            "managed_sessions": f"python ACP_AGENT/acp.py managed-sessions --agent {preferred_agent_name} --agent-token {token_value}",
            "managed_start": (
                f"python ACP_AGENT/acp.py managed-start --agent {preferred_agent_name} "
                f"--agent-token {token_value} --title \"Short task\" --capabilities planning"
            ),
            "managed_join": (
                f"python ACP_AGENT/acp.py managed-join --agent {preferred_agent_name} "
                f"--agent-token {token_value} --session-id SESSION_ID"
            ),
            "managed_replay": (
                f"python ACP_AGENT/acp.py replay --agent {preferred_agent_name} "
                f"--agent-token {token_value} --session-id SESSION_ID --actor worker-1 --action REPLY --limit 20"
            ),
            "managed_close": (
                f"python ACP_AGENT/acp.py managed-close --agent {preferred_agent_name} "
                f"--agent-token {token_value} --session-id SESSION_ID"
            ),
            "connect_worker": (
                f"python ACP_AGENT/acp.py connect --role worker --agent {preferred_agent_name} "
                f"--agent-token {token_value} --project PROJECT_ID --workspace /path/to/project --capabilities backend,python"
            ),
            "invite_worker": (
                "python ACP_AGENT/acp.py invite --role worker --agent worker-1 "
                "--capabilities backend,python --session-id SESSION_ID --project PROJECT_ID"
            ),
            "onboard_help": (
                f"python ACP_AGENT/acp.py onboard-help --agent {preferred_agent_name} --project PROJECT_ID"
            ),
            "onboard_worker": (
                f"python ACP_AGENT/acp.py onboard --agent {preferred_agent_name} "
                f"--agent-token {token_value} --project PROJECT_ID --workspace /path/to/project --capabilities backend,python"
            ),
            "chief_start": (
                f"python ACP_AGENT/acp.py chief start --agent {preferred_agent_name} "
                "--backlog-dir coord/backlog --provider claude_local --workspace /path/to/project"
            ),
            "runner_start_headless": (
                f"python ACP_AGENT/acp.py runner start --agent {preferred_agent_name} "
                f"--hub-http {origin} --session-id SESSION_ID --member-token MEMBER_TOKEN "
                "--provider claude_local --workspace /path/to/project"
            ),
        },
        "rest_examples": {
            "create_managed_session": {
                "method": "POST",
                "url": f"{origin}/managed/agent/sessions",
                "headers": {"Authorization": "Bearer <managed-agent-token>"},
                "json": {"agent_name": preferred_agent_name, "title": "Short task", "capabilities": ["planning"]},
            },
            "join_managed_session": {
                "method": "POST",
                "url": f"{origin}/managed/agent/sessions/{{session_id}}/join",
                "headers": {"Authorization": "Bearer <managed-agent-token>"},
                "json": {"agent_name": preferred_agent_name, "capabilities": ["backend"]},
            },
            "close_managed_session": {
                "method": "POST",
                "url": f"{origin}/managed/agent/sessions/{{session_id}}/close",
                "headers": {"Authorization": "Bearer <managed-agent-token>"},
                "json": {"detail": "Work complete"},
            },
            "managed_replay": {
                "method": "GET",
                "url": f"{origin}/managed/agent/sessions/{{session_id}}/replay?actor=worker-1&action=REPLY&limit=20",
                "headers": {"Authorization": "Bearer <managed-agent-token>"},
            },
            "send_message": {
                "method": "POST",
                "url": f"{origin}/sessions/send",
                "headers": {"X-ACP-Member-Token": "<member-token>"},
                "json": {
                    "session_id": "SESSION_ID",
                    "agent_name": preferred_agent_name,
                    "to": "member-name-or-all",
                    "action": "TASK",
                    "payload": {"task": "Do the work"},
                },
            },
            "wait_for_message": {
                "method": "POST",
                "url": f"{origin}/sessions/wait",
                "headers": {"X-ACP-Member-Token": "<member-token>"},
                "json": {"session_id": "SESSION_ID", "agent_name": preferred_agent_name, "timeout_seconds": 30},
            },
        },
        "share_prompt": share_prompt,
    }


def _session_dashboard_url(*, request: Request, session_id: str, agent_name: str, member_token: str) -> str:
    # session_id and agent_name are not secrets and may travel in the query
    # string. member_token is sensitive and is placed in the URL fragment so it
    # never appears in proxy access logs, Referer headers, or browser history
    # back-ends. The managed SPA reads location.hash to recover it.
    _ = request
    query = urllib.parse.urlencode(
        {
            "session_id": session_id,
            "agent_name": agent_name,
        }
    )
    fragment = urllib.parse.urlencode({"member_token": member_token})
    return f"/managed/dashboard/session?{query}#{fragment}"


def _session_dashboard_fallback_url(*, request: Request, session_id: str) -> str:
    _ = request
    query = urllib.parse.urlencode({"session_id": session_id})
    return f"/managed/dashboard/session?{query}"
