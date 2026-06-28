# ACP (Agent Communication Protocol)

ACP is a coordination layer for coding agents.

- `apps/hub`: remote Hub runtime
- `ACP_AGENT`: one portable folder copied into each project

The Hub owns routing, sessions, and dashboards. `ACP_AGENT/acp.py` is the local bridge an agent uses inside a project.

## Repository Layout

```text
apps/
  hub/
    Dockerfile
    docker-compose.yml
    src/acp/hub/
    src/acp/protocol/
ACP_AGENT/
  acp.py
  AGENT.md
  install_from_bundle.py
  skills/
tests/
```

## What Runs Where

- Dokploy server: `apps/hub`
- Local machine per agent: one copied `ACP_AGENT/` folder inside the project

The Hub stays remote. There is no local ACP server. The recommended flow is session-based over Hub HTTP. The WebSocket `run` mode still exists for compatibility.

## Managed Model

The open ACP Manager includes the workspace layer. It uses a minimal split:

- `ACP core`: sessions, members, message routing, wait/listen/send/status, session dashboards
- `Workspace layer`: workspace creation, workspace admin invitations, workspace token rotation, rooms, wall, and web operator

Canonical architecture reference:

- [ARCHITECTURE_SIMPLIFIED.md](ARCHITECTURE_SIMPLIFIED.md)
- [MODULAR_BOUNDARIES.md](MODULAR_BOUNDARIES.md)

### Roles

- `instance_admin`
  - creates workspaces
  - invites exactly one human `workspace_admin`
  - can disable a workspace
- `workspace_admin`
  - accepts an invitation link and creates or links a VPS account
  - enters the workspace dashboard
  - rotates the single workspace token
  - creates and reviews ACP sessions for that workspace
- session collaborators
  - do not need a web account
  - join only through ACP session flows

### Tokens and codes

- invitation link
  - sent or copied by the `instance_admin`
  - used only to activate the human `workspace_admin`
- workspace token
  - single active token per workspace
  - used by the workspace admin or ACP client to create workspace sessions
  - rotating it revokes the previous token
- `join_code`
  - shared with collaborators so they can join a concrete ACP session
- `member_token`
  - returned after an agent joins a session
  - used for `wait`, `listen`, `send`, `status`, and `leave`

### Managed flow

1. `instance_admin` creates the workspace.
2. `instance_admin` invites the `workspace_admin` with a link.
3. The invitee accepts the link and creates or links a VPS account.
4. The `workspace_admin` opens `/managed/ui/workspaces/{slug}`.
5. The `workspace_admin` rotates the single workspace token.
6. Sessions are created:
   - from the workspace dashboard, or
   - from ACP client with the workspace token
7. Other agents join the session with `join_code`.
8. Once inside, ACP core continues with normal `member_token` semantics.

## Prerequisites

- Python 3.11+
- `pip`
- Optional for container flow: Docker + Docker Compose plugin

Install the hub in editable mode (declared in `apps/hub/pyproject.toml`):

```bash
python -m pip install -e apps/hub
```

For tests, install the `test` extra:

```bash
python -m pip install -e "apps/hub[test]"
```

## Run Hub Locally

```powershell
uvicorn acp.hub.app:app --host 0.0.0.0 --port 8000
```

### Zero-config local mode (embedded Hub)

For local development, `acp.py` can launch and manage a local Hub for you, so
agents coordinate with no remote infra. This requires the hub package installed
once (`python -m pip install -e apps/hub`); ACP_AGENT speaks the same protocol,
so the same flow scales to a remote Hub later by setting `--hub-http`.

One command to a working local setup — installs the skill + deps, provisions a
local-mode agent config, and starts the local Hub:

```powershell
python ACP_AGENT/acp.py quickstart --agent dev
```

Or manage the local Hub directly:

```powershell
python ACP_AGENT/acp.py hub-up        # start (or reuse) a local Hub on 127.0.0.1:8000
python ACP_AGENT/acp.py hub-status    # show whether the local Hub is running/healthy
python ACP_AGENT/acp.py hub-down      # stop it
```

While a local Hub is running, commands without `--hub-http` auto-detect it — e.g.
`python ACP_AGENT/acp.py create-session --agent codex-chief --title "..."` just
works. The local Hub uses the durable `sqlite` backend so sessions survive a
restart. State is tracked in `ACP_AGENT/.local_hub.json`.

### Push mode (background watcher)

The default receive loop is *pull* (`listen --stop-after-message`). If your
harness can run a process in the background and wake the agent on its output
(e.g. Claude Code's Monitor tool), run `listen` as that background watcher for
push-style delivery with no idle token cost and without blocking the turn:
`listen --stop-after-message` (one message then exit) or persistent `listen`
(one JSON line per message). See the skill's "Push mode" section for the recipe.

Dashboard:

- http://localhost:8000/dashboard
- global data API: `GET /dashboard/overview`
- session detail UI: `http://localhost:8000/dashboard/session`

## Recommended Agent Flow

Session-based flow:

```powershell
python ACP_AGENT/acp.py create-session --config ACP_AGENT/agents/codex-chief.json --title "Auth Refactor"
python ACP_AGENT/acp.py join-session --config ACP_AGENT/agents/claude-review.json --code ABC123
python ACP_AGENT/acp.py listen --config ACP_AGENT/agents/claude-review.json
python ACP_AGENT/acp.py send --config ACP_AGENT/agents/codex-chief.json --to claude-review --action TASK --payload "Revisa auth"
python ACP_AGENT/acp.py status --config ACP_AGENT/agents/claude-review.json --state busy --text "Tomando ownership de auth"
python ACP_AGENT/acp.py leave-session --config ACP_AGENT/agents/claude-review.json
```

Simplified human-friendly flow:

```powershell
python ACP_AGENT/acp.py init --agent codex-chief --agent claude-review --hub-mode custom --hub-http https://YOUR_HUB --hub-ws wss://YOUR_HUB/ws --force
python ACP_AGENT/acp.py start --agent codex-chief --title "Auth Refactor"
python ACP_AGENT/acp.py join --agent claude-review ABC123
python ACP_AGENT/acp.py task --agent codex-chief --to claude-review "Revisa auth"
python ACP_AGENT/acp.py reply --agent claude-review --to codex-chief "Revision lista"
```

If there is only one config in `ACP_AGENT/agents/`, most commands can omit `--config` and `--agent`.

Operational policy:

- Keep `listen` running as the default background listener.
- Publish `waiting` while the agent is available and listening.
- Reserve `idle` for true detach/teardown states only.
- If immediate follow-up is likely, or local work is done and the next step depends on external instructions, hold a foreground active-wait window of up to 20 minutes.
- Prefer the built-in helper: `python ACP_AGENT/acp.py wait-window --config ACP_AGENT/agents/<agent>.json --window-minutes 20`

Compatibility mode:

```powershell
python ACP_AGENT/acp.py run --hub ws://localhost:8000/ws --name "Claude-Back" --inbox-dir ACP_AGENT/inbox/Claude-Back --outbox-dir ACP_AGENT/outbox/Claude-Back --sent-dir ACP_AGENT/sent/Claude-Back
```

## Portable Folder

Use the portable `ACP_AGENT/` folder at the repository root.

Copy that whole folder into the target project. Then tell the coding agent to inspect `ACP_AGENT/`.

The agent can read:

- [AGENT.md](ACP_AGENT/AGENT.md)
- [install_from_bundle.py](ACP_AGENT/install_from_bundle.py)

That folder carries:

- the ACP skill
- the local `acp.py`
- the self-contained installer

So the agent can install the global skill and initialize `ACP_AGENT/` itself as the live bridge folder.

If the human does not provide a prepared prompt, the agent should still be able to bootstrap from `ACP_AGENT/AGENT.md`, ask only for missing Hub values or agent names, and complete initialization.

In this model, `ACP_AGENT/` is the operational folder inside the project:

```text
my-project/
  ACP_AGENT/
    AGENT.md
    acp.py
    install_from_bundle.py
    skills/
      acp-session-coordinator/
        SKILL.md
    agents/
    inbox/
    outbox/
    sent/
```

The human only copies `ACP_AGENT/` and tells the agent to inspect it.

## Session Model

This bridge is centered on session-oriented coordination:

1. A chief agent creates a session and gets a `join_code`.
   The `create-session` output also includes `session_dashboard_url`, `session_dashboard_url_template`, and `shareable_session_access`.
2. Collaborators join with that code.
   The `join-session` output includes each collaborator's own `session_dashboard_url`.
3. Available agents execute `acp.py listen` and stay in espera persistente hasta que llegue un mensaje.
   `listen` renueva `wait` automaticamente hasta recibir trabajo real y, mientras vive, el estado publicado correcto es `waiting`, no `idle`.
4. On message arrival, `listen` emite un JSON por mensaje recibido y el agente trabaja sobre ese payload. Solo se vuelve a lanzar `listen` si se detuvo explicitamente o si se uso un modo one-shot.
5. The agent reports progress with `acp.py status` and sends tasks or replies with `acp.py send`.
6. Si se espera una instruccion inmediata, o si el trabajo local ya termino y el siguiente paso depende de instrucciones externas, el agente puede mantener una ventana activa foreground de hasta 20 minutos con `acp.py wait-window`. Internamente encadena `wait` en ciclos sucesivos y cada long-poll individual sigue limitado por el Hub a 300 segundos.
7. Cuando la ventana foreground termina, el agente vuelve a quedar en `waiting` con `listen` activo.
8. When the session is over, the agent leaves cleanly with `acp.py leave-session`.

Use the bridge directly from the copied project folder:

```powershell
python ACP_AGENT/acp.py send --config ACP_AGENT/agents/codex-chief.json --to claude-review --action TASK --payload "Revisa el modulo auth"
```

ACP stays limited to coordination. It does not own how the coding agent reasons or edits code.

When a chief creates a session, the expected handoff is no longer just the `join_code`. The agent should share the access block returned by `create-session`, especially:

- `session_id`
- `join_code`
- `hub_http`
- `hub_ws` if present
- `session_dashboard_url_template`
- `shareable_session_access`

`ACP_AGENT` reads its distribution flavor from `ACP_AGENT/DISTRIBUTION.json`.

- if the bundle defines `default_hub_mode = official`, it may use the bundled hosted hub
- if the bundle defines `default_hub_mode = explicit`, the user must provide `hub_http` and `hub_ws`

The public community bundle should stay in `explicit` mode.

## Dashboard Access Model

- `/dashboard` shows the global Hub view: active sessions, connected live agents, current member states, visible tasks, and recent traces.
- `/dashboard/overview` is the JSON source for the global dashboard.
- If the Hub uses `ACP_TOKEN`, the global dashboard uses an admin browser session created from that token.
- Admin session routes:
  - `POST /dashboard/auth/login`
  - `POST /dashboard/auth/logout`
  - `GET /dashboard/auth/session`
- `/dashboard/session` shows one session in detail.
- Session detail can be opened either:
  - as a session member with `session_id + agent_name + member_token`
  - as a Hub admin with the dashboard browser session or the global token

## Docker Quickstart

Uses `apps/hub/Dockerfile` and `apps/hub/docker-compose.yml`:

```bash
docker compose -f apps/hub/docker-compose.yml up -d
docker compose -f apps/hub/docker-compose.yml ps
docker compose -f apps/hub/docker-compose.yml logs -f hub
```

If you run compose from inside `apps/hub`, the classic command also works:

```bash
docker compose up -d
```

Stop:

```bash
docker compose -f apps/hub/docker-compose.yml down
```

## Dokploy Configuration (New Layout)

Recommended:

- Build Path: `/apps/hub`
- Docker File: `Dockerfile`
- Docker Context Path: `.`
- Docker Build Stage: empty
- Container Port: `8000`
- Watch Paths: `apps/hub/**`

## Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `ACP_HOST` | `0.0.0.0` | Hub bind host |
| `ACP_PORT` | `8000` | Hub bind/listen port |
| `ACP_TOKEN` | empty | Optional shared token for `HELLO` and `/send` |
| `ACP_TOKEN_PREVIOUS` | empty | Previous token accepted during overlap window |
| `ACP_TOKEN_OVERLAP_UNTIL` | empty | RFC3339 UTC cutoff for previous token |
| `ACP_AUTH_ENFORCE` | `false` | Enforce identity + ACL deny behavior |
| `ACP_PERSISTENCE_STRICT` | `false` | Fail closed on non-critical persistence append failures |
| `ACP_PERSISTENCE_BACKEND` | `sqlite` | Persistence backend (`sqlite` or `memory`) |
| `ACP_SQLITE_PATH` | `.planning/acp.sqlite3` | Sqlite path when backend is `sqlite` |
| `ACP_MAX_PAYLOAD_BYTES` | `32768` | Payload size guardrail |
| `ACP_VERSION` | `0.1.0` | Hub version label |

## MVP Limitations

- Two persistence backends: `sqlite` (the default — durable) and `memory` (opt-in via `ACP_PERSISTENCE_BACKEND=memory`, for ephemeral local dev).
- With the `memory` backend, active coordination sessions are lost on Hub restart.
- Hub state (active WebSocket agents, trace sink, dashboard sessions) lives in a single Python process. Running multiple uvicorn workers or replicas is not supported.
- No external queues (Redis/NATS/Kafka).
- No multi-tenant ACL model beyond the managed workspace overlay.
- No exactly-once delivery guarantees.
- Dashboard is intentionally simple (single-file, no advanced analytics).

## Testing

```bash
python -m pip install -e "apps/hub[test]"
python -m pytest tests -q
```
