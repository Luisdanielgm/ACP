<template>
  <div>
    <header>
      <ManagedNav />
    </header>
    <main id="main-content">
      <section class="hero">
        <span class="hero-kicker">{{ t('dash_kicker') }}</span>
        <h1>{{ isInstanceAdmin ? t('dash_instance_title') : t('dash_workspace_title') }}</h1>
        <p class="hero-body">
          {{ isInstanceAdmin ? t('dash_instance_body') : t('dash_workspace_body') }}
        </p>
        <div v-if="!isInstanceAdmin" class="hero-actions">
          <RouterLink to="/managed/ui/workspaces" class="primary-button">{{ t('dash_open_workspaces') }}</RouterLink>
        </div>
      </section>

      <section v-if="isInstanceAdmin" class="panel dashboard-shell">
        <div class="panel-header">
          <div>
            <span class="panel-kicker">{{ t('admin_kicker') }}</span>
            <h2 class="panel-title">{{ t('dash_admin_surface_title') }}</h2>
            <p class="panel-sub">{{ t('dash_admin_surface_body') }}</p>
          </div>
        </div>

        <CreateWorkspaceForm
          ref="createFormRef"
          layout="expanded"
          :submitting="submittingCreate"
          :current-user-email="user?.email ?? ''"
          @submit="handleCreate"
        />

        <div v-if="lastCreateResult" class="result-banner" role="alert" aria-live="polite">
          <div class="result-icon" aria-hidden="true">&#10003;</div>
          <div>
            <p class="result-title">{{ lastCreateResult.title }}</p>
            <p class="result-body">{{ lastCreateResult.body }}</p>
            <div class="result-actions">
              <RouterLink v-if="lastCreateResult.workspaceSlug" :to="`/managed/ui/workspaces/${encodeURIComponent(lastCreateResult.workspaceSlug)}`" class="secondary-button">
                {{ t('admin_open_workspace') }}
              </RouterLink>
              <template v-if="lastCreateResult.invitationUrl">
                <div class="invite-url-block">
                  <code>{{ lastCreateResult.invitationUrl }}</code>
                  <button class="secondary-button copy-btn" @click="copyText(lastCreateResult.invitationUrl)" :aria-label="t('ws_token_copy')">
                    {{ t('ws_token_copy') }}
                  </button>
                </div>
              </template>
            </div>
          </div>
          <button class="result-dismiss" @click="lastCreateResult = null" :aria-label="t('dismiss')">&times;</button>
        </div>

        <div v-if="loading" class="skeleton-shell" role="status" aria-live="polite" :aria-label="t('loading')">
          <div class="skeleton-summary">
            <div class="skeleton-card"><SkeletonBlock h="18px" width="60%" /><SkeletonBlock h="32px" width="30%" /><SkeletonBlock h="12px" width="80%" /></div>
            <div class="skeleton-card"><SkeletonBlock h="18px" width="55%" /><SkeletonBlock h="32px" width="25%" /><SkeletonBlock h="12px" width="75%" /></div>
            <div class="skeleton-card"><SkeletonBlock h="18px" width="50%" /><SkeletonBlock h="32px" width="20%" /><SkeletonBlock h="12px" width="70%" /></div>
          </div>
          <div class="skeleton-columns">
            <div class="skeleton-col">
              <SkeletonBlock h="10px" width="80px" /><SkeletonBlock h="18px" width="50%" /><SkeletonBlock h="12px" width="70%" />
              <div class="skeleton-card-block"><SkeletonBlock h="16px" width="40%" /><SkeletonBlock h="12px" width="60%" /><SkeletonBlock h="12px" width="45%" /><SkeletonBlock h="34px" width="120px" /></div>
              <div class="skeleton-card-block"><SkeletonBlock h="16px" width="35%" /><SkeletonBlock h="12px" width="55%" /><SkeletonBlock h="12px" width="50%" /><SkeletonBlock h="34px" width="120px" /></div>
            </div>
            <div class="skeleton-col">
              <SkeletonBlock h="10px" width="70px" /><SkeletonBlock h="18px" width="45%" /><SkeletonBlock h="12px" width="65%" />
              <div class="skeleton-card-block dashed"><SkeletonBlock h="14px" width="50%" /><SkeletonBlock h="30px" width="80px" /></div>
            </div>
          </div>
        </div>

        <template v-else>
          <div class="dashboard-summary">
            <article class="summary-card summary-card-accent">
              <span class="summary-label">{{ t('dash_stat_ready') }}</span>
              <strong class="summary-value">{{ myAdminItems.length }}</strong>
              <span class="summary-note">{{ t('dash_stat_ready_body') }}</span>
            </article>
            <article class="summary-card">
              <span class="summary-label">{{ t('dash_stat_global') }}</span>
              <strong class="summary-value">{{ otherAdminItems.length }}</strong>
              <span class="summary-note">{{ t('dash_stat_global_body') }}</span>
            </article>
            <article class="summary-card">
              <span class="summary-label">{{ t('dash_stat_total') }}</span>
              <strong class="summary-value">{{ items.length }}</strong>
              <span class="summary-note">{{ t('dash_stat_total_body') }}</span>
            </article>
          </div>

          <div class="workspace-columns">
            <section class="workspace-column primary-column" aria-labelledby="my-ws-heading">
              <div class="section-head">
                <span class="section-chip section-chip-accent">{{ t('dash_primary_section') }}</span>
                <h3 id="my-ws-heading">{{ t('dash_my_workspaces') }}</h3>
                <p>{{ t('dash_my_workspaces_body') }}</p>
              </div>

              <div v-if="myAdminItems.length === 0" class="empty-state">
                <div class="empty-icon" aria-hidden="true">
                  <svg width="40" height="40" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5"><path d="M3 7v10a2 2 0 002 2h14a2 2 0 002-2V9a2 2 0 00-2-2h-6l-2-2H5a2 2 0 00-2 2z"/></svg>
                </div>
                <p class="empty-title">{{ t('dash_my_workspaces_empty') }}</p>
                <p class="empty-body">{{ t('dash_my_workspaces_empty_hint') }}</p>
              </div>

              <div v-else class="workspace-admin-list">
                <WorkspaceCard
                  v-for="item in myAdminItems"
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

            <section class="workspace-column secondary-column" aria-labelledby="other-ws-heading">
              <div class="section-head">
                <span class="section-chip">{{ t('dash_secondary_section') }}</span>
                <h3 id="other-ws-heading">{{ t('dash_other_workspaces') }}</h3>
                <p>{{ t('dash_other_workspaces_body') }}</p>
              </div>

              <div v-if="otherAdminItems.length === 0" class="empty-state compact">
                <p class="empty-title">{{ t('dash_other_workspaces_empty') }}</p>
              </div>

              <div v-else class="secondary-overview">
                <p>
                  <strong>{{ otherAdminItems.length }}</strong>
                  {{ t('dash_other_collapsed_summary') }}
                </p>
                <button
                  class="secondary-toggle"
                  @click="showOtherWorkspaces = !showOtherWorkspaces"
                  :aria-expanded="showOtherWorkspaces"
                  aria-controls="other-ws-list"
                >
                  {{ showOtherWorkspaces ? t('dash_other_hide') : t('dash_other_show') }}
                </button>
              </div>

              <div
                v-if="otherAdminItems.length > 0 && showOtherWorkspaces"
                id="other-ws-list"
                class="workspace-admin-list"
                role="region"
                :aria-label="t('dash_other_workspaces')"
              >
                <WorkspaceCard
                  v-for="item in otherAdminItems"
                  :key="item.workspace.workspace_id"
                  :workspace="item.workspace"
                  :workspace-admin="item.workspace_admin"
                  :has-pending-invitation="item._hasPendingInvitation"
                  :invitation-url="item._invitationUrl"
                  variant="secondary"
                  @invite="onCardInvite"
                  @update="onCardUpdate"
                  @delete="requestDelete"
                  @copy="copyText"
                />
              </div>
            </section>
          </div>
        </template>
      </section>

      <ConfirmDialog
        :open="showConfirmDelete"
        :title="t('admin_delete_submit')"
        :message="t('confirm_delete')"
        :confirm-label="t('confirm_delete_btn')"
        :cancel-label="t('confirm_cancel')"
        :require-typed-value="confirmDeleteSlug ?? undefined"
        :typed-prompt="confirmDeleteSlug ? t('confirm_type_workspace_slug', { slug: confirmDeleteSlug }) : ''"
        @confirm="handleConfirmDelete"
        @cancel="handleCancelDelete"
      />
    </main>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { RouterLink, useRouter } from 'vue-router'
import ManagedNav from '../components/ManagedNav.vue'
import ConfirmDialog from '../components/ConfirmDialog.vue'
import SkeletonBlock from '../components/SkeletonBlock.vue'
import WorkspaceCard from '../components/WorkspaceCard.vue'
import CreateWorkspaceForm from '../components/CreateWorkspaceForm.vue'
import { useManagedAuth } from '../composables/useManagedAuth'
import { useToast } from '../composables/useToast'
import { useManagedI18n } from '../i18n'
import {
  createWorkspace,
  deleteWorkspace,
  fetchAdminWorkspaces,
  fetchMyWorkspaces,
  inviteWorkspaceAdmin,
  updateWorkspace,
  type Invitation,
  type Workspace,
  type WorkspaceMembership,
} from '../api/managed'

interface AdminItem {
  workspace: Workspace
  workspace_admin: WorkspaceMembership | null
  invitations: Invitation[]
  // Only _hasPendingInvitation and _invitationUrl remain on the parent — the
  // per-card form state moved into <WorkspaceCard>.
  _hasPendingInvitation: boolean
  _invitationUrl: string | null
}

interface MyWorkspaceItem {
  workspace: Workspace
  membership: WorkspaceMembership
  sessions: { session_id: string }[]
}

interface CreateResultState {
  title: string
  body: string
  invitationUrl: string | null
  workspaceSlug: string | null
}

const { isInstanceAdmin, requireAuth, user } = useManagedAuth()
const { t } = useManagedI18n()
const toast = useToast()
const router = useRouter()

const loading = ref(true)
const submittingCreate = ref(false)
const items = ref<AdminItem[]>([])
const ownWorkspaces = ref<MyWorkspaceItem[]>([])
const lastCreateResult = ref<CreateResultState | null>(null)
const showOtherWorkspaces = ref(false)
const confirmDeleteSlug = ref<string | null>(null)
const showConfirmDelete = ref(false)
const createFormRef = ref<InstanceType<typeof CreateWorkspaceForm> | null>(null)

const myWorkspaceIds = computed(() => new Set(ownWorkspaces.value.map(item => item.workspace.workspace_id)))
const myAdminItems = computed(() =>
  items.value
    .filter(item => myWorkspaceIds.value.has(item.workspace.workspace_id))
    .slice()
    .sort((left, right) => left.workspace.name.localeCompare(right.workspace.name)),
)
const otherAdminItems = computed(() =>
  items.value
    .filter(item => !myWorkspaceIds.value.has(item.workspace.workspace_id))
    .slice()
    .sort((left, right) => left.workspace.name.localeCompare(right.workspace.name)),
)

function hydrateAdminItems(
  workspaces: { workspace: Workspace; workspace_admin: WorkspaceMembership | null; invitations: Invitation[] }[],
) {
  items.value = workspaces.map(item => ({
    ...item,
    _hasPendingInvitation: item.invitations.some(invitation => invitation.status === 'pending'),
    _invitationUrl: null,
  }))
}

async function loadData() {
  const myData = await fetchMyWorkspaces()
  ownWorkspaces.value = myData.workspaces
  if (!isInstanceAdmin.value) return
  const adminData = await fetchAdminWorkspaces()
  hydrateAdminItems(adminData.workspaces)
}

async function redirectWorkspaceAdminSurface() {
  if (ownWorkspaces.value.length === 1) {
    await router.replace(`/managed/ui/workspaces/${encodeURIComponent(ownWorkspaces.value[0].workspace.slug)}`)
    return
  }
  await router.replace('/managed/ui/workspaces')
}

async function handleCreate(payload: { name: string; admin_email: string }) {
  const name = payload.name.trim()
  const adminEmail = payload.admin_email.trim().toLowerCase()
  if (!name || !adminEmail) return
  submittingCreate.value = true
  lastCreateResult.value = null
  try {
    const result = await createWorkspace({ name, admin_email: adminEmail })
    createFormRef.value?.reset()
    await loadData()
    if (result.admin_assignment === 'self_assigned') {
      await router.push(`/managed/ui/workspaces/${encodeURIComponent(result.workspace.slug)}`)
      return
    }
    if (result.admin_assignment === 'invited') {
      lastCreateResult.value = {
        title: t('dash_created_invite_title'),
        body: t('dash_created_invite_body'),
        invitationUrl: result.invitation_url,
        workspaceSlug: null,
      }
      return
    }
    lastCreateResult.value = {
      title: t('workspace_created_title'),
      body: t('dash_created_unassigned_body'),
      invitationUrl: null,
      workspaceSlug: null,
    }
  } finally {
    submittingCreate.value = false
  }
}

function findItem(slug: string): AdminItem | undefined {
  return items.value.find(item => item.workspace.slug === slug)
}

async function onCardInvite(slug: string, email: string) {
  const item = findItem(slug)
  if (!item) return
  const result = await inviteWorkspaceAdmin(slug, email)
  item._invitationUrl = result.invitation_url
  item._hasPendingInvitation = true
  toast.show(t('invitation_created_title'), 'success')
}

async function onCardUpdate(slug: string, data: { name?: string; status?: string }) {
  if (!data.name && !data.status) return
  await updateWorkspace(slug, data)
  toast.show(t('admin_update_submit') + ' ✓', 'success')
  await loadData()
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
  await deleteWorkspace(slug)
  toast.show(t('admin_delete_submit') + ' ✓', 'success')
  await loadData()
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
  const currentUser = await requireAuth()
  if (!currentUser) return
  try {
    await loadData()
    if (!isInstanceAdmin.value) {
      await redirectWorkspaceAdminSurface()
      return
    }
  } finally {
    loading.value = false
  }
})
</script>

<style scoped>
.hero {
  text-align: center;
  padding: 56px 24px 32px;
  position: relative;
  overflow: hidden;
}
.hero::before {
  content: '';
  position: absolute;
  top: -50%;
  left: 50%;
  transform: translateX(-50%);
  width: 600px;
  height: 600px;
  background: radial-gradient(circle, var(--accent-subtle) 0%, transparent 70%);
  pointer-events: none;
  animation: hero-glow 8s ease-in-out infinite;
}
@keyframes hero-glow {
  0%, 100% { opacity: 0.6; transform: translateX(-50%) scale(1); }
  50% { opacity: 1; transform: translateX(-50%) scale(1.1); }
}
.hero-kicker {
  font-size: 0.72rem;
  text-transform: uppercase;
  letter-spacing: 0.15em;
  color: var(--accent);
  font-weight: 600;
  position: relative;
}
.hero h1 {
  margin: 10px 0 14px;
  font-size: clamp(1.6rem, 4vw, 2.2rem);
  color: var(--text-1);
  line-height: 1.15;
  letter-spacing: -0.03em;
  font-weight: 800;
  position: relative;
  text-shadow: 0 2px 20px var(--accent-subtle);
}
.hero-body {
  max-width: 640px;
  margin: 0 auto;
  color: var(--text-2);
  font-size: 1rem;
  line-height: 1.6;
  position: relative;
}
.hero-actions {
  display: flex;
  justify-content: center;
  gap: 14px;
  flex-wrap: wrap;
  margin-top: 24px;
  position: relative;
}

.panel {
  max-width: 1140px;
  margin: 0 auto 32px;
  padding: 28px;
  position: relative;
}
.dashboard-shell {
  display: flex;
  flex-direction: column;
  gap: 24px;
}
.panel-header {
  display: flex;
  justify-content: space-between;
  gap: 16px;
}
.panel-kicker {
  font-size: 0.72rem;
  text-transform: uppercase;
  letter-spacing: 0.15em;
  color: var(--accent);
  font-weight: 600;
}
.panel-title {
  font-size: 1.4rem;
  color: var(--text-1);
  margin: 6px 0 8px;
  letter-spacing: -0.02em;
  font-weight: 700;
}
.panel-sub {
  color: var(--text-2);
  font-size: 0.92rem;
  margin: 0;
  line-height: 1.55;
}

/* ── Create Card ── */
.create-card,
.result-banner,
.workspace-admin-card,
.logout-panel {
  background: var(--glass-bg);
  backdrop-filter: var(--glass-blur);
  -webkit-backdrop-filter: var(--glass-blur);
  border: 1px solid var(--glass-border);
  border-radius: var(--radius-xl);
  transition: all var(--transition-spring);
}
.create-card:hover,
.workspace-admin-card:hover {
  border-color: var(--accent-glow);
  box-shadow: var(--shadow-md), 0 0 40px var(--accent-subtle);
  transform: translateY(-2px);
}
.create-card {
  display: grid;
  grid-template-columns: minmax(200px, 1fr) minmax(280px, 1.3fr);
  gap: 28px;
  padding: 26px;
}
.create-copy h3 {
  margin: 0 0 10px;
  color: var(--text-1);
  font-size: 1.1rem;
  font-weight: 700;
}
.create-copy p {
  margin: 0;
  color: var(--text-2);
  line-height: 1.6;
  font-size: 0.9rem;
}
.create-form {
  display: grid;
  gap: 14px;
}
.field {
  display: grid;
  gap: 6px;
}
.field label {
  color: var(--text-2);
  font-size: 0.84rem;
  font-weight: 500;
}
.create-form input,
.inline-form input,
.inline-form select {
  padding: 11px 14px;
  border: 1px solid var(--glass-border);
  border-radius: var(--radius-md);
  background: var(--surface-0);
  color: var(--text-1);
  font-size: 0.9rem;
  transition: all var(--transition-fast);
}
.create-form input:focus,
.inline-form input:focus,
.inline-form select:focus {
  border-color: var(--accent);
  box-shadow: 0 0 0 3px var(--accent-subtle);
  outline: none;
}
.create-hint {
  margin: 0;
  font-size: 0.82rem;
  color: var(--text-3);
  display: flex;
  align-items: center;
  gap: 8px;
}
.hint-icon {
  font-size: 1rem;
  color: var(--accent);
}

/* ── Result Banner ── */
.result-banner {
  padding: 20px 22px;
  display: flex;
  gap: 16px;
  align-items: flex-start;
  border-left: 3px solid var(--accent);
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
  font-size: 1rem;
}
.result-title {
  margin: 0 0 4px;
  color: var(--text-1);
  font-weight: 600;
  font-size: 0.95rem;
}
.result-body {
  margin: 0;
  color: var(--text-2);
  font-size: 0.88rem;
}
.result-actions {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 10px;
  margin-top: 12px;
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
.result-actions code,
.invite-result code,
.invite-url-block code {
  display: block;
  padding: 10px 12px;
  border-radius: var(--radius-md);
  background: var(--surface-2);
  color: var(--text-1);
  word-break: break-all;
  font-size: 0.82rem;
}
.invite-url-block {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  align-items: center;
}

/* ── Summary Cards ── */
.dashboard-summary {
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: 16px;
}
.summary-card {
  display: grid;
  gap: 8px;
  padding: 22px 24px;
  background: var(--glass-bg);
  backdrop-filter: var(--glass-blur);
  -webkit-backdrop-filter: var(--glass-blur);
  border: 1px solid var(--glass-border);
  border-radius: var(--radius-xl);
  transition: all var(--transition-spring);
  position: relative;
  overflow: hidden;
}
.summary-card::before {
  content: '';
  position: absolute;
  top: 0;
  left: 0;
  right: 0;
  height: 3px;
  background: linear-gradient(90deg, var(--accent), transparent);
  opacity: 0;
  transition: opacity var(--transition-fast);
}
.summary-card:hover::before {
  opacity: 1;
}
.summary-card:hover {
  transform: translateY(-3px);
  box-shadow: var(--shadow-lg), 0 0 40px var(--accent-subtle);
  border-color: var(--accent-glow);
}
.summary-card-accent {
  background: var(--glass-bg), linear-gradient(135deg, var(--accent-subtle) 0%, transparent 60%);
  border-color: var(--accent-glow);
}
.summary-card-accent::before {
  opacity: 1;
}
.summary-label {
  font-size: 0.72rem;
  text-transform: uppercase;
  letter-spacing: 0.12em;
  color: var(--text-3);
  font-weight: 600;
}
.summary-value {
  font-size: 2.2rem;
  line-height: 1;
  color: var(--text-1);
  font-weight: 800;
  letter-spacing: -0.03em;
}
.summary-note {
  font-size: 0.86rem;
  color: var(--text-2);
  line-height: 1.4;
}

/* ── Workspace Columns ── */
.workspace-columns {
  display: grid;
  grid-template-columns: minmax(0, 1.5fr) minmax(280px, 0.95fr);
  gap: 24px;
  align-items: start;
}
.workspace-column {
  display: flex;
  flex-direction: column;
  gap: 16px;
}
.section-chip {
  display: inline-flex;
  width: fit-content;
  margin-bottom: 10px;
  padding: 5px 12px;
  border-radius: 999px;
  background: var(--accent-subtle);
  color: var(--accent);
  font-size: 0.7rem;
  text-transform: uppercase;
  letter-spacing: 0.1em;
  font-weight: 600;
  border: 1px solid var(--accent-glow);
}
.section-head h3 {
  margin: 0 0 6px;
  color: var(--text-1);
  font-size: 1.15rem;
  font-weight: 700;
}
.section-head p {
  margin: 0;
  color: var(--text-2);
  font-size: 0.9rem;
  line-height: 1.5;
}

/* ── Empty States ── */
.loading,
.empty-state {
  text-align: center;
  padding: 40px 28px;
  color: var(--text-3);
}
.loading {
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 10px;
  font-size: 0.9rem;
}
.empty-state {
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
  max-width: 300px;
  line-height: 1.5;
}

/* ── Workspace Cards ── */
.workspace-admin-list {
  display: flex;
  flex-direction: column;
  gap: 14px;
}
.workspace-admin-card {
  padding: 20px 22px;
  animation: card-enter var(--transition-spring) backwards;
}
@keyframes card-enter {
  from { opacity: 0; transform: translateY(12px); }
  to { opacity: 1; transform: translateY(0); }
}
.workspace-admin-card:nth-child(1) { animation-delay: 0ms; }
.workspace-admin-card:nth-child(2) { animation-delay: 60ms; }
.workspace-admin-card:nth-child(3) { animation-delay: 120ms; }
.workspace-admin-card:nth-child(4) { animation-delay: 180ms; }
.workspace-admin-card:nth-child(5) { animation-delay: 240ms; }
.workspace-admin-card:focus-visible {
  outline: none;
  border-color: var(--accent);
  box-shadow: 0 0 0 3px var(--accent-subtle);
}
.secondary-card {
  background: var(--glass-bg);
}
.secondary-overview {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  padding: 16px 20px;
  background: var(--glass-bg);
  backdrop-filter: var(--glass-blur);
  -webkit-backdrop-filter: var(--glass-blur);
  border: 1px dashed var(--glass-border);
  border-radius: var(--radius-lg);
}
.secondary-overview p {
  margin: 0;
  color: var(--text-2);
  font-size: 0.9rem;
}
.secondary-toggle {
  padding: 8px 16px;
  border: 1px solid var(--glass-border);
  background: var(--surface-2);
  color: var(--text-1);
  border-radius: var(--radius-md);
  cursor: pointer;
  font-size: 0.84rem;
  font-weight: 500;
  white-space: nowrap;
  transition: all var(--transition-fast);
}
.secondary-toggle:hover {
  border-color: var(--accent);
  background: var(--accent-subtle);
  color: var(--accent);
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
.workspace-note {
  font-size: 0.78rem;
  color: var(--text-3);
  text-align: right;
}
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
  font-size: 0.6rem;
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
.workspace-inline-actions,
.inline-form {
  display: flex;
  align-items: center;
  gap: 10px;
  flex-wrap: wrap;
}
.workspace-inline-actions {
  justify-content: space-between;
}
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

/* ── Buttons ── */
.primary-button,
.create-form button {
  padding: 11px 20px;
  background: var(--accent);
  color: var(--button-accent-text);
  border: none;
  border-radius: var(--radius-md);
  font-weight: 700;
  text-decoration: none;
  font-size: 0.9rem;
  cursor: pointer;
  display: inline-flex;
  align-items: center;
  gap: 8px;
  transition: all var(--transition-spring);
  position: relative;
  overflow: hidden;
}
.primary-button::after,
.create-form button::after {
  content: '';
  position: absolute;
  inset: 0;
  background: linear-gradient(135deg, rgba(255,255,255,0.2), transparent);
  opacity: 0;
  transition: opacity var(--transition-fast);
}
.primary-button:hover::after,
.create-form button:hover::after {
  opacity: 1;
}
.primary-button:hover,
.create-form button:hover {
  transform: translateY(-2px);
  box-shadow: 0 6px 20px var(--accent-glow);
}
.primary-button:active,
.create-form button:active {
  transform: scale(0.97);
}
.secondary-button,
.copy-btn {
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
}
.secondary-button:hover {
  border-color: var(--accent);
  background: var(--accent-subtle);
  color: var(--accent);
  transform: translateY(-1px);
}
.inline-form button {
  padding: 9px 15px;
  background: var(--surface-2);
  color: var(--text-1);
  border: 1px solid var(--glass-border);
  border-radius: var(--radius-md);
  cursor: pointer;
  font-size: 0.84rem;
  font-weight: 600;
  transition: all var(--transition-fast);
}
.inline-form button:hover {
  border-color: var(--accent);
  background: var(--accent-subtle);
  color: var(--accent);
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
.logout-panel {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 16px;
}

/* ── Focus States ── */
.primary-button:focus-visible,
.secondary-button:focus-visible,
.danger:focus-visible,
.copy-btn:focus-visible,
.inline-form button:focus-visible,
.secondary-toggle:focus-visible,
.create-form input:focus-visible,
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
  gap: 22px;
}
.skeleton-summary {
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: 16px;
}
.skeleton-card {
  display: flex;
  flex-direction: column;
  gap: 10px;
  padding: 22px 24px;
  background: var(--glass-bg);
  backdrop-filter: var(--glass-blur);
  -webkit-backdrop-filter: var(--glass-blur);
  border: 1px solid var(--glass-border);
  border-radius: var(--radius-xl);
}
.skeleton-columns {
  display: grid;
  grid-template-columns: minmax(0, 1.5fr) minmax(280px, 0.95fr);
  gap: 24px;
}
.skeleton-col {
  display: flex;
  flex-direction: column;
  gap: 12px;
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
.skeleton-card-block.dashed {
  border-style: dashed;
}

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

@media (max-width: 940px) {
  .dashboard-summary,
  .workspace-columns,
  .create-card,
  .skeleton-summary,
  .skeleton-columns {
    grid-template-columns: 1fr;
  }
  .create-card {
    gap: 18px;
    padding: 20px;
  }
}

@media (max-width: 640px) {
  .hero {
    padding: 40px 16px 24px;
  }
  .hero h1 {
    font-size: 1.6rem;
  }
  .panel {
    padding: 18px;
  }
  .workspace-card-head,
  .workspace-inline-actions,
  .logout-panel,
  .secondary-overview {
    flex-direction: column;
    align-items: stretch;
  }
  .workspace-card-head .secondary-button {
    text-align: center;
  }
  .dashboard-summary {
    gap: 10px;
  }
  .summary-card {
    padding: 16px 18px;
  }
  .summary-value {
    font-size: 1.8rem;
  }
}
</style>
