# ACP Roadmap & State

ACP (Agent Communication Protocol) — open-source coordination layer for coding
agents. This file is the single source of truth **inside this repo** for the plan
and where we are. Update the "Current state" section whenever you finish a slice.

See [OPEN_CORE_MODEL.md](OPEN_CORE_MODEL.md) for the open-core model and
[ONBOARDING.md](ONBOARDING.md) to get set up.

---

## 📍 Current state (update me)

- **Milestones reached:** ★ M1 (clean engine) · ★ M2 (open source — this repo is public).
- **Public product state:** self-hostable ACP Manager is moving to `single_workspace` by default: one admin, one workspace, many rooms/sessions. Cloud/operator remains private.
  - ✅ Broadcast (one-to-all) — already in `coordination_service.send_message`.
  - ✅ Room prompt (session instructions) — backend + dashboard. Owner sets it on
    session create; agents receive it on join/detail. (`test_room_prompt.py`)
  - [done] Persistent room wall - separate durable wall store, owner/agent posts, owner pin/delete, managed dashboard detail view. (`test_room_wall.py`)
  - [done] Web operator (Option B: server-side pseudo-member) - browser admin can send into the room without exposing pseudo-member credentials. (`test_web_operator.py`)
- **Tests:** `python -m pytest tests/ -q` → all green (a few skip when internal
  `.planning`/`.codex` artifacts are absent, which is normal in this public repo).
- **DX client automation:** deterministic `connect`/`coordinate`/`onboard`/`chief`/`runner` surfaces exist, and the bundled ACP skill is now a short command router instead of a long reasoning recipe.

### Persistent room wall - DESIGN DECISION
Implemented as a separate durable wall store, not as replay/event history.
- Feed-style posts are attached to managed workspace sessions.
- Owners and agents can post.
- Owners can pin/unpin and delete in v1.
- Replay remains operational audit/history, not the room wall.

### Web operator - IMPLEMENTED
The browser operator is implemented as a server-side pseudo-member so a human can operate
the room from the managed dashboard without exposing pseudo-member credentials to the browser.

---

## 🧭 Milestones

| # | Milestone | What it delivers | Status |
|---|---|---|---|
| M1 | Clean engine | De-tangled managed app (routers + `ManagedRouterDeps` seam), at-least-once message idempotency | ✅ done |
| M2 | Open source | This repo public; AGPL server + Apache client; CLA; CI | ✅ done |
| M3 | Rooms (Salas) | Room prompt, persistent wall, web operator (Option B) | ✅ done |
| M4 | Storage | Per-room files/instructions, quotas | ✅ done |
| M5 | Single-workspace public mode | Public self-host defaults to one workspace/one admin; private `acp-cloud` owns operator multi-workspace mode | in progress |
| DX | **Client automation** (parallel track) | Deterministic connect/coordinate/onboard/chief/runner commands; slim skill guardrail | ✅ done |
| — | 🎯 **Sellable OSS product** | engine + rooms + storage, self-hostable, durable | ✅ done |
| (Cloud) | Commercial overlay | Billing/provisioning/branding — lives in the **separate private `acp-cloud` repo**, not here | deferred/private |

Cloud/billing, HA, and the pilot are intentionally **last** — they don't block the
open-source product, and the commercial overlay lives in `acp-cloud` (private).

## 🏛️ Architecture (orient fast)

- `apps/hub/src/acp/hub/` — the **core** ACP hub (sessions, coordination, routing, persistence).
- `apps/hub/src/acp_managed/` — the **managed workspace layer** (auth, single-workspace public mode, agent tokens; operator mode is for private/cloud).
  Routes live in `acp_managed/routing/*` as `build_*_router(deps)` factories that
  consume the `ManagedRouterDeps` seam; `app.py` is thin composition.
- `ACP_AGENT/` — the portable **client** (Apache-2.0).
- `apps/hub/frontend/packages/managed-app/` — the dashboard (Vue).

**Security invariants** (do not break):
- Agent (Bearer) responses must never include `owner_member_token` — only the
  browser workspace-admin router exposes it.
- The public engine must never import `acp_cloud` (the pre-push hook enforces this).

## 🤖 Client DX / agent automation (parallel track — `ACP_AGENT/`)

**Problem solved:** to connect & coordinate, an agent used to read ~449 lines of
`ACP_AGENT/skills/acp-session-coordinator/SKILL.md`, calls several tools, reasons
multiple times, and frequently **mis-assembles commands and substitutes tokens
wrong** — wasted tokens + real errors.

**Result:** the common flows are **deterministic and pre-packaged** so the agent
runs one command instead of reasoning through a multi-step recipe. Especially the
**connect/join flow** (token handling is the error-prone part).

**Done:** `connect`, `coordinate`, `onboard`, `chief`, and `runner` are available; the bundled skill is capped by test at 180 lines and currently routes agents to canned commands instead of re-explaining the protocol.

## 🤝 Parallel work
- One agent per repo is the clean pattern (`acp-public` engine vs. `acp-cloud`
  overlay — separate repos, one-way dependency).
- Two agents in **this** repo at once → use feature branches + PRs (don't both push
  `main`). Coordinate any change to the public API surface.
