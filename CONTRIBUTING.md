# Contributing to ACP

Thanks for your interest in ACP (Agent Communication Protocol). This guide covers
how to get set up, the quality bar, and how contributions are licensed.

## Licensing of contributions

ACP is open-core (see [LICENSING.md](LICENSING.md)): the Manager (server) is
AGPL-3.0-or-later, the client (`ACP_AGENT/`) is Apache-2.0. Contributions are
accepted under the Contributor License Agreement ([CLA.md](CLA.md)) — please read
it before opening your first pull request.

## Development setup

ACP targets Python 3.11+ (CI pins 3.11 and 3.12; some newer interpreters lack
prebuilt wheels for native deps).

```bash
cd apps/hub
python -m venv .venv && . .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -e ".[test,dev]"
```

## Running the tests

The full suite must be green before any push:

```bash
python -m pytest tests/ -q
```

### Local safety net (free CI)

This repo gates pushes with a local pre-push hook that runs the suite — no paid CI
required. Enable it once per clone:

```bash
git config core.hooksPath scripts/hooks
```

A push is aborted if the suite is red. Override only in emergencies with
`git push --no-verify` (not recommended).

## Quality bar

- **Tests first.** New behavior comes with tests; bug fixes come with a test that
  reproduces the bug. Refactors keep the suite green before and after.
- **Surgical changes.** Touch only what the change requires; match the surrounding
  style; don't refactor unrelated code in the same PR.
- **Route surface is frozen by a baseline.** `tests/hub/managed_routes_baseline.json`
  pins the managed app's routes; if a change intentionally alters it, regenerate
  and explain why.

## Commits and PRs

- Use **Conventional Commits** (`feat:`, `fix:`, `refactor:`, `chore:`, `docs:`,
  `test:`).
- Keep PRs focused and reasonably small; describe the intent and how you verified.
- Sign off your commits per the CLA (`Signed-off-by: Name <email>`) and add the one-time PR acknowledgement described in [`CLA.md`](CLA.md).

## Reporting bugs and proposing features

Open an issue describing the problem or proposal with enough context to reproduce
or evaluate it. For security issues, do **not** open a public issue — see
[SECURITY.md](SECURITY.md).
