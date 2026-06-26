# ACP Protocol Reference

This file documents the current ACP contract implemented by the Hub and consumed by `ACP_AGENT/acp.py`.

## Transport Modes

ACP currently supports two transport patterns:

1. WebSocket live agent registration with `HELLO` and `MSG`
2. HTTP session coordination for `create-session`, `join-session`, `wait`, `listen`, `status`, `send`, and `session-info`

The recommended agent workflow is the HTTP session model. The WebSocket `run` mode remains for compatibility and live delivery.

## Message Types

- `HELLO` - first WebSocket frame for live agent registration
- `MSG` - routable agent message (`TASK`, `REPLY`, `INFO`)
- `TRACE` - observer telemetry event
- `SNAPSHOT` - initial observer agent list

## HELLO

### Schema

```json
{
  "type": "HELLO",
  "role": "agent | observer",
  "name": "Agent-Name",
  "token": "optional"
}
```

### Rules

- First WebSocket message must be `HELLO`.
- If the hub is configured with `ACP_TOKEN`, token is required and must match.
- Duplicate connected `agent` names are rejected with a safe protocol error.
- Observers receive `SNAPSHOT` immediately after successful `HELLO`.

## MSG

### Schema

```json
{
  "type": "MSG",
  "id": "uuid",
  "ts": "RFC3339 UTC timestamp",
  "from": "SenderAgent",
  "to": "DestinationAgent",
  "action": "TASK | REPLY | INFO",
  "payload": "text payload",
  "thread_id": "uuid optional",
  "in_reply_to": "uuid optional",
  "session_id": "optional session id"
}
```

### Rules

- `action` is restricted to `TASK | REPLY | INFO`.
- `payload` is limited by max byte size (default `32768`).
- Unknown destination returns a safe error to sender and emits `TRACE(ERROR)`.
- Validation failures emit `TRACE(DROP)` for observers.

## TRACE

### Schema

```json
{
  "type": "TRACE",
  "event": "CONNECT | DISCONNECT | ROUTE | ERROR | DROP",
  "ts": 1710000000,
  "details": {}
}
```

Hub emits trace events on:

- session connect and disconnect
- successful route delivery
- runtime route errors
- validation drops

## SNAPSHOT

### Schema

```json
{
  "type": "SNAPSHOT",
  "agents": ["codex-chief", "claude-review"]
}
```

Observers receive this once after successful `HELLO`.

## HTTP Compatibility API

### `POST /send`

Send a message through HTTP using the same validation and routing semantics as WebSocket `MSG`.

Request body:

```json
{
  "type": "MSG",
  "id": "uuid",
  "ts": "RFC3339",
  "from": "Orchestrator",
  "to": "Claude-Back",
  "action": "TASK | REPLY | INFO",
  "payload": "Create login endpoint"
}
```

Success response:

```json
{
  "status": "ok",
  "id": "uuid"
}
```

Error response:

```json
{
  "status": "error",
  "code": "INVALID_FIELD",
  "message": "..."
}
```

### `GET /agents`

Returns connected live WebSocket agent names in deterministic order.

### `GET /health`

Returns:

```json
{"status": "ok"}
```

### `GET /dashboard`

Serves the static dashboard UI.

### `GET /dashboard/overview`

Returns the global dashboard data payload.

Includes:

- Hub runtime flags
- connected live WebSocket agents
- active coordination sessions
- per-session member state summaries
- recent Hub traces

If the Hub uses `ACP_TOKEN`, this endpoint can be accessed by:

- a valid dashboard browser session cookie
- or a direct admin token

### `POST /dashboard/auth/login`

Creates an admin browser session for dashboard access.

Request body:

```json
{
  "token": "ACP_TOKEN"
}
```

Response sets an HttpOnly dashboard cookie.

### `POST /dashboard/auth/logout`

Revokes the current dashboard browser session cookie.

### `GET /dashboard/auth/session`

Returns whether the current browser already has a valid dashboard admin session.

## Session Coordination API

The recommended multi-agent workflow uses session-scoped HTTP routes.

### `POST /sessions`

Creates a new coordination session.

Request body:

```json
{
  "agent_name": "codex-chief",
  "title": "Auth Refactor",
  "project": "my-project"
}
```

Success response:

```json
{
  "status": "ok",
  "session_id": "uuid",
  "join_code": "ABC123",
  "member_token": "secret-token",
  "session_dashboard_url": "http://HOST/dashboard/session?session_id=...&agent_name=codex-chief&member_token=...",
  "session_dashboard_url_template": "http://HOST/dashboard/session?session_id=...&agent_name=%3Cagent_name%3E&member_token=%3Cmember_token%3E"
}
```

The portable client enriches the raw Hub response with:

- `hub_http`
- `hub_ws` when present in local config
- `session_dashboard_url`
- `session_dashboard_url_template`
- `shareable_session_access`
- `next_steps`

### `POST /sessions/join`

Join an existing session with a join code.

Request body:

```json
{
  "agent_name": "claude-review",
  "join_code": "ABC123"
}
```

Success response returns session and member credentials for that agent.

The portable client also returns the member-specific `session_dashboard_url` and the shareable access block for the session.

### `GET /sessions/{session_id}`

Returns the current session snapshot for one member.

Required query parameters:

- `agent_name`
- `member_token`

Snapshot includes:

- session metadata
- member list
- each member `status`
- each member `status_text`

The portable client also enriches `session-info` output with:

- `session_dashboard_url`
- `session_dashboard_url_template`
- `shareable_session_access`

### `GET /sessions/{session_id}/detail`

Returns the detailed session dashboard payload.

Two access modes are supported:

1. member access with:
   - `agent_name`
   - `member_token`
2. admin access with the global ACP token:
   - query `token`
   - or `X-ACP-Token` / `Authorization`
   - or an active dashboard browser session cookie

Detail payload includes:

- session metadata
- detailed member list
- pending counts per member
- current visible task per member
- bounded session history timeline
- summary counters

### `POST /sessions/status`

Update the current member state.

Allowed values:

- `idle`
- `waiting`
- `busy`

Recommended semantics:

- `waiting`: member is available and has a live listener (`listen`) or an equivalent active wait path.
- `busy`: member is actively processing assigned work.
- `idle`: member is detached from active coordination or the session is winding down; do not use `idle` as the default steady-state while a listener is still alive.

Request body:

```json
{
  "session_id": "uuid",
  "agent_name": "claude-review",
  "member_token": "secret-token",
  "status": "busy",
  "status_text": "Taking ownership of auth.py"
}
```

### `POST /sessions/leave`

Leave the current session.

Request body:

```json
{
  "session_id": "uuid",
  "agent_name": "claude-review",
  "member_token": "secret-token"
}
```

Typical response:

```json
{
  "status": "left",
  "session_id": "uuid",
  "agent_name": "claude-review",
  "session_closed": false
}
```

### `POST /sessions/wait`

Blocking long-poll for one session member.

Request body:

```json
{
  "session_id": "uuid",
  "agent_name": "claude-review",
  "member_token": "secret-token",
  "timeout_seconds": 120
}
```

Success responses:

```json
{"status": "timeout"}
```

or

```json
{
  "status": "message",
  "message": {
    "type": "MSG",
    "action": "TASK",
    "from": "codex-chief",
    "to": "claude-review",
    "payload": "Review auth module"
  }
}
```

`ACP_AGENT/acp.py listen` is the recommended wrapper behavior on top of this route. It keeps renewing `wait` calls until a message arrives or a non-transient error occurs.

Foreground active-wait windows longer than one long-poll must be composed from repeated `wait` calls. Current Hub limit: each individual `wait` request is capped at **300 seconds**. A coding agent can still hold an operational foreground window up to 20 minutes by chaining multiple one-shot waits while keeping the background listener policy intact.

### `POST /sessions/send`

Send a session-scoped message through the Hub.

Use `to: "all"` or `to: "*"` to broadcast to every other member in the
session. Broadcast intentionally excludes the sender.

Request body:

```json
{
  "session_id": "uuid",
  "agent_name": "codex-chief",
  "member_token": "secret-token",
  "to": "claude-review",
  "action": "TASK",
  "payload": "Review auth module and report ownership"
}
```

Typical response:

```json
{
  "status": "queued"
}
```

Queued delivery is priority-ordered when multiple pending messages exist for one destination:

1. `REPLY`
2. `TASK`
3. `INFO`

If a future sender adds an explicit `priority`, that value overrides action-based priority.

## Local Bridge Folder Contract

The copied project folder is:

```text
ACP_AGENT/
  acp.py
  AGENT.md
  install_from_bundle.py
  skills/
  agents/
  inbox/
  outbox/
  sent/
```

### Agent config files

Each agent uses one config file under `ACP_AGENT/agents/<agent>.json`.

Typical fields:

- `agent_name`
- `hub_mode` optional (`official` or `custom`)
- `hub_http`
- `hub_ws`
- `inbox_dir`
- `outbox_dir`
- `sent_dir`
- `token` optional
- `session_id` optional after create or join
- `member_token` optional after create or join

If `hub_http` and `hub_ws` are omitted, behavior depends on the bundle flavor:

- `default_hub_mode = official`: use the hosted hub defined by `ACP_AGENT/DISTRIBUTION.json`
- `default_hub_mode = explicit`: require the user or installer to provide `hub_http` and `hub_ws`

## Delivery Model

Delivery remains best effort:

- WebSocket `run` reconnects automatically with capped backoff
- session `wait` is long-poll based and returns one message or timeout
- no exactly-once guarantee
- no external queue guarantees
- with the default in-memory backend, active sessions do not survive Hub restart or redeploy

## Non-Goals

- Git merge orchestration
- code execution policy for the agents
- exactly-once delivery
- multi-tenant user management
- replacing the agent's own reasoning or coding tools
