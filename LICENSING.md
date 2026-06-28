# Licensing map

ACP is open-core. Different parts of this repository are licensed differently,
matching the model in [OPEN_CORE_MODEL.md](OPEN_CORE_MODEL.md). This file is the
human-readable map; the canonical legal texts are the `LICENSE` files.

| Path | Component | License | Text |
| --- | --- | --- | --- |
| `/` (default) | **ACP Manager** (server: `apps/hub`, core + managed workspace layer) | **AGPL-3.0-or-later** | [`LICENSE`](LICENSE) |
| `ACP_AGENT/` | **ACP Client / SDK** | **Apache-2.0** | [`ACP_AGENT/LICENSE`](ACP_AGENT/LICENSE) |
| `acp-cloud` (separate private repo) | **ACP Cloud** overlay (billing/provisioning/branding) | Proprietary — never published | — |

## Why this split

- **Apache-2.0 for the client** maximizes adoption (explicit patent grant); the
  SDK should run everywhere with no friction.
- **AGPL-3.0 for the server** closes the SaaS loophole: anyone running a modified
  Manager as a network service must publish their changes, so improvements flow
  back. It is still OSI-approved open source (unlike source-available BSL/SSPL),
  so it attracts contributors.
- **The private `acp-cloud` overlay** is the commercial product and is never
  published.

## Contributions

Contributions to this repository are accepted under the Contributor License
Agreement in [`CLA.md`](CLA.md). The CLA lets the project owner offer the
Manager both as AGPL to the world and under a private license inside the
proprietary `acp-cloud` overlay (dual-licensing). Without it, externally
contributed Manager code could not legally be linked into the Cloud overlay.

## Trademark

The license frees the **code**, not the **brand**. "ACP" and associated marks are
not licensed for use in a competing hosted service. See [`NOTICE`](NOTICE).

---

> Not legal advice. The direction is locked, but a legal review is warranted
> before accepting outside contributions at scale or launching a commercial
> hosted tier - in particular the copyright-holder identity and final CLA text.
