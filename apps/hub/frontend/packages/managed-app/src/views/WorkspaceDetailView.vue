<template>
  <div>
    <header>
      <ManagedNav />
    </header>
    <main id="main-content">
      <div v-if="!workspace" class="skeleton-shell" role="status" aria-live="polite" :aria-label="t('loading')">
        <div class="skeleton-metrics">
          <div class="skeleton-card"><SkeletonBlock h="14px" width="50%" /><SkeletonBlock h="32px" width="30%" /><SkeletonBlock h="12px" width="70%" /></div>
          <div class="skeleton-card"><SkeletonBlock h="14px" width="40%" /><SkeletonBlock h="18px" width="60%" /><SkeletonBlock h="12px" width="65%" /></div>
          <div class="skeleton-card"><SkeletonBlock h="14px" width="35%" /><SkeletonBlock h="18px" width="50%" /><SkeletonBlock h="12px" width="75%" /></div>
        </div>
        <div class="skeleton-grid">
          <div class="skeleton-col">
            <div class="skeleton-card-block"><SkeletonBlock h="10px" width="80px" /><SkeletonBlock h="18px" width="55%" /><SkeletonBlock h="12px" width="80%" /><SkeletonBlock h="36px" width="100%" /><SkeletonBlock h="36px" width="100%" /><SkeletonBlock h="36px" width="100%" /></div>
            <div class="skeleton-card-block"><SkeletonBlock h="10px" width="70px" /><SkeletonBlock h="18px" width="45%" /><SkeletonBlock h="12px" width="70%" /><div class="skeleton-session-row"><SkeletonBlock h="14px" width="40%" /><SkeletonBlock h="12px" width="60%" /></div><div class="skeleton-session-row"><SkeletonBlock h="14px" width="35%" /><SkeletonBlock h="12px" width="55%" /></div></div>
          </div>
          <div class="skeleton-col">
            <div class="skeleton-card-block"><SkeletonBlock h="10px" width="70px" /><SkeletonBlock h="18px" width="45%" /><SkeletonBlock h="12px" width="50%" /><SkeletonBlock h="12px" width="60%" /><SkeletonBlock h="12px" width="45%" /></div>
            <div class="skeleton-card-block"><SkeletonBlock h="10px" width="90px" /><SkeletonBlock h="18px" width="50%" /><SkeletonBlock h="12px" width="70%" /><SkeletonBlock h="32px" width="100%" /></div>
          </div>
        </div>
      </div>

      <section v-else class="panel">
        <div class="panel-header">
          <div>
            <span class="panel-kicker">{{ t('workspace_kicker') }}</span>
            <h1 class="panel-title">{{ workspace.name }}</h1>
            <p class="panel-sub">{{ t('workspace_dashboard_body') }}</p>
            <div class="header-meta">
              <span class="pill">
                {{ t('ws_sessions') }}: <strong>{{ sessions.length }}</strong>
              </span>
              <span class="pill">
                {{ t('ws_admin') }}: <strong>{{ adminEmail }}</strong>
              </span>
              <span class="pill">
                {{ t('ws_your_role') }}: <strong>{{ viewerRole }}</strong>
              </span>
            </div>
          </div>
          <RouterLink v-if="!isSingleWorkspace" to="/managed/ui/workspaces" class="back-link">&larr; {{ t('nav_workspaces') }}</RouterLink>
        </div>

        <div v-if="pageBanner" class="page-banner" role="status" aria-live="polite">
          <div>
            <p class="page-banner-title">{{ pageBanner.title }}</p>
            <p class="page-banner-body">{{ pageBanner.body }}</p>
          </div>
          <button class="page-banner-dismiss" type="button" @click="dismissBanner" :aria-label="t('dismiss')">&times;</button>
        </div>

        <OnboardingChecklist
          :workspace-slug="workspace.slug"
          :has-active-token="!!activeToken"
          :has-sessions="sessions.length > 0"
        />

        <div class="workspace-grid">
          <div class="primary-stack">
            <article class="surface-card">
              <div class="section-head">
                <span class="section-chip section-chip-accent">{{ t('workspace_primary_section') }}</span>
                <h2 id="session-heading">{{ t('workspace_sessions_title') }}</h2>
                <p>{{ t('session_create_help') }}</p>
              </div>

              <div class="shortcut-grid" role="group" :aria-label="t('session_create_help')">
                <button class="shortcut-button" @click="quickCreate('codex-chief')" :disabled="sessionLoading">
                  <span class="shortcut-icon" aria-hidden="true">&#9889;</span>
                  {{ t('create_session_codex') }}
                </button>
                <button class="shortcut-button" @click="quickCreate('claude-chief')" :disabled="sessionLoading">
                  <span class="shortcut-icon" aria-hidden="true">&#9889;</span>
                  {{ t('create_session_claude') }}
                </button>
              </div>

              <form @submit.prevent="handleCreateSession" class="workspace-form" novalidate>
                <div class="field full-width">
                  <label for="agent-name">{{ t('owner_agent_label') }}</label>
                  <input
                    id="agent-name"
                    v-model="newSession.agent_name"
                    type="text"
                    placeholder="codex-chief"
                    required
                    :aria-required="true"
                    :class="{ 'input-error': sessionErrors.agent_name }"
                    @input="clearSessionErrors"
                  />
                  <span v-if="sessionErrors.agent_name" class="field-error" role="alert">{{ sessionErrors.agent_name }}</span>
                </div>
                <div class="field">
                  <label for="session-title">{{ t('title_label') }}</label>
                  <input id="session-title" v-model="newSession.title" type="text" :placeholder="t('title_ph')" />
                </div>
                <div class="field">
                  <label for="session-project">{{ t('project_label') }}</label>
                  <input id="session-project" v-model="newSession.project" type="text" :placeholder="t('project_ph')" />
                </div>
                <div class="field">
                  <label for="session-prompt">{{ t('prompt_label') }}</label>
                  <textarea id="session-prompt" v-model="newSession.prompt" rows="3" :placeholder="t('prompt_ph')"></textarea>
                </div>
                <button type="submit" class="primary-button full-width" :disabled="sessionLoading">
                  <span v-if="sessionLoading" class="spinner" aria-hidden="true"></span>
                  {{ sessionLoading ? t('creating_session') : t('create_session_and_open_dashboard') }}
                </button>
              </form>
            </article>

            <article class="surface-card" aria-labelledby="session-heading">
              <div class="section-head">
                <span class="section-chip">{{ t('workspace_secondary_section') }}</span>
                <h2>{{ t('workspace_recent_sessions_title') }}</h2>
                <p>{{ t('workspace_recent_sessions_body') }}</p>
              </div>

              <div v-if="sessions.length === 0" class="empty-state compact">
                <div class="empty-icon" aria-hidden="true">
                  <svg width="36" height="36" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5"><circle cx="12" cy="12" r="10"/><polyline points="12 6 12 12 16 14"/></svg>
                </div>
                <p class="empty-title">{{ t('no_sessions') }}</p>
                <p class="empty-body">{{ t('no_sessions_hint') }}</p>
              </div>

              <div v-else class="session-cards">
                <RouterLink
                  v-for="s in sessions"
                  :key="s.session_id"
                  :to="sessionDetailPath(s)"
                  class="session-card"
                  :aria-label="`${s.owner_agent_name} — ${s.title || t('untitled_session')} — ${t('open_session_detail')}`"
                >
                  <div class="session-card-main">
                    <div class="session-card-agent">{{ s.owner_agent_name }}</div>
                    <div class="session-card-title">{{ s.title || t('untitled_session') }}</div>
                    <div class="session-card-meta">
                      <span
                        class="pill session-status-pill"
                        :class="s.live_status === 'active' ? 'pill-status-active' : 'pill-status-none'"
                        :title="sessionStatusTooltip(s)"
                      >
                        <span class="pill-icon" aria-hidden="true">{{ s.live_status === 'active' ? '●' : '○' }}</span>
                        {{ s.live_status === 'active' ? t('session_status_active') : t('session_status_closed') }}
                        <span v-if="s.live_status === 'active' && typeof s.member_count === 'number'" class="session-status-count">
                          · {{ t('session_member_count', { count: s.member_count }) }}
                        </span>
                      </span>
                      <code class="session-id">{{ s.session_id }}</code>
                      <span v-if="s.project" class="session-project">{{ s.project }}</span>
                      <time class="session-time" :datetime="s.created_at" :title="formatAbsolute(s.created_at)">{{ relativeTime(s.created_at) }}</time>
                    </div>
                  </div>
                  <span class="session-card-action">{{ t('open_session_detail') }} &rarr;</span>
                </RouterLink>
              </div>
            </article>
          </div>

          <aside class="secondary-stack">
            <article class="surface-card">
              <div class="section-head">
                <span class="section-chip">{{ t('workspace_secondary_section') }}</span>
                <h2>{{ t('workspace_overview_title') }}</h2>
              </div>
              <dl class="info-grid">
                <div class="info-item">
                  <dt>{{ t('ws_slug') }}</dt>
                  <dd><code>{{ workspace.slug }}</code></dd>
                </div>
                <div class="info-item">
                  <dt>{{ t('ws_status') }}</dt>
                  <dd><span class="pill" :class="'pill-status-' + workspace.status">{{ t('status_' + workspace.status) }}</span></dd>
                </div>
                <div class="info-item">
                  <dt>{{ t('ws_sessions') }}</dt>
                  <dd>{{ sessions.length }}</dd>
                </div>
                <div class="info-item">
                  <dt>{{ t('ws_your_role') }}</dt>
                  <dd>{{ viewerRole }}</dd>
                </div>
              </dl>
            </article>

            <article class="surface-card token-card">
              <div class="section-head">
                <span class="section-chip section-chip-warning">{{ t('workspace_token_section') }}</span>
                <h2>{{ t('workspace_token_title') }}</h2>
                <p>{{ t('ws_token_help') }}</p>
              </div>

              <div class="token-meta">
                <div class="token-meta-row">
                  <span class="token-meta-label">{{ t('ws_status') }}</span>
                  <span v-if="activeToken" class="pill pill-status-active"><span class="pill-icon" aria-hidden="true">&#10003;</span> {{ t('ws_token_active') }}</span>
                  <span v-else class="pill pill-status-none"><span class="pill-icon" aria-hidden="true">&#8226;</span> {{ t('ws_token_none') }}</span>
                </div>
                <div v-if="activeToken" class="token-meta-row">
                  <span class="token-meta-label">{{ t('ws_token_hint') }}</span>
                  <code>{{ activeToken.token_hint ?? t('ws_token_hint_none') }}</code>
                </div>
                <p class="help-text">{{ t('ws_token_hint_help') }}</p>
              </div>

              <div v-if="newToken" class="token-reveal" role="alert" aria-live="polite">
                <div class="token-danger-banner">
                  <span class="danger-icon" aria-hidden="true">&#9888;</span>
                  <p>{{ t('ws_token_warning') }}</p>
                </div>
                <div class="feature-grid">
                  <article class="feature-card"><h3>{{ t('ws_token_step1') }}</h3><p>{{ t('ws_token_step1_body') }}</p></article>
                  <article class="feature-card"><h3>{{ t('ws_token_step2') }}</h3><p>{{ t('ws_token_step2_body') }}</p></article>
                  <article class="feature-card"><h3>{{ t('ws_token_step3') }}</h3><p>{{ t('ws_token_step3_body') }}</p></article>
                </div>
                <div class="token-value-block">
                  <label for="new-token-value" class="sr-only">Token</label>
                  <code id="new-token-value">{{ newToken }}</code>
                  <button class="secondary-button copy-btn" @click="copyToken">
                    {{ copied ? t('ws_token_copied') : t('ws_token_copy') }}
                  </button>
                </div>
                <div v-if="sharePrompt" class="share-prompt-block">
                  <p class="share-prompt-label">{{ t('ws_token_share_prompt') }}</p>
                  <pre>{{ sharePrompt }}</pre>
                  <button class="secondary-button copy-btn" @click="copySharePrompt">
                    {{ promptCopied ? t('ws_token_prompt_copied') : t('ws_token_copy_prompt') }}
                  </button>
                </div>
                <div class="token-hide-row">
                  <button
                    class="ghost-button"
                    type="button"
                    @click="hideRevealedToken"
                    :aria-label="t('ws_token_hide')"
                  >
                    {{ t('ws_token_hide') }}
                  </button>
                </div>
              </div>

              <div class="token-actions">
                <button class="secondary-button" @click="handleRotateToken" :disabled="tokenLoading">
                  <span v-if="tokenLoading" class="spinner" aria-hidden="true"></span>
                  {{ activeToken ? t('ws_token_rotate') : t('ws_token_generate') }}
                </button>
                <button v-if="activeToken" class="danger" @click="requestRevokeToken" :disabled="tokenLoading">
                  {{ t('ws_token_revoke') }}
                </button>
              </div>
            </article>
          </aside>
        </div>
      </section>
      <ConfirmDialog
        :open="showConfirmRevoke"
        :title="t('ws_token_revoke')"
        :message="t('confirm_revoke_token')"
        :confirm-label="t('confirm_revoke_btn')"
        :cancel-label="t('confirm_cancel')"
        :resource-name="workspace?.name"
        :require-typed-value="workspace?.slug"
        :typed-prompt="t('confirm_type_workspace_slug', { slug: workspace?.slug ?? '' })"
        @confirm="handleConfirmRevoke"
        @cancel="handleCancelRevoke"
      />
    </main>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted } from 'vue'
import { useRoute, useRouter, RouterLink } from 'vue-router'
import ManagedNav from '../components/ManagedNav.vue'
import ConfirmDialog from '../components/ConfirmDialog.vue'
import SkeletonBlock from '../components/SkeletonBlock.vue'
import OnboardingChecklist from '../components/OnboardingChecklist.vue'
import { useManagedAuth } from '../composables/useManagedAuth'
import { useToast } from '../composables/useToast'
import { useManagedI18n } from '../i18n'
import { relativeTime, formatAbsolute } from '../lib/time'
import {
  fetchWorkspaceDetail,
  rotateWorkspaceToken,
  revokeWorkspaceToken,
  createWorkspaceSession,
  type Workspace,
  type WorkspaceMembership,
  type AgentToken,
  type WorkspaceSession,
} from '../api/managed'
import { getApiErrorMessage } from '../api/client'
import { buildManagedSessionDashboardPath } from '../lib/sessionLive'

const route = useRoute()
const router = useRouter()
const { requireAuth, isSingleWorkspace, user } = useManagedAuth()
const { t } = useManagedI18n()
const toast = useToast()

const slug = computed(() => String(route.params.slug))

const workspace = ref<Workspace | null>(null)
const adminMembership = ref<WorkspaceMembership | null>(null)
const viewerMembership = ref<WorkspaceMembership | null>(null)
const activeToken = ref<AgentToken | null>(null)
const sessions = ref<WorkspaceSession[]>([])

const newToken = ref('')
const sharePrompt = ref('')
const copied = ref(false)
const promptCopied = ref(false)
const tokenLoading = ref(false)
const sessionLoading = ref(false)
const showConfirmRevoke = ref(false)
const pageBanner = ref<{ title: string; body: string } | null>(null)

const newSession = ref({ agent_name: '', title: '', project: '', prompt: '' })
const sessionErrors = ref({ agent_name: '', title: '', project: '' })

function validateSession(): boolean {
  const errors = { agent_name: '', title: '', project: '' }
  if (!newSession.value.agent_name.trim()) {
    errors.agent_name = t('error_required')
  } else if (!/^[A-Za-z0-9_.-]+$/.test(newSession.value.agent_name.trim())) {
    errors.agent_name = t('error_agent_name_format')
  }
  sessionErrors.value = errors
  return !errors.agent_name
}

function clearSessionErrors() {
  sessionErrors.value = { agent_name: '', title: '', project: '' }
}

const adminEmail = computed(() => adminMembership.value?.email ?? t('ws_admin_pending'))
const viewerRole = computed(() => {
  if (viewerMembership.value) return t('role_' + viewerMembership.value.role)
  if (user.value) return t('role_' + user.value.role)
  return ''
})

function sessionStatusTooltip(session: WorkspaceSession): string {
  if (session.live_status !== 'active') {
    return t('session_status_closed_tooltip')
  }
  const counts = session.status_counts || {}
  const parts: string[] = []
  for (const key of ['busy', 'waiting', 'idle']) {
    const value = counts[key]
    if (typeof value === 'number' && value > 0) {
      parts.push(`${value} ${t('status_' + key)}`)
    }
  }
  if (parts.length === 0) return t('session_status_active_tooltip')
  return parts.join(', ')
}

function livePath(session: WorkspaceSession) {
  return buildManagedSessionDashboardPath({
    sessionId: session.session_id,
    agentName: session.owner_agent_name,
    memberToken: session.owner_member_token,
  })
}

function sessionDetailPath(session: WorkspaceSession) {
  return `/managed/ui/workspaces/${encodeURIComponent(slug.value)}/sessions/${encodeURIComponent(session.session_id)}`
}

async function loadData() {
  const data = await fetchWorkspaceDetail(slug.value)
  workspace.value = data.workspace
  adminMembership.value = data.workspace_admin
  viewerMembership.value = data.viewer_membership
  activeToken.value = data.active_token
  sessions.value = data.sessions.sort((a, b) => new Date(b.created_at).getTime() - new Date(a.created_at).getTime())
}

function dismissBanner() {
  pageBanner.value = null
}

async function showFlashBannerIfNeeded() {
  const flash = String(route.query.flash ?? '').trim()
  if (flash !== 'invitation-accepted') return
  pageBanner.value = {
    title: t('invitation_accepted'),
    body: t('workspace_invitation_accepted_banner'),
  }
  const nextQuery = { ...route.query }
  delete nextQuery.flash
  await router.replace({ query: nextQuery })
}

async function handleRotateToken() {
  tokenLoading.value = true
  try {
    const result = await rotateWorkspaceToken(slug.value)
    activeToken.value = result.agent_token
    newToken.value = result.raw_token
    sharePrompt.value = result.bootstrap.share_prompt
    copied.value = false
    promptCopied.value = false
    toast.show(t('ws_token_rotated_title'), 'success')
  } catch (err) {
    toast.show(getApiErrorMessage(err), 'error')
  } finally {
    tokenLoading.value = false
  }
}

function requestRevokeToken() {
  showConfirmRevoke.value = true
}

async function handleConfirmRevoke() {
  showConfirmRevoke.value = false
  tokenLoading.value = true
  try {
    await revokeWorkspaceToken(slug.value)
    activeToken.value = null
    newToken.value = ''
    sharePrompt.value = ''
    copied.value = false
    promptCopied.value = false
    toast.show(t('ws_token_revoked_title'), 'success')
  } catch (err) {
    toast.show(getApiErrorMessage(err), 'error')
  } finally {
    tokenLoading.value = false
  }
}

function handleCancelRevoke() {
  showConfirmRevoke.value = false
}

async function copyToken() {
  try {
    await navigator.clipboard.writeText(newToken.value)
    copied.value = true
    setTimeout(() => { copied.value = false }, 1500)
  } catch {
    prompt(t('copy_failed'), newToken.value)
  }
}

function hideRevealedToken() {
  // The token is only ever shown in cleartext immediately after rotation. Once
  // the admin signals they've stored it, wipe it from the DOM and from local
  // memory so that bystanders, screenshots, and the back/forward cache do not
  // hold onto it.
  newToken.value = ''
  sharePrompt.value = ''
  copied.value = false
  promptCopied.value = false
}

async function copySharePrompt() {
  try {
    await navigator.clipboard.writeText(sharePrompt.value)
    promptCopied.value = true
    setTimeout(() => { promptCopied.value = false }, 1500)
  } catch {
    prompt(t('copy_failed'), sharePrompt.value)
  }
}

function notifyResolvedAgentName(requestedAgentName: string, session: WorkspaceSession) {
  const actualAgentName = session.owner_agent_name
  if (!requestedAgentName.trim() || requestedAgentName.trim() === actualAgentName) return
  toast.show(
    t('workspace_agent_name_resolved', {
      requested: requestedAgentName.trim(),
      actual: actualAgentName,
    }),
    'info',
    4200,
  )
}

async function openCreatedSession(data: { workspace_session: WorkspaceSession }, requestedAgentName?: string) {
  if (requestedAgentName) {
    notifyResolvedAgentName(requestedAgentName, data.workspace_session)
  }
  await router.push(livePath(data.workspace_session))
}

async function quickCreate(agentName: string) {
  sessionLoading.value = true
  try {
    const result = await createWorkspaceSession(slug.value, { agent_name: agentName })
    await openCreatedSession(result, agentName)
  } catch (err) {
    toast.show(getApiErrorMessage(err), 'error')
  } finally {
    sessionLoading.value = false
  }
}

async function handleCreateSession() {
  if (!validateSession()) return
  sessionLoading.value = true
  try {
    const result = await createWorkspaceSession(slug.value, {
      agent_name: newSession.value.agent_name,
      title: newSession.value.title || undefined,
      project: newSession.value.project || undefined,
      prompt: newSession.value.prompt || undefined,
    })
    await openCreatedSession(result, newSession.value.agent_name)
  } catch (err) {
    toast.show(getApiErrorMessage(err), 'error')
  } finally {
    sessionLoading.value = false
  }
}

onMounted(async () => {
  const currentUser = await requireAuth()
  if (!currentUser) return
  await loadData()
  await showFlashBannerIfNeeded()
})
</script>

<style scoped>
.panel {
  max-width: 1140px;
  margin: 32px auto;
  padding: 28px;
  position: relative;
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
  font-size: 1.6rem;
  color: var(--text-1);
  margin: 6px 0 8px;
  letter-spacing: -0.03em;
  font-weight: 800;
}
.panel-sub {
  margin: 0;
  color: var(--text-2);
  font-size: 0.94rem;
  max-width: 680px;
  line-height: 1.55;
}
.header-meta {
  margin-top: 14px;
  display: flex;
  flex-wrap: wrap;
  gap: 10px;
}
.back-link {
  color: var(--text-2);
  text-decoration: none;
  font-size: 0.86rem;
  padding: 8px 14px;
  border-radius: var(--radius-md);
  border: 1px solid var(--glass-border);
  white-space: nowrap;
  transition: all var(--transition-fast);
  background: var(--glass-bg);
  backdrop-filter: var(--glass-blur);
  -webkit-backdrop-filter: var(--glass-blur);
}
.back-link:hover {
  border-color: var(--accent);
  color: var(--accent);
  background: var(--accent-subtle);
}
.back-link:focus-visible {
  outline: none;
  border-color: var(--accent);
  box-shadow: 0 0 0 3px var(--accent-subtle);
}

.page-banner {
  margin-bottom: 20px;
  padding: 16px 20px;
  border-radius: var(--radius-lg);
  border: 1px solid var(--success-glow);
  background: var(--glass-bg);
  backdrop-filter: var(--glass-blur);
  -webkit-backdrop-filter: var(--glass-blur);
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 16px;
  animation: slide-in var(--transition-spring);
}
@keyframes slide-in {
  from { opacity: 0; transform: translateY(-8px); }
  to { opacity: 1; transform: translateY(0); }
}
.page-banner-title {
  margin: 0 0 4px;
  color: var(--text-1);
  font-size: 0.94rem;
  font-weight: 700;
}
.page-banner-body {
  margin: 0;
  color: var(--text-2);
  font-size: 0.86rem;
  line-height: 1.5;
}
.page-banner-dismiss {
  border: none;
  background: transparent;
  color: var(--text-3);
  font-size: 1.2rem;
  cursor: pointer;
  padding: 4px 8px;
  border-radius: var(--radius-sm);
  line-height: 1;
  transition: all var(--transition-fast);
}
.page-banner-dismiss:hover {
  color: var(--text-1);
  background: var(--surface-2);
}

/* ── Metrics ── */

/* ── Grid ── */
.workspace-grid {
  display: grid;
  grid-template-columns: minmax(0, 1.55fr) minmax(300px, 0.95fr);
  gap: 24px;
  align-items: start;
}
.primary-stack,
.secondary-stack {
  display: flex;
  flex-direction: column;
  gap: 20px;
}
.surface-card {
  background: var(--glass-bg);
  backdrop-filter: var(--glass-blur);
  -webkit-backdrop-filter: var(--glass-blur);
  border: 1px solid var(--glass-border);
  border-radius: var(--radius-xl);
  padding: 24px;
  transition: all var(--transition-spring);
}
.surface-card:hover {
  border-color: var(--accent-glow);
  box-shadow: var(--shadow-md), 0 0 30px var(--accent-subtle);
}
.section-head {
  margin-bottom: 18px;
}
.section-head h2 {
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
.section-chip-accent {
  background: var(--accent-subtle);
}
.section-chip-warning {
  background: var(--warning-subtle);
  color: var(--warning);
  border-color: var(--warning-glow);
}

/* ── Info Grid ── */
.info-grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(160px, 1fr));
  gap: 16px;
  margin: 0;
}
.info-item {
  display: flex;
  flex-direction: column;
  gap: 5px;
}
.info-item dt {
  font-size: 0.72rem;
  color: var(--text-3);
  text-transform: uppercase;
  letter-spacing: 0.08em;
  font-weight: 600;
}
.info-item dd {
  margin: 0;
  font-size: 0.92rem;
  color: var(--text-1);
  font-weight: 500;
}
.info-item code {
  font-size: 0.86rem;
}
.pill {
  display: inline-block;
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
.pill-status-none {
  color: var(--text-3);
}
.pill-icon {
  font-size: 0.65rem;
  margin-right: 3px;
}

/* ── Session Creation ── */
.shortcut-grid {
  display: flex;
  gap: 12px;
  flex-wrap: wrap;
  margin-bottom: 18px;
}
.shortcut-button {
  padding: 11px 18px;
  background: var(--glass-bg);
  backdrop-filter: var(--glass-blur);
  -webkit-backdrop-filter: var(--glass-blur);
  color: var(--text-1);
  border: 1px solid var(--glass-border);
  border-radius: var(--radius-md);
  cursor: pointer;
  font-size: 0.86rem;
  font-weight: 600;
  display: inline-flex;
  align-items: center;
  gap: 8px;
  transition: all var(--transition-fast);
  position: relative;
  overflow: hidden;
}
.shortcut-button::before {
  content: '';
  position: absolute;
  inset: 0;
  background: linear-gradient(135deg, var(--accent-subtle), transparent);
  opacity: 0;
  transition: opacity var(--transition-fast);
}
.shortcut-button:hover:not(:disabled)::before {
  opacity: 1;
}
.shortcut-button:hover:not(:disabled) {
  border-color: var(--accent);
  color: var(--accent);
  transform: translateY(-2px);
  box-shadow: 0 4px 16px var(--accent-subtle);
}
.shortcut-icon {
  font-size: 1rem;
  position: relative;
}
.workspace-form {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 14px;
}
.field {
  display: flex;
  flex-direction: column;
  gap: 6px;
}
.field.full-width {
  grid-column: 1 / -1;
}
.field label {
  font-size: 0.84rem;
  color: var(--text-2);
  font-weight: 500;
}
.workspace-form input {
  padding: 11px 14px;
  border: 1px solid var(--glass-border);
  border-radius: var(--radius-md);
  background: var(--surface-0);
  color: var(--text-1);
  font-size: 0.9rem;
  transition: all var(--transition-fast);
}
.workspace-form input:focus {
  border-color: var(--accent);
  box-shadow: 0 0 0 3px var(--accent-subtle);
  outline: none;
}
.workspace-form input.input-error {
  border-color: var(--danger);
  box-shadow: 0 0 0 3px var(--danger-subtle);
}
.field-error {
  font-size: 0.78rem;
  color: var(--danger);
  margin-top: 2px;
}

/* ── Session Cards ── */
.session-cards {
  display: flex;
  flex-direction: column;
  gap: 10px;
}
.session-card {
  display: flex;
  justify-content: space-between;
  align-items: center;
  gap: 16px;
  padding: 16px 18px;
  background: var(--glass-bg);
  backdrop-filter: var(--glass-blur);
  -webkit-backdrop-filter: var(--glass-blur);
  border: 1px solid var(--glass-border);
  border-radius: var(--radius-lg);
  text-decoration: none;
  color: inherit;
  transition: all var(--transition-spring);
  animation: card-enter var(--transition-spring) backwards;
}
@keyframes card-enter {
  from { opacity: 0; transform: translateY(8px); }
  to { opacity: 1; transform: translateY(0); }
}
.session-card:nth-child(1) { animation-delay: 0ms; }
.session-card:nth-child(2) { animation-delay: 50ms; }
.session-card:nth-child(3) { animation-delay: 100ms; }
.session-card:nth-child(4) { animation-delay: 150ms; }
.session-card:nth-child(5) { animation-delay: 200ms; }
.session-card:hover {
  border-color: var(--accent-glow);
  box-shadow: var(--shadow-md), 0 0 30px var(--accent-subtle);
  transform: translateY(-2px);
}
.session-card:focus-visible {
  outline: none;
  border-color: var(--accent);
  box-shadow: 0 0 0 3px var(--accent-subtle);
}
.session-card-main {
  display: flex;
  flex-direction: column;
  gap: 5px;
  min-width: 0;
}
.session-card-agent {
  font-weight: 700;
  font-size: 0.92rem;
  color: var(--text-1);
}
.session-card-title {
  font-size: 0.84rem;
  color: var(--text-2);
}
.session-card-meta {
  display: flex;
  flex-wrap: wrap;
  gap: 10px;
  align-items: center;
}
.session-id {
  font-size: 0.72rem;
  color: var(--text-3);
  background: var(--surface-2);
  padding: 3px 8px;
  border-radius: var(--radius-sm);
  font-family: monospace;
}
.session-project {
  font-size: 0.72rem;
  color: var(--text-3);
}
.session-time {
  font-size: 0.72rem;
  color: var(--text-3);
}
.session-card-action {
  font-size: 0.82rem;
  color: var(--accent);
  font-weight: 600;
  white-space: nowrap;
  flex-shrink: 0;
  transition: all var(--transition-fast);
}

/* ── Empty State ── */
.empty-state {
  text-align: center;
  padding: 36px 24px;
  color: var(--text-3);
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 8px;
}
.empty-state.compact {
  background: var(--glass-bg);
  backdrop-filter: var(--glass-blur);
  -webkit-backdrop-filter: var(--glass-blur);
  border: 1px dashed var(--glass-border);
  border-radius: var(--radius-lg);
}
.empty-icon {
  color: var(--text-3);
  opacity: 0.5;
  margin-bottom: 4px;
}
.empty-title {
  font-size: 0.94rem;
  color: var(--text-2);
  margin: 0;
  font-weight: 600;
}
.empty-body {
  font-size: 0.84rem;
  color: var(--text-3);
  margin: 0;
  max-width: 280px;
  line-height: 1.5;
}

/* ── Token ── */
.token-meta {
  display: flex;
  flex-direction: column;
  gap: 12px;
  margin-bottom: 18px;
}
.token-meta-row {
  display: flex;
  align-items: center;
  gap: 10px;
  font-size: 0.9rem;
  color: var(--text-1);
}
.token-meta-row code {
  font-size: 0.84rem;
}
.token-meta-label {
  font-size: 0.78rem;
  color: var(--text-3);
  font-weight: 600;
  min-width: 52px;
}
.help-text {
  color: var(--text-2);
  font-size: 0.84rem;
  margin: 0;
  line-height: 1.5;
}

.token-reveal {
  background: var(--surface-0);
  border: 2px solid var(--warning-glow);
  border-radius: var(--radius-lg);
  padding: 18px;
  margin: 14px 0;
  animation: glow-pulse 2s ease-in-out infinite;
}
@keyframes glow-pulse {
  0%, 100% { box-shadow: 0 0 20px var(--warning-subtle); }
  50% { box-shadow: 0 0 35px var(--warning-glow); }
}
.token-danger-banner {
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 12px 16px;
  background: var(--warning-subtle);
  border-radius: var(--radius-md);
  margin-bottom: 16px;
}
.token-danger-banner p {
  margin: 0;
  font-size: 0.86rem;
  color: var(--warning);
  font-weight: 700;
}
.danger-icon {
  font-size: 1.2rem;
  flex-shrink: 0;
}
.feature-grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(140px, 1fr));
  gap: 12px;
  margin-bottom: 16px;
}
.feature-card {
  background: var(--surface-2);
  border-radius: var(--radius-md);
  padding: 14px;
  transition: all var(--transition-fast);
}
.feature-card:hover {
  background: var(--accent-subtle);
  transform: translateY(-2px);
}
.feature-card h3 {
  font-size: 0.84rem;
  color: var(--text-1);
  margin: 0 0 5px;
  font-weight: 700;
}
.feature-card p {
  font-size: 0.78rem;
  color: var(--text-2);
  margin: 0;
  line-height: 1.4;
}
.token-value-block {
  display: flex;
  flex-wrap: wrap;
  gap: 10px;
  align-items: center;
}
.token-value-block code {
  flex: 1;
  min-width: 200px;
  padding: 12px 14px;
  background: var(--surface-2);
  border-radius: var(--radius-md);
  font-size: 0.84rem;
  word-break: break-all;
  color: var(--text-1);
  border: 1px solid var(--glass-border);
}
.share-prompt-block {
  margin-top: 14px;
  display: flex;
  flex-direction: column;
  gap: 10px;
}
.share-prompt-label {
  margin: 0;
  font-size: 0.78rem;
  color: var(--text-2);
  font-weight: 600;
}
.share-prompt-block pre {
  margin: 0;
  padding: 14px;
  border-radius: var(--radius-md);
  border: 1px solid var(--glass-border);
  background: var(--surface-2);
  color: var(--text-1);
  font-size: 0.8rem;
  line-height: 1.55;
  white-space: pre-wrap;
  word-break: break-word;
}
.token-actions {
  display: flex;
  gap: 12px;
  flex-wrap: wrap;
}

/* ── Buttons ── */
.primary-button {
  padding: 11px 20px;
  background: var(--accent);
  color: var(--button-accent-text);
  border: none;
  border-radius: var(--radius-md);
  font-weight: 700;
  cursor: pointer;
  font-size: 0.9rem;
  display: inline-flex;
  align-items: center;
  gap: 8px;
  justify-content: center;
  transition: all var(--transition-spring);
  position: relative;
  overflow: hidden;
}
.primary-button::after {
  content: '';
  position: absolute;
  inset: 0;
  background: linear-gradient(135deg, rgba(255,255,255,0.2), transparent);
  opacity: 0;
  transition: opacity var(--transition-fast);
}
.primary-button:hover::after {
  opacity: 1;
}
.primary-button:hover:not(:disabled) {
  transform: translateY(-2px);
  box-shadow: 0 6px 20px var(--accent-glow);
}
.primary-button:active:not(:disabled) {
  transform: scale(0.97);
}
.primary-button.full-width {
  width: 100%;
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

/* ── Focus States ── */
.primary-button:focus-visible,
.secondary-button:focus-visible,
.danger:focus-visible,
.copy-btn:focus-visible,
.page-banner-dismiss:focus-visible,
.shortcut-button:focus-visible,
.workspace-form input:focus-visible {
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
  max-width: 1140px;
  margin: 32px auto;
  padding: 28px;
  display: flex;
  flex-direction: column;
  gap: 22px;
}
.skeleton-metrics {
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
.skeleton-grid {
  display: grid;
  grid-template-columns: minmax(0, 1.55fr) minmax(300px, 0.95fr);
  gap: 24px;
}
.skeleton-col {
  display: flex;
  flex-direction: column;
  gap: 20px;
}
.skeleton-card-block {
  display: flex;
  flex-direction: column;
  gap: 12px;
  padding: 24px;
  background: var(--glass-bg);
  backdrop-filter: var(--glass-blur);
  -webkit-backdrop-filter: var(--glass-blur);
  border: 1px solid var(--glass-border);
  border-radius: var(--radius-xl);
}
.skeleton-session-row {
  display: flex;
  flex-direction: column;
  gap: 8px;
  padding: 14px 16px;
  background: var(--surface-0);
  border: 1px solid var(--glass-border);
  border-radius: var(--radius-lg);
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

@media (max-width: 940px) {
  .workspace-grid,
  .workspace-form,
  .skeleton-metrics,
  .skeleton-grid {
    grid-template-columns: 1fr;
  }
  .panel {
    padding: 20px;
  }
}
@media (max-width: 600px) {
  .panel-header {
    flex-direction: column;
    gap: 12px;
  }
  .shortcut-grid {
    flex-direction: column;
  }
  .session-card {
    flex-direction: column;
    align-items: flex-start;
    gap: 12px;
  }
  .session-card-action {
    width: 100%;
    text-align: center;
    padding: 8px 0;
    border-top: 1px solid var(--glass-border);
  }
  .token-actions {
    flex-direction: column;
  }
  .token-actions button {
    width: 100%;
    text-align: center;
  }
}
</style>
