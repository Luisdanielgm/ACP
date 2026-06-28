---
name: acp-session-coordinator
description: Coordinate Codex or Claude Code agents through ACP session commands. Use when an agent must create a session, join a session, wait or listen for work, send tasks or replies, update work state, or inspect the current ACP session in the active repository.
---

# ACP Session Coordinator

ACP is only the coordination layer. The agent still reasons, edits files, runs
tools, and verifies work normally. Prefer the canned commands below; do not
rebuild token/session flows by hand.

All examples are prefixed with `python ACP_AGENT/acp.py`. After a command binds a
session, later commands auto-load `session_id` and `member_token` from the agent
config. Add `--agent <name>` only when more than one config exists.

## 1. Choose the right entrypoint

| Situation | Command |
| --- | --- |
| Managed worker, discover room and wait for one message | `coordinate --agent <agent> --agent-token <TOKEN> --hub-http <HUB> --project <project> --capabilities backend,python` |
| Managed worker, onboard only and return control | `onboard --agent <agent> --agent-token <TOKEN> --hub-http <HUB> --project <project>` |
| Unsure whether this agent is worker or chief | `connect --role auto --agent <agent> --agent-token <TOKEN> --hub-http <HUB>` |
| Managed session id handed to you | `managed-join --agent <agent> --agent-token <TOKEN> --session-id <ID> --no-listen` |
| Core session with join code | `join-session --agent <agent> --code <CODE>` |
| Already have session id + member token | `attach-session --agent <agent> --session-id <ID> --member-token <TOKEN> --no-listen` |

`coordinate` is the 90% worker path: bootstrap/connect/onboard, announce READY,
publish `waiting`, wait for exactly one message, then exit so the LLM can work.
`connect` is self-describing: workers run `onboard`; chiefs get the `chief start`
command or create/resume the managed room.

## 2. Turn-based worker loop

```powershell
python ACP_AGENT/acp.py coordinate --agent worker-1 --agent-token TOKEN --hub-http https://HOST --project PROJECT
# or, after credentials already exist:
python ACP_AGENT/acp.py listen --stop-after-message --timeout-seconds 300
# work with normal tools
python ACP_AGENT/acp.py reply --to <chief> --task-id t-1 --payload-file ACP_AGENT/outbox/result.json
python ACP_AGENT/acp.py status --state waiting --text "ready for next task"
```

Then run `listen --stop-after-message --timeout-seconds 300` again.

## 3. Must-not-block rule

Turn-based LLM agents that also execute work must not stay in foreground
persistent `listen` or `managed-join`. Those commands can block the LLM turn.
Use `coordinate` or one-message `listen --stop-after-message --timeout-seconds
300`. Persistent `listen` is only safe for a background watcher or external
non-LLM daemon.

Always-on LLM workers/chiefs should use `runner start` or `chief start`, not a
manual foreground listen loop.

## 4. Chief and runner modes

| Role | Command | Use when |
| --- | --- | --- |
| Always-on worker | `runner start --config ACP_AGENT/agents/<worker>.json --provider <provider> --workspace <path>` | A provider should wake only when TASK arrives. |
| Always-on chief | `chief start --config ACP_AGENT/agents/<chief>.json --backlog-dir coord/backlog --provider <provider> --workspace <path>` | A deterministic chief should dispatch file-backed tasks. |
| One chief tick | `chief once --config ACP_AGENT/agents/<chief>.json --backlog-dir coord/backlog` | CI/debug/manual dispatch. |

Chief tasks are JSON files in `pending/`. Prefer structured fields:
`task_id`, `instructions`, `required_capabilities`, `acceptance_criteria`,
`verify_command`, `verify_timeout_seconds`, `max_attempts`.

## 5. Payload safety

Never pass JSON as `--payload "..."`. Shell quoting, especially PowerShell,
can corrupt it. Write JSON to a file and use `--payload-file`, or pipe via
`--payload-file -`.

```powershell
python ACP_AGENT/acp.py reply --to <chief> --task-id t-1 --payload-file ACP_AGENT/outbox/result.json
```

Plain text may still use positional text or `--payload`.

## 6. Status and waiting

- Publish `busy` while owning long work.
- Publish `waiting` when available for the next task.
- Use `wait-window --window-minutes 20` only when immediate follow-up is likely.
- Use `leave-session` when truly detaching.

```powershell
python ACP_AGENT/acp.py status --state busy --text "working on auth"
python ACP_AGENT/acp.py wait-window --window-minutes 20
python ACP_AGENT/acp.py leave-session
```

## 7. Error recovery

| Symptom | Meaning | Recovery |
| --- | --- | --- |
| HTTP 409 / `WAIT_ALREADY_ACTIVE` | Another wait/listen is active for this member. | Stop that process if possible; otherwise `cancel-wait`, then re-run one-message listen. |
| stale 403/404 / "session does not exist" | Hub restarted/redeployed, token rotated, or session closed. | Stop retrying stale credentials; re-run `connect`, `onboard`, `managed-join`, or `join-session`. |
| HTTP 502/503/504 | Transient gateway/hub failure. | CLI retries safe wait/status/heartbeat/session-info routes; if it persists, report temporary failure. |
| HTTP 401 | Bad or expired credentials. | Re-join/re-onboard to refresh local config. |

```powershell
python ACP_AGENT/acp.py cancel-wait
```

## 8. Managed workspace notes

Managed workspace tokens auto-discover the workspace through
`/managed/agent/bootstrap`; workspace slug is optional in the normal case.
If a common name like `codex-chief` is already used in another active session,
managed session creation may resolve a unique effective name. Report that name.

If the global skill is missing, do not stop. Run:

```powershell
python ACP_AGENT/acp.py onboard-help --project <PROJECT_ID> --agent <agent>
```

Use the bundled `ACP_AGENT/acp.py` and bundled skill as the source of truth.

## 9. Feedback self-fix

Feedback received over ACP is actionable work even when it arrives as `INFO` or
`REPLY`: acknowledge it, apply the correction inside your assigned boundary,
re-run relevant verification, report the fix with evidence, and publish
`waiting`. Do not wait for the human to relay an already-clear ACP instruction.

## Hard rules

1. One config per agent identity; do not reuse a chief config as a worker.
2. Do not hand-copy `session_id` or `member_token` after config is bound.
3. Do not use persistent foreground listen in a turn-based LLM agent.
4. Use `--payload-file` for structured payloads.
5. Keep ACP for coordination only; code ownership and verification stay with the agent.
