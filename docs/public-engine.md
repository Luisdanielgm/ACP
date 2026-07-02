# ACP Public Engine

ACP is the open-source coordination engine for coding agents. It gives a
self-hosted team one workspace, many rooms/sessions, and a portable client
folder that agents can use from inside any project.

This document explains the public engine only. It does not describe ACP Cloud,
customer provisioning, billing, or private hosted automation.

## Quick path

1. Self-host the Hub in single-workspace mode.
2. Rotate or copy the workspace token from the workspace dashboard.
3. Copy `ACP_AGENT/` into a project.
4. Connect a turn-based worker with:

   ```bash
   python ACP_AGENT/acp.py coordinate \
     --agent worker-1 \
     --agent-token TOKEN \
     --hub-http https://acp.example.com \
     --project my-project
   ```

5. Use `TASK`, `REPLY`, and `INFO` messages inside the session.

## What ACP public is

| Part | Purpose |
| --- | --- |
| `apps/hub` | Self-hosted Hub: sessions, routing, persistence, dashboards, and the single-workspace layer. |
| `ACP_AGENT/` | Portable client folder copied into each project. |
| Workspace | Administrative boundary for one self-hosted install. |
| Session / room | Active collaboration space where agents work. |
| Member | An agent identity inside a session. |

## What ACP public is not

| Not included | Why |
| --- | --- |
| ACP Cloud customer registry | Belongs to the private hosted control plane. |
| Billing, plans, metering | Commercial layer, not public engine. |
| Multi-customer provisioning | Private cloud automation. |
| Hosted default hub URL | Public bundle must stay explicit/self-hosted. |
| Private branding or customer domains | Public repo must stay generic. |

## Mental model

```text
ACP Hub
  -> single workspace
      -> rooms / sessions
          -> members / agents
              -> TASK / REPLY / INFO
          -> replay / dashboard / wall / files
```

The workspace organizes access. The session does the work.

## Tokens and codes

| Credential | Scope | Used by | Purpose |
| --- | --- | --- | --- |
| Workspace admin login | Workspace UI | Human admin | Open the dashboard and rotate the workspace token. |
| Workspace token / agent token | Workspace | Admin, automation, `ACP_AGENT` | Create/list/join managed workspace sessions. |
| `join_code` | One session | Collaborators | Join a concrete core session. |
| `member_token` | One member in one session | Joined agent | Send, wait, listen, update status, replay/session-info where allowed. |

Do not mix these. A workspace token is not a member token. A `join_code` is not
workspace access.

## Recommended command surfaces

Prefer the high-level commands. They persist local config and avoid repeated
manual handling of `session_id` and `member_token`.

| Situation | Command |
| --- | --- |
| Turn-based managed worker | `coordinate --agent <name> --agent-token <TOKEN> --hub-http <HUB> --project <project>` |
| Managed worker onboarding without waiting for work | `onboard --agent <name> --agent-token <TOKEN> --hub-http <HUB> --project <project>` |
| Unknown role / self-describing entrypoint | `connect --role auto --agent <name> --agent-token <TOKEN> --hub-http <HUB>` |
| Create managed session as chief | `managed-start --agent <name> --agent-token <TOKEN> --hub-http <HUB> --title "Task" --no-listen` |
| Join managed session by id | `managed-join --agent <name> --agent-token <TOKEN> --session-id <ID> --no-listen` |
| Join core session by code | `join-session --agent <name> --code <JOIN_CODE>` |
| Always-on worker | `runner start --config ACP_AGENT/agents/<worker>.json --provider <provider> --workspace <path>` |
| Always-on chief | `chief start --config ACP_AGENT/agents/<chief>.json --backlog-dir coord/backlog --provider <provider> --workspace <path>` |

## Turn-based worker loop

Turn-based LLM agents must not block themselves in persistent foreground
listeners. Use one-message waits:

```bash
python ACP_AGENT/acp.py coordinate \
  --agent worker-1 \
  --agent-token TOKEN \
  --hub-http https://acp.example.com \
  --project my-project

# After the first binding, config carries session_id/member_token.
python ACP_AGENT/acp.py listen --stop-after-message --timeout-seconds 300

# Work with normal coding tools, then report back.
python ACP_AGENT/acp.py reply \
  --to codex-chief \
  --task-id task-1 \
  --payload-file ACP_AGENT/outbox/result.json

python ACP_AGENT/acp.py status --state waiting --text "ready for next task"
```

Persistent `listen` is for external daemons. Always-on LLM workers should use
`runner start`.

## Communication protocol

ACP messages are intentionally small and explicit:

| Action | Meaning |
| --- | --- |
| `TASK` | Assign work to another member. |
| `REPLY` | Return a result, answer, or task completion. |
| `INFO` | Share status, context, feedback, or coordination notes. |

Structured payloads should go through files:

```bash
python ACP_AGENT/acp.py reply --to codex-chief --payload-file ACP_AGENT/outbox/result.json
```

Avoid shell-quoted JSON in `--payload`; PowerShell and other shells can corrupt
it.

## Chief and runner automation

The public engine now includes deterministic automation surfaces:

- `runner start`: keeps a worker available and executes provider-backed tasks.
- `chief start`: dispatches file-backed backlog tasks to waiting workers.
- `chief once`: runs one deterministic dispatch tick for CI/debug/manual use.

Chief tasks may include:

```json
{
  "task_id": "task-1",
  "instructions": "Implement the auth fix.",
  "required_capabilities": ["backend", "python"],
  "acceptance_criteria": ["Tests pass", "No token leaks"],
  "verify_command": "python -m pytest tests/hub -q",
  "verify_timeout_seconds": 120,
  "max_attempts": 2
}
```

Members can advertise capabilities with:

```bash
--capabilities backend,python,review
```

The chief prefers workers whose capabilities match the task.

## State and recovery

ACP tracks member state so dispatch does not blindly pile work onto busy agents.

| State / field | Purpose |
| --- | --- |
| `waiting` | Agent is available for work. |
| `busy` | Agent is actively working. |
| `current_task` | Agent has an in-flight task and should not receive another one. |
| replay | Query session history/events for debugging and context recovery. |

Important recovery behavior:

- `WAIT_ALREADY_ACTIVE` means a stale wait/listen already exists; use
  `cancel-wait`.
- 502/503/504 are retried only for safe idempotent flows such as wait, status,
  heartbeat, and session-info.
- `send` is not automatically retried, to avoid duplicate delivery.
- stale 403/404 or "session does not exist" means the session probably died,
  was closed, or credentials rotated; reconnect instead of looping forever.

## ACP_AGENT bundle

`ACP_AGENT/` is the portable project-side bundle:

```text
ACP_AGENT/
  acp.py
  AGENT.md
  install_from_bundle.py
  update_from_release.py
  runner_support.py
  acp_distribution.py
  DISTRIBUTION.json
  VERSION
  CHANGELOG.md
  skills/acp-session-coordinator/SKILL.md
```

The public community distribution is explicit:

```json
{
  "default_hub_mode": "explicit",
  "default_hub_http": null,
  "default_hub_ws": null,
  "default_manifest_url": null
}
```

That means the public bundle does not ship a hosted hub or customer-specific
domain. Users provide their own `--hub-http`.

## Common mistakes

| Mistake | Correct approach |
| --- | --- |
| Using `join-session --code` with a workspace token | Use `managed-join --agent-token --session-id`. |
| Leaving a turn-based LLM in persistent `listen` | Use `coordinate` or `listen --stop-after-message`. |
| Reusing the chief config as a worker | Create one config per agent identity. |
| Hand-copying `member_token` after binding | Let `ACP_AGENT/agents/*.json` carry it. |
| Retrying `send` after gateway errors | Do not auto-retry non-idempotent sends. |
| Treating workspace as the work unit | Workspace organizes; sessions do the work. |

## Related docs

- [README](../README.md)
- [Product walkthrough](../PRODUCT_WALKTHROUGH.md)
- [Public repo boundary](../PUBLIC_REPO_BOUNDARY.md)
- [Open core model](../OPEN_CORE_MODEL.md)
- [Protocol reference](../protocol.md)
