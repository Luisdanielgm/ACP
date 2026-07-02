# ACP Open-Core & Product Model

**Status: canonical.** This document is the source of truth for what is open source, what stays private, and what customers pay for.

## Decision

ACP has one public engine and one private operator overlay.

| Piece | Open / Private | What it is |
| --- | --- | --- |
| **ACP Client** | Open | The bridge an agent runs to participate (`ACP_AGENT`). It connects agents to any ACP Manager, local or remote. |
| **ACP Manager** | Open | The self-host server: ACP core plus a **single-workspace** UI/API by default. One admin, one workspace, many rooms/sessions. |
| **ACP Cloud** | Private | The hosted commercial control plane: landing, signup, billing, official downloads, customer registry, provisioning runbooks/automation, branding, plan limits, and links to each hosted ACP service. |

## The open-core line

- **Open**: ACP core, client, and the public self-host workspace experience.
- **Private**: hosted/commercial operation and anything that provisions or monetizes multiple customer workspaces.

Public ACP must be useful without private code, but it should not expose the full operator business surface by default.

## Deployment model

Public ACP has one runtime shape: **one ACP service equals one workspace**.

| Runtime | Repo | Behavior |
| --- | --- | --- |
| Public ACP service | public `ACP` | Bootstraps exactly one workspace and one workspace admin. Rejects `ACP_DEPLOYMENT_MODE=operator`. |
| ACP Cloud admin | private `acp-cloud` | Tracks customers and provisioning state. It does not host customer rooms inside its own process. |

The public side must never import private `acp_cloud`. The private side creates or tracks separate public ACP deployments per customer/workspace.

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

There is no shared SQLite database and no customer workspace living inside the private ACP Cloud domain.

```text
Customer agents ---> customer ACP service (public repo, one workspace)
Operator/admin ---> ACP Cloud (private repo, customer registry + provisioning)
```

A hosted customer receives their own ACP service/container/domain/volume. ACP Cloud stores the commercial/admin record and points to that customer URL. Automation can be added later, but the architectural boundary remains the same.

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
2. Public repo rejects `ACP_DEPLOYMENT_MODE=operator` and no longer mounts global workspace admin routes.
3. Private `acp-cloud` owns hosted/commercial admin surfaces and tracks customer ACP services.
4. Future docs and tests must describe public self-host as one workspace, not a global VPS operator dashboard.
