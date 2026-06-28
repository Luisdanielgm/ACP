# ACP Roadmap & State

ACP (Agent Communication Protocol) — open-source coordination layer for coding
agents. This file is the single source of truth **inside this repo** for the plan
and where we are. Update the "Current state" section whenever you finish a slice.

See [OPEN_CORE_MODEL.md](OPEN_CORE_MODEL.md) for the open-core model and
[ONBOARDING.md](ONBOARDING.md) to get set up.

---

## 📍 Current state (update me)

- **Milestones reached:** ★ M1 (clean engine) · ★ M2 (open source — this repo is public).
- **In progress:** M3 follow-up polish, DX client automation, and release/product polish.
  - ✅ Broadcast (one-to-all) — already in `coordination_service.send_message`.
  - ✅ Room prompt (session instructions) — backend + dashboard. Owner sets it on
    session create; agents receive it on join/detail. (`test_room_prompt.py`)
  - [done] Persistent room wall - separate durable wall store, owner/agent posts, owner pin/delete, managed dashboard detail view. (`test_room_wall.py`)
  - [done] Web operator (Option B: server-side pseudo-member) - browser admin can send into the room without exposing pseudo-member credentials. (`test_web_operator.py`)
- **Tests:** `python -m pytest tests/ -q` → all green (a few skip when internal
  `.planning`/`.codex` artifacts are absent, which is normal in this public repo).
- **DX client automation:** first deterministic turn-based worker entrypoint exists:
  `python ACP_AGENT/acp.py coordinate ...` wraps managed connect/onboard and waits
  for exactly one message, so agents do not hand-assemble session/member-token
  commands for the initial turn.

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
| M3 | Rooms (Salas) | Room prompt, persistent wall, web operator (Option B) | core slices done; polish follow-up |
| M4 | Storage | Per-room files/instructions, quotas | ✅ done |
| DX | **Client automation** (parallel track) | Deterministic connect/coordinate commands so the agent stops re-reasoning + mis-assembling token commands | 🔄 first slice |
| — | 🎯 **Sellable OSS product** | engine + rooms + storage, self-hostable, durable | 🔄 polish |
| (Cloud) | Commercial overlay | Billing/provisioning/branding — lives in the **separate private `acp-cloud` repo**, not here | ⬜ deferred |

Cloud/billing, HA, and the pilot are intentionally **last** — they don't block the
open-source product, and the commercial overlay lives in `acp-cloud` (private).

## 🏛️ Architecture (orient fast)

- `apps/hub/src/acp/hub/` — the **core** ACP hub (sessions, coordination, routing, persistence).
- `apps/hub/src/acp_managed/` — the **managed workspace layer** (auth, workspaces, agent tokens).
  Routes live in `acp_managed/routing/*` as `build_*_router(deps)` factories that
  consume the `ManagedRouterDeps` seam; `app.py` is thin composition.
- `ACP_AGENT/` — the portable **client** (Apache-2.0).
- `apps/hub/frontend/packages/managed-app/` — the dashboard (Vue).

**Security invariants** (do not break):
- Agent (Bearer) responses must never include `owner_member_token` — only the
  browser workspace-admin router exposes it.
- The public engine must never import `acp_cloud` (the pre-push hook enforces this).

## 🤖 Client DX / agent automation (parallel track — `ACP_AGENT/`)

**Problem:** to connect & coordinate, an agent today reads ~449 lines of
`ACP_AGENT/skills/acp-session-coordinator/SKILL.md`, calls several tools, reasons
multiple times, and frequently **mis-assembles commands and substitutes tokens
wrong** — wasted tokens + real errors.

**Goal:** make the common flows **deterministic and pre-packaged** so the agent
runs one command instead of reasoning through a multi-step recipe. Especially the
**connect/join flow** (token handling is the error-prone part).

**Approach (decide during design):**
- High-level `acp.py` subcommands that encapsulate multi-step flows (e.g. a single
  connect/join that resolves config + token internally; a `work-loop`; a chief run).
- And/or shipped recipe scripts the agent just invokes.
- Then slim the SKILL.md to point at those canned commands instead of explaining
  the reasoning.

**Done when:** an agent connects and runs a turn loop without hand-assembling
token commands; SKILL.md shrinks; fewer tokens + fewer mistakes per session.
This is independent of M3 (rooms) and can run in parallel.

## 🤝 Parallel work
- One agent per repo is the clean pattern (`acp-public` engine vs. `acp-cloud`
  overlay — separate repos, one-way dependency).
- Two agents in **this** repo at once → use feature branches + PRs (don't both push
  `main`). Coordinate any change to the public API surface.
