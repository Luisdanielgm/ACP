# Security Policy

## Reporting a vulnerability

**Do not open a public issue for security vulnerabilities.**

Please report them privately so they can be fixed before disclosure:

- Open a private vulnerability report via GitHub Security Advisories — use
  **"Report a vulnerability"** on the repository's **Security** tab.

Include enough detail to reproduce: affected version/commit, component (Hub
server vs. `ACP_AGENT` client), steps, and impact.

We aim to acknowledge reports within a few business days and will keep you
updated on the fix and disclosure timeline.

## Scope

This policy covers the open-source components in this repository:

- **ACP Manager** (server, `apps/hub`) — AGPL-3.0-or-later.
- **ACP Client / SDK** (`ACP_AGENT/`) — Apache-2.0.

The proprietary ACP Cloud overlay is tracked separately.

## Handling sensitive areas

Authentication, session tokens, agent Bearer tokens, and the invitation flow are
the most security-sensitive surfaces. Two invariants in particular must hold:

- Agent (Bearer) responses must never expose `owner_member_token`; only
  authenticated browser workspace-admins receive it.
- Accepting an invitation for an existing account requires proving ownership with
  that account's password (no session is minted from a leaked invitation link).

If you believe a change could affect these, flag it explicitly.
