# ACP Roadmap & State

ACP (Agent Communication Protocol) — open-source coordination layer for coding
agents. This file is the single source of truth **inside this repo** for the plan
and where we are. Update the "Current state" section whenever you finish a slice.

See [OPEN_CORE_MODEL.md](OPEN_CORE_MODEL.md) for the open-core model and
[ONBOARDING.md](ONBOARDING.md) to get set up.

---

## 📍 Current state (update me)

- **Milestones reached:** ★ M1 (clean engine) · ★ M2 (open source — this repo is public).
- **In progress:** ★ M3 (Rooms / Salas).
  - ✅ Broadcast (one-to-all) — already in `coordination_service.send_message`.
  - ✅ Room prompt (session instructions) — backend + dashboard. Owner sets it on
    session create; agents receive it on join/detail. (`test_room_prompt.py`)
  - ⬜ **Persistent room wall** ← next. Needs a design decision first (see below).
  - ⬜ Web operator (Opción B: server-side pseudo-member) — the big one (backend + Vue).
- **Tests:** `python -m pytest tests/ -q` → all green (a few skip when internal
  `.planning`/`.codex` artifacts are absent, which is normal in this public repo).

### Next slice: persistent room wall — OPEN DESIGN QUESTION
Decide before coding:
- What is the wall? Pinned announcements vs. a chronological feed.
- Who posts? Agents, the owner, or both.
- Note: a session already has an **event/replay history**
  (`/managed/agent/.../sessions/{id}/replay`). Decide whether the wall *is* that
  history surfaced, or a separate "pinned notes" store.

---

## 🧭 Milestones

| # | Milestone | What it delivers | Status |
|---|---|---|---|
| M1 | Clean engine | De-tangled managed app (routers + `ManagedRouterDeps` seam), at-least-once message idempotency | ✅ done |
| M2 | Open source | This repo public; AGPL server + Apache client; CLA; CI | ✅ done |
| M3 | Rooms (Salas) | Room prompt, persistent wall, web operator (Opción B) | 🔄 in progress |
| M4 | Storage | Per-room files/instructions, quotas | ⬜ |
| — | 🎯 **Sellable OSS product** | engine + rooms + storage, self-hostable, durable | ⬜ |
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

## 🤝 Parallel work
- One agent per repo is the clean pattern (`acp-public` engine vs. `acp-cloud`
  overlay — separate repos, one-way dependency).
- Two agents in **this** repo at once → use feature branches + PRs (don't both push
  `main`). Coordinate any change to the public API surface.
