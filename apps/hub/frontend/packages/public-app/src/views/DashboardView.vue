<template>
  <div class="page">
    <!-- Hero -->
    <section class="hero">
      <div class="hero-top">
        <div style="display:flex;align-items:center;gap:12px">
          <div class="title">{{ t('db_hero_title') }}</div>
          <button class="info-toggle" type="button" :title="t('db_info_toggle_title')" @click="showSub = !showSub">i</button>
        </div>
        <div class="hero-controls">
          <LangToggle :messages="messages" />
          <ThemeToggle :messages="messages" />
        </div>
      </div>
      <div class="sub" :class="{ show: showSub }">{{ t('db_hero_sub') }}</div>
    </section>

    <!-- Layout -->
    <main class="layout" :class="{ locked: dashboard.locked.value }">
      <!-- Access panel -->
      <section class="panel access-panel" :class="{ compact: accessCompact }">
        <div class="panel-head">
          <div class="panel-title">{{ t('db_access_title') }}</div>
        </div>
        <div class="panel-body">
          <div class="stack">
            <!-- Compact summary -->
            <div class="access-summary">
              <div class="access-summary-copy">
                <div class="access-summary-title">{{ t('db_access_active_title') }}</div>
                <div class="access-summary-primary">{{ accessModeLabel }}</div>
                <div class="access-summary-secondary">
                  <span class="access-summary-chip">{{ accessModeLabel }}</span>
                </div>
              </div>
              <button type="button" class="ghost compact-action" @click="accessCompact = false">{{ t('db_edit_access_btn') }}</button>
            </div>
            <!-- Full form -->
            <div class="access-form">
              <div class="access-form-grid">
                <label>
                  <span>{{ t('db_global_token_label') }}</span>
                  <input v-model="tokenInput" type="password" :placeholder="t('db_global_token_placeholder')" @keyup.enter="doLogin" />
                </label>
                <div class="access-actions">
                  <button :disabled="dashboard.loading.value" @click="doLogin">{{ t('db_login_btn') }}</button>
                  <button v-if="!dashboard.locked.value" class="ghost" @click="doReload">{{ t('db_reload_btn') }}</button>
                  <button v-if="!dashboard.locked.value" class="ghost" @click="doLogout">{{ t('db_logout_btn') }}</button>
                  <button v-if="!dashboard.locked.value" class="ghost" @click="dashboard.clearTraces()">{{ t('db_clear_traces_btn') }}</button>
                </div>
              </div>
            </div>
            <!-- Status -->
            <div class="status-line" :class="{ danger: dashboard.statusIsError.value }">
              <span v-if="dashboard.polling.value" class="poll-spinner" :title="t('db_poll_active_title')">
                <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><polyline points="23 4 23 10 17 10"/><polyline points="1 20 1 14 7 14"/><path d="M3.51 9a9 9 0 0 1 14.85-3.36L23 10M1 14l4.64 4.36A9 9 0 0 0 20.49 15"/></svg>
              </span>
              {{ statusText }}
            </div>
            <!-- Hub flags -->
            <div v-if="hubFlags" class="hub-flags-row">
              <span class="flag-chip"><span class="flag-icon" :class="hubFlags.token_required ? 'on' : 'off'"></span>{{ t('db_flag_token_required') }}: {{ hubFlags.token_required ? t('db_yes') : t('db_no') }}</span>
              <span class="flag-chip"><span class="flag-icon" :class="hubFlags.storage_ready ? 'on' : 'off'"></span>{{ t('db_flag_storage_ready') }}: {{ hubFlags.storage_ready ? t('db_yes') : t('db_no') }}</span>
              <span class="flag-chip"><span class="flag-icon" :class="hubFlags.auth_ready ? 'on' : 'off'"></span>{{ t('db_flag_auth_ready') }}: {{ hubFlags.auth_ready ? t('db_yes') : t('db_no') }}</span>
              <span class="flag-chip"><span class="flag-icon" :class="hubFlags.auth_enforce ? 'on' : 'off'"></span>{{ t('db_flag_auth_enforce') }}: {{ hubFlags.auth_enforce ? t('db_yes') : t('db_no') }}</span>
              <span class="flag-chip"><span class="flag-icon num"></span>{{ t('db_flag_dashboard_sessions') }}: {{ hubFlags.dashboard_sessions ?? 0 }}</span>
            </div>
          </div>
        </div>
      </section>

      <!-- Summary panel -->
      <section v-if="!dashboard.locked.value" class="panel">
        <div class="panel-head">
          <div class="panel-title">{{ t('db_global_summary_title') }}</div>
        </div>
        <div class="panel-body">
          <div class="grid">
            <div class="metric"><div class="metric-k">{{ t('db_metric_sessions') }}</div><div class="metric-v">{{ overview?.session_count ?? 0 }}</div></div>
            <div class="metric"><div class="metric-k">{{ t('db_metric_members') }}</div><div class="metric-v">{{ overview?.member_count ?? 0 }}</div></div>
            <div class="metric"><div class="metric-k">{{ t('db_metric_ws') }}</div><div class="metric-v">{{ dashboard.payload.value?.connected_agents?.length ?? 0 }}</div></div>
            <div class="metric"><div class="metric-k">{{ t('db_metric_idle') }}</div><div class="metric-v">{{ overview?.status_counts?.idle ?? 0 }}</div></div>
            <div class="metric"><div class="metric-k">{{ t('db_metric_waiting') }}</div><div class="metric-v">{{ overview?.status_counts?.waiting ?? 0 }}</div></div>
            <div class="metric"><div class="metric-k">{{ t('db_metric_busy') }}</div><div class="metric-v">{{ overview?.status_counts?.busy ?? 0 }}</div></div>
          </div>
        </div>
      </section>
    </main>

    <div v-if="!dashboard.locked.value" class="sections-stack">
      <!-- Cockpit -->
      <section class="panel">
        <div class="panel-head">
          <div>
            <div class="panel-title">{{ t('db_collaboration_cockpit_title') }}</div>
            <div class="muted">{{ t('db_collaboration_cockpit_sub') }}</div>
          </div>
          <div class="traffic-status">
            <span class="traffic-chip" :class="dashboard.trafficSnapshot.value.level">{{ t(`db_traffic_${dashboard.trafficSnapshot.value.level}`) }}</span>
            <span class="traffic-chip">{{ t('db_traffic_recent', { count: String(dashboard.trafficSnapshot.value.count) }) }}</span>
            <span class="traffic-chip">{{ t('db_traffic_issues', { count: String(dashboard.issueCount.value) }) }}</span>
          </div>
        </div>
        <div class="panel-body">
          <div class="cockpit-grid">
            <!-- Squad Map -->
            <div class="cockpit-card" :data-load="dashboard.trafficSnapshot.value.level">
              <div class="cockpit-head">
                <div>
                  <div class="cockpit-title">{{ t('db_squad_map_title') }}</div>
                  <div class="cockpit-sub">{{ t('db_squad_map_sub') }}</div>
                </div>
              </div>
              <div class="squad-map">
                <div v-if="!squadSessions.length" class="empty-state">
                  <svg width="48" height="48" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5"><circle cx="12" cy="12" r="10"/><line x1="12" y1="8" x2="12" y2="12"/><line x1="12" y1="16" x2="12.01" y2="16"/></svg>
                  <span>{{ t('db_no_squads') }}</span>
                </div>
                <div v-else class="squad-canvas" v-html="squadMapSvg"></div>
              </div>
            </div>
            <!-- Hot tasks + Recovery -->
            <div class="cockpit-card">
              <div class="cockpit-head">
                <div>
                  <div class="cockpit-title">{{ t('db_hot_tasks_title') }}</div>
                  <div class="cockpit-sub">{{ t('db_hot_tasks_sub') }}</div>
                </div>
              </div>
              <div v-if="!hotTaskItems.length" class="empty-state">
                <span>{{ t('db_no_hot_tasks') }}</span>
              </div>
              <div v-else class="lane-stack">
                <article v-for="item in hotTaskItems" :key="item.agent_name + item.session_id" class="lane-card">
                  <div class="lane-session">{{ shortLabel(item.session_label, 28) }}</div>
                  <div class="lane-top">
                    <div class="lane-title">{{ item.agent_name }}</div>
                    <span class="lane-role" :style="{ background: roleTone(item.role) }">{{ roleGlyph(item.role) }}</span>
                  </div>
                  <div class="lane-meta">
                    <span>{{ translateStatus(item.status) }}</span>
                    <span>{{ item.pending_count }} {{ t('db_pending') }}</span>
                    <span>{{ t('db_since') }} {{ timeAgo(item.current_task_at || item.last_message_at, locale) }}</span>
                  </div>
                  <div class="lane-task">
                    <strong>{{ t('db_current_task') }}:</strong> {{ item.current_task || t('db_no_detail') }}
                  </div>
                </article>
              </div>

              <div class="cockpit-head" style="margin-top:18px">
                <div>
                  <div class="cockpit-title">{{ t('db_recovery_feed_title') }}</div>
                  <div class="cockpit-sub">{{ t('db_recovery_feed_sub') }}</div>
                </div>
              </div>
              <div v-if="!recoveryItems.length" class="empty-state">
                <span>{{ t('db_no_recovery') }}</span>
              </div>
              <div v-else class="recovery-stack">
                <article v-for="item in recoveryItems" :key="item.agent_name + item.ts" class="recovery-row">
                  <div class="recovery-title">{{ item.title }}</div>
                  <div class="recovery-meta">
                    <span>{{ item.agent_name }}</span>
                    <span>{{ shortLabel(item.session_label, 26) }}</span>
                    <span>{{ timeAgo(item.ts, locale) }}</span>
                    <span class="health-badge" :class="item.state">{{ heartbeatLabel(item.state) }}</span>
                  </div>
                </article>
              </div>
            </div>
          </div>
        </div>
      </section>

      <!-- Task Ledger -->
      <section class="panel">
        <div class="panel-head">
          <div class="panel-title">{{ t('db_task_ledger_title') }}</div>
          <div class="muted">{{ t('db_task_ledger_sub') }}</div>
        </div>
        <div class="panel-body">
          <div v-if="!taskLedgerItems.length" class="empty-state">
            <span>{{ t('db_no_task_ledger') }}</span>
          </div>
          <div v-else class="task-ledger">
            <article v-for="item in taskLedgerItems" :key="item.member.agent_name + item.session_id" class="ledger-card">
              <div class="ledger-top">
                <div class="ledger-title">{{ item.member.agent_name }}</div>
                <span class="health-badge" :class="getHeartbeatState(item.member)">{{ heartbeatLabel(getHeartbeatState(item.member)) }} · {{ heartbeatAgeSuffix(item.member) }}</span>
              </div>
              <div class="ledger-sub">{{ shortLabel(item.session_label, 34) }} · {{ translateRole(item.member.role) }} · {{ translateStatus(item.member.status) }}</div>
              <div class="ledger-task">
                <strong>{{ t('db_current_task') }}:</strong> {{ item.member.current_task || item.member.status_text || t('db_no_detail') }}
              </div>
              <div class="ledger-sub">{{ item.member.pending_count || 0 }} {{ t('db_pending') }} · {{ t('db_since') }} {{ timeAgo(item.member.current_task_at || item.member.last_message_at || item.member.last_seen_at, locale) }}</div>
            </article>
          </div>
        </div>
      </section>

      <!-- Sessions -->
      <section class="panel">
        <div class="panel-head">
          <div class="panel-title">{{ t('db_active_sessions_title') }}</div>
          <div class="muted">{{ t('db_active_sessions_sub') }}</div>
        </div>
        <div class="panel-body">
          <div class="filter-row" style="margin-bottom:16px">
            <label class="inline-filter">
              <span>{{ t('db_filter_label') }}</span>
              <input v-model="dashboard.filterText.value" :placeholder="t('db_filter_placeholder')" />
            </label>
            <button type="button" class="filter-chip" :class="{ active: dashboard.issueMode.value }" @click="dashboard.issueMode.value = !dashboard.issueMode.value">
              {{ dashboard.issueMode.value ? t('db_issues_filter_on') : t('db_issues_filter_off') }}
            </button>
            <button type="button" class="ghost compact-action" @click="dashboard.resetFilters()">{{ t('db_reset_btn') }}</button>
          </div>
          <div v-if="!dashboard.filteredSessions.value.length" class="empty-state">
            <span>{{ (dashboard.filterText.value || dashboard.issueMode.value) ? t('db_no_filtered') : t('db_no_sessions') }}</span>
          </div>
          <div v-else class="session-grid">
            <article v-for="session in dashboard.filteredSessions.value" :key="session.session_id" class="session-card">
              <div class="session-head">
                <div>
                  <div class="session-title">{{ session.title || session.project || session.session_id }}</div>
                  <div class="session-sub">{{ t('db_session_sub', { chief: session.created_by ?? '-', members: String(session.member_count), pending: String(session.pending_total) }) }}</div>
                  <div class="session-sub">{{ t('db_session_last_activity', { value: timeAgo(session.last_event_at, locale) }) }}</div>
                </div>
                <router-link class="pill" :to="sessionDetailUrl(session)">{{ t('db_view_session') }}</router-link>
              </div>
              <div class="members">
                <div v-for="member in session.members" :key="member.agent_name" class="member">
                  <span class="status-dot" :class="String(member.status || '').toLowerCase()"></span>
                  <div class="member-top">
                    <div class="member-name">{{ member.agent_name }}</div>
                    <div class="member-meta">
                      <span class="pill">{{ translateRole(member.role) }}</span>
                      <span class="health-badge" :class="getHeartbeatState(member)">{{ heartbeatLabel(getHeartbeatState(member)) }}</span>
                      <span>{{ member.pending_count || 0 }} {{ t('db_pending') }}</span>
                    </div>
                  </div>
                </div>
              </div>
            </article>
          </div>
        </div>
      </section>

      <!-- Traces -->
      <section class="panel">
        <div class="panel-head">
          <div class="panel-title">{{ t('db_recent_traces_title') }}</div>
          <div class="muted">{{ t('db_recent_traces_sub') }}</div>
        </div>
        <div class="panel-body">
          <div v-if="!visibleTraces.length" class="empty-state">
            <span>{{ t('db_no_traces') }}</span>
          </div>
          <div v-else class="trace-log">
            <div v-for="(event, i) in visibleTraces" :key="i" class="trace-row">
              <div class="trace-head">
                <div style="display:flex;gap:8px;align-items:center">
                  <span class="trace-summary">{{ event.event || event.type || t('db_trace_fallback') }}</span>
                  <span class="muted" style="font-size:11px">{{ event.from || '' }} → {{ event.to || '' }}</span>
                </div>
                <div style="display:flex;gap:8px;align-items:center">
                  <span class="muted" style="font-size:11px">{{ timeAgo(event.ts, locale) }}</span>
                  <button class="trace-toggle" @click="toggleTrace(i)">▸ JSON</button>
                </div>
              </div>
              <pre v-if="expandedTraces.has(i)" class="trace-json">{{ JSON.stringify(event, null, 2) }}</pre>
            </div>
          </div>
        </div>
      </section>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, watchEffect } from 'vue'
import { useI18n, useTheme, ThemeToggle, LangToggle } from '@acp/shared'
import { messages } from '../i18n'
import { useDashboardOverview } from '../composables/useDashboardOverview'
import {
  timeAgo, shortLabel, roleGlyph, roleTone, statusTone,
  heartbeatState, heartbeatAgeSeconds, collectTaskLane,
  type TaskLaneItem,
} from '../composables/dashboardHelpers'
import type { MemberData, SessionData, TraceEvent } from '../api/overview'

const { locale, t } = useI18n(messages)
useTheme()

const dashboard = useDashboardOverview()

const showSub = ref(false)
const tokenInput = ref('')
const accessCompact = ref(false)
const expandedTraces = ref(new Set<number>())

const MAX_TRACES = 200

const overview = computed(() => dashboard.payload.value?.overview)
const hubFlags = computed(() => dashboard.payload.value?.hub)

const statusText = computed(() => {
  if (dashboard.statusMessage.value) return dashboard.statusMessage.value
  if (dashboard.locked.value) {
    return dashboard.tokenRequired.value ? t('db_token_required') : t('db_status_not_loaded')
  }
  if (overview.value) {
    return t('db_dashboard_loaded', { count: String(overview.value.session_count) })
  }
  return t('db_status_not_loaded')
})

const accessModeLabel = computed(() => {
  if (dashboard.tokenRequired.value && dashboard.authenticated.value) return t('db_access_mode_admin')
  if (dashboard.tokenRequired.value) return t('db_access_mode_locked')
  return t('db_access_mode_open')
})

const squadSessions = computed(() =>
  dashboard.filteredSessions.value.filter(s => s.members?.length)
)

const squadMapSvg = computed(() => {
  const graphSessions = squadSessions.value
  if (!graphSessions.length) return ''

  const cs = dashboard.connectedSet.value
  const width = 1080
  const rowHeight = 160
  const height = Math.max(260, graphSessions.length * rowHeight + 40)
  const nodes = new Map<string, { x: number; y: number; member: MemberData }>()
  let markup = ''

  graphSessions.forEach((session, si) => {
    const members = session.members || []
    const chiefName = session.created_by || members[0]?.agent_name || ''
    const chiefMember = members.find(m => m.agent_name === chiefName) || members[0]
    if (!chiefMember) return

    const rowY = 86 + si * rowHeight
    const chiefX = 190
    const others = members.filter(m => m.agent_name !== chiefMember.agent_name)

    markup += `<text class="squad-title" x="36" y="${rowY - 42}">${esc(shortLabel(session.title || session.project || session.session_id, 28))}</text>`
    markup += `<text class="squad-subtitle" x="36" y="${rowY - 24}">${esc(session.session_id)}</text>`

    nodes.set(chiefMember.agent_name, { x: chiefX, y: rowY, member: chiefMember })

    others.forEach((member, mi) => {
      const total = Math.max(1, others.length - 1)
      const baseX = others.length === 1 ? 760 : 470 + (mi * 460) / total
      const offset = others.length === 1 ? 0 : (mi % 2 === 0 ? -32 : 32)
      nodes.set(member.agent_name, { x: baseX, y: rowY + offset, member })
      markup += `<line class="signal-line" x1="${chiefX}" y1="${rowY}" x2="${baseX}" y2="${rowY + offset}" />`
    })
  })

  const traces = dashboard.traceEvents.value
  const routes = traces
    .filter(e => e.event === 'ROUTE' && nodes.has(e.from!) && nodes.has(e.to!) && e.from !== e.to)
    .slice(-10)

  routes.forEach((e, ri) => {
    const from = nodes.get(e.from!)!
    const to = nodes.get(e.to!)!
    markup += `<line class="signal-line route-pulse" style="animation-delay:${ri * 120}ms" x1="${from.x}" y1="${from.y}" x2="${to.x}" y2="${to.y}" />`
  })

  nodes.forEach(node => {
    const m = node.member
    const fill = roleTone(m.role)
    const cls = cs.has(m.agent_name) ? 'online' : 'offline'
    markup += `<g class="node-ring ${cls}">
      <circle class="node-shell" cx="${node.x}" cy="${node.y}" r="26"/>
      <circle cx="${node.x}" cy="${node.y}" r="18" fill="${fill}"/>
      <circle cx="${node.x + 20}" cy="${node.y - 18}" r="5" fill="${statusTone(m.status)}"/>
      <text class="node-glyph" x="${node.x}" y="${node.y + 4}" text-anchor="middle">${esc(roleGlyph(m.role))}</text>
      <text class="node-label" x="${node.x}" y="${node.y + 48}" text-anchor="middle">${esc(shortLabel(m.agent_name, 16))}</text>
      <text class="node-subtext" x="${node.x}" y="${node.y + 64}" text-anchor="middle">${esc(shortLabel(m.current_task || translateStatus(m.status), 22))}</text>
    </g>`
  })

  return `<svg viewBox="0 0 ${width} ${height}" role="img" aria-label="${esc(t('db_squad_map_title'))}">${markup}</svg>`
})

const hotTaskItems = computed(() => collectTaskLane(dashboard.filteredSessions.value))

const recoveryItems = computed(() => {
  const items: { kind: string; title: string; agent_name: string; session_label: string; ts?: string; state: string }[] = []
  const cs = dashboard.connectedSet.value

  for (const session of dashboard.filteredSessions.value) {
    for (const member of session.members || []) {
      const state = heartbeatState(member, cs)
      if (state !== 'quiet' && state !== 'stale') continue
      items.push({
        kind: `member_${state}`,
        title: state === 'stale' ? t('db_recovery_member_stale') : t('db_recovery_member_quiet'),
        agent_name: member.agent_name,
        session_label: session.title || session.project || session.session_id,
        ts: member.last_seen_at,
        state,
      })
    }
  }

  const traces = dashboard.traceEvents.value
  traces
    .filter(e => e && ['CONNECT', 'DISCONNECT', 'ERROR'].includes(String(e.event || '')))
    .slice(-6)
    .reverse()
    .forEach(e => {
      const ev = String(e.event || '')
      items.push({
        kind: `trace_${ev.toLowerCase()}`,
        title: ev === 'CONNECT' ? t('db_recovery_connect') : ev === 'DISCONNECT' ? t('db_recovery_disconnect') : t('db_recovery_error'),
        agent_name: e.name || e.from || e.to || '-',
        session_label: e.session || e.session_id || '-',
        ts: e.ts,
        state: ev === 'DISCONNECT' ? 'stale' : ev === 'ERROR' ? 'quiet' : 'live',
      })
    })

  return items.slice(0, 8)
})

const taskLedgerItems = computed(() => {
  const items: { session_id: string; session_label: string; member: MemberData }[] = []
  for (const session of dashboard.filteredSessions.value) {
    for (const member of session.members || []) {
      if (!member.current_task && !(member.pending_count || 0) && String(member.status || '').toLowerCase() === 'idle') continue
      items.push({
        session_id: session.session_id,
        session_label: session.title || session.project || session.session_id,
        member,
      })
    }
  }
  return items
})

const visibleTraces = computed(() =>
  dashboard.traceEvents.value.slice(-MAX_TRACES).reverse()
)

function translateStatus(value: string | undefined): string {
  const s = String(value || '').toLowerCase()
  if (s === 'idle') return t('db_metric_idle')
  if (s === 'waiting') return t('db_metric_waiting')
  if (s === 'busy') return t('db_metric_busy')
  return value || '-'
}

function translateRole(value: string | undefined): string {
  const r = String(value || '').toLowerCase()
  if (r === 'chief') return t('db_role_chief')
  if (r === 'collaborator') return t('db_role_collaborator')
  if (r === 'member') return t('db_role_member')
  return value || '-'
}

function heartbeatLabel(state: string): string {
  const s = state.toLowerCase()
  if (s === 'live') return t('db_heartbeat_live')
  if (s === 'quiet') return t('db_heartbeat_quiet')
  if (s === 'stale') return t('db_heartbeat_stale')
  return t('db_heartbeat_unknown')
}

function getHeartbeatState(member: MemberData): string {
  return heartbeatState(member, dashboard.connectedSet.value)
}

function heartbeatAgeSuffix(member: MemberData): string {
  const age = heartbeatAgeSeconds(member)
  return age === null ? '-' : `${age}s`
}

function sessionDetailUrl(session: SessionData): string {
  const params = new URLSearchParams({ session_id: session.session_id })
  return `/dashboard/session?${params.toString()}`
}

function esc(value: string): string {
  return value
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
}

function toggleTrace(index: number) {
  const s = new Set(expandedTraces.value)
  if (s.has(index)) s.delete(index)
  else s.add(index)
  expandedTraces.value = s
}

async function doLogin() {
  await dashboard.login(tokenInput.value.trim())
  if (dashboard.authenticated.value) {
    tokenInput.value = ''
    accessCompact.value = true
    dashboard.setStatus(t('db_admin_started'))
  }
}

async function doReload() {
  await dashboard.loadOverview()
  dashboard.startPolling()
}

async function doLogout() {
  await dashboard.logout()
  accessCompact.value = false
  dashboard.setStatus(t('db_admin_closed'))
}

watchEffect(() => {
  document.title = t('db_page_title')
})

watchEffect(() => {
  if (!dashboard.locked.value && overview.value) {
    accessCompact.value = dashboard.authenticated.value || !dashboard.tokenRequired.value
  }
})
</script>

<style src="../../../shared/src/tokens/dashboard.css"></style>
<style scoped>
.page { max-width: 1400px; margin: 0 auto; padding: 24px; position: relative; z-index: 1; }
.hero, .panel {
  background: var(--panel);
  border: 1px solid var(--line);
  border-radius: 20px;
  backdrop-filter: blur(16px);
  -webkit-backdrop-filter: blur(16px);
  box-shadow: var(--shadow-elev);
  transition: transform 0.25s cubic-bezier(0.16, 1, 0.3, 1), border-color 0.25s ease, box-shadow 0.25s ease;
}
.hero:hover, .panel:hover { border-color: var(--hover-line); }
.hero:hover { transform: translateY(-2px); box-shadow: var(--shadow-glow); }
.hero { padding: 16px 24px; margin-bottom: 20px; position: relative; overflow: hidden; }
.hero::before { content:''; position:absolute; top:0; left:0; right:0; height:1px; background:linear-gradient(90deg,transparent,var(--accent-glow),transparent); }
.hero-top { display:flex; justify-content:space-between; gap:16px; align-items:center; flex-wrap:wrap; }
.title { font-size:26px; font-weight:800; line-height:1.2; letter-spacing:-0.03em; background:linear-gradient(90deg,var(--title-start),var(--title-end)); -webkit-background-clip:text; -webkit-text-fill-color:transparent; }
.sub { margin-top:0; color:var(--muted); max-width:880px; line-height:1.6; font-size:13px; font-weight:300; display:none; }
.sub.show { display:block; }
.info-toggle { background:none; border:1px solid var(--line); color:var(--muted); width:32px; height:32px; border-radius:50%; font-size:14px; padding:0; display:inline-flex; align-items:center; justify-content:center; cursor:pointer; transition:all 0.2s ease; flex-shrink:0; }
.info-toggle:hover { color:var(--ink); border-color:var(--accent); background:var(--accent-glow); transform:rotate(90deg); }
.hero-controls { display:inline-flex; gap:10px; align-items:center; flex-wrap:wrap; }
.layout { display:grid; gap:24px; grid-template-columns:380px 1fr; }
.layout.locked { grid-template-columns:1fr; }
.panel-head { padding:14px 20px; border-bottom:1px solid var(--line); display:flex; justify-content:space-between; gap:10px; align-items:center; flex-wrap:wrap; }
.panel-title { font-weight:700; font-size:11px; text-transform:uppercase; letter-spacing:0.12em; color:var(--muted); position:relative; padding-left:12px; }
.panel-title::before { content:''; position:absolute; left:0; top:50%; transform:translateY(-50%); width:4px; height:4px; border-radius:50%; background:var(--accent); }
.panel-body { padding:18px; }
.stack { display:grid; gap:16px; }
.grid { display:grid; gap:16px; grid-template-columns:repeat(3, minmax(0,1fr)); }
.session-grid { display:grid; gap:16px; }
.filter-row { display:flex; gap:8px; flex-wrap:wrap; align-items:center; }
.filter-chip { background:var(--soft); color:var(--muted); border:1px solid var(--line); border-radius:999px; padding:6px 14px; font-size:11px; font-weight:700; cursor:pointer; transition:all 0.2s ease; }
.filter-chip:hover { color:var(--ink); border-color:var(--accent); }
.filter-chip.active { background:var(--accent); color:var(--button-ink); border-color:var(--accent); }
.inline-filter { display:inline-flex; align-items:center; gap:8px; color:var(--muted); font-size:11px; font-weight:700; letter-spacing:0.04em; text-transform:uppercase; }
.inline-filter input { min-width:180px; padding:8px 14px; border-radius:999px; font-size:13px; font-weight:500; text-transform:none; border:1px solid var(--line); background:var(--input-bg,transparent); color:var(--ink); outline:none; transition:all 0.2s ease; }
.inline-filter input:focus { border-color:var(--accent); box-shadow:0 0 0 3px var(--accent-glow); }
.compact-action { padding:8px 14px; font-size:11px; border-radius:10px; }
.cockpit-grid { display:grid; gap:16px; grid-template-columns:minmax(0,1.6fr) minmax(280px,0.9fr); }
.cockpit-card { border:1px solid var(--line); border-radius:18px; padding:20px; background:linear-gradient(180deg,var(--card-bg-soft),var(--soft)); position:relative; overflow:hidden; }
.cockpit-card::before { content:''; position:absolute; top:0; left:0; right:0; height:1px; background:linear-gradient(90deg,transparent,var(--accent-glow),transparent); }
.cockpit-head { display:flex; justify-content:space-between; gap:12px; align-items:flex-start; margin-bottom:16px; }
.cockpit-title { font-size:15px; font-weight:700; letter-spacing:-0.02em; }
.cockpit-sub { font-size:12px; color:var(--muted); line-height:1.5; margin-top:4px; }
.traffic-status { display:flex; gap:8px; flex-wrap:wrap; align-items:center; justify-content:flex-end; }
.traffic-chip { display:inline-flex; align-items:center; gap:6px; padding:6px 12px; border-radius:999px; border:1px solid var(--line); background:var(--soft); font-size:10px; font-weight:800; letter-spacing:0.05em; text-transform:uppercase; color:var(--muted); }
.traffic-chip.low { color:#34d399; border-color:rgba(52,211,153,0.22); background:rgba(16,185,129,0.08); }
.traffic-chip.medium { color:#fbbf24; border-color:rgba(251,191,36,0.24); background:rgba(251,191,36,0.1); }
.traffic-chip.high { color:#f87171; border-color:rgba(248,113,113,0.24); background:rgba(248,113,113,0.1); }
.traffic-chip.critical { color:#c084fc; border-color:rgba(192,132,252,0.24); background:rgba(192,132,252,0.1); }
.squad-map { min-height:340px; }
.squad-canvas { width:100%; min-height:340px; border:1px solid var(--canvas-border); border-radius:18px; background:radial-gradient(circle at top,var(--accent-glow),transparent 38%),linear-gradient(180deg,var(--canvas-top),var(--canvas-bottom)); overflow:hidden; position:relative; }
.squad-canvas :deep(svg) { width:100%; height:auto; display:block; }
.squad-canvas :deep(.squad-title) { font-size:12px; font-weight:700; fill:var(--ink); }
.squad-canvas :deep(.squad-subtitle) { font-size:11px; fill:var(--muted); }
.squad-canvas :deep(.node-label) { font-size:12px; font-weight:700; fill:var(--ink); }
.squad-canvas :deep(.node-subtext) { font-size:10px; fill:var(--muted); }
.squad-canvas :deep(.signal-line) { stroke:var(--signal-line); stroke-width:2; }
.squad-canvas :deep(.signal-line.route-pulse) { stroke:rgba(34,211,238,0.9); stroke-width:3; stroke-dasharray:8 10; stroke-linecap:round; animation:route-pulse 1.45s cubic-bezier(0.22,1,0.36,1) infinite; }
.squad-canvas :deep(.node-shell) { fill:var(--node-core); stroke:var(--shell-stroke); stroke-width:2; }
.squad-canvas :deep(.node-ring.online) { filter:drop-shadow(0 0 10px rgba(34,211,238,0.35)); }
.squad-canvas :deep(.node-ring.offline) { opacity:0.55; }
.squad-canvas :deep(.node-glyph) { font-size:11px; font-weight:800; fill:var(--glyph-ink); letter-spacing:0.06em; }
.lane-stack { display:grid; gap:12px; }
.lane-card { border:1px solid var(--line); border-radius:12px; padding:12px; background:var(--card-bg-strong); position:relative; overflow:hidden; transition:all 0.2s ease; }
.lane-card:hover { border-color:var(--accent); transform:translateY(-2px); box-shadow:var(--shadow-glow); }
.lane-top { display:flex; justify-content:space-between; gap:12px; align-items:center; }
.lane-title { font-size:14px; font-weight:700; }
.lane-role { display:inline-flex; align-items:center; justify-content:center; min-width:34px; height:26px; padding:0 10px; border-radius:999px; font-size:10px; font-weight:800; letter-spacing:0.08em; color:var(--glyph-ink); }
.lane-meta { margin-top:10px; font-size:11px; color:var(--muted); display:flex; flex-wrap:wrap; gap:10px; }
.lane-task { margin-top:12px; border-radius:12px; border:1px solid rgba(34,211,238,0.16); background:rgba(34,211,238,0.08); padding:14px; font-size:12px; line-height:1.6; }
.lane-task strong { color:var(--accent); }
.lane-session { font-size:11px; color:var(--muted); text-transform:uppercase; letter-spacing:0.08em; }
.recovery-stack { display:grid; gap:10px; margin-top:18px; }
.recovery-row { border:1px solid var(--line); border-radius:10px; padding:12px; background:var(--card-bg-soft); transition:all 0.2s ease; }
.recovery-row:hover { border-color:var(--hover-line); }
.recovery-title { font-size:12px; font-weight:700; }
.recovery-meta { margin-top:8px; color:var(--muted); font-size:11px; display:flex; gap:10px; flex-wrap:wrap; }
.task-ledger { display:grid; gap:12px; grid-template-columns:repeat(2, minmax(0,1fr)); }
.ledger-card { border:1px solid var(--line); border-radius:12px; padding:12px; background:var(--card-bg); transition:all 0.2s ease; }
.ledger-card:hover { border-color:var(--accent); transform:translateY(-2px); box-shadow:var(--shadow-glow); }
.ledger-top { display:flex; justify-content:space-between; gap:10px; align-items:center; }
.ledger-title { font-size:13px; font-weight:700; }
.ledger-sub { margin-top:8px; font-size:11px; color:var(--muted); }
.ledger-task { margin-top:12px; border-radius:10px; padding:12px 14px; background:var(--card-bg-soft); border:1px solid var(--line); font-size:12px; line-height:1.5; }
.health-badge { display:inline-flex; align-items:center; gap:6px; border-radius:999px; padding:4px 12px; font-size:10px; font-weight:700; letter-spacing:0.05em; border:1px solid transparent; }
.health-badge.live { color:#34d399; border-color:rgba(52,211,153,0.22); background:rgba(52,211,153,0.08); }
.health-badge.quiet { color:#fbbf24; border-color:rgba(251,191,36,0.22); background:rgba(251,191,36,0.08); }
.health-badge.stale { color:#f87171; border-color:rgba(248,113,113,0.22); background:rgba(248,113,113,0.08); }
.health-badge.unknown { color:#a1a1aa; border-color:rgba(161,161,170,0.22); background:rgba(161,161,170,0.08); }
.access-summary { display:none; align-items:center; justify-content:space-between; gap:16px; }
.access-summary-copy { min-width:0; display:grid; gap:6px; }
.access-summary-title { font-size:10px; font-weight:700; letter-spacing:0.12em; text-transform:uppercase; color:var(--muted); }
.access-summary-primary { font-size:16px; font-weight:800; letter-spacing:-0.02em; color:var(--ink); word-break:break-word; }
.access-summary-secondary { display:flex; gap:8px; flex-wrap:wrap; align-items:center; color:var(--muted); font-size:12px; }
.access-summary-chip { display:inline-flex; align-items:center; gap:6px; padding:5px 12px; border-radius:999px; border:1px solid var(--line); background:var(--soft); }
.access-form { display:block; }
.access-form-grid { display:grid; gap:12px; }
.access-actions { display:flex; gap:10px; flex-wrap:wrap; align-items:center; }
.access-panel.compact .access-summary { display:flex; }
.access-panel.compact .access-form { display:none; }
label { display:grid; gap:6px; font-size:12px; font-weight:500; color:var(--muted); }
input { width:100%; border:1px solid var(--line); border-radius:10px; padding:8px 12px; font:inherit; font-size:13px; background:var(--input-bg,transparent); color:var(--ink); transition:all 0.2s ease; outline:none; }
input:focus { border-color:var(--accent); box-shadow:0 0 0 3px var(--accent-glow); }
button { border:0; border-radius:10px; padding:9px 16px; font:inherit; font-size:13px; font-weight:600; background:var(--accent); color:var(--button-ink); cursor:pointer; transition:all 0.25s cubic-bezier(0.16,1,0.3,1); }
button:hover { background:var(--accent-hover); transform:translateY(-2px); box-shadow:0 6px 20px rgba(34,211,238,0.35); }
.ghost { background:var(--soft); color:var(--ink); border:1px solid var(--line); box-shadow:none; }
.ghost:hover { background:var(--trace-hover); border-color:var(--accent); box-shadow:var(--shadow-glow); transform:translateY(-1px); }
.muted { color:var(--muted); }
.pill { display:inline-flex; align-items:center; gap:6px; border-radius:999px; padding:4px 12px; font-size:10px; font-weight:700; letter-spacing:0.05em; background:var(--accent-soft); color:var(--accent); border:1px solid var(--accent-glow); text-decoration:none; }
.metric { border:1px solid var(--line); border-radius:12px; padding:14px 16px; background:var(--card-bg); position:relative; overflow:hidden; transition:all 0.2s ease; }
.metric:hover { border-color:var(--accent); transform:translateY(-2px); box-shadow:var(--shadow-glow); }
.metric-k { font-size:10px; font-weight:600; letter-spacing:0.08em; text-transform:uppercase; color:var(--muted); }
.metric-v { margin-top:6px; font-size:30px; font-weight:800; letter-spacing:-0.04em; color:var(--ink); }
.session-card, .trace-row { border:1px solid var(--line); border-radius:14px; padding:14px; background:var(--card-bg); transition:all 0.25s cubic-bezier(0.16,1,0.3,1); }
.session-card:hover, .trace-row:hover { border-color:var(--accent); transform:translateY(-3px); box-shadow:var(--shadow-glow); }
.session-head { display:flex; justify-content:space-between; gap:12px; align-items:flex-start; }
.session-title { font-weight:700; font-size:16px; letter-spacing:-0.01em; }
.session-sub { margin-top:6px; color:var(--muted); font-size:12px; }
.session-card .pill { background:transparent; border:1px solid var(--line); color:var(--ink); }
.session-card .pill:hover { background:var(--ink); color:var(--bg); border-color:var(--ink); }
.members { display:grid; gap:8px; margin-top:14px; }
.member { border:1px solid var(--line); border-radius:10px; padding:10px 14px; background:var(--card-bg-soft); display:flex; align-items:center; gap:10px; transition:all 0.2s ease; }
.member:hover { border-color:var(--hover-line); }
.member-top { display:flex; justify-content:space-between; gap:8px; align-items:center; flex:1; min-width:0; }
.member-name { font-weight:600; font-size:13px; color:var(--ink); white-space:nowrap; overflow:hidden; text-overflow:ellipsis; }
.member .pill { background:var(--chip-bg); color:var(--muted); border-color:var(--chip-border); font-size:10px; padding:3px 10px; }
.member-meta { font-size:11px; color:var(--muted); display:flex; gap:8px; align-items:center; white-space:nowrap; }
.status-dot { width:10px; height:10px; border-radius:50%; flex-shrink:0; }
.status-dot.idle { background:#34d399; box-shadow:0 0 8px #34d399; }
.status-dot.waiting { background:#fbbf24; box-shadow:0 0 8px #fbbf24; }
.status-dot.busy { background:#f87171; box-shadow:0 0 8px #f87171; }
.trace-log { display:grid; gap:10px; }
.trace-head { display:flex; justify-content:space-between; gap:8px; align-items:center; }
.trace-summary { font-weight:600; font-size:12px; letter-spacing:0.04em; color:var(--accent); }
.trace-json { margin-top:8px; padding:12px; border-radius:10px; border:1px solid var(--line); background:var(--card-bg-soft); font-family:'JetBrains Mono',monospace; font-size:11px; line-height:1.5; overflow-x:auto; white-space:pre-wrap; }
.trace-toggle { background:none; border:1px solid var(--line); color:var(--muted); font-size:11px; padding:6px 12px; border-radius:8px; cursor:pointer; font-weight:600; }
.trace-toggle:hover { color:var(--ink); border-color:var(--accent); transform:none; box-shadow:none; }
.status-line { font-size:13px; color:var(--muted); display:flex; align-items:center; gap:8px; }
.status-line.danger { color:var(--danger); }
.sections-stack { display:grid; gap:24px; margin-top:24px; }
.empty-state { display:flex; flex-direction:column; align-items:center; gap:16px; padding:60px 24px; text-align:center; }
.empty-state svg { opacity:0.25; }
.empty-state span { color:var(--muted); font-size:14px; }
.flag-chip { display:inline-flex; align-items:center; gap:8px; padding:8px 16px; border-radius:999px; font-size:12px; font-weight:600; border:1px solid var(--line); background:var(--card-bg-strong); color:var(--muted); }
.flag-icon { width:8px; height:8px; border-radius:50%; flex-shrink:0; }
.flag-icon.on { background:#34d399; box-shadow:0 0 8px #34d399; }
.flag-icon.off { background:#ef4444; box-shadow:0 0 8px rgba(239,68,68,0.4); }
.flag-icon.num { background:var(--accent); box-shadow:0 0 8px rgba(34,211,238,0.4); }
.hub-flags-row { display:flex; flex-wrap:wrap; gap:10px; }
.poll-spinner { display:inline-flex; align-items:center; justify-content:center; width:18px; height:18px; flex-shrink:0; }
.poll-spinner svg { width:16px; height:16px; color:var(--accent); opacity:0.6; animation:poll-spin 2.8s cubic-bezier(0.22,1,0.36,1) infinite; }
@keyframes poll-spin { 0% { transform:rotate(0deg); opacity:0.28; } 18% { opacity:0.82; } 76% { opacity:0.52; } 100% { transform:rotate(360deg); opacity:0.28; } }
@keyframes route-pulse { 0% { stroke-dashoffset:0; opacity:0.18; } 18% { opacity:0.95; } 100% { stroke-dashoffset:-36; opacity:0.24; } }

@media (max-width:1400px) { .page { max-width:1200px; } .grid { grid-template-columns:repeat(2,1fr); } }
@media (max-width:1200px) { .layout { grid-template-columns:340px 1fr; } .cockpit-grid { grid-template-columns:1fr; } .task-ledger { grid-template-columns:1fr; } }
@media (max-width:1080px) { .layout { grid-template-columns:1fr; } .grid { grid-template-columns:repeat(2,1fr); gap:12px; } }
@media (max-width:900px) { .page { padding:20px; } .hero { padding:20px; } .hero-top { flex-direction:column; align-items:flex-start; gap:16px; } .hero-controls { width:100%; } .metric-v { font-size:26px; } }
@media (max-width:768px) {
  .page { padding:16px; } .hero { padding:18px; border-radius:16px; }
  .panel-head { padding:14px 18px; flex-direction:column; align-items:flex-start; gap:10px; }
  .panel-body { padding:16px; } .title { font-size:22px; }
  .grid { grid-template-columns:1fr; gap:10px; } .task-ledger { grid-template-columns:1fr; }
  .metric-v { font-size:22px; } .session-head { flex-direction:column; gap:10px; }
  .member-top { flex-direction:column; align-items:flex-start; gap:6px; }
  .access-summary { flex-direction:column; align-items:stretch; }
  .access-actions { align-items:stretch; flex-direction:column; }
  .access-actions button { width:100%; }
  .traffic-status { justify-content:flex-start; }
  .cockpit-card { padding:16px; border-radius:14px; }
}
@media (max-width:600px) {
  .page { padding:12px; } .hero { padding:16px; border-radius:14px; } .title { font-size:20px; }
  .panel { border-radius:14px; } .panel-head { padding:12px 14px; } .panel-body { padding:14px; }
  .metric { padding:12px; border-radius:10px; } .metric-v { font-size:20px; }
  .squad-map { min-height:240px; } .squad-canvas { min-height:240px; }
}
@media (max-width:480px) {
  .page { padding:10px; } .hero { padding:14px; border-radius:12px; } .title { font-size:18px; }
  .panel { border-radius:12px; } .metric { padding:10px; border-radius:8px; } .metric-v { font-size:18px; }
  .cockpit-card { padding:12px; border-radius:12px; }
  .session-card { padding:10px; border-radius:10px; } .session-title { font-size:12px; }
}
@media (prefers-reduced-motion: reduce) {
  *, *::before, *::after { animation-duration:0.01ms !important; transition-duration:0.01ms !important; }
}
</style>
