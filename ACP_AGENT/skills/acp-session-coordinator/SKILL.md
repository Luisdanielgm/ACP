---
name: acp-session-coordinator
description: Coordinate Codex or Claude Code agents through ACP session commands. Use when an agent must create a session, join a session, wait or listen for work, send tasks or replies, update work state, or inspect the current ACP session in the active repository.
---

# ACP Session Coordinator

Use ACP only as a coordination layer. Do not delegate coding logic to ACP. The
agent still reasons, edits files, and uses tools normally.

You are expected to be ACP-literate after loading this skill. Do not ask the
human to teach you ACP or hand them raw bootstrap chores unless a required
secret or policy decision is genuinely missing.

All commands below are prefixed with `python ACP_AGENT/acp.py`. After you join a
session, every later command **auto-loads `session_id` and `member_token` from
config** — never re-pass them. The only thing you carry between calls is which
config to use: `--agent <name>`, or nothing at all when a single config exists.

---

# Worker Quick Start (the 90% path)

You are usually a worker: run one deterministic entrypoint, then loop
**receive → work → reply**.

## 1. Connect + receive — prefer the canned path

| Situation | Command (after `python ACP_AGENT/acp.py`) |
| --- | --- |
| Managed workspace worker, discover the room and wait for one incoming message | `coordinate --agent <agent> --agent-token <TOKEN> --hub-http <HUB> --project <project> --capabilities backend,python` |
| Managed workspace, discover the room by project | `onboard --agent <agent> --agent-token <TOKEN> --hub-http <HUB> --project <project> --capabilities backend,python` |
| Unsure whether you are worker or chief | `connect --role auto --agent <agent> --agent-token <TOKEN> --hub-http <HUB>` |
| Core (non-managed) session with a join code | `join-session --agent <agent> --code <CODE>` |
| Managed session id handed to you | `managed-join --agent <agent> --agent-token <TOKEN> --session-id <ID> --no-listen` |
| You already have session id + member token | `attach-session --agent <agent> --session-id <ID> --member-token <TOKEN> --no-listen` |

Each call persists credentials to config and publishes `waiting`. `coordinate`
wraps the managed worker path (`connect`/`onboard`) and then waits for exactly
one incoming message, so a turn-based agent does not assemble token/session
commands by hand. `onboard` finds the room, announces `READY` to the chief, and
prepares runner mode in one shot (~5 Hub round-trips collapsed into one CLI
call). Prefer these composites over hand-rolling `create-session` /
`join-session` / `status` / `send` chains.

## 2. Turn loop — the steady state

```powershell
python ACP_AGENT/acp.py coordinate --agent worker-1 --agent-token TOKEN --hub-http https://HOST --project PROJECT
# ...or, after credentials already exist:
python ACP_AGENT/acp.py listen --stop-after-message --timeout-seconds 300
# ...do the work with your normal tools...
python ACP_AGENT/acp.py status --state busy --text "working on auth.py"   # optional, while working
python ACP_AGENT/acp.py reply --to <chief> "Auth review complete. Files touched: auth.py"
python ACP_AGENT/acp.py status --state waiting --text "listening for next task"
```

Then run `listen --stop-after-message` again. Add `--agent <agent>` to any
command only if more than one agent config exists; with a single config it is
auto-resolved and you can omit both `--agent` and `--config`.

## Must-not-block rule

Turn-based LLM agents that also execute work must **never block** in persistent
`listen` or in `managed-join` *in the foreground*. Always receive with
`listen --stop-after-message --timeout-seconds 300` so you regain control after
each message. Persistent `listen` in the foreground is only for non-LLM daemons;
always-on LLM workers should use `runner start` (see Ops). `managed-join` is only
for attaching credentials and returning control — do not leave it running as your
foreground receiver. The exception is a background watcher — see Push mode.

## Push mode (background watcher / Claude Code Monitor)

The turn loop above is *pull*: you call `listen` and wait. If your harness can
run a process in the **background** and wake you when it emits output (for
example Claude Code's Monitor tool), receive *push*-style instead — no idle token
cost and no blocking of your turn:

- Background a receiver and let the harness watch it:
  - `listen --stop-after-message --timeout-seconds 300` — blocks until one
    message, prints it, and exits; relaunch after you handle it; or
  - persistent `listen` — stays alive and prints **one JSON line per message**.
- The harness wakes you on each emitted `{"status": "message", ...}` line. Act on
  it, send your `REPLY` / `INFO`, then let the watcher keep receiving (persistent)
  or relaunch it (one-shot).

This is the **only** case where an LLM agent should use persistent `listen`: the
background watcher is decoupled from your turn, so you are never blocked. Without
such a watcher, stay on the foreground one-message loop above.

## JSON payloads

> Never pass JSON as a `--payload "..."` argument. Shell quoting (especially
> PowerShell `"`, `$`, backtick) mangles it and the payload silently degrades to
> plain text. Write the JSON to a file and use `--payload-file`, or pipe it via
> `--payload-file -`. Works the same on `send`, `task`, and `reply`; plain-text
> payloads can still use `--payload`.
>
> ```powershell
> python ACP_AGENT/acp.py reply --to <chief> --task-id t-1 --payload-file ACP_AGENT/outbox/result.json
> ```

## Error → recovery

| Symptom | What it means | Do this |
| --- | --- | --- |
| HTTP 409 / `WAIT_ALREADY_ACTIVE` | another wait/listen is active for this member | stop the other receiver if you control it; otherwise `cancel-wait`, then re-`listen`. Response carries `details.wait_ttl_seconds`. |
| "session does not exist" (stale 403/404) | Hub restarted/redeployed or token rotated → session truly lost | stop retrying with stale credentials; re-`join`/`onboard`, or `create-session` |
| HTTP 502 / 503 / 504 | transient Hub/gateway error | CLI auto-retries safe `wait`/`status`/`heartbeat`/`session-info` with short backoff; if it persists, report a temporary failure. `send` is intentionally **not** auto-retried (avoids duplicate delivery). |
| HTTP 401 / bad token | credentials are wrong | re-join to refresh the binding |

```powershell
python ACP_AGENT/acp.py cancel-wait        # clear this member's active or zombie wait, then re-listen
```

## Waiting window (optional)

If immediate follow-up is likely, or your local work is done and the next step
depends on another agent, hold a foreground wait window for up to **20 minutes**
right after sending the `REPLY`:

```powershell
python ACP_AGENT/acp.py wait-window --window-minutes 20
```

It chains one-shot waits internally because each Hub long-poll is capped at
**300 seconds**. When it expires, return to `waiting` and the one-message loop.
Publish `waiting` while available; reserve `idle` for a real detach/teardown.

## Feedback self-fix

Feedback received over ACP is actionable work even when it arrives as `INFO` or
`REPLY` instead of a fresh `TASK`: acknowledge it, apply the correction inside
your assigned boundary, re-run the relevant verification, report the fix with
evidence, then publish `waiting`. Do not wait for the human to relay a new
prompt when the ACP feedback is already specific enough to act on.

## Leave

```powershell
python ACP_AGENT/acp.py leave-session       # when the session is intentionally over
```

## Receive primitives (lookup)

| Primitive | Use it for | Do not use it for |
| --- | --- | --- |
| `join-session --code` | Core/non-managed sessions | Managed workspace sessions with an agent-token |
| `managed-join` | Attach managed credentials and exit | Receiving TASKs in a turn-based agent |
| `listen --stop-after-message --timeout-seconds 300` | Turn-based executor receive loop | Daemon-only operation |
| `wait` | One foreground receive | Parallel/concurrent listening |
| `cancel-wait` | Clear this member's active or zombie wait before retrying | Cancelling other members or replacing `leave-session` |
| persistent `listen` | External daemon/listener, or a background watcher under a harness Monitor (Push mode) | A foreground LLM turn that must act after receive |
| `runner start` | Always-on workers/chiefs that should stay available | Manual turn-based execution |
| `managed-sessions` / `managed-close` | Workspace ops by `--hub-http` + `--agent-token` (or a config with `managed_agent_token`) | Requiring a specific worker config when pure flags suffice |

| Operation model | Receiver | Correct use |
| --- | --- | --- |
| Turn-based LLM chat | `managed-join --no-listen` or `join-session`, then `listen --stop-after-message` / `wait-window` | Human-invoked agents that must regain control after each message |
| Always-on worker/chief | `runner start` | Agent pools and chiefs that stay available without manual wakeups |
| External consumer daemon | persistent `listen` | Non-LLM service that only streams/forwards messages |

---

# Ops & Advanced

**Workers can skip this section.** It covers chiefs, runners, managed-workspace
administration, inspection, and updating ACP.

## Setup: layout, config, dependencies

Assume the repository already has an `ACP_AGENT/` folder with:

- `ACP_AGENT/acp.py`
- `ACP_AGENT/requirements.txt`
- `ACP_AGENT/agents/<agent>.json`

Install the Python dependency before using ACP commands:

```powershell
python -m pip install -r ACP_AGENT/requirements.txt
```

If the folder is missing, ask the user to copy `ACP_AGENT/` into the project. If
it exists but is not initialized, run:

```powershell
python ACP_AGENT/install_from_bundle.py --agent AGENT_NAME --force
```

For a private deployment instead of the official hub:

```powershell
python ACP_AGENT/install_from_bundle.py --hub-mode custom --hub-http https://HOST --hub-ws wss://HOST/ws --agent AGENT_NAME --force
```

If the human gave no prompt details, inspect `ACP_AGENT/AGENT.md`, then ask only
for the missing bootstrap values in this order:

1. whether to use the default hub defined by `ACP_AGENT/DISTRIBUTION.json` or a custom hub
2. `hub_http` and `hub_ws` only if a custom hub is requested
3. agent name
4. optional ACP token
5. if session work starts now: whether to create a session or join one
6. if creating: title/project when needed
7. if joining: the `join_code`

Do not ask for `hub_http`/`hub_ws` when the official hub is acceptable.

### Pick the agent config

Use exactly one config file per agent instance (chief example
`ACP_AGENT/agents/codex-chief.json`, collaborator example
`ACP_AGENT/agents/claude-review.json`). Do not share one config between agents,
and do not reuse a chief config as a collaborator or vice versa. If a config is
still bound to a live session, `create-session` and `join-session` must fail;
use a different config or `leave-session` first.

## Chief workflow

1. Create the session:

```powershell
python ACP_AGENT/acp.py create-session --config ACP_AGENT/agents/codex-chief.json --title "Short task label"
```

2. `create-session` persists credentials and auto-publishes `waiting`. A
   turn-based chief must not start persistent `listen`; use one-message receives
   or `wait-window`. A chief that must react without a human waking it should run
   as `runner start` or under an external scheduler.

3. Read the JSON output and capture: `session_id`, `join_code`, `hub_http`,
   `hub_ws` (if present), `session_dashboard_url`, `current_member_dashboard_url`,
   `session_dashboard_url_template`, `shareable_dashboard_url_template`,
   `shareable_session_access`.

4. Tell collaborators all access data: `join_code`, `hub_http`, `hub_ws` (if
   present), `shareable_dashboard_url_template`, the `join_command_example` from
   `shareable_session_access`, and that each collaborator uses its own
   `member_token` after joining.

5. Assign work, publish state, and leave when done:

```powershell
python ACP_AGENT/acp.py send --config ACP_AGENT/agents/codex-chief.json --to claude-review --action TASK --payload "Review auth module and report file ownership"
python ACP_AGENT/acp.py status --config ACP_AGENT/agents/codex-chief.json --state busy --text "Planning tasks"
python ACP_AGENT/acp.py listen --config ACP_AGENT/agents/codex-chief.json --stop-after-message --timeout-seconds 300
python ACP_AGENT/acp.py status --config ACP_AGENT/agents/codex-chief.json --state waiting --text "Listening for updates"
python ACP_AGENT/acp.py leave-session --config ACP_AGENT/agents/codex-chief.json
```

For TASK payloads with structure (task_id, instructions), use `--payload-file`
(see the JSON payloads rule above), and pass `--task-id` and
`--reply-to`/`--in-reply-to` instead of embedding IDs in free text.

## Autonomous chief & runner

For an always-on coordinator, use `runner start` (workers) or `chief start`
(chiefs) instead of manual turn loops. A turn-based chat chief will not wake
itself merely because ACP received a message.

```powershell
python ACP_AGENT/acp.py chief start --config ACP_AGENT/agents/<chief>.json --backlog-dir coord/backlog --provider claude_local --workspace <PROJECT_PATH>
```

The first chief implementation is deterministic. It does not invent work. It
dispatches file-backed tasks from `coord/backlog/` or `coord/backlog/pending/`
to available members, then moves files through:

- `assigned/` after a TASK is sent
- `done/` after a successful REPLY with `task_id` and passing verification
- `failed/` after an unsuccessful/unknown REPLY with `task_id`, or a failed verification

Use `.task.md`, `.md`, `.txt`, or `.json` task files. JSON task files may define
`task_id`, `instructions`, `provider`, `workspace_path`, `metadata`,
`required_capabilities`, `required_role`, `tags`, `verify_command`,
`verify_timeout_seconds`, `acceptance_criteria`/`verify_prompt`, `judge_provider`,
`judge_timeout_seconds`, and `max_attempts`. Markdown/text task files use the
whole file body as instructions. When capability requirements are present, the
chief prefers a `waiting` worker whose advertised capabilities cover them, and
falls back to any available worker rather than blocking forever. The chief
dispatches at most one task per worker per tick; a member with `current_task` is
not available even if its visible status is still `waiting`. When `verify_command`
is present, the chief runs it after a worker reports success; a failure writes a
failed result, requeues with explicit feedback, and re-dispatches when a worker
is free. Prefer `verify_command` as an argument list; string commands run through
the local shell and are for trusted local tasks only. When `acceptance_criteria`
or `verify_prompt` is present, the chief runs a local LLM judge after mechanical
verification and expects JSON `{ "pass": true|false, "feedback": "..." }`; a
failed judge requeues with the feedback until `max_attempts` is exhausted. If a
worker sends `REPLY` without `task_id` but has exactly one assignment in flight,
the chief infers the task id instead of dropping the reply. Assigned files have a
TTL (`--assignment-ttl-seconds`, default 1800s); expired assignments are requeued
and recorded in `failed/`. If the chief hits its own `WAIT_ALREADY_ACTIVE`, it
cancels that stale wait and retries once. For long tasks, prefix instructions
with `[long]` or `[busy-hold:30]`; runners detect the marker inside JSON TASK
payloads and start an automatic busy heartbeat hold. Run `chief once` for
CI/debugging or `chief start --once` for one loop through the same surface.

Autonomous-pool checklist:

1. Keep one config per chief/worker identity.
2. Inspect `session-info` to maintain a pool of members and their status.
3. When a worker reports `REPLY`/DONE, verify the result, mark it available, and
   dispatch the next backlog item to a matching `waiting` worker when the task
   has `required_capabilities`; otherwise use any available worker.
4. Send `TASK` with clear file/ownership boundaries; workers send `INFO` when
   taking ownership and `REPLY` when finished.
5. Escalate to the human only when the backlog is empty, policy is ambiguous, or
   verification fails.

## Managed workspace administration

Do not use `join-session --code` with a managed workspace agent-token. Managed
commands can read the workspace token from the selected config when it contains
`managed_agent_token`, or take pure flags. Managed tokens no longer need the
workspace slug in the normal case: `managed-start`, `managed-join`, and
`managed-sessions` discover the workspace from the token, and
`GET /managed/agent/bootstrap` validates the token and inspects its context.

```powershell
python ACP_AGENT/acp.py managed-sessions --hub-http https://HOST --agent-token <TOKEN>
python ACP_AGENT/acp.py managed-close --hub-http https://HOST --agent-token <TOKEN> --session-id <SESSION_ID>
```

`onboard` validates the token with `/managed/agent/bootstrap`, lists managed
sessions, matches by `project` (or exact `--session-id`), runs `managed-join`,
sends an `INFO` `READY` payload to the chief, publishes `waiting`, and prepares
the config as `delivery_mode=runner`. With `--capabilities` the member advertises
those tags in `session-info` and keeps publishing them through
status/heartbeat/runner updates. It prints a `runner_command` and returns control
by default; pass `--start-runner` only when this process should become the
long-lived runner. If several rooms match the same project, `onboard` fails on
purpose — pass `--session-id`, or `--prefer-latest` to choose the newest room.

`connect` is the self-describing entrypoint: it runs the worker `onboard` flow
for workers and orients/starts the chief flow for configs marked
`member_role=chief`. To invite another agent, generate the prompt with the CLI
instead of writing it by hand:

```powershell
python ACP_AGENT/acp.py invite --role worker --agent <agent> --capabilities backend,python --session-id <SESSION_ID> --project <PROJECT_ID>
```

The skill is documentation, not the transport. If the runtime cannot find a
globally installed `acp-session-coordinator` skill, do not stop — use the
bundle's executable and print a self-contained quickstart:

```powershell
python ACP_AGENT/acp.py onboard-help --project <PROJECT_ID> --agent <agent>
```

## Session inspection & Hub endpoints

```powershell
python ACP_AGENT/acp.py session-info --config ACP_AGENT/agents/codex-chief.json
```

`create-session`, `join-session`, and `session-info` already return
`session_dashboard_url`, `current_member_dashboard_url` (direct chat-ready alias),
`session_dashboard_url_template`, `shareable_dashboard_url_template`, and
`shareable_session_access`. Prefer those returned values instead of rebuilding
URLs by hand. For managed flows the dashboard URLs point to
`/managed/dashboard/session`; core flows may use the core dashboard path from the
config.

`acp.py` wraps the core session flow, but the Hub exposes more operational
context. Query it over HTTP when you need a snapshot, detail, member list, live
states, history, replay, or health:

- `GET /health`
- `GET /agents`
- `GET /dashboard/overview`
- `GET /sessions/{session_id}`
- `GET /sessions/{session_id}/detail`
- `GET /replay/events`
- `GET /replay/messages/{message_id}`

For the global Hub view, open `<hub_http>/dashboard` (use `ACP_TOKEN` if the Hub
requires it; the global token also grants admin session detail).

If `session-info`/`listen`/`send`/`status` fail with "session does not exist",
treat it as a real session loss (usually a Hub restart/redeploy) — see the
worker Error → recovery table.

## Updating ACP

If the user asks to update ACP, or the bundle looks stale, compare the installed
folder against the official release channel first (inspect
`ACP_AGENT/BUNDLE_INFO.json`, `ACP_AGENT/DISTRIBUTION.json`, `ACP_AGENT/AGENT.md`,
`ACP_AGENT/RELEASE_CHECKLIST.md`):

```powershell
python ACP_AGENT/update_from_release.py --check
```

If the result is `update_available`, or the user wants the latest, apply it:

```powershell
python ACP_AGENT/update_from_release.py
```

For a connected agent, prefer the safe release-aware wrapper:

```powershell
python ACP_AGENT/acp.py update-check --config ACP_AGENT/agents/<agent>.json
python ACP_AGENT/acp.py self-update --config ACP_AGENT/agents/<agent>.json --auto-when-idle
```

Autonomous updates are allowed only when the local `ACP_AGENT/` install is **not**
tracked by git, unless the human explicitly allows tracked-repo mutation. If
`ACP_AGENT/` is tracked, report `update_available` and wait for explicit
permission — this prevents ACP from silently editing a user's project repo.
Agent configs can opt into release checks during `listen` via
`{"update_policy": "notify"}` (values: `off`, `notify`, `auto_when_idle`).
Turn-based agents update only between turns: finish work, send `REPLY`, publish
`waiting`, run `self-update --auto-when-idle`, then re-enter
`listen --stop-after-message`. Daemons/runners update by rolling restart, not
while `busy`.

The update flow must preserve `ACP_AGENT/agents/`, `ACP_AGENT/inbox/`,
`ACP_AGENT/outbox/`, and `ACP_AGENT/sent/`. After install or update, inspect
`ACP_AGENT/BUNDLE_INFO.json` (installed version, release date, local
install/update timestamp) and re-read `ACP_AGENT/VERSION`,
`ACP_AGENT/CHANGELOG.md`, `ACP_AGENT/AGENT.md`, `ACP_AGENT/RELEASE_CHECKLIST.md`,
`ACP_AGENT/skills/acp-session-coordinator/SKILL.md`, and the installed copies
under `.codex/skills/`, `~/.codex/skills/`, and `~/.claude/skills/` if present.

If the project is too old to contain `update_from_release.py`, use the downloads
surface defined by `ACP_AGENT/DISTRIBUTION.json` (its default manifest/downloads
surface), or ask the human which release surface to use, then replace the ACP
core files while preserving the runtime state folders above. If the human says
"look for ACP updates", "update ACP", or "update the ACP skill", this update flow
is mandatory before continuing with ACP work.

## Operating rules

1. Keep one agent identity per config file.
2. Use ACP to coordinate ownership, dependencies, status, and results.
3. Announce file ownership before changing risky shared files.
4. Send `INFO` when taking ownership or changing plan.
5. Send `REPLY` when finishing a requested task.
6. Turn-based executors must use `listen --stop-after-message --timeout-seconds 300` loops; persistent `listen` is only for external daemons. Always-on LLM workers/chiefs should prefer `runner start`.
7. Publish `waiting` when available and listening; reserve `idle` for a real detach/teardown state.
8. Use an optional foreground `wait` window of up to 20 minutes when expecting immediate follow-up or when the next step depends on external instructions; prefer `wait-window`.
9. Use `leave-session` when the session is intentionally over.
10. When creating or joining a session, explicitly report the session access data and dashboard URL, not only the join code.
11. In managed workspace flows, if a common name like `codex-chief` is already attached to another active session, report the effective resolved agent name the session received.
12. Default to the hub defined by `ACP_AGENT/DISTRIBUTION.json` when the bundle provides one, unless the user explicitly asks for a custom hub.
13. Ask for `hub_http`/`hub_ws` only when a custom hub is requested.

## What ACP does not do

ACP does not decide implementation strategy, merge code, resolve Git conflicts,
or replace your normal coding tools. ACP only gives the agent a reliable
coordination channel.
