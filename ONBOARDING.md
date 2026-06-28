# Onboarding — ACP (public engine)

You are working on the **public** ACP repo: the engine (core hub + managed
workspace layer) and the portable client. Read this before touching anything,
then see [ROADMAP.md](ROADMAP.md) for current state and [PRODUCT_WALKTHROUGH.md](PRODUCT_WALKTHROUGH.md) for the end-to-end product path.

## What this repo is

- `apps/hub/src/acp/hub/` — core ACP hub (sessions, coordination, routing, persistence).
- `apps/hub/src/acp_managed/` — managed workspace layer (auth, workspaces, agent tokens).
  Routes are `build_*_router(deps)` factories in `acp_managed/routing/*` consuming
  the `ManagedRouterDeps` seam; `app.py` is thin `include_router` composition.
- `ACP_AGENT/` — portable client (Apache-2.0). The rest is AGPL-3.0. See LICENSING.md.
- `apps/hub/frontend/packages/managed-app/` — dashboard (Vue 3 + Vite, i18n en/es).

## Dev setup

Python 3.11–3.12 (CI pins those; newer interpreters may fail to build native deps).

```bash
# 1. Frontend (the route-baseline test needs the managed SPA dist mounted)
cd apps/hub/frontend && npm install && npm run build && cd ../../..

# 2. Python package + test deps
pip install -e "apps/hub[test]"
# If your interpreter can't build pydantic-core (e.g. 3.14) but deps are already
# installed, re-point the editable install without rebuilding deps:
#   pip install -e apps/hub --no-deps

# 3. Run the suite
python -m pytest tests/ -q

# 4. Enable the free local CI gate (runs the suite + import-direction check on push)
git config core.hooksPath scripts/hooks
```

## How we work (conventions)

- **TDD.** New behavior ships with a test; bugs ship with a failing test first;
  refactors stay green before and after.
- **Conventional commits** (`feat:`, `fix:`, `refactor:`, `chore:`, `docs:`, `test:`).
- **Push from the terminal.** `git push` runs the pre-push hook (full suite + the
  one-way-dependency gate). **Do NOT use VS Code "Publish to GitHub" / its commit
  button** — it has squashed and re-initialized git history here twice.
- **Identity:** commit as a GitHub noreply email to keep personal email out of
  public history: `git config user.email "<you>@users.noreply.github.com"`.
- **Route surface is frozen** by `tests/hub/managed_routes_baseline.json`. If a
  change intentionally alters routes, regenerate the baseline and say why.

## Hard rules (will break things / leak)

- **Never import `acp_cloud`** in this repo. It's the private overlay; the
  dependency is one-way (acp-cloud → acp, never back). The pre-push hook fails the
  push if you do.
- **Agent (Bearer) responses must never include `owner_member_token`.** Only the
  browser workspace-admin router (`routing/workspace_admin.py`) exposes it. The
  agent router (`routing/agent.py`) must not. There's a docstring invariant there.
- **No secrets, private hosts, or personal data** in committed files — this repo is
  public. `tests/hub/test_public_repo_hygiene.py` guards against known markers.

## Parallel work

- Cleanest: one agent per repo (this engine vs. the private `acp-cloud` overlay).
- Two agents in **this** repo at once → feature branches + PRs, don't both push
  `main`, and coordinate any change to the public HTTP/API surface.

## Where the plan lives

- This repo: [ROADMAP.md](ROADMAP.md) (plan + current state).
- Product walkthrough: [PRODUCT_WALKTHROUGH.md](PRODUCT_WALKTHROUGH.md) (workspace -> room -> agents -> durable context).
- Cross-repo big picture: the owner's Obsidian vault (not in any repo).
