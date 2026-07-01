<template>
  <div>
    <header>
      <ManagedNav />
    </header>
    <main id="main-content">
      <section class="panel">
        <div class="panel-header">
          <div>
            <span class="panel-kicker">{{ t('workspace_surface_kicker') }}</span>
            <h1 class="panel-title">{{ t('my_workspaces_page_title') }}</h1>
            <p class="panel-sub">{{ t('my_workspaces_page_body') }}</p>
          </div>
        </div>

        <div v-if="loading" class="skeleton-shell" role="status" aria-live="polite" :aria-label="t('loading')">
          <div class="skeleton-summary">
            <div class="skeleton-card"><SkeletonBlock h="18px" width="60%" /><SkeletonBlock h="32px" width="30%" /><SkeletonBlock h="12px" width="80%" /></div>
            <div class="skeleton-card"><SkeletonBlock h="18px" width="55%" /><SkeletonBlock h="32px" width="25%" /><SkeletonBlock h="12px" width="75%" /></div>
          </div>
          <div class="skeleton-columns">
            <div class="skeleton-col">
              <SkeletonBlock h="10px" width="80px" /><SkeletonBlock h="18px" width="50%" /><SkeletonBlock h="12px" width="70%" />
              <div class="skeleton-card-block"><SkeletonBlock h="16px" width="45%" /><SkeletonBlock h="12px" width="70%" /><SkeletonBlock h="12px" width="55%" /></div>
              <div class="skeleton-card-block"><SkeletonBlock h="16px" width="40%" /><SkeletonBlock h="12px" width="65%" /><SkeletonBlock h="12px" width="50%" /></div>
              <div class="skeleton-card-block"><SkeletonBlock h="16px" width="50%" /><SkeletonBlock h="12px" width="60%" /><SkeletonBlock h="12px" width="45%" /></div>
            </div>
            <div class="skeleton-col">
              <SkeletonBlock h="10px" width="70px" /><SkeletonBlock h="18px" width="45%" /><SkeletonBlock h="12px" width="65%" />
              <div class="skeleton-card-block dashed"><SkeletonBlock h="14px" width="50%" /><SkeletonBlock h="30px" width="80px" /></div>
            </div>
          </div>
        </div>

        <div v-if="sortedOwnWorkspaces.length === 0" class="empty-state large">
          <div class="empty-icon" aria-hidden="true">
            <svg width="48" height="48" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5"><path d="M3 7v10a2 2 0 002 2h14a2 2 0 002-2V9a2 2 0 00-2-2h-6l-2-2H5a2 2 0 00-2 2z"/></svg>
          </div>
          <p class="empty-title">{{ t('no_workspaces') }}</p>
          <p class="empty-body">{{ t('no_workspaces_body') }}</p>
        </div>

        <div v-else class="workspace-list">
          <RouterLink
            v-for="item in sortedOwnWorkspaces"
            :key="item.workspace.workspace_id"
            :to="`/managed/ui/workspaces/${encodeURIComponent(item.workspace.slug)}`"
            class="workspace-card workspace-card-link"
          >
            <div class="workspace-card-head">
              <div>
                <div class="workspace-card-title">{{ item.workspace.name }}</div>
                <div class="workspace-card-meta">
                  <span class="pill">{{ t('ws_slug') }}: <strong>{{ item.workspace.slug }}</strong></span>
                  <span class="pill">{{ t('ws_role') }}: <strong>{{ t('role_' + item.membership.role) }}</strong></span>
                  <span class="pill" :class="'pill-status-' + item.workspace.status"><span class="pill-icon" aria-hidden="true">{{ item.workspace.status === 'active' ? '&#10003;' : item.workspace.status === 'disabled' ? '&#10005;' : '&#8230;' }}</span> {{ t('status_' + item.workspace.status) }}</span>
                  <span class="pill" :class="item.sessions.length > 0 ? 'pill-sessions-active' : 'pill-sessions-none'">{{ t('ws_sessions') }}: <strong>{{ item.sessions.length }}</strong></span>
                </div>
              </div>
              <span class="card-arrow" aria-hidden="true">&rarr;</span>
            </div>
          </RouterLink>
        </div>
      </section>
    </main>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { RouterLink, useRouter } from 'vue-router'
import ManagedNav from '../components/ManagedNav.vue'
import SkeletonBlock from '../components/SkeletonBlock.vue'
import { useManagedAuth } from '../composables/useManagedAuth'
import { useManagedI18n } from '../i18n'
import {
  fetchMyWorkspaces,
  type Workspace,
  type WorkspaceMembership,
  type WorkspaceSession,
} from '../api/managed'

interface MyWorkspaceItem {
  workspace: Workspace
  membership: WorkspaceMembership
  sessions: WorkspaceSession[]
}

const { requireAuth } = useManagedAuth()
const { t } = useManagedI18n()
const router = useRouter()

const loading = ref(true)
const ownWorkspaces = ref<MyWorkspaceItem[]>([])

const sortedOwnWorkspaces = computed(() =>
  ownWorkspaces.value
    .slice()
    .sort((left, right) => left.workspace.name.localeCompare(right.workspace.name)),
)

onMounted(async () => {
  const currentUser = await requireAuth()
  if (!currentUser) return
  try {
    const myData = await fetchMyWorkspaces()
    ownWorkspaces.value = myData.workspaces
    if (myData.workspaces.length === 1) {
      await router.replace(`/managed/ui/workspaces/${encodeURIComponent(myData.workspaces[0].workspace.slug)}`)
      return
    }
  } finally {
    loading.value = false
  }
})
</script>

<style scoped>
.panel {
  max-width: 1000px;
  margin: 32px auto;
  padding: 28px;
}
.panel-header {
  margin-bottom: 28px;
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
  color: var(--text-2);
  font-size: 0.94rem;
  margin: 0;
  line-height: 1.55;
}

.workspace-summary {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 16px;
  margin-bottom: 24px;
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
  font-size: 2rem;
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

.workspace-columns {
  display: grid;
  grid-template-columns: minmax(0, 1.5fr) minmax(260px, 0.9fr);
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

/* ── Empty States ── */
.empty-state {
  text-align: center;
  padding: 40px 28px;
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
  transition: all var(--transition-fast);
}
.empty-state:hover {
  border-color: var(--accent-glow);
}
.empty-state.compact {
  padding: 24px 20px;
}
.empty-state.large {
  padding: 52px 28px;
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
.workspace-list {
  display: flex;
  flex-direction: column;
  gap: 12px;
}
.workspace-card {
  background: var(--glass-bg);
  backdrop-filter: var(--glass-blur);
  -webkit-backdrop-filter: var(--glass-blur);
  border: 1px solid var(--glass-border);
  border-radius: var(--radius-lg);
  padding: 18px 20px;
  text-decoration: none;
  color: inherit;
  transition: all var(--transition-spring);
  animation: card-enter var(--transition-spring) backwards;
}
@keyframes card-enter {
  from { opacity: 0; transform: translateY(8px); }
  to { opacity: 1; transform: translateY(0); }
}
.workspace-card:nth-child(1) { animation-delay: 0ms; }
.workspace-card:nth-child(2) { animation-delay: 50ms; }
.workspace-card:nth-child(3) { animation-delay: 100ms; }
.workspace-card:nth-child(4) { animation-delay: 150ms; }
.workspace-card:nth-child(5) { animation-delay: 200ms; }
.workspace-card-link:hover {
  border-color: var(--accent-glow);
  box-shadow: var(--shadow-md), 0 0 35px var(--accent-subtle);
  transform: translateY(-2px);
}
.workspace-card:focus-visible {
  outline: none;
  border-color: var(--accent);
  box-shadow: 0 0 0 3px var(--accent-subtle);
}
.primary-column .workspace-card {
  box-shadow: var(--shadow-sm);
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
  padding: 9px 15px;
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
  transform: translateY(-1px);
}
.workspace-card-head {
  display: flex;
  justify-content: space-between;
  align-items: flex-start;
  gap: 16px;
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
.card-arrow {
  color: var(--text-3);
  font-size: 1.2rem;
  flex-shrink: 0;
  transition: all var(--transition-fast);
}
.workspace-card-link:hover .card-arrow {
  color: var(--accent);
  transform: translateX(4px);
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
.pill-icon {
  font-size: 0.65rem;
  margin-right: 3px;
}
.pill-sessions-active {
  color: var(--accent);
  background: var(--accent-subtle);
  border-color: var(--accent-glow);
}
.pill-sessions-active strong {
  color: var(--accent);
}
.pill-sessions-none {
  color: var(--text-3);
}

/* ── Focus States ── */
.secondary-toggle:focus-visible,
.workspace-card:focus-visible {
  outline: none;
  border-color: var(--accent);
  box-shadow: 0 0 0 3px var(--accent-subtle);
}

/* ── Secondary Button ── */
.secondary-button {
  padding: 10px 16px;
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
  margin-top: 8px;
}
.secondary-button:hover {
  border-color: var(--accent);
  background: var(--accent-subtle);
  color: var(--accent);
  transform: translateY(-1px);
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

@media (max-width: 820px) {
  .workspace-summary,
  .workspace-columns {
    grid-template-columns: 1fr;
  }
  .panel {
    padding: 20px;
  }
}
@media (max-width: 600px) {
  .workspace-card-head,
  .secondary-overview {
    flex-direction: column;
  }
  .card-arrow {
    display: none;
  }
  .workspace-card {
    padding: 14px 16px;
  }
}

/* ── Skeleton Loading ── */
.skeleton-shell {
  display: flex;
  flex-direction: column;
  gap: 22px;
}
.skeleton-summary {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
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
  grid-template-columns: minmax(0, 1.5fr) minmax(260px, 0.9fr);
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
@media (max-width: 820px) {
  .skeleton-summary,
  .skeleton-columns {
    grid-template-columns: 1fr;
  }
}
</style>
