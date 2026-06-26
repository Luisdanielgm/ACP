<template>
  <div>
    <header>
      <ManagedNav />
    </header>
    <main id="main-content">
      <section class="panel">
        <div class="panel-header">
          <div>
            <span class="panel-kicker">{{ t('admin_kicker') }}</span>
            <h1 class="panel-title">{{ t('admin_title') }}</h1>
            <p class="panel-sub">{{ t('admin_workspace_admin_body') }}</p>
          </div>
          <RouterLink to="/managed/dashboard" class="back-link">&larr; {{ t('nav_dashboard') }}</RouterLink>
        </div>

        <CreateWorkspaceForm
          ref="createFormRef"
          layout="compact"
          :submitting="creating"
          :require-admin-email="false"
          :current-user-email="user?.email ?? ''"
          @submit="handleCreate"
        />

        <div v-if="createResult" class="result-banner" role="alert" aria-live="polite">
          <div class="result-icon" aria-hidden="true">&#10003;</div>
          <div>
            <p class="result-title">{{ createResult.title }}</p>
            <p class="result-body">{{ createResult.body }}</p>
            <div v-if="createResult.invitationUrl" class="result-actions">
              <code>{{ createResult.invitationUrl }}</code>
              <button class="copy-btn" @click="copyText(createResult.invitationUrl)" :aria-label="t('ws_token_copy')">{{ t('ws_token_copy') }}</button>
            </div>
          </div>
          <button class="result-dismiss" type="button" @click="createResult = null" :aria-label="t('dismiss')">&times;</button>
        </div>

        <div class="search-bar">
          <label for="workspace-search" class="sr-only">{{ t('admin_search') }}</label>
          <input
            id="workspace-search"
            v-model="searchQuery"
            type="search"
            :placeholder="t('admin_search_ph')"
            class="search-input"
          />
        </div>

        <div v-if="loading" class="skeleton-shell" role="status" aria-live="polite" :aria-label="t('loading')">
          <div class="skeleton-list">
            <div class="skeleton-card-block"><SkeletonBlock h="16px" width="40%" /><SkeletonBlock h="12px" width="70%" /><SkeletonBlock h="12px" width="55%" /><SkeletonBlock h="34px" width="120px" /></div>
            <div class="skeleton-card-block"><SkeletonBlock h="16px" width="35%" /><SkeletonBlock h="12px" width="65%" /><SkeletonBlock h="12px" width="50%" /><SkeletonBlock h="34px" width="120px" /></div>
            <div class="skeleton-card-block"><SkeletonBlock h="16px" width="45%" /><SkeletonBlock h="12px" width="60%" /><SkeletonBlock h="12px" width="45%" /><SkeletonBlock h="34px" width="120px" /></div>
          </div>
        </div>

        <div v-else-if="items.length === 0" class="empty-state">
          <div class="empty-icon" aria-hidden="true">
            <svg width="40" height="40" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5"><path d="M3 7v10a2 2 0 002 2h14a2 2 0 002-2V9a2 2 0 00-2-2h-6l-2-2H5a2 2 0 00-2 2z"/></svg>
          </div>
          <p class="empty-title">{{ t('no_workspaces_admin') }}</p>
          <p class="empty-body">{{ t('no_workspaces_admin_hint') }}</p>
        </div>

        <div v-else-if="filteredItems.length === 0 && searchQuery" class="empty-state">
          <div class="empty-icon" aria-hidden="true">
            <svg width="40" height="40" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5"><circle cx="11" cy="11" r="8"/><path d="m21 21-4.35-4.35"/></svg>
          </div>
          <p class="empty-title">{{ t('no_results') }}</p>
          <p class="empty-body">{{ t('no_results_hint') }}</p>
        </div>

        <div v-else class="workspace-admin-list">
          <WorkspaceCard
            v-for="item in filteredItems"
            :key="item.workspace.workspace_id"
            :workspace="item.workspace"
            :workspace-admin="item.workspace_admin"
            :has-pending-invitation="item._hasPendingInvitation"
            :invitation-url="item._invitationUrl"
            variant="primary"
            @invite="onCardInvite"
            @update="onCardUpdate"
            @delete="requestDelete"
            @copy="copyText"
          />
        </div>
      </section>

      <ConfirmDialog
        :open="showConfirmDelete"
        :title="t('admin_delete_submit')"
        :message="t('confirm_delete')"
        :confirm-label="t('confirm_delete_btn')"
        :cancel-label="t('confirm_cancel')"
        :resource-name="items.find(i => i.workspace.slug === confirmDeleteSlug)?.workspace.name"
        :require-typed-value="confirmDeleteSlug ?? undefined"
        :typed-prompt="confirmDeleteSlug ? t('confirm_type_workspace_slug', { slug: confirmDeleteSlug }) : ''"
        @confirm="handleConfirmDelete"
        @cancel="handleCancelDelete"
      />
    </main>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted } from 'vue'
import { RouterLink } from 'vue-router'
import ManagedNav from '../components/ManagedNav.vue'
import ConfirmDialog from '../components/ConfirmDialog.vue'
import SkeletonBlock from '../components/SkeletonBlock.vue'
import { useManagedAuth } from '../composables/useManagedAuth'
import { useToast } from '../composables/useToast'
import { useManagedI18n } from '../i18n'
import {
  fetchAdminWorkspaces,
  createWorkspace,
  updateWorkspace,
  deleteWorkspace,
  inviteWorkspaceAdmin,
  type Workspace,
  type WorkspaceMembership,
  type Invitation,
} from '../api/managed'
import { getApiErrorMessage } from '../api/client'
import WorkspaceCard from '../components/WorkspaceCard.vue'
import CreateWorkspaceForm from '../components/CreateWorkspaceForm.vue'

interface AdminItem {
  workspace: Workspace
  workspace_admin: WorkspaceMembership | null
  invitations: Invitation[]
  _hasPendingInvitation: boolean
  _invitationUrl: string | null
}

interface CreateResultState {
  title: string
  body: string
  invitationUrl: string | null
}

const { requireRole, user } = useManagedAuth()
const { t } = useManagedI18n()
const toast = useToast()

const loading = ref(true)
const creating = ref(false)
const items = ref<AdminItem[]>([])
const createResult = ref<CreateResultState | null>(null)
const confirmDeleteSlug = ref<string | null>(null)
const showConfirmDelete = ref(false)
const searchQuery = ref('')
const createFormRef = ref<InstanceType<typeof CreateWorkspaceForm> | null>(null)

const filteredItems = computed(() => {
  if (!searchQuery.value.trim()) return items.value
  const q = searchQuery.value.toLowerCase()
  return items.value.filter(item =>
    item.workspace.name.toLowerCase().includes(q) ||
    item.workspace.slug.toLowerCase().includes(q) ||
    item.workspace_admin?.email?.toLowerCase().includes(q)
  )
})

async function loadData() {
  const data = await fetchAdminWorkspaces()
  items.value = data.workspaces.map(w => ({
    ...w,
    _hasPendingInvitation: w.invitations.some(i => i.status === 'pending'),
    _invitationUrl: null,
  }))
}

async function handleCreate(payload: { name: string; admin_email: string }) {
  const name = payload.name.trim()
  if (!name) return
  creating.value = true
  createResult.value = null
  try {
    const adminEmail =
      payload.admin_email.trim().toLowerCase() || user.value?.email?.toLowerCase() || undefined
    const result = await createWorkspace({ name, admin_email: adminEmail })
    createFormRef.value?.reset()
    await loadData()
    if (result.admin_assignment === 'invited' && result.invitation_url) {
      createResult.value = {
        title: t('dash_created_invite_title'),
        body: t('dash_created_invite_body'),
        invitationUrl: result.invitation_url,
      }
    }
  } catch (err) {
    toast.show(getApiErrorMessage(err), 'error')
  } finally {
    creating.value = false
  }
}

function findItem(slug: string): AdminItem | undefined {
  return items.value.find(item => item.workspace.slug === slug)
}

async function onCardInvite(slug: string, email: string) {
  const item = findItem(slug)
  if (!item) return
  try {
    const result = await inviteWorkspaceAdmin(slug, email)
    item._invitationUrl = result.invitation_url
    item._hasPendingInvitation = true
    toast.show(t('invitation_created_title'), 'success')
  } catch (err) {
    toast.show(getApiErrorMessage(err), 'error')
  }
}

async function onCardUpdate(slug: string, data: { name?: string; status?: string }) {
  if (!data.name && !data.status) return
  try {
    await updateWorkspace(slug, data)
    toast.show(t('admin_update_submit') + ' ✓', 'success')
    await loadData()
  } catch (err) {
    toast.show(getApiErrorMessage(err), 'error')
  }
}

function requestDelete(slug: string) {
  confirmDeleteSlug.value = slug
  showConfirmDelete.value = true
}

async function handleConfirmDelete() {
  const slug = confirmDeleteSlug.value
  showConfirmDelete.value = false
  confirmDeleteSlug.value = null
  if (!slug) return
  try {
    await deleteWorkspace(slug)
    toast.show(t('admin_delete_submit') + ' ✓', 'success')
    await loadData()
  } catch (err) {
    toast.show(getApiErrorMessage(err), 'error')
  }
}

function handleCancelDelete() {
  showConfirmDelete.value = false
  confirmDeleteSlug.value = null
}

async function copyText(text: string) {
  try {
    await navigator.clipboard.writeText(text)
  } catch {
    prompt(t('copy_failed'), text)
  }
}

onMounted(async () => {
  const currentUser = await requireRole('instance_admin')
  if (!currentUser) return
  try {
    await loadData()
  } finally {
    loading.value = false
  }
})
</script>

<style scoped>
.panel {
  max-width: 1140px;
  margin: 32px auto;
  padding: 28px;
}
.panel-header {
  margin-bottom: 28px;
  display: flex;
  justify-content: space-between;
  align-items: flex-start;
  gap: 16px;
  flex-wrap: wrap;
}
.panel-kicker {
  font-size: 0.72rem;
  text-transform: uppercase;
  letter-spacing: 0.15em;
  color: var(--accent);
  font-weight: 600;
}
.panel-title {
  font-size: 1.5rem;
  color: var(--text-1);
  margin: 4px 0 6px;
}
.panel-sub {
  color: var(--text-2);
  font-size: 0.9rem;
  margin: 0;
  line-height: 1.5;
}
.back-link {
  color: var(--text-2);
  text-decoration: none;
  font-size: 0.84rem;
  padding: 6px 12px;
  border-radius: 8px;
  border: 1px solid var(--border);
  white-space: nowrap;
  transition: border-color 0.15s, color 0.15s;
}
.back-link:hover {
  border-color: var(--text-3);
  color: var(--text-1);
}
.back-link:focus-visible {
  outline: none;
  border-color: var(--accent);
  box-shadow: 0 0 0 3px var(--accent-subtle);
}

/* ── Fieldset ── */
.compact-fieldset {
  border: 1px solid var(--glass-border);
  border-radius: var(--radius-xl);
  padding: 20px;
  margin-bottom: 20px;
  background: var(--glass-bg);
  backdrop-filter: var(--glass-blur);
  -webkit-backdrop-filter: var(--glass-blur);
}
.compact-fieldset legend {
  font-size: 0.85rem;
  color: var(--text-1);
  font-weight: 600;
  padding: 0 8px;
}
.create-row {
  gap: 10px;
  margin-top: 8px;
}

/* ── Inline Forms ── */
.inline-form {
  display: flex;
  gap: 8px;
  align-items: center;
  flex-wrap: wrap;
}
.inline-form input,
.inline-form select {
  padding: 8px 12px;
  border: 1px solid var(--border);
  border-radius: 8px;
  background: var(--surface-0);
  color: var(--text-1);
  font-size: 0.85rem;
  transition: border-color 0.15s;
}
.inline-form input:focus,
.inline-form select:focus {
  border-color: var(--accent);
  box-shadow: 0 0 0 3px var(--accent-subtle);
  outline: none;
}
.inline-form button {
  padding: 9px 15px;
  background: var(--accent);
  color: var(--button-accent-text);
  border: none;
  border-radius: var(--radius-md);
  font-weight: 600;
  cursor: pointer;
  font-size: 0.85rem;
  display: inline-flex;
  align-items: center;
  gap: 6px;
  transition: all var(--transition-spring);
  position: relative;
  overflow: hidden;
}
.inline-form button::after {
  content: '';
  position: absolute;
  inset: 0;
  background: linear-gradient(135deg, rgba(255,255,255,0.2), transparent);
  opacity: 0;
  transition: opacity var(--transition-fast);
}
.inline-form button:hover::after {
  opacity: 1;
}
.inline-form button:hover {
  transform: translateY(-1px);
  box-shadow: 0 4px 16px var(--accent-glow);
}
.inline-form button:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}

/* ── Search Bar ── */
.search-bar {
  margin-bottom: 18px;
}
.search-input {
  padding: 12px 16px;
  border: 1px solid var(--glass-border);
  border-radius: var(--radius-md);
  background: var(--glass-bg);
  backdrop-filter: var(--glass-blur);
  -webkit-backdrop-filter: var(--glass-blur);
  color: var(--text-1);
  font-size: 0.92rem;
  width: 100%;
  max-width: 380px;
  transition: all var(--transition-fast);
}
.search-input:hover {
  border-color: var(--accent-glow);
}
.search-input:focus {
  border-color: var(--accent);
  box-shadow: 0 0 0 3px var(--accent-subtle);
  outline: none;
}
.search-input::placeholder {
  color: var(--text-3);
}

/* ── Result Banner ── */
.result-banner {
  padding: 18px 20px;
  display: flex;
  gap: 16px;
  align-items: flex-start;
  background: var(--glass-bg);
  backdrop-filter: var(--glass-blur);
  -webkit-backdrop-filter: var(--glass-blur);
  border: 1px solid var(--glass-border);
  border-left: 3px solid var(--accent);
  border-radius: var(--radius-lg);
  margin-bottom: 20px;
  animation: slide-in var(--transition-spring);
}
@keyframes slide-in {
  from { opacity: 0; transform: translateY(-8px); }
  to { opacity: 1; transform: translateY(0); }
}
.result-icon {
  flex-shrink: 0;
  width: 32px;
  height: 32px;
  display: grid;
  place-items: center;
  border-radius: 50%;
  background: var(--accent-subtle);
  color: var(--accent);
  font-weight: 700;
}
.result-title {
  margin: 0 0 4px;
  color: var(--text-1);
  font-weight: 600;
  font-size: 0.94rem;
}
.result-body {
  margin: 0;
  color: var(--text-2);
  font-size: 0.86rem;
}
.result-actions {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 10px;
  margin-top: 12px;
}
.result-actions code {
  display: block;
  padding: 10px 12px;
  border-radius: var(--radius-md);
  background: var(--surface-2);
  color: var(--text-1);
  word-break: break-all;
  font-size: 0.82rem;
  border: 1px solid var(--glass-border);
}
.result-dismiss {
  margin-left: auto;
  background: none;
  border: none;
  color: var(--text-3);
  font-size: 1.2rem;
  cursor: pointer;
  padding: 4px 8px;
  border-radius: var(--radius-sm);
  line-height: 1;
  transition: all var(--transition-fast);
}
.result-dismiss:hover {
  background: var(--surface-2);
  color: var(--text-1);
}

/* ── Empty State ── */
.empty-state {
  text-align: center;
  padding: 44px 28px;
  color: var(--text-3);
  background: var(--glass-bg);
  backdrop-filter: var(--glass-blur);
  -webkit-backdrop-filter: var(--glass-blur);
  border: 1px dashed var(--glass-border);
  border-radius: var(--radius-xl);
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 10px;
}
.empty-icon {
  color: var(--text-3);
  opacity: 0.5;
  margin-bottom: 6px;
}
.empty-title {
  font-size: 0.98rem;
  color: var(--text-2);
  margin: 0;
  font-weight: 600;
}
.empty-body {
  font-size: 0.84rem;
  color: var(--text-3);
  margin: 0;
  max-width: 320px;
  line-height: 1.5;
}

/* ── Workspace Cards ── */
.workspace-admin-list {
  display: flex;
  flex-direction: column;
  gap: 14px;
}
.workspace-admin-card {
  background: var(--glass-bg);
  backdrop-filter: var(--glass-blur);
  -webkit-backdrop-filter: var(--glass-blur);
  border: 1px solid var(--glass-border);
  border-radius: var(--radius-xl);
  padding: 20px 22px;
  transition: all var(--transition-spring);
  animation: card-enter var(--transition-spring) backwards;
}
@keyframes card-enter {
  from { opacity: 0; transform: translateY(10px); }
  to { opacity: 1; transform: translateY(0); }
}
.workspace-admin-card:hover {
  border-color: var(--accent-glow);
  box-shadow: var(--shadow-md), 0 0 35px var(--accent-subtle);
  transform: translateY(-2px);
}
.workspace-admin-card:focus-visible {
  outline: none;
  border-color: var(--accent);
  box-shadow: 0 0 0 3px var(--accent-subtle);
}
.workspace-card-head {
  display: flex;
  justify-content: space-between;
  align-items: flex-start;
  gap: 14px;
  margin-bottom: 12px;
}
.workspace-card-title {
  font-size: 1.08rem;
  font-weight: 700;
  color: var(--text-1);
  margin-bottom: 8px;
  letter-spacing: -0.01em;
}
.workspace-card-meta {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
}

/* ── Pills ── */
.pill {
  font-size: 0.72rem;
  padding: 4px 10px;
  background: var(--surface-2);
  border-radius: 999px;
  color: var(--text-2);
  font-weight: 500;
  border: 1px solid var(--glass-border);
}
.pill-status-active {
  color: var(--success);
  background: var(--success-subtle);
  border-color: var(--success-glow);
}
.pill-status-disabled {
  color: var(--danger);
  background: var(--danger-subtle);
  border-color: var(--danger-glow);
}
.pill-pending {
  color: var(--warning);
  background: var(--warning-subtle);
  border-color: var(--warning-glow);
}
.pill-icon {
  font-size: 0.65rem;
  margin-right: 3px;
}

/* ── Details/Manage ── */
.workspace-details {
  margin-top: 6px;
}
.details-summary {
  font-size: 0.84rem;
  color: var(--text-2);
  cursor: pointer;
  padding: 8px 0;
  user-select: none;
  list-style: none;
  display: flex;
  align-items: center;
  gap: 8px;
  transition: color var(--transition-fast);
}
.details-summary:hover {
  color: var(--accent);
}
.details-summary::before {
  content: '\25B6';
  font-size: 0.6rem;
  transition: transform var(--transition-fast);
  color: var(--text-3);
}
details[open] > .details-summary::before {
  transform: rotate(90deg);
}
details[open] > .details-summary {
  color: var(--accent);
}
.details-summary:focus-visible {
  outline: 2px solid var(--accent);
  outline-offset: 2px;
  border-radius: var(--radius-sm);
}
.details-body {
  padding: 14px 0 6px;
  display: flex;
  flex-direction: column;
  gap: 14px;
  border-top: 1px solid var(--glass-border);
  margin-top: 8px;
}

.workspace-compact-row,
.workspace-inline-actions {
  display: flex;
  align-items: center;
  gap: 10px;
  flex-wrap: wrap;
}
.workspace-inline-actions {
  justify-content: space-between;
}

/* ── Invite Result ── */
.invite-result {
  margin-top: 14px;
  display: grid;
  gap: 10px;
  padding: 14px;
  background: var(--surface-0);
  border-radius: var(--radius-md);
  border: 1px solid var(--glass-border);
}
.invite-result-label {
  margin: 0;
  color: var(--text-1);
  font-weight: 600;
  font-size: 0.86rem;
}
.invite-result code {
  font-size: 0.78rem;
  word-break: break-all;
  display: block;
  padding: 10px 12px;
  background: var(--surface-2);
  border-radius: var(--radius-sm);
  border: 1px solid var(--glass-border);
}

/* ── Buttons ── */
.secondary-button {
  padding: 9px 15px;
  background: var(--glass-bg);
  backdrop-filter: var(--glass-blur);
  -webkit-backdrop-filter: var(--glass-blur);
  color: var(--text-1);
  border: 1px solid var(--glass-border);
  border-radius: var(--radius-md);
  text-decoration: none;
  font-size: 0.84rem;
  cursor: pointer;
  font-weight: 500;
  transition: all var(--transition-fast);
  white-space: nowrap;
}
.secondary-button:hover {
  border-color: var(--accent);
  background: var(--accent-subtle);
  color: var(--accent);
  transform: translateY(-1px);
}
.danger {
  padding: 9px 15px;
  background: var(--danger);
  color: var(--button-danger-text);
  border: none;
  border-radius: var(--radius-md);
  cursor: pointer;
  font-size: 0.84rem;
  font-weight: 600;
  transition: all var(--transition-fast);
  box-shadow: 0 4px 12px var(--danger-subtle);
}
.danger:hover {
  opacity: 0.9;
  transform: translateY(-1px);
  box-shadow: 0 6px 20px var(--danger-glow);
}
.copy-btn {
  padding: 7px 13px;
  background: var(--surface-1);
  border: 1px solid var(--glass-border);
  border-radius: var(--radius-md);
  cursor: pointer;
  font-size: 0.8rem;
  color: var(--text-1);
  transition: all var(--transition-fast);
}
.copy-btn:hover {
  border-color: var(--accent);
  background: var(--accent-subtle);
  color: var(--accent);
}

/* ── Focus States ── */
.secondary-button:focus-visible,
.danger:focus-visible,
.copy-btn:focus-visible,
.inline-form button:focus-visible,
.inline-form input:focus-visible,
.inline-form select:focus-visible {
  outline: none;
  border-color: var(--accent);
  box-shadow: 0 0 0 3px var(--accent-subtle);
}

/* ── Spinner ── */
.spinner {
  width: 16px;
  height: 16px;
  border: 2px solid currentColor;
  border-top-color: transparent;
  border-radius: 50%;
  animation: spin 0.6s linear infinite;
  display: inline-block;
}
@keyframes spin {
  to { transform: rotate(360deg); }
}

/* ── Screen reader only ── */
.sr-only {
  position: absolute;
  width: 1px;
  height: 1px;
  padding: 0;
  margin: -1px;
  overflow: hidden;
  clip: rect(0, 0, 0, 0);
  white-space: nowrap;
  border: 0;
}

/* ── Skeleton Loading ── */
.skeleton-shell {
  display: flex;
  flex-direction: column;
  gap: 14px;
}
.skeleton-list {
  display: flex;
  flex-direction: column;
  gap: 14px;
}
.skeleton-card-block {
  display: flex;
  flex-direction: column;
  gap: 10px;
  padding: 20px 22px;
  background: var(--glass-bg);
  backdrop-filter: var(--glass-blur);
  -webkit-backdrop-filter: var(--glass-blur);
  border: 1px solid var(--glass-border);
  border-radius: var(--radius-xl);
}

/* ── Reduced motion ── */
@media (prefers-reduced-motion: reduce) {
  .spinner {
    animation: none;
    border-top-color: currentColor;
    opacity: 0.5;
  }
  * {
    transition-duration: 0s !important;
    animation-duration: 0s !important;
  }
}

@media (max-width: 700px) {
  .panel {
    padding: 18px;
  }
  .workspace-card-head,
  .workspace-inline-actions {
    flex-direction: column;
    align-items: stretch;
  }
  .workspace-card-head .secondary-button {
    text-align: center;
  }
  .create-row {
    flex-direction: column;
  }
  .create-row input {
    width: 100%;
  }
}
</style>
