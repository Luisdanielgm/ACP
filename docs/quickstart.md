# Quickstart

Get a self-hosted ACP hub running and coordinate your first agent in about
five minutes. For the concepts behind this flow — the workspace/session model,
token scopes, and recommended commands — read [public-engine.md](public-engine.md)
first or alongside.

Every host below uses `acp.example.com` as a placeholder. Replace it with your
own hub URL.

## Prerequisites

- Python 3.11+
- Docker + Docker Compose (recommended path below), or the ability to run
  `uvicorn` locally
- A checkout of this repository (the `ACP_AGENT/` folder is the portable client
  you copy into projects)

## 1. Run the hub

The hub runs in single-workspace mode: one admin, one workspace, many sessions.
Generate the environment file, then boot with Docker Compose.

```bash
# From the repo root: install the hub package (provides the setup CLI)
python -m pip install -e apps/hub

# Generate apps/hub/.env — this prompts for the admin password and writes the
# hashed value plus fresh session secrets. Nothing secret is stored in plaintext.
python -m acp_managed.setup init-single-workspace \
  --env-file apps/hub/.env \
  --workspace-name "My ACP Workspace" \
  --workspace-slug default \
  --admin-email admin@example.com

# Boot the hub (builds the frontend + API image on first run)
cd apps/hub && docker compose up -d --build
```

The generated `.env` sets the values the hub requires to boot:
`ACP_WORKSPACE_SLUG`, `ACP_WORKSPACE_NAME`, `ACP_WORKSPACE_ADMIN_EMAIL`,
`ACP_WORKSPACE_ADMIN_PASSWORD_HASH`, `ACP_MANAGED_SESSION_SECRET`, and
`ACP_MANAGED_AGENT_TOKEN_SECRET`. See the [README env table](../README.md) for
the optional variables (persistence backend, payload limits, proxy trust, etc.).

> For a throwaway local hub without Docker, `python ACP_AGENT/acp.py hub-up`
> starts an auto-managed local instance (`hub-status` / `hub-down` to inspect
> and stop it). See the README for details.

## 2. Verify the hub is healthy (smoke test)

Before wiring an agent, confirm the hub answers. This doubles as the smoke test
for any fresh deploy.

```bash
# Liveness — should return a JSON health payload
python ACP_AGENT/acp.py health --hub-http https://acp.example.com

# End-to-end diagnostics — runs a series of ok/warn/fail checks:
# bundle version, distribution mode, hub URL resolution, GET /health,
# GET /agents (token-gated), WS reachability, local agent configs, and
# that the websockets package is importable.
python ACP_AGENT/acp.py doctor --hub-http https://acp.example.com
```

`doctor` exits non-zero only on `fail` checks; `warn` results (for example, no
agent configs yet) are expected on a brand-new install. A green `health` plus a
`doctor` run with no `fail` lines means the hub is ready.

## 3. Get a workspace token

Agents authenticate with a **workspace token**. It is minted from the workspace
dashboard, not the CLI:

1. Open `https://acp.example.com/managed/ui` and sign in with the admin email
   and password you set in step 1.
2. Open your workspace (`default`) and use **Rotate token**.
3. Copy the token value shown. Rotating again revokes the previous token, so
   store it somewhere safe — there is only one active token per workspace.

> Automating this? The same result comes from the HTTP API: sign in with
> `POST /managed/auth/login` (admin credentials) to get a session cookie, then
> `POST /managed/workspaces/default/token/rotate`, which returns the token as
> `raw_token`.

## 4. Connect an agent

Copy `ACP_AGENT/` into your project, then connect a turn-based worker. This
binds the agent to the hub and waits for one turn-ready message:

```bash
python ACP_AGENT/acp.py coordinate \
  --agent worker-1 \
  --agent-token <WORKSPACE_TOKEN> \
  --hub-http https://acp.example.com \
  --project my-project
```

That is the five-minute path: a running hub, a healthy check, a token, and a
connected agent.

## 5. Run a first TASK → REPLY

Coordination needs a session and at least two agent identities — a chief that
assigns work and a worker that does it.

```bash
# As the chief: create a managed session (returns a session_id and join_code)
python ACP_AGENT/acp.py managed-start \
  --agent chief \
  --agent-token <WORKSPACE_TOKEN> \
  --hub-http https://acp.example.com \
  --title "First task" --no-listen

# The worker joins that session. --listen-once handles a single turn and exits
# (use this, not persistent listen, for turn-based LLM agents).
python ACP_AGENT/acp.py managed-join \
  --agent worker-1 \
  --agent-token <WORKSPACE_TOKEN> \
  --hub-http https://acp.example.com \
  --session-id <SESSION_ID> \
  --listen-once

# The chief assigns work
python ACP_AGENT/acp.py task --to worker-1 "Summarize the README"

# The worker replies once it has a result, then reports it is free again
python ACP_AGENT/acp.py reply --to chief --payload-file result.json
python ACP_AGENT/acp.py status --state waiting --text "ready for next task"
```

Use `--payload-file` for structured JSON payloads instead of inlining complex
JSON in the shell. Messages carry a clear intent: `TASK` assigns work, `REPLY`
returns a result, `INFO` shares status or context.

> **Do not** leave a turn-based LLM agent in persistent `listen`. Loop with
> `coordinate` (or `listen --stop-after-message --timeout-seconds 300`) so the
> agent takes one turn and returns control. Persistent `listen`, `runner`, and
> `chief` are for real always-on daemons.

## 6. See what happened

```bash
# Replay the session's events
python ACP_AGENT/acp.py replay \
  --hub-http https://acp.example.com \
  --agent-token <WORKSPACE_TOKEN> \
  --session-id <SESSION_ID>
```

Or open the live dashboard in a browser at
`https://acp.example.com/managed/ui/workspaces/default/sessions/<SESSION_ID>` to
watch members, the message timeline, and status in real time.

## Next steps

- [public-engine.md](public-engine.md) — the mental model, token scopes,
  recommended command surfaces, and common mistakes.
- [protocol.md](../protocol.md) — the message protocol reference.
- [README](../README.md) — repository layout, the full environment-variable
  table, and always-on `runner` / `chief` workers.
