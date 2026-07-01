# Single-workspace Public Mode Plan

This plan changes ACP so the public repo is easy to self-host as one workspace, while the private Cloud/operator repo owns multi-workspace provisioning and monetization.

## Decision

| Area | Decision |
| --- | --- |
| Public ACP | Single workspace by default: one admin user, one workspace, many rooms/sessions. |
| Private ACP Cloud | Multi-workspace operator product: landing, billing, signup, hosted downloads, provisioning, plan limits. |
| Code ownership | Keep one public engine. Do **not** maintain a private copy of the public repo. |
| Deployment connection | `acp-cloud` composes/imports public ACP in the same app process. Do **not** run two containers sharing one SQLite database. |
| Nephila reset | Prefer a clean volume for the new public single-workspace deployment; old multi-workspace volume can be backed up, not reused blindly. |

## Current implementation status

- Done: public product-boundary docs.
- Done: `ACP_DEPLOYMENT_MODE=single_workspace|operator` backend config.
- Done: public single-workspace bootstrap and fail-fast multi-workspace DB guard.
- Done: operator-only global workspace admin routes.
- Done: login/session payloads and SPA redirects to the default workspace.
- Done: setup helper for generating a private single-workspace `.env`.
- Done: Docker Compose env wiring for single-workspace mode.
- Done: private `acp-cloud` validates/uses `ACP_DEPLOYMENT_MODE=operator`.
- Not done in code here: live Nephila/Dokploy volume backup/reset and redeploy.

## Target product behavior

### Public self-host behavior

A user installing the public repo gets:

1. One ACP server locally or on a VPS.
2. One workspace created at first boot.
3. One workspace admin account.
4. Login redirects directly to that workspace.
5. The workspace admin can create many rooms/sessions.
6. Agents connect through the bundled `ACP_AGENT` commands/skill.
7. No global operator dashboard.
8. No create-workspace UI.
9. No create-user UI.
10. No multi-workspace list for the public/default install.

### Private hosted behavior

The private `acp-cloud` product gets:

1. Public landing and commercial docs.
2. Hosted bundle/download page.
3. Signup and billing.
4. Operator dashboard.
5. Workspace provisioning.
6. Multiple customer workspaces.
7. Plan limits and quotas.
8. Branding and official hosted distribution metadata.
9. Customer login into assigned workspace only.
10. Internal operator access to all workspaces.

## Configuration model

### New public mode env vars

Add a deployment mode switch:

```env
ACP_DEPLOYMENT_MODE=single_workspace
```

Allowed values:

| Value | Owner | Behavior |
| --- | --- | --- |
| `single_workspace` | Public/default | Bootstraps exactly one workspace and one admin. Disables global multi-workspace admin routes/UI. |
| `operator` | Private `acp-cloud` | Enables multi-workspace operator routes/UI. Requires private overlay or explicit operator config. |

Public default should be `single_workspace`.

### Single-workspace bootstrap env vars

Use explicit setup values instead of hardcoded credentials:

```env
ACP_WORKSPACE_SLUG=default
ACP_WORKSPACE_NAME="My ACP Workspace"
ACP_WORKSPACE_ADMIN_EMAIL=admin@example.com
ACP_WORKSPACE_ADMIN_PASSWORD_HASH=<scrypt-or-sha256-hash>
```

Optional:

```env
ACP_WORKSPACE_ADMIN_PASSWORD=<only-for-first-boot-or-local-dev>
```

Recommendation:

- Prefer password hash in production.
- Allow plaintext only through a setup command or local dev helper, never document it as the production path.
- On first boot, write admin + workspace into `ACP_MANAGED_AUTH_SQLITE_PATH` only if the DB is empty.

## Architecture changes

### 1. Separate deployment mode from auth roles

Current model has `instance_admin` and `workspace_admin` roles in public. Keep the data model, but change public behavior:

- `single_workspace` mode should not expose `instance_admin` UX.
- The bootstrap user may internally have enough permission to administer the single workspace, but should experience the product as `workspace_admin`.
- `operator` mode can keep true global `instance_admin` semantics for private/cloud.

### 2. Add a managed deployment settings module

Create a small config layer, likely near:

```txt
apps/hub/src/acp_managed/config.py
```

Responsibilities:

- Parse `ACP_DEPLOYMENT_MODE`.
- Validate `single_workspace` bootstrap env.
- Validate `operator` mode requirements.
- Expose helpers such as:
  - `managed_deployment_mode()`
  - `single_workspace_settings()`
  - `operator_mode_enabled()`

### 3. Add single-workspace bootstrap service

Create service code, likely:

```txt
apps/hub/src/acp_managed/services/single_workspace.py
```

Responsibilities:

- On startup, if mode is `single_workspace`:
  - Ensure auth DB exists.
  - If DB is empty, create the single workspace.
  - Create the single admin principal.
  - Add admin as active `workspace_admin` membership.
  - Optionally generate or rotate first workspace agent token only through UI/explicit action.
- If DB has exactly one workspace, continue.
- If DB has zero workspaces but principals exist, fail with a clear setup error.
- If DB has more than one workspace, fail with a clear error explaining that the DB is from operator/multi-workspace mode.

### 4. Gate global admin routes

In `single_workspace` mode, disable or hide these route groups:

```txt
/managed/admin/*
```

Expected behavior:

- API returns `404` or `403` with a clear message.
- UI does not link to global admin pages.
- Tests assert global workspace creation is unavailable in single mode.

Implementation target:

```txt
apps/hub/src/acp_managed/routing/instance_admin.py
apps/hub/src/acp_managed/app.py
```

Options:

| Option | Tradeoff |
| --- | --- |
| Do not mount `instance_admin` router in single mode | Cleanest public surface. Route baseline changes. |
| Mount but guard every handler | Easier incremental patch, but global routes remain visible to scanners. |

Recommendation: do not mount the router in `single_workspace` mode.

### 5. Redirect login to the single workspace

In public/single mode:

- Login should resolve the user's only workspace.
- After successful login, redirect to `/managed/ui/workspaces/{slug}`.
- A generic dashboard may still exist, but it should behave as a redirect/landing, not as a multi-workspace control panel.

Likely files:

```txt
apps/hub/src/acp_managed/routing/auth.py
apps/hub/frontend/packages/managed-app/src/views/LoginView.vue
apps/hub/frontend/packages/managed-app/src/views/ManagedDashboardView.vue
apps/hub/frontend/packages/managed-app/src/router.ts
```

### 6. Hide multi-workspace UI in public mode

In `single_workspace` mode:

- Hide workspace list as a primary surface.
- Hide create workspace controls.
- Hide invite workspace admin controls.
- Hide global audit/admin controls.
- Keep room/session management.
- Keep room files/wall/operator inside the workspace.

Likely files:

```txt
apps/hub/frontend/packages/managed-app/src/views/WorkspaceListView.vue
apps/hub/frontend/packages/managed-app/src/views/ManagedDashboardView.vue
apps/hub/frontend/packages/managed-app/src/views/WorkspaceDetailView.vue
apps/hub/frontend/packages/managed-app/src/components/ManagedNav.vue
```

### 7. Preserve workspace functionality

These must keep working in public single mode:

- login/logout
- workspace detail
- rotate workspace agent token
- create/list/detail/close room sessions
- room prompt/instructions
- room wall
- room files
- web operator
- agent `/managed/agent/*` routes
- ACP client `connect`, `coordinate`, `onboard`, `runner`, `chief`

### 8. Keep private operator path clean

`acp-cloud` should enable operator mode via env:

```env
ACP_DEPLOYMENT_MODE=operator
```

Private app composition should:

- Import public `create_managed_app` or a new app factory with settings.
- Mount private landing/billing/download/operator pages.
- Use one DB/volume in one process.
- Own workspace provisioning policy.
- Own hosted bundle defaults.

Do **not** duplicate public repo code.

## Database and volume strategy

### Public self-host DB

Recommended paths remain:

```env
ACP_SQLITE_PATH=/data/acp/acp.sqlite3
ACP_MANAGED_AUTH_SQLITE_PATH=/data/acp/acp-managed-auth.sqlite3
```

Public install uses a Docker volume at `/data`.

### Local install DB

Local dev can default to repo-local `.data/`, but docs should make this explicit:

```txt
.data/acp.sqlite3
.data/acp-managed-auth.sqlite3
```

### Existing multi-workspace DB in single mode

If `single_workspace` mode finds more than one workspace:

- fail fast
- do not delete data
- show message: use `ACP_DEPLOYMENT_MODE=operator` or start with a clean auth DB/volume

### Nephila migration

Recommended:

1. Back up old volume.
2. Start new clean volume for public single-workspace deployment.
3. Configure one admin/workspace.
4. Validate login and room creation.
5. Keep old volume available for manual recovery only.

## Install UX

### Public quickstart target

The user should run one setup path:

```bash
cp apps/hub/.env.example apps/hub/.env
python -m acp_managed.setup init-single-workspace
cd apps/hub
docker compose up -d
```

The setup command should:

- ask for workspace name
- ask for admin email
- ask for password
- generate strong secrets
- generate password hash
- write/update `.env`
- never print secrets after generation unless explicitly requested

### Docker/Dokploy target

Docs should show:

- Dockerfile: `apps/hub/Dockerfile`
- Docker context: `/` (repository root, so the image can include `ACP_AGENT/`)
- port: `8000`
- volume: `/data`
- env vars required

### Security defaults

- Require `ACP_MANAGED_SESSION_SECRET` in VPS/Dokploy.
- Generate `ACP_MANAGED_AGENT_TOKEN_SECRET` separately.
- Never ship default admin password.
- Never allow `admin/admin` examples.
- If `ACP_WORKSPACE_ADMIN_PASSWORD` is used, only use it to hash and store on first boot; warn if left set after bootstrap.

## Test plan

### Backend tests

Add tests for:

1. Single mode bootstraps one workspace from env.
2. Single mode bootstraps one admin from env.
3. Single mode does not bootstrap again when DB already has one workspace.
4. Single mode fails if DB has multiple workspaces.
5. Single mode does not mount or denies `/managed/admin/*`.
6. Single mode login redirects to only workspace.
7. Single mode workspace admin can create sessions.
8. Single mode agent token flow still works.
9. Operator mode preserves multi-workspace admin behavior.
10. Existing room wall/file/operator tests still pass in both relevant modes.

Likely files:

```txt
tests/hub/test_single_workspace_mode.py
tests/hub/test_managed_auth.py
tests/hub/test_managed_workspaces.py
tests/hub/managed_routes_baseline.json
```

### Frontend tests/build

At minimum:

```bash
npm run build --workspace=packages/managed-app
```

If frontend test infra exists later, add:

- single mode navigation hides global admin
- login lands in workspace
- workspace detail still manages rooms/files/wall

### Full validation

```bash
python -m pytest tests/ -q
npm run build --workspace=packages/managed-app
```

Also run the public/private hygiene gate:

- public repo must not import `acp_cloud`
- bearer/agent responses must not expose `owner_member_token`
- route baseline updated if route surface changes

## Implementation phases

### Phase 0 — Lock product boundary docs

Files:

```txt
OPEN_CORE_MODEL.md
PRODUCT_WALKTHROUGH.md
README.md
ROADMAP.md
```

Tasks:

- Replace “public full multi-workspace Manager” wording with “public single-workspace Manager by default”.
- Define `operator` mode as private/cloud.
- Document why public single mode still supports many rooms/sessions.
- Document that AGPL/trademark help, but product boundary is enforced through deployment mode.

Acceptance:

- A reader understands public vs private without asking.
- No doc suggests public self-host gets a global workspace operator dashboard by default.

### Phase 1 — Config and bootstrap backend

Files:

```txt
apps/hub/src/acp_managed/config.py
apps/hub/src/acp_managed/services/single_workspace.py
tests/hub/test_single_workspace_mode.py
```

Tasks:

- Add deployment mode parser.
- Add bootstrap settings parser.
- Add single-workspace bootstrap service.
- Add fail-fast checks for invalid DB state.
- Test empty DB, existing one-workspace DB, and multi-workspace DB.

Acceptance:

- Empty DB becomes one workspace + one admin.
- Existing one-workspace DB is stable.
- Multi-workspace DB fails clearly.

### Phase 2 — Route gating

Files:

```txt
apps/hub/src/acp_managed/app.py
apps/hub/src/acp_managed/routing/instance_admin.py
tests/hub/managed_routes_baseline.json
tests/hub/test_single_workspace_mode.py
```

Tasks:

- Mount `instance_admin` router only in operator mode.
- Keep workspace admin and agent routes in single mode.
- Update route baseline intentionally.
- Add tests proving `/managed/admin/*` is unavailable in single mode.
- Add tests proving operator mode keeps admin routes.

Acceptance:

- Public default has no global admin surface.
- Private/operator mode still supports multi-workspace provisioning.

### Phase 3 — Login and UX redirect

Files:

```txt
apps/hub/src/acp_managed/routing/auth.py
apps/hub/src/acp_managed/services/access.py
apps/hub/frontend/packages/managed-app/src/router.ts
apps/hub/frontend/packages/managed-app/src/views/LoginView.vue
apps/hub/frontend/packages/managed-app/src/views/ManagedDashboardView.vue
```

Tasks:

- Add API/session payload that exposes deployment mode and default workspace slug.
- Redirect single-mode login to the only workspace.
- Make dashboard redirect or show a one-workspace landing.
- Hide irrelevant multi-workspace navigation.

Acceptance:

- User logs in and lands where they can create rooms.
- User never sees global workspace management in single mode.

### Phase 4 — Setup command and env examples

Files:

```txt
apps/hub/.env.example
apps/hub/src/acp_managed/setup.py
pyproject.toml
README.md
ONBOARDING.md
```

Tasks:

- Add CLI command to generate `.env` for single workspace.
- Generate strong managed secrets.
- Generate password hash.
- Document local and VPS setup.
- Document Dokploy setup.

Acceptance:

- Fresh user can install in a few steps.
- No default password exists.
- VPS install has durable `/data` volume guidance.

### Phase 5 — Private `acp-cloud` operator mode

Repo:

```txt
C:\Users\Orion\OneDrive\Desktop\sistemas\all_projects\acp-cloud
```

Tasks:

- Set `ACP_DEPLOYMENT_MODE=operator` in private deployment docs/config.
- Ensure private app composes public app in one process.
- Move/own landing/downloads/official bundle docs in private.
- Keep billing/provisioning/branding private.
- Confirm operator can create many workspaces.
- Confirm customer login only enters assigned workspace.

Acceptance:

- Hosted Cloud can monetize workspaces.
- Public repo is not duplicated.
- No two containers share one SQLite DB.

### Phase 6 — Nephila deployment reset

Tasks:

- Back up current volume.
- Create clean volume for single-workspace public deployment.
- Set public single-workspace env vars.
- Redeploy public ACP.
- Login as one workspace admin.
- Create a room.
- Connect an agent through `ACP_AGENT`.
- Verify wall/files/operator.

Acceptance:

- Nephila public deployment behaves as one workspace.
- Old multi-workspace state is not accidentally reused.
- Rollback is possible from backup.

## Risks and mitigations

| Risk | Mitigation |
| --- | --- |
| Breaking private operator flow | Keep `operator` mode tests before changing routes. |
| Accidentally deleting old Nephila data | Back up volume; single mode fail-fast must never delete. |
| Weak public setup security | No default password; setup wizard generates secrets/hash. |
| Route baseline churn | Update `managed_routes_baseline.json` only after intentional route gating. |
| Maintaining two repos manually | Never fork public into a private copy; private composes public. |
| Third party commercializes public code | AGPL + trademark + single-workspace public UX; private operator features stay out of public default. |

## Definition of done

- Public default is `single_workspace`.
- Public install creates/uses exactly one workspace.
- Public install creates/uses exactly one admin user.
- Public UI has no global multi-workspace admin path.
- Workspace can create many rooms/sessions.
- Agents can connect with the bundled client/skill.
- Operator/multi-workspace mode exists only when explicitly enabled for private/cloud.
- Docs explain public install vs hosted Cloud clearly.
- Tests and frontend build pass.
- Nephila can be reset to clean single-workspace mode.
