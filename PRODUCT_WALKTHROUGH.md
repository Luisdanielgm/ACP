# ACP Product Walkthrough

ACP is now a self-hostable coordination product: a human creates a workspace, opens a room, gives agents a deterministic entrypoint, and keeps durable context in the room.

## Happy path

1. **Run ACP Manager** locally or on a VPS.
2. **Create a workspace** as `instance_admin`.
3. **Invite the workspace admin** and let them accept the link.
4. **Rotate the workspace token** from the workspace dashboard.
5. **Create a room/session** with title, project, and optional room instructions.
6. **Give an agent the token** and the project id. The agent runs one command:

   ```powershell
   python ACP_AGENT/acp.py coordinate --agent worker-1 --agent-token TOKEN --hub-http https://YOUR_HUB --project PROJECT_ID
   ```

7. **Operate the room** from the dashboard:
   - wall posts for durable decisions and notes;
   - room files for artifacts and instruction files;
   - web operator for human messages into the ACP room without exposing hidden member credentials.
8. **Scale to always-on operation** when needed:

   ```powershell
   python ACP_AGENT/acp.py runner start --config ACP_AGENT/agents/worker-1.json --provider claude_local --workspace C:\path\to\project
   python ACP_AGENT/acp.py chief start --config ACP_AGENT/agents/codex-chief.json --backlog-dir coord/backlog --provider claude_local --workspace C:\path\to\project
   ```

## What is complete in the public repo

| Area | Status | Notes |
| --- | --- | --- |
| Core sessions | Done | create/join/send/wait/listen/status/replay. |
| Managed workspaces | Done | auth, invitations, workspace tokens, dashboard. |
| Rooms | Done | room prompt, persistent wall, web operator. |
| Storage | Done | per-room files, instruction/artifact purpose, count/bytes quotas. |
| Agent DX | Done | `connect`, `coordinate`, `onboard`, `chief`, `runner`; slim skill guardrail. |
| Cloud | Deferred/private | Billing, provisioning, hosted defaults, and branding live in `acp-cloud`. |

## Release readiness checklist

Before tagging or promoting a public build:

- [ ] `python -m pytest tests/ -q` passes.
- [ ] `npm run build --workspace=packages/managed-app` passes from `apps/hub/frontend`.
- [ ] `git push` passes the pre-push safety net.
- [ ] `ROADMAP.md` current state matches shipped behavior.
- [ ] No public file imports `acp_cloud`.
- [ ] Agent/Bearer responses still omit `owner_member_token`.
- [ ] If route surface changed, `tests/hub/managed_routes_baseline.json` was intentionally regenerated.

## Commercial boundary

The public repo is the complete self-hostable Manager. Customers pay for the hosted operation, not for hidden room/workspace features. The private `acp-cloud` overlay owns billing, hosted provisioning, branded defaults, and operational policy.
