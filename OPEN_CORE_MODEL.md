# ACP Open-Core & Product Model

**Status: canonical.** This document is the source of truth for what is open source, what stays private, and what customers pay for.

## Decision

ACP has one public engine and one private operator overlay.

| Piece | Open / Private | What it is |
| --- | --- | --- |
| **ACP Client** | Open | The bridge an agent runs to participate (`ACP_AGENT`). It connects agents to any ACP Manager, local or remote. |
| **ACP Manager** | Open | The self-host server: ACP core plus a **single-workspace** UI/API by default. One admin, one workspace, many rooms/sessions. |
| **ACP Cloud** | Private | The hosted commercial operator product: landing, signup, billing, official downloads, provisioning, branding, plan limits, and multi-workspace operator dashboard. |

## The open-core line

- **Open**: ACP core, client, and the public self-host workspace experience.
- **Private**: hosted/commercial operation and anything that provisions or monetizes multiple customer workspaces.

Public ACP must be useful without private code, but it should not expose the full operator business surface by default.

## Deployment modes

| Mode | Repo | Behavior |
| --- | --- | --- |
| `single_workspace` | public `ACP` | Default. Bootstraps exactly one workspace and one workspace admin. Disables global multi-workspace admin routes/UI. |
| `operator` | private `acp-cloud` | Enables multi-workspace operator/admin behavior for hosted provisioning and billing. |

The public side must never import private `acp_cloud`. The private side may import and compose the public Manager.

## What customers pay for

Customers do not pay for hidden room/workspace features. They pay for hosted operation.

| | Self-host public ACP | ACP Cloud |
| --- | --- | --- |
| Setup | User installs locally/VPS | Operator hosts it |
| Workspace count | One workspace | One or many, by plan/payment |
| Users | One workspace admin | Operator creates/provisions customers |
| Rooms/sessions | Many inside the workspace | Many inside each paid workspace |
| Maintenance/backups | User | Operator |
| Billing/provisioning | Not included | Private |

## Composition model

There is no network bridge between public and private code.

```text
ACP Client ---> ACP Manager public engine
                     ^
                     |
             acp-cloud private overlay
```

`acp-cloud` composes/imports the public Manager inside the same app process and uses one database/volume. Do **not** run two containers sharing the same SQLite database.

## What stays private

- Commercial landing/signup flow.
- Hosted bundle/download page and official distribution defaults.
- Billing, plan limits, metering, and provisioning.
- Multi-workspace operator dashboard.
- Branding assets and hosted domains.
- Admission policy for the hosted tier.

## Licensing

| Component | License | Why |
| --- | --- | --- |
| **ACP Client / SDK** (`ACP_AGENT`) | Apache-2.0 | Maximize adoption and agent compatibility. |
| **ACP Manager** server | AGPL-3.0-or-later | Anyone running a modified network service must publish modifications. |
| **ACP Cloud** overlay | Proprietary | Commercial operator product; never published. |

Trademark matters separately: the license frees the code, not the ACP brand. See `LICENSING.md` and `NOTICE`.

The CLA remains mandatory for external contributions. It preserves the project
owner's ability to dual-license the public Manager inside the proprietary
`acp-cloud` overlay while still publishing the server as AGPL for everyone else.

## Current implementation status

1. Public repo already ships core sessions, rooms, storage, and agent DX.
2. Public repo is being moved from multi-workspace default to `single_workspace` default.
3. Private `acp-cloud` owns `operator` mode and all hosted/commercial surfaces.
4. Future docs and tests must describe public self-host as one workspace, not a global VPS operator dashboard.
