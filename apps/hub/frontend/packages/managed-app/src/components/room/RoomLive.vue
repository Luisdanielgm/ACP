<template>
  <div class="room">
    <!-- Live bar: status, title, vital chips, admin actions -->
    <div class="room-bar">
      <span
        class="health-dot"
        :class="[session.healthState.value, { polling: session.polling.value }]"
        :title="st('sd_session_health_' + session.healthState.value)"
      ></span>
      <h1 class="room-title">{{ roomTitle }}</h1>

      <div class="room-chips">
        <span class="room-chip" :title="st('sd_members_meta')">
          <RoomIcon name="users" :size="14" />{{ memberCount }}
        </span>
        <span class="room-chip" :class="{ warn: pendingTotal > 0 }" :title="st('sd_pending_total_meta')">
          <RoomIcon name="inbox" :size="14" />{{ pendingTotal }}
        </span>
        <span class="room-chip" :title="st('sd_last_event_meta')">
          <RoomIcon name="clock" :size="14" />{{ lastEventLabel }}
        </span>
        <span
          class="room-chip traffic"
          :class="trafficLevel"
          :title="st('sd_traffic_recent_events', { count: String(session.trafficSnapshot.value.count) })"
        >
          {{ st('sd_traffic_level_' + trafficLevel) }}
        </span>
      </div>

      <div class="room-actions">
        <button
          class="icon-button"
          type="button"
          :class="{ active: legendOpen }"
          :aria-label="t('room_legend_toggle')"
          :title="t('room_legend_toggle')"
          :aria-pressed="legendOpen"
          @click="legendOpen = !legendOpen"
        >
          <RoomIcon name="info" :size="16" />
        </button>
        <template v-if="session.adminActionsAvailable.value">
          <button
            class="icon-button"
            type="button"
            :aria-label="st('sd_invite_prompt_btn')"
            :title="st('sd_invite_prompt_btn')"
            @click="copyInvite"
          >
            <RoomIcon name="user-plus" :size="16" />
          </button>
          <button
            class="icon-button danger"
            type="button"
            :aria-label="st('sd_close_session_btn')"
            :title="st('sd_close_session_btn')"
            @click="confirmCloseSession"
          >
            <RoomIcon name="power" :size="16" />
          </button>
        </template>
      </div>
    </div>

    <!-- Poll error strip -->
    <div v-if="session.statusIsError.value && session.statusMessage.value" class="room-error" role="alert">
      <span>{{ session.statusMessage.value }}</span>
      <button class="secondary-button" type="button" @click="retry">{{ t('room_live_retry') }}</button>
    </div>

    <!-- Initial load -->
    <div v-if="!session.payload.value && session.loading.value" class="room-loading" role="status">
      <span class="spinner" aria-hidden="true"></span>
      <span>{{ st('sd_session_waiting_load') }}</span>
    </div>

    <template v-if="session.payload.value">
      <!-- Signal legend (toggled from the bar) -->
      <div v-if="legendOpen" class="signal-legend">
        <span class="legend-chip"><span class="legend-line" style="background:#fbbf24"></span>{{ st('sd_legend_task') }}</span>
        <span class="legend-chip"><span class="legend-line" style="background:#22d3ee"></span>{{ st('sd_legend_info') }}</span>
        <span class="legend-chip"><span class="legend-line" style="background:#a78bfa"></span>{{ st('sd_legend_reply') }}</span>
        <span class="legend-chip">
          <span class="legend-work" aria-hidden="true"><span></span><span></span><span></span><span></span></span>
          {{ st('sd_legend_working') }}
        </span>
        <span class="legend-chip" :title="st('sd_legend_issue_low_help')"><span class="legend-dot" style="background:#c084fc"></span>{{ st('sd_legend_issue_low') }}</span>
        <span class="legend-chip" :title="st('sd_legend_issue_medium_help')"><span class="legend-dot" style="background:#fbbf24"></span>{{ st('sd_legend_issue_medium') }}</span>
        <span class="legend-chip" :title="st('sd_legend_issue_high_help')"><span class="legend-dot" style="background:#f87171"></span>{{ st('sd_legend_issue_high') }}</span>
      </div>

      <!-- Pulse strip: what is happening right now -->
      <div v-if="pulseChips.length" class="pulse-strip">
        <span v-for="chip in pulseChips" :key="chip.key" class="pulse-chip" :class="chip.className">{{ chip.label }}</span>
      </div>

      <!-- Cockpit: map + lanes -->
      <div class="cockpit-grid">
        <SquadMap
          :payload="session.payload.value"
          :connected-set="session.connectedSet.value"
          :traffic-level="trafficLevel"
        />
        <MemberLanes
          :members="session.visibleMembers.value"
          :activity-map="session.activityMap.value"
          :connected-set="session.connectedSet.value"
          :traffic-level="trafficLevel"
          :is-first-render="session.isFirstRender.value"
          :admin-actions-available="session.adminActionsAvailable.value"
          :problem-mode="session.problemMode.value"
          @disconnect-member="confirmDisconnect"
        />
      </div>

      <!-- Dock: collapsible room panels -->
      <nav class="dock" :aria-label="t('room_dock_label')">
        <button
          v-for="tab in dockTabs"
          :key="tab.id"
          class="dock-tab"
          type="button"
          :class="{ active: activeTab === tab.id }"
          :aria-expanded="activeTab === tab.id"
          @click="toggleTab(tab.id)"
        >
          <RoomIcon :name="tab.icon" :size="15" />
          <span class="dock-tab-label">{{ tab.label }}</span>
          <span v-if="tab.badge !== undefined" class="dock-badge">{{ tab.badge }}</span>
        </button>
      </nav>

      <section v-show="activeTab" class="dock-panel">
        <div v-show="activeTab === 'wall'" class="dock-panel-inner">
          <RoomWallPanel :slug="slug" :session-id="sessionId" @count="wallCount = $event" />
        </div>
        <div v-show="activeTab === 'files'" class="dock-panel-inner">
          <RoomFilesPanel :slug="slug" :session-id="sessionId" @count="filesCount = $event" />
        </div>
        <div v-show="activeTab === 'operator'" class="dock-panel-inner">
          <RoomOperatorPanel :slug="slug" :session-id="sessionId" :members="operatorMembers" />
        </div>
        <div v-show="activeTab === 'team'" class="dock-panel-inner bare">
          <MemberRoster
            :members="session.members.value"
            :visible-members="session.visibleMembers.value"
            :activity-map="session.activityMap.value"
            :connected-set="session.connectedSet.value"
            :is-first-render="session.isFirstRender.value"
            v-model:agent-filter="session.agentFilter.value"
            v-model:problem-mode="session.problemMode.value"
            :problem-summary="session.problemSummary.value"
          />
        </div>
        <div v-show="activeTab === 'timeline'" class="dock-panel-inner bare">
          <EventTimeline
            :events="session.filteredHistory.value"
            :members="session.members.value"
            v-model:timeline-filter="session.timelineFilter.value"
            :effective-motion="effectiveMotion"
          />
        </div>
        <div v-show="activeTab === 'json'" class="dock-panel-inner bare">
          <RawJsonPanel
            :payload="session.payload.value"
            v-model:show-raw-json="session.showRawJson.value"
          />
        </div>
      </section>
    </template>
  </div>
</template>

<script setup lang="ts">
import { computed, ref, watchEffect } from 'vue'
import { useI18n, useMotion } from '@acp/shared'
import {
  SquadMap,
  MemberLanes,
  MemberRoster,
  EventTimeline,
  RawJsonPanel,
  useSessionDashboard,
} from '@acp/public-app'
import { messages as sdMessages } from '@acp/public-app/i18n'
import {
  buildInvitePrompt,
  timeAgo,
  messageActionType,
  deliveryMode,
  actionChipClass,
  memberActivity,
} from '@acp/public-app/composables/sessionHelpers'
import { translateDelivery } from '@acp/public-app/composables/dashboardTranslations'
import type { WorkspaceSession } from '../../api/managed'
import { useManagedI18n } from '../../i18n'
import { useToast } from '../../composables/useToast'
import RoomIcon, { type RoomIconName } from './RoomIcon.vue'
import RoomWallPanel from './RoomWallPanel.vue'
import RoomFilesPanel from './RoomFilesPanel.vue'
import RoomOperatorPanel from './RoomOperatorPanel.vue'

const props = defineProps<{
  slug: string
  sessionId: string
  wsSession: WorkspaceSession
}>()

const { t } = useManagedI18n()
const { locale, t: st } = useI18n(sdMessages)
const toast = useToast()
const { resolveEffectiveMode, applyMotion } = useMotion()

// Owner member token grants live member access without putting the token in
// the URL. Without it, fall back to session-id-only (admin cookie) access.
const session = useSessionDashboard({
  authEndpoint: '/managed/dashboard/auth/session',
  redirectPath: '/managed/dashboard',
  context: props.wsSession.owner_member_token
    ? {
        sessionId: props.sessionId,
        agentName: props.wsSession.owner_agent_name,
        memberToken: props.wsSession.owner_member_token,
      }
    : { sessionId: props.sessionId },
})

// ── Live bar ──

const roomTitle = computed(() =>
  session.payload.value?.title
  || props.wsSession.title
  || props.wsSession.owner_agent_name
)

const memberCount = computed(() => {
  const p = session.payload.value
  return p?.summary?.member_count ?? p?.members?.length ?? 0
})

const pendingTotal = computed(() => session.payload.value?.summary?.pending_total ?? 0)

const lastEventLabel = computed(() => {
  const p = session.payload.value
  if (!p) return '-'
  return timeAgo(p.summary?.last_event_at || p.created_at, locale.value)
})

const trafficLevel = computed(() => session.trafficSnapshot.value.level)
const effectiveMotion = computed(() => resolveEffectiveMode(trafficLevel.value))
const legendOpen = ref(false)

const operatorMembers = computed(() =>
  session.members.value
    .map(member => member.agent_name)
    .filter(name => typeof name === 'string' && !name.startsWith('web-operator-'))
)

// ── Pulse strip ──

interface PulseChip {
  key: string
  label: string
  className: string
}

const pulseChips = computed(() => {
  const payload = session.payload.value
  if (!payload) return [] as PulseChip[]

  const recentEvents = (payload.history || []).filter(event => {
    const ts = Date.parse(String(event.ts || ''))
    return !Number.isNaN(ts) && (Date.now() - ts) <= 20000
  })

  const actionCounts = new Map<string, number>()
  const deliveryCounts = new Map<string, number>()
  for (const event of recentEvents) {
    const action = messageActionType(event)
    if (action) actionCounts.set(action, (actionCounts.get(action) || 0) + 1)
    const delivery = deliveryMode(event)
    if (delivery) deliveryCounts.set(delivery, (deliveryCounts.get(delivery) || 0) + 1)
  }

  const busyCount = session.members.value.filter(member => memberActivity(member, session.activityMap.value).isBusy).length
  const chips: PulseChip[] = []

  ;(['TASK', 'INFO', 'REPLY'] as const).forEach(action => {
    const count = actionCounts.get(action) || 0
    if (!count) return
    chips.push({
      key: `action-${action}`,
      label: `${st('sd_action_' + action)} ${count}`,
      className: actionChipClass(action),
    })
  })

  ;(['immediate', 'queued', 'dequeued'] as const).forEach(delivery => {
    const count = deliveryCounts.get(delivery) || 0
    if (!count) return
    chips.push({
      key: `delivery-${delivery}`,
      label: `${translateDelivery(st, delivery)} ${count}`,
      className: delivery,
    })
  })

  if (busyCount) {
    chips.push({
      key: 'busy-members',
      label: `${st('sd_activity_working')} ${busyCount}`,
      className: 'busy',
    })
  }

  return chips
})

// ── Dock ──

type DockTabId = 'wall' | 'files' | 'operator' | 'team' | 'timeline' | 'json'

interface DockTab {
  id: DockTabId
  icon: RoomIconName
  label: string
  badge?: number
}

const activeTab = ref<DockTabId | null>('wall')
const wallCount = ref(0)
const filesCount = ref(0)

const dockTabs = computed<DockTab[]>(() => [
  { id: 'wall', icon: 'pin', label: t('room_tab_wall'), badge: wallCount.value },
  { id: 'files', icon: 'folder', label: t('room_tab_files'), badge: filesCount.value },
  { id: 'operator', icon: 'send', label: t('room_tab_operator') },
  { id: 'team', icon: 'list', label: t('room_tab_team'), badge: session.members.value.length },
  { id: 'timeline', icon: 'activity', label: t('room_tab_timeline') },
  { id: 'json', icon: 'code', label: t('room_tab_json') },
])

function toggleTab(id: DockTabId) {
  activeTab.value = activeTab.value === id ? null : id
  if (activeTab.value === 'json') session.showRawJson.value = true
}

// ── Actions ──

async function copyValue(value: string, label: string) {
  try {
    await navigator.clipboard.writeText(value)
    toast.show(st('sd_copied_value', { label }), 'success')
  } catch {
    toast.show(st('sd_copy_failed', { label }), 'error')
  }
}

async function copyInvite() {
  if (!session.payload.value) return
  const text = buildInvitePrompt(session.payload.value, locale.value)
  copyValue(text, st('sd_invite_prompt_label'))
}

async function confirmCloseSession() {
  if (!confirm(st('sd_confirm_close_session'))) return
  const ok = await session.doCloseSession()
  if (ok) toast.show(st('sd_session_closed_admin'), 'success')
}

async function confirmDisconnect(agentName: string) {
  if (!confirm(st('sd_confirm_disconnect_member', { agent: agentName }))) return
  const ok = await session.doDisconnectMember(agentName)
  if (ok) toast.show(st('sd_member_disconnected_admin', { agent: agentName }), 'success')
}

function retry() {
  session.loadSession(true)
}

watchEffect(() => {
  applyMotion(trafficLevel.value)
})
</script>

<style scoped>
.room { display: flex; flex-direction: column; gap: 14px; }

/* Live bar */
.room-bar {
  position: sticky;
  top: 12px;
  z-index: 5;
  display: flex;
  align-items: center;
  gap: 12px;
  flex-wrap: wrap;
  padding: 12px 18px;
  border: 1px solid var(--line);
  border-radius: 18px;
  background: var(--panel);
  backdrop-filter: blur(16px);
  -webkit-backdrop-filter: blur(16px);
  box-shadow: var(--shadow-elev);
}
.room-title {
  margin: 0;
  font-size: 1.15rem;
  font-weight: 800;
  letter-spacing: -0.02em;
  color: var(--ink);
  min-width: 0;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.health-dot { width: 10px; height: 10px; border-radius: 50%; flex-shrink: 0; }
.health-dot.healthy { background: #34d399; box-shadow: 0 0 8px rgba(52, 211, 153, 0.5); }
.health-dot.warning { background: #fbbf24; box-shadow: 0 0 8px rgba(251, 191, 36, 0.5); }
.health-dot.critical { background: #f87171; box-shadow: 0 0 8px rgba(248, 113, 113, 0.5); }
.health-dot.polling { animation: health-pulse 2s ease-in-out infinite; }
@keyframes health-pulse {
  0%, 100% { transform: scale(1); opacity: 1; }
  50% { transform: scale(0.8); opacity: 0.6; }
}

.room-chips { display: inline-flex; gap: 6px; flex-wrap: wrap; align-items: center; }
.room-chip {
  display: inline-flex;
  align-items: center;
  gap: 5px;
  padding: 5px 11px;
  border-radius: 999px;
  border: 1px solid var(--line);
  background: var(--soft);
  color: var(--muted);
  font-size: 0.78rem;
  font-weight: 700;
}
.room-chip.warn { color: #fbbf24; border-color: rgba(251, 191, 36, 0.3); background: rgba(251, 191, 36, 0.08); }
.room-chip.traffic { text-transform: uppercase; letter-spacing: 0.05em; font-size: 0.68rem; }
.room-chip.traffic.low { color: #34d399; border-color: rgba(52, 211, 153, 0.22); background: rgba(16, 185, 129, 0.08); }
.room-chip.traffic.medium { color: #fbbf24; border-color: rgba(251, 191, 36, 0.24); background: rgba(251, 191, 36, 0.1); }
.room-chip.traffic.high { color: #f87171; border-color: rgba(248, 113, 113, 0.24); background: rgba(248, 113, 113, 0.1); }
.room-chip.traffic.critical { color: #c084fc; border-color: rgba(192, 132, 252, 0.24); background: rgba(192, 132, 252, 0.1); }

.room-actions { margin-left: auto; display: inline-flex; gap: 8px; }
.icon-button {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 34px;
  height: 34px;
  padding: 0;
  border: 1px solid var(--line);
  border-radius: 10px;
  background: transparent;
  color: var(--muted);
  cursor: pointer;
  transition: all 0.15s ease;
}
.icon-button:hover, .icon-button.active { color: var(--ink); border-color: var(--hover-line); background: var(--soft); }
.icon-button.danger:hover { color: #f87171; border-color: rgba(248, 113, 113, 0.4); background: rgba(248, 113, 113, 0.08); }

/* Error + loading */
.room-error {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  flex-wrap: wrap;
  padding: 10px 16px;
  border: 1px solid rgba(248, 113, 113, 0.3);
  border-radius: 14px;
  background: rgba(248, 113, 113, 0.08);
  color: #f87171;
  font-size: 0.88rem;
}
.room-loading {
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 12px;
  padding: 48px 24px;
  border: 1px solid var(--line);
  border-radius: 18px;
  background: var(--panel);
  color: var(--muted);
}

/* Signal legend */
.signal-legend { display: flex; flex-wrap: wrap; gap: 10px; padding: 12px 16px; border: 1px solid var(--line); border-radius: 12px; background: var(--card-bg-soft); }
.legend-chip { display: inline-flex; align-items: center; gap: 6px; font-size: 10px; font-weight: 700; color: var(--muted); letter-spacing: 0.05em; }
.legend-line { width: 18px; height: 3px; border-radius: 2px; }
.legend-dot { width: 8px; height: 8px; border-radius: 50%; }
.legend-work { display: inline-flex; align-items: flex-end; gap: 3px; height: 14px; }
.legend-work span { display: inline-block; width: 4px; border-radius: 999px; background: #34d399; animation: work-bars 1s steps(3, end) infinite; transform-origin: bottom; }
.legend-work span:nth-child(1) { height: 5px; animation-delay: 0s; }
.legend-work span:nth-child(2) { height: 11px; animation-delay: 0.16s; }
.legend-work span:nth-child(3) { height: 7px; animation-delay: 0.32s; }
.legend-work span:nth-child(4) { height: 12px; animation-delay: 0.48s; }
@keyframes work-bars { 0%, 100% { transform: scaleY(0.72); opacity: 0.52; } 45% { transform: scaleY(1.08); opacity: 1; } }

/* Pulse strip */
.pulse-strip { display: flex; flex-wrap: wrap; align-items: center; gap: 8px; }
.pulse-chip { display: inline-flex; align-items: center; gap: 6px; min-height: 26px; padding: 4px 12px; border-radius: 999px; border: 1px solid var(--line); background: var(--soft); color: var(--muted); font-size: 10px; font-weight: 800; letter-spacing: 0.05em; text-transform: uppercase; }
.pulse-chip.task { color: #fbbf24; border-color: rgba(251, 191, 36, 0.24); background: rgba(251, 191, 36, 0.1); }
.pulse-chip.info { color: #22d3ee; border-color: rgba(34, 211, 238, 0.24); background: rgba(34, 211, 238, 0.1); }
.pulse-chip.reply { color: #a78bfa; border-color: rgba(167, 139, 250, 0.24); background: rgba(167, 139, 250, 0.1); }
.pulse-chip.busy { color: #34d399; border-color: rgba(52, 211, 153, 0.22); background: rgba(52, 211, 153, 0.1); }
.pulse-chip.immediate { color: #67e8f9; border-color: rgba(103, 232, 249, 0.24); background: rgba(34, 211, 238, 0.08); }
.pulse-chip.queued { color: #fbbf24; border-color: rgba(251, 191, 36, 0.2); background: rgba(251, 191, 36, 0.08); opacity: 0.88; }
.pulse-chip.dequeued { color: #f8fafc; border-color: rgba(248, 250, 252, 0.22); background: rgba(148, 163, 184, 0.12); }

/* Cockpit */
.cockpit-grid { display: grid; gap: 14px; grid-template-columns: minmax(0, 1.6fr) minmax(280px, 0.9fr); }

/* Dock */
.dock { display: flex; gap: 6px; flex-wrap: wrap; align-items: center; }
.dock-tab {
  display: inline-flex;
  align-items: center;
  gap: 7px;
  padding: 9px 15px;
  border-radius: 999px;
  border: 1px solid var(--line);
  background: var(--soft);
  color: var(--muted);
  font-size: 0.82rem;
  font-weight: 700;
  cursor: pointer;
  transition: all 0.15s ease;
}
.dock-tab:hover { color: var(--ink); border-color: var(--hover-line); }
.dock-tab.active { color: var(--accent); border-color: var(--accent-glow); background: var(--accent-soft); }
.dock-badge {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  min-width: 18px;
  height: 18px;
  padding: 0 5px;
  border-radius: 999px;
  background: var(--card-bg);
  border: 1px solid var(--line);
  font-size: 0.68rem;
  font-weight: 800;
}
.dock-tab.active .dock-badge { border-color: var(--accent-glow); }

.dock-panel {
  border: 1px solid var(--line);
  border-radius: 18px;
  background: var(--panel);
  backdrop-filter: blur(16px);
  -webkit-backdrop-filter: blur(16px);
  box-shadow: var(--shadow-elev);
}
.dock-panel-inner { padding: 18px; }
.dock-panel-inner.bare { padding: 0; }
.dock-panel-inner.bare :deep(.panel) { border: none; background: transparent; box-shadow: none; backdrop-filter: none; -webkit-backdrop-filter: none; }

/* Motion accessibility */
html[data-motion="off"] .health-dot.polling,
html[data-motion="off"] .legend-work span { animation: none !important; }
html[data-motion="reduced"] .health-dot.polling,
html[data-motion="reduced"] .legend-work span { animation-duration: 2.4s !important; }

/* Responsive */
@media (max-width: 1200px) { .cockpit-grid { grid-template-columns: 1fr; } }
@media (max-width: 768px) {
  .room-bar { position: static; padding: 12px 14px; border-radius: 14px; }
  .room-title { white-space: normal; }
  .room-actions { margin-left: 0; }
  .dock-tab-label { display: none; }
  .dock-tab { padding: 9px 12px; }
}
@media (prefers-reduced-motion: reduce) {
  *, *::before, *::after { animation-duration: 0.01ms !important; transition-duration: 0.01ms !important; }
}
</style>
