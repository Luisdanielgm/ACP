# ACP (Agent Communication Protocol)

ACP is a coordination layer for coding agents.

- `apps/hub`: remote/self-hosted Hub + ACP Manager runtime
- `ACP_AGENT`: one portable folder copied into each project

The Hub owns routing, sessions, the self-host workspace, rooms, storage, and dashboards. `ACP_AGENT/acp.py` is the local bridge an agent uses inside a project. See [PRODUCT_WALKTHROUGH.md](PRODUCT_WALKTHROUGH.md) for the end-to-end product path.

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

The open ACP Manager includes the workspace layer, but public self-host installs run in **single-workspace mode by default**:

- `ACP core`: sessions, members, message routing, wait/listen/send/status, session dashboards
- `Workspace layer`: one self-host workspace, one workspace admin, workspace token rotation, rooms, room prompts, persistent wall, room files/instructions with quotas, and web operator
- `Cloud/admin layer`: customer registry, provisioning runbook, billing, hosted downloads, and commercial automation live in the private `acp-cloud` repo. Public ACP no longer ships an operator/multi-workspace runtime mode.

Canonical architecture reference:

- [ARCHITECTURE_SIMPLIFIED.md](ARCHITECTURE_SIMPLIFIED.md)
- [MODULAR_BOUNDARIES.md](MODULAR_BOUNDARIES.md)

### Public roles

- `workspace_admin`
  - logs into the single self-host workspace
  - rotates the single workspace token
  - creates and reviews ACP sessions for that workspace
- session collaborators
  - do not need a web account
  - join only through ACP session flows

### Tokens and codes

- workspace admin login
  - configured at install time from `ACP_WORKSPACE_ADMIN_EMAIL` and `ACP_WORKSPACE_ADMIN_PASSWORD_HASH`
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

1. Public self-host starts in `single_workspace` mode. `ACP_DEPLOYMENT_MODE` may be omitted or set to `single_workspace`; `operator` is rejected.
2. First boot creates one workspace and one `workspace_admin` from env/setup values.
3. The `workspace_admin` opens `/managed/ui/workspaces/{slug}`.
4. The `workspace_admin` rotates the single workspace token.
5. Sessions are created:
   - from the workspace dashboard, or
   - from ACP client with the workspace token
6. Other agents can join with `join_code`, or use deterministic managed commands such as `coordinate` / `connect` with the workspace token.
7. Once inside, the room keeps durable context through the prompt, wall posts, and room files/instructions. ACP core continues with normal `member_token` semantics.

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

## Public Single-workspace Setup

For a fresh local/VPS install, generate a private `.env` first. This creates one
workspace, one admin login, strong browser/agent secrets, and an scrypt password
hash. Do not commit the generated file.

```bash
python -m pip install -e apps/hub
python -m acp_managed.setup init-single-workspace \
  --env-file apps/hub/.env \
  --workspace-name "My ACP Workspace" \
  --workspace-slug default \
  --admin-email admin@example.com
```

The command prompts for the admin password. For Dokploy/Docker, keep a durable
volume mounted at `/data` because the default production paths are:

```env
ACP_SQLITE_PATH=/data/acp/acp.sqlite3
ACP_MANAGED_AUTH_SQLITE_PATH=/data/acp/acp-managed-auth.sqlite3
```

Then run the container from `apps/hub`:

```bash
cd apps/hub
docker compose up -d --build
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

Managed workspace worker, turn-based 90% path:

```powershell
python ACP_AGENT/acp.py coordinate --agent worker-1 --agent-token TOKEN --hub-http https://YOUR_HUB --project PROJECT_ID
# work on the received message, then reply
python ACP_AGENT/acp.py reply --to codex-chief --task-id t-1 --payload-file ACP_AGENT/outbox/result.json
python ACP_AGENT/acp.py status --state waiting --text "ready for next task"
```

Unsure whether the agent is chief or worker:

```powershell
python ACP_AGENT/acp.py connect --role auto --agent worker-1 --agent-token TOKEN --hub-http https://YOUR_HUB --project PROJECT_ID
```

Always-on operation:

```powershell
python ACP_AGENT/acp.py runner start --config ACP_AGENT/agents/worker-1.json --provider claude_local --workspace C:\\path\\to\\project
python ACP_AGENT/acp.py chief start --config ACP_AGENT/agents/codex-chief.json --backlog-dir coord/backlog --provider claude_local --workspace C:\\path\\to\\project
```

Core session-based compatibility flow still exists:

```powershell
python ACP_AGENT/acp.py create-session --config ACP_AGENT/agents/codex-chief.json --title "Auth Refactor"
python ACP_AGENT/acp.py join-session --config ACP_AGENT/agents/claude-review.json --code ABC123
python ACP_AGENT/acp.py listen --config ACP_AGENT/agents/claude-review.json --stop-after-message --timeout-seconds 300
python ACP_AGENT/acp.py send --config ACP_AGENT/agents/codex-chief.json --to claude-review --action TASK --payload "Revisa auth"
python ACP_AGENT/acp.py status --config ACP_AGENT/agents/claude-review.json --state busy --text "Tomando ownership de auth"
python ACP_AGENT/acp.py leave-session --config ACP_AGENT/agents/claude-review.json
```

Simplified human-friendly core flow:

```powershell
python ACP_AGENT/acp.py init --agent codex-chief --agent claude-review --hub-mode custom --hub-http https://YOUR_HUB --hub-ws wss://YOUR_HUB/ws --force
python ACP_AGENT/acp.py start --agent codex-chief --title "Auth Refactor"
python ACP_AGENT/acp.py join --agent claude-review ABC123
python ACP_AGENT/acp.py task --agent codex-chief --to claude-review "Revisa auth"
python ACP_AGENT/acp.py reply --agent claude-review --to codex-chief "Revision lista"
```

If there is only one config in `ACP_AGENT/agents/`, most commands can omit `--config` and `--agent`.

Operational policy:

- Turn-based LLM agents should receive with `coordinate` or `listen --stop-after-message --timeout-seconds 300`, not foreground persistent `listen`.
- Publish `waiting` while the agent is available.
- Reserve `idle` for true detach/teardown states only.
- If immediate follow-up is likely, hold a foreground active-wait window of up to 20 minutes with `python ACP_AGENT/acp.py wait-window --config ACP_AGENT/agents/<agent>.json --window-minutes 20`.

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

ACP stays limited to coordination. It does not own how the coding agent reasons or edits code. Durable room context lives in the room prompt, wall, and room files; code execution and verification remain with the agent.

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
- No multi-tenant/operator workspace management in the public runtime; deploy one ACP service per workspace.
- No exactly-once delivery guarantees.
- Dashboard is intentionally simple (single-file, no advanced analytics).

## Testing

```bash
python -m pip install -e "apps/hub[test]"
python -m pytest tests -q
```
