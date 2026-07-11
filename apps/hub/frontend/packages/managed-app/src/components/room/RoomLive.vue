<template>
  <div class="room">
    <!-- Live bar: status, title, vital chips, admin actions.
         Rendered inside the shell topbar so the header IS the room. -->
    <Teleport to="#managed-topbar-session">
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
    </Teleport>

    <!-- Styled confirm dialog for destructive actions (close / disconnect) -->
    <ConfirmDialog
      :open="!!pendingConfirm"
      :title="pendingConfirm?.title || ''"
      :message="pendingConfirm?.message || ''"
      :confirm-label="pendingConfirm?.confirmLabel || ''"
      :cancel-label="t('room_cancel')"
      @confirm="runPendingConfirm"
      @cancel="pendingConfirm = null"
    />

    <!-- Invite prompt dialog: shows the full prompt (incl. session id) and copies it -->
    <div v-if="inviteOpen" class="invite-overlay" @click.self="inviteOpen = false">
      <div ref="inviteDialogRef" class="invite-dialog" role="dialog" aria-modal="true" tabindex="-1" :aria-label="t('room_invite_title')">
        <div class="invite-head">
          <RoomIcon name="user-plus" :size="16" />
          <strong>{{ t('room_invite_title') }}</strong>
          <button
            class="icon-button"
            type="button"
            :aria-label="t('room_invite_close')"
            @click="inviteOpen = false"
          >
            <RoomIcon name="x" :size="15" />
          </button>
        </div>
        <p class="invite-help">{{ t('room_invite_help') }}</p>
        <pre class="invite-text">{{ inviteText }}</pre>
        <div class="invite-actions">
          <button class="primary-button" type="button" @click="copyInviteText">
            {{ t('room_invite_copy') }}
          </button>
        </div>
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
        <span class="legend-chip"><img class="legend-icon" :src="stateIconUrl('presence-online')" alt="" aria-hidden="true" />{{ st('sd_legend_connected') }}</span>
        <span class="legend-chip" :title="st('sd_legend_stale_help')"><img class="legend-icon" :src="stateIconUrl('presence-disconnected')" alt="" aria-hidden="true" />{{ st('sd_legend_stale') }}</span>
        <span class="legend-chip"><img class="legend-icon" :src="stateIconUrl('operation-working')" alt="" aria-hidden="true" />{{ st('sd_legend_working') }}</span>
        <span class="legend-chip"><img class="legend-icon" :src="stateIconUrl('message-task')" alt="" aria-hidden="true" />{{ st('sd_legend_task') }}</span>
        <span class="legend-chip"><img class="legend-icon" :src="stateIconUrl('message-information')" alt="" aria-hidden="true" />{{ st('sd_legend_info') }}</span>
        <span class="legend-chip"><img class="legend-icon" :src="stateIconUrl('message-response')" alt="" aria-hidden="true" />{{ st('sd_legend_reply') }}</span>
        <span class="legend-chip" :title="st('sd_legend_edge_fresh_help')"><img class="legend-icon" :src="stateIconUrl('link-current')" alt="" aria-hidden="true" />{{ st('sd_legend_edge_fresh') }}</span>
        <span class="legend-chip" :title="st('sd_legend_edge_cooling_help')"><img class="legend-icon" :src="stateIconUrl('link-old')" alt="" aria-hidden="true" />{{ st('sd_legend_edge_cooling') }}</span>
        <span class="legend-chip" :title="st('sd_legend_queued_help')"><img class="legend-icon" :src="stateIconUrl('result-pending')" alt="" aria-hidden="true" />{{ st('sd_legend_queued') }}</span>
      </div>

      <!-- Pulse strip: what is happening right now -->
      <div v-if="pulseChips.length" class="pulse-strip">
        <span v-for="chip in pulseChips" :key="chip.key" class="pulse-chip" :class="chip.className">{{ chip.label }}</span>
      </div>

      <!-- Pinned wall note: durable context stays visible without opening the dock -->
      <button
        v-if="pinnedPost"
        class="pinned-banner"
        type="button"
        :title="t('room_tab_wall')"
        @click="activeTab = 'wall'"
      >
        <RoomIcon name="pin" :size="13" />
        <span class="pinned-banner-body">{{ pinnedPost.body }}</span>
        <span class="pinned-banner-meta">{{ pinnedPost.author_name }}</span>
      </button>

      <!-- Cockpit: map + lanes -->
      <div class="cockpit-grid">
        <SquadMap
          :payload="session.payload.value"
          :connected-set="session.connectedSet.value"
          :traffic-level="trafficLevel"
          :admin-actions-available="session.adminActionsAvailable.value"
          :can-message="true"
          @invite="copyInvite"
          @message-member="messageMember"
          @disconnect-member="confirmDisconnect"
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
          <RoomWallPanel
            :slug="slug"
            :session-id="sessionId"
            @count="wallCount = $event"
            @pinned="pinnedPost = $event"
          />
        </div>
        <div v-show="activeTab === 'files'" class="dock-panel-inner">
          <RoomFilesPanel :slug="slug" :session-id="sessionId" @count="filesCount = $event" />
        </div>
        <div v-show="activeTab === 'operator'" class="dock-panel-inner">
          <RoomOperatorPanel
            :slug="slug"
            :session-id="sessionId"
            :members="operatorMembers"
            :target="operatorTarget"
          />
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
import { computed, nextTick, onUnmounted, ref, watch, watchEffect } from 'vue'
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
import { stateIconUrl } from '@acp/public-app/assets/acp/acpAssets'
import type { RoomWallPost, WorkspaceSession } from '../../api/managed'
import { useManagedI18n } from '../../i18n'
import { useToast } from '../../composables/useToast'
import ConfirmDialog from '../ConfirmDialog.vue'
import RoomIcon, { type RoomIconName } from './RoomIcon.vue'
import RoomWallPanel from './RoomWallPanel.vue'
import RoomFilesPanel from './RoomFilesPanel.vue'
import RoomOperatorPanel from './RoomOperatorPanel.vue'

const props = defineProps<{
  slug: string
  sessionId: string
  wsSession: WorkspaceSession
}>()

const emit = defineEmits<{
  closed: []
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
const pinnedPost = ref<RoomWallPost | null>(null)
const operatorTarget = ref('')

function messageMember(agentName: string) {
  operatorTarget.value = agentName
  activeTab.value = 'operator'
}

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

const inviteOpen = ref(false)
const inviteText = ref('')
const inviteDialogRef = ref<HTMLElement | null>(null)

function onInviteKeydown(event: KeyboardEvent) {
  if (event.key === 'Escape') inviteOpen.value = false
}

watch(inviteOpen, async open => {
  if (open) {
    document.addEventListener('keydown', onInviteKeydown)
    await nextTick()
    inviteDialogRef.value?.focus()
  } else {
    document.removeEventListener('keydown', onInviteKeydown)
  }
})

onUnmounted(() => {
  document.removeEventListener('keydown', onInviteKeydown)
})

async function copyInvite() {
  if (!session.payload.value) return
  inviteText.value = buildInvitePrompt(session.payload.value, locale.value)
  inviteOpen.value = true
  copyValue(inviteText.value, st('sd_invite_prompt_label'))
}

function copyInviteText() {
  if (inviteText.value) copyValue(inviteText.value, st('sd_invite_prompt_label'))
}

// Styled confirmations instead of the browser's native confirm() popup.
interface PendingConfirm {
  title: string
  message: string
  confirmLabel: string
  run: () => Promise<void>
}

const pendingConfirm = ref<PendingConfirm | null>(null)

function confirmCloseSession() {
  pendingConfirm.value = {
    title: st('sd_close_session_btn'),
    message: st('sd_confirm_close_session'),
    confirmLabel: st('sd_close_session_btn'),
    run: async () => {
      const ok = await session.doCloseSession()
      if (ok) {
        toast.show(st('sd_session_closed_admin'), 'success')
        emit('closed')
      }
    },
  }
}

function confirmDisconnect(agentName: string) {
  pendingConfirm.value = {
    title: st('sd_disconnect_member_btn'),
    message: st('sd_confirm_disconnect_member', { agent: agentName }),
    confirmLabel: st('sd_disconnect_member_btn'),
    run: async () => {
      const ok = await session.doDisconnectMember(agentName)
      if (ok) toast.show(st('sd_member_disconnected_admin', { agent: agentName }), 'success')
    },
  }
}

async function runPendingConfirm() {
  const action = pendingConfirm.value
  pendingConfirm.value = null
  if (action) await action.run()
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

/* Live bar — teleported into the shell topbar, so no panel chrome of its own */
.room-bar {
  display: flex;
  align-items: center;
  gap: 12px;
  width: 100%;
  min-width: 0;
}
.room-title {
  margin: 0;
  font-size: 1.05rem;
  font-weight: 800;
  letter-spacing: -0.02em;
  color: var(--ink);
  min-width: 0;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.health-dot { width: 10px; height: 10px; border-radius: 50%; flex-shrink: 0; }
.health-dot.healthy { background: #5DCAA5; box-shadow: 0 0 8px rgba(93, 202, 165, 0.5); }
.health-dot.warning { background: #EF9F27; box-shadow: 0 0 8px rgba(239, 159, 39, 0.5); }
.health-dot.critical { background: #F0997B; box-shadow: 0 0 8px rgba(240, 153, 123, 0.5); }
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
.room-chip.warn { color: #EF9F27; border-color: rgba(239, 159, 39, 0.3); background: rgba(239, 159, 39, 0.08); }
.room-chip.traffic { text-transform: uppercase; letter-spacing: 0.05em; font-size: 0.68rem; }
.room-chip.traffic.low { color: #5DCAA5; border-color: rgba(93, 202, 165, 0.22); background: rgba(29, 158, 117, 0.08); }
.room-chip.traffic.medium { color: #EF9F27; border-color: rgba(239, 159, 39, 0.24); background: rgba(239, 159, 39, 0.1); }
.room-chip.traffic.high { color: #F0997B; border-color: rgba(240, 153, 123, 0.24); background: rgba(240, 153, 123, 0.1); }
.room-chip.traffic.critical { color: #AFA9EC; border-color: rgba(175, 169, 236, 0.24); background: rgba(175, 169, 236, 0.1); }

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
.icon-button.danger:hover { color: #F0997B; border-color: rgba(240, 153, 123, 0.4); background: rgba(240, 153, 123, 0.08); }

/* Invite dialog */
.invite-overlay {
  position: fixed;
  inset: 0;
  z-index: 200;
  display: grid;
  place-items: center;
  padding: 24px;
  background: rgba(0, 0, 0, 0.55);
  backdrop-filter: blur(4px);
  -webkit-backdrop-filter: blur(4px);
}
.invite-dialog {
  width: min(640px, 100%);
  max-height: 80vh;
  display: flex;
  flex-direction: column;
  gap: 10px;
  padding: 20px;
  border: 1px solid var(--line);
  border-radius: 18px;
  background: var(--bg);
  box-shadow: var(--shadow-elev);
}
.invite-head {
  display: flex;
  align-items: center;
  gap: 10px;
  color: var(--ink);
}
.invite-head .icon-button { margin-left: auto; }
.invite-help {
  margin: 0;
  color: var(--muted);
  font-size: 0.84rem;
}
.invite-text {
  margin: 0;
  padding: 14px;
  border: 1px solid var(--line);
  border-radius: 12px;
  background: var(--card-bg);
  color: var(--ink);
  font-size: 0.78rem;
  line-height: 1.5;
  white-space: pre-wrap;
  word-break: break-word;
  overflow: auto;
  flex: 1;
  min-height: 0;
}
.invite-actions {
  display: flex;
  justify-content: flex-end;
}

/* Error + loading */
.room-error {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  flex-wrap: wrap;
  padding: 10px 16px;
  border: 1px solid rgba(240, 153, 123, 0.3);
  border-radius: 14px;
  background: rgba(240, 153, 123, 0.08);
  color: #F0997B;
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
.legend-icon { width: 16px; height: 16px; display: block; flex-shrink: 0; }

/* Pinned wall banner */
.pinned-banner {
  display: flex;
  align-items: center;
  gap: 10px;
  width: 100%;
  padding: 9px 14px;
  border: 1px solid rgba(239, 159, 39, 0.28);
  border-radius: 12px;
  background: rgba(239, 159, 39, 0.07);
  color: var(--ink);
  font-size: 0.85rem;
  text-align: left;
  cursor: pointer;
  transition: all 0.15s ease;
}
.pinned-banner:hover { border-color: rgba(239, 159, 39, 0.5); }
.pinned-banner svg { color: #EF9F27; flex-shrink: 0; }
.pinned-banner-body {
  flex: 1;
  min-width: 0;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.pinned-banner-meta { color: var(--muted); font-size: 0.74rem; flex-shrink: 0; }

/* Pulse strip */
.pulse-strip { display: flex; flex-wrap: wrap; align-items: center; gap: 8px; }
.pulse-chip { display: inline-flex; align-items: center; gap: 6px; min-height: 26px; padding: 4px 12px; border-radius: 999px; border: 1px solid var(--line); background: var(--soft); color: var(--muted); font-size: 10px; font-weight: 800; letter-spacing: 0.05em; text-transform: uppercase; }
.pulse-chip.task { color: #EF9F27; border-color: rgba(239, 159, 39, 0.24); background: rgba(239, 159, 39, 0.1); }
.pulse-chip.info { color: #85B7EB; border-color: rgba(133, 183, 235, 0.24); background: rgba(133, 183, 235, 0.1); }
.pulse-chip.reply { color: #AFA9EC; border-color: rgba(175, 169, 236, 0.24); background: rgba(175, 169, 236, 0.1); }
.pulse-chip.busy { color: #5DCAA5; border-color: rgba(93, 202, 165, 0.22); background: rgba(93, 202, 165, 0.1); }
.pulse-chip.immediate { color: #B5D4F4; border-color: rgba(181, 212, 244, 0.24); background: rgba(133, 183, 235, 0.08); }
.pulse-chip.queued { color: #EF9F27; border-color: rgba(239, 159, 39, 0.2); background: rgba(239, 159, 39, 0.08); opacity: 0.88; }
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
html[data-motion="off"] .health-dot.polling { animation: none !important; }
html[data-motion="reduced"] .health-dot.polling { animation-duration: 2.4s !important; }

/* Responsive */
@media (max-width: 1200px) { .cockpit-grid { grid-template-columns: 1fr; } }
@media (max-width: 900px) {
  .room-chips { display: none; }
}
@media (max-width: 768px) {
  .dock-tab-label { display: none; }
  .dock-tab { padding: 9px 12px; }
}
@media (prefers-reduced-motion: reduce) {
  *, *::before, *::after { animation-duration: 0.01ms !important; transition-duration: 0.01ms !important; }
}
</style>
