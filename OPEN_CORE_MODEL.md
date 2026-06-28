# ACP Open-Core & Product Model

**Status: canonical (decided 2026-06-19).** This document is the single source of
truth for what is open source vs private and what customers pay for. Where the
older boundary docs disagree (they assumed an earlier split), this one wins.

## The three pieces

| Piece | Open / Private | What it is |
| --- | --- | --- |
| **ACP Client** | 🟢 open | The bridge an agent runs to participate (`ACP_AGENT`). Mode (a) pure client → connect agents to any hub; mode (b) local embedded hub (`acp.py hub-up`) → coordinate agents on the same machine, zero infra. This is what users download. |
| **ACP Manager** | 🟢 open | The **server**: ACP core (sessions, protocol, routing, replay) **plus** the workspace layer (auth, invitations, workspace tokens, workspaces, admin UI). Self-hostable on a VPS (remote, multi-user) or locally (bound to `127.0.0.1`, same-machine only). |
| **ACP Cloud** | 🔒 private | The hosted commercial offering: the operator runs ACP Manager on their own VPS with a **thin** private overlay — public landing/downloads page, signup, billing/plan limits, branding, and provisioning automation. Lives only in the operator's deployment + website; never published. |

## The open-core line (Option Y)

- **Open**: ACP core **and** the full workspace layer — anyone can self-host a
  complete product (workspaces, auth, invitations, multi-session) with no
  external dependency.
- **Private**: only the commercial hosted overlay (page, billing, branding,
  provisioning, hosted distribution defaults).

This supersedes the earlier "all of `acp_managed` is private" line.

## What customers pay for

**Not the software — the operation.** The software is open and free to
self-host. Paying customers buy *not having to run it*:

| | Self-host (free) | ACP Cloud (paid) |
| --- | --- | --- |
| Software | ACP Manager, open source | the **same** ACP Manager, open source |
| Who runs it | the user, on their VPS/machine | the operator, 24/7 |
| Who maintains/updates/backs up | the user | the operator |
| What the customer gets | the code; runs it themselves | a **ready workspace, no install**, always-on, support |

Direct analogues: GitLab CE (free self-host) vs GitLab.com (paid hosted);
Supabase self-host vs Supabase Cloud. **The payment model lives entirely on the
page and the deployment — never in the code.** The repos know nothing about
billing.

## How a workspace connects to the rooms (the key mechanic)

There is no fragile network bridge. The layers compose by **package dependency**:

- ACP Manager imports the core app factory and mounts the workspace layer on it:
  `from acp.hub.app import create_app` → `create_app(runtime=...)` → mount
  workspace routes. (This is already what today's `acp_managed/app.py` does
  in-repo.)
- ACP Cloud imports ACP Manager and mounts the private overlay on it the same way.

**Delivering a workspace to a paying customer** uses the existing invitation
flow: the operator (instance_admin on the hosted Manager) creates a workspace and
sends an invitation link; the customer accepts → becomes `workspace_admin` of
that workspace, on the operator's VPS, without installing anything. Billing (on
the page) only automates "paid → create workspace + send invite".

**Administering a local workspace** is the same Manager software run locally; the
user is admin via the same UI. "Local" just means it is bound to the machine and
only same-machine agents can reach it.

> The Manager is the **same program** whether self-hosted (free) or run by the
> operator as Cloud (paid). The difference is not in the code — it is *who runs
> it and who can reach it*. That is why the rooms/workspaces can be fully open
> source without breaking the business.

## Dependency rule

```text
ACP Client ── connects to ──▶ any ACP Manager (local or remote)

ACP core ◀── workspace layer        (inside ACP Manager)
ACP Manager ◀── ACP Cloud overlay   (private)
```

The public side must **never** import the private side. Private may import public.

## Recommended repo layout

- **`acp` (public)**: ships ACP Client and ACP Manager (one repo with two install
  targets/flavors, or two repos — packaging choice is open). `DISTRIBUTION.json`
  here stays the community flavor: `default_hub_mode = "explicit"`, no hosted hub
  URL, no default manifest.
- **`acp-cloud` (private)**: depends on the public ACP Manager package; adds the
  page, billing, branding, provisioning, and the `official` `DISTRIBUTION.json`
  flavor (hosted hub URLs + default manifest).

## What stays private (thin)

- public landing / branded downloads page + signup
- billing, plan limits, multi-tenant metering and provisioning across customers
- the `official` distribution metadata + hosted hub URLs/secrets/domains
- private branding assets
- the admission **policy** for the hosted tier (the whitelist *mechanism* is open;
  "who is allowed on the operator's VPS" is private)

## Licensing (decided 2026-06-24)

Split license tuned to the open-core model and applied in the public repo.

| Component | License | Why |
| --- | --- | --- |
| **ACP Client / SDK** (`ACP_AGENT`) | **Apache-2.0** | Maximize adoption — this should run everywhere, no friction. Apache (not MIT) for the explicit patent grant. |
| **ACP Manager** (server) | **AGPL-3.0** | Closes the SaaS loophole: anyone running a modified version as a network service must publish their changes. No third party builds a closed product on the engine; improvements flow back. Still OSI open source (attracts contributors, unlike source-available BSL/SSPL). |
| **ACP Cloud** overlay | **Proprietary** | The commercial product; never published. |

**CLA is mandatory** on every contribution to the public repo — it is the linchpin,
not a formality:

- AGPL binds *third parties*, not the copyright holder. Because the operator owns
  the code (original author + CLA-assigned contributions), they can use the AGPL
  Manager inside the **proprietary `acp-cloud`** without triggering AGPL copyleft
  against themselves. This is dual-licensing: AGPL for the world, private license
  for the owner.
- Without a CLA, externally-contributed Manager code is pure AGPL and **cannot
  legally be linked into the private Cloud overlay** — which would break the
  business. The CLA preserves that right (and the option to sell commercial
  exceptions later).

**Trademark** the product name separately — the license frees the code, not the
brand. Nobody should offer a competing hosted service under the ACP name.

> Not legal advice. The direction is locked; a legal review is still warranted
> before accepting outside contributions at scale or launching a commercial hosted tier.

## Current implementation state

1. [done] Open-core line decided: Option Y, with Client / Manager / Cloud split.
2. [done] Public repo ships ACP Client + ACP Manager, including the workspace layer.
3. [done] Managed routes use `build_*_router(deps)` factories around `ManagedRouterDeps`.
4. [done] Public-product core is sellable/self-hostable: rooms, storage, quotas, DX automation, and release guidance are documented in [ROADMAP.md](ROADMAP.md) and [PRODUCT_WALKTHROUGH.md](PRODUCT_WALKTHROUGH.md).
5. [deferred/private] The separate private `acp-cloud` repo owns billing, provisioning, hosted defaults, and branding.

See also: [ARCHITECTURE_SIMPLIFIED.md](ARCHITECTURE_SIMPLIFIED.md) (layer model),
[MODULAR_BOUNDARIES.md](MODULAR_BOUNDARIES.md) (dependency direction).
