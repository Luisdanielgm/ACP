# Public Repo Boundary

> **Updated 2026-06-19 — Option Y.** The open-core line moved: the **workspace
> layer is now open source**, not private. The single source of truth for the
> model is [OPEN_CORE_MODEL.md](OPEN_CORE_MODEL.md). This file applies that
> decision to the public repository boundary.

This repository is the public open-source product: **ACP Client + ACP Manager**.
Only the separate **ACP Cloud** overlay stays private.

## Included in the public repo (ACP Client + ACP Manager)

- `ACP_AGENT/` community bundle — **ACP Client**
- `apps/hub/src/acp/hub/` — core hub runtime
- `apps/hub/src/acp/protocol/` — protocol models and validators
- the **workspace layer** (today inside `apps/hub/src/acp_managed/`, to be
  de-tangled): human auth/login mechanism, whitelist mechanism, workspaces,
  invitations, workspace tokens, workspace→session bridge, workspace admin
  routes and UI
- `tests/` for public contracts
- `README.md`, `protocol.md`

Together these are **ACP Manager**: a complete, self-hostable server (VPS or
local). A self-hoster needs nothing else.

## Must stay out of the public repo (ACP Cloud only)

- private landing assets and private branding
- the public signup/payment page
- billing, plan limits, and multi-tenant metering/provisioning across customers
- the `official` hosted distribution metadata: hosted hub URLs, default manifest
- operator-specific defaults, secrets, and domains
- the admission **policy** for the hosted tier (the whitelist *mechanism* is
  public; "who is allowed on the operator's VPS" is private)

## Public bundle rules

- `ACP_AGENT/DISTRIBUTION.json` must remain the community flavor
- public flavor must use `default_hub_mode = explicit`
- public flavor must not ship a hosted hub URL
- public flavor must not ship a default release manifest URL

## Dependency rule

The public side must never import the private side. The private **ACP Cloud**
overlay imports the public **ACP Manager** package and mounts its routes on top
(see [OPEN_CORE_MODEL.md](OPEN_CORE_MODEL.md) → "How a workspace connects").

## Enforcement

`tests/hub/test_public_repo_hygiene.py` validates the public repository
surface, including the workspace layer. The guarantee is that **branding, the
payment page, billing, and hosted defaults** must not leak into this repo, or CI
fails.
