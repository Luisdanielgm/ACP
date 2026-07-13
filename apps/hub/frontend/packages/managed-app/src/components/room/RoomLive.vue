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
          v-if="activitySpark.length"
          class="room-chip spark"
          :class="trafficLevel"
          :title="st('sd_traffic_recent_events', { count: String(session.trafficSnapshot.value.count) })"
        >
          <img class="spark-orb" :src="objectUrl('heartbeat-orb', 128)" alt="" aria-hidden="true" />
          <span class="spark-bars" aria-hidden="true">
            <i v-for="(h, i) in activitySpark" :key="i" :style="{ height: (2 + h * 13).toFixed(1) + 'px' }"></i>
          </span>
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
        <span class="room-chip clock" :title="t('room_clock_title')">
          <RoomIcon name="clock" :size="14" />{{ clockLabel }}
        </span>
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

    <div v-if="session.payload.value" class="room-shell">
      <!-- Pinned wall note: durable context stays visible without opening the dock -->
      <button
        v-if="pinnedPost"
        class="pinned-banner"
        type="button"
        :title="t('room_tab_wall')"
        @click="openDock('wall')"
      >
        <RoomIcon name="pin" :size="13" />
        <span class="pinned-banner-body">{{ pinnedPost.body }}</span>
        <span class="pinned-banner-meta">{{ pinnedPost.author_name }}</span>
      </button>

      <!-- Cockpit: map + lanes -->
      <div class="cockpit-grid">
        <div class="cockpit-left">
        <SquadMap
          :payload="session.payload.value"
          :connected-set="session.connectedSet.value"
          :traffic-level="trafficLevel"
          :admin-actions-available="session.adminActionsAvailable.value"
          :can-message="true"
          :fit-height="true"
          :inbox-agent="wsSession.owner_member_token ? wsSession.owner_agent_name : undefined"
          :receive-inbox="receiveInboxForMap"
          @invite="copyInvite"
          @send-message="sendInlineMessage"
          @disconnect-member="confirmDisconnect"
        >
          <template #status>
            <span v-for="chip in pulseChips" :key="chip.key" class="pulse-chip" :class="chip.className">{{ chip.label }}</span>
          </template>
          <template #tools>
            <div ref="roomToolsRef" class="room-tools">
              <button
                ref="roomToolsTriggerRef"
                class="map-tool room-tools-trigger"
                type="button"
                :aria-label="t('room_dock_label')"
                :title="t('room_dock_label')"
                aria-haspopup="dialog"
                aria-controls="room-tools-palette"
                :aria-expanded="roomToolsOpen"
                @click.stop="toggleRoomTools"
              >
                <span class="room-tools-glyph" aria-hidden="true">
                  <i v-for="index in 6" :key="index"></i>
                </span>
              </button>
            </div>
            <Teleport to="body">
              <div
                v-if="roomToolsOpen"
                id="room-tools-palette"
                ref="roomToolsPaletteRef"
                class="room-tools-palette"
                role="dialog"
                tabindex="-1"
                :aria-label="t('room_dock_label')"
                :style="roomToolsPaletteStyle"
                @click.stop
                @keydown="onRoomToolsPaletteKeydown"
              >
                <button
                  v-for="tab in dockTabs"
                  :key="tab.id"
                  class="room-tool-command"
                  type="button"
                  @click="openDockFromTools(tab.id)"
                >
                  <RoomIcon :name="tab.icon" :size="16" />
                  <span>{{ tab.label }}</span>
                  <span v-if="tab.badge !== undefined" class="dock-badge">{{ tab.badge }}</span>
                </button>
              </div>
            </Teleport>
          </template>
        </SquadMap>
        <!-- Real-time activity feed: sessions, messages, waits and detailed
             states, right under the live map -->
        <section class="feed-strip">
          <EventTimeline
            :events="session.filteredHistory.value"
            :members="session.members.value"
            v-model:timeline-filter="session.timelineFilter.value"
            :effective-motion="effectiveMotion"
            compact
            :compact-rows="3"
            @expand="openDock('timeline')"
          />
        </section>
        </div>
        <div class="cockpit-right">
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
          <!-- Legend: always visible, mockup-style, under the lanes -->
          <div class="signal-legend">
            <span class="legend-chip"><img class="legend-icon" :src="stateIconUrl('presence-online')" alt="" aria-hidden="true" />{{ st('sd_legend_connected') }}</span>
            <span class="legend-chip" :title="st('sd_legend_stale_help')"><img class="legend-icon" :src="stateIconUrl('presence-disconnected')" alt="" aria-hidden="true" />{{ st('sd_legend_stale') }}</span>
            <span class="legend-chip"><img class="legend-icon" :src="stateIconUrl('operation-working')" alt="" aria-hidden="true" />{{ st('sd_legend_working') }}</span>
            <span class="legend-chip"><img class="legend-icon" :src="stateIconUrl('message-task')" alt="" aria-hidden="true" />{{ st('sd_legend_task') }}</span>
            <span class="legend-chip"><img class="legend-icon" :src="stateIconUrl('message-information')" alt="" aria-hidden="true" />{{ st('sd_legend_info') }}</span>
            <span class="legend-chip"><img class="legend-icon" :src="stateIconUrl('message-response')" alt="" aria-hidden="true" />{{ st('sd_legend_reply') }}</span>
            <span class="legend-chip" :title="st('sd_legend_edge_fresh_help')"><img class="legend-icon" :src="stateIconUrl('link-current')" alt="" aria-hidden="true" />{{ st('sd_link_current') }}</span>
            <span class="legend-chip"><img class="legend-icon" :src="stateIconUrl('link-recent')" alt="" aria-hidden="true" />{{ st('sd_link_recent') }}</span>
            <span class="legend-chip" :title="st('sd_legend_edge_cooling_help')"><img class="legend-icon" :src="stateIconUrl('link-old')" alt="" aria-hidden="true" />{{ st('sd_link_old') }}</span>
            <span class="legend-chip"><img class="legend-icon" :src="stateIconUrl('link-expired')" alt="" aria-hidden="true" />{{ st('sd_link_expired') }}</span>
            <span class="legend-chip" :title="st('sd_legend_queued_help')"><img class="legend-icon" :src="stateIconUrl('result-pending')" alt="" aria-hidden="true" />{{ st('sd_legend_queued') }}</span>
          </div>
        </div>
      </div>

      <Teleport to="body">
        <div v-show="activeTab" class="dock-overlay" @click.self="closeDock">
          <section
            id="room-dock-dialog"
            ref="dockDialogRef"
            class="dock-panel"
            role="dialog"
            aria-modal="true"
            aria-labelledby="room-dock-title"
            tabindex="-1"
            @keydown="onDockKeydown"
          >
            <header class="dock-panel-head">
              <strong id="room-dock-title">{{ activeDockLabel }}</strong>
              <button class="icon-button" type="button" :aria-label="t('room_invite_close')" @click="closeDock">
                <RoomIcon name="x" :size="15" />
              </button>
            </header>
            <div class="dock-panel-scroll">
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
              <div v-show="activeTab === 'timeline'" class="dock-panel-inner bare timeline-drawer">
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
            </div>
          </section>
        </div>
      </Teleport>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed, nextTick, onUnmounted, ref, watch, watchEffect, type CSSProperties } from 'vue'
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
import { stateIconUrl, objectUrl } from '@acp/public-app/assets/acp/acpAssets'
import { sendSessionOperatorMessage, receiveSessionOperatorMessage, type RoomWallPost, type WorkspaceSession } from '../../api/managed'
import { getApiErrorMessage } from '../../api/client'
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

// Real "recent activity" sparkline: event counts bucketed over the last 2 min.
const activitySpark = computed<number[]>(() => {
  const p = session.payload.value
  if (!p) return []
  const now = Date.now()
  const BUCKETS = 14
  const SPAN = 120_000
  const buckets = new Array(BUCKETS).fill(0)
  for (const e of p.history || []) {
    const ts = Date.parse(String(e.ts || ''))
    if (Number.isNaN(ts)) continue
    const age = now - ts
    if (age < 0 || age > SPAN) continue
    const idx = Math.min(BUCKETS - 1, Math.floor(((SPAN - age) / SPAN) * BUCKETS))
    buckets[idx] += 1
  }
  const max = Math.max(1, ...buckets)
  return buckets.map(v => v / max)
})

const trafficLevel = computed(() => session.trafficSnapshot.value.level)
const effectiveMotion = computed(() => resolveEffectiveMode(trafficLevel.value))

// System clock in the room bar (mockup-style).
const clockLabel = ref(new Date().toLocaleTimeString())
const clockTimer = setInterval(() => {
  clockLabel.value = new Date().toLocaleTimeString()
}, 1000)

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

// Dock starts collapsed so the live cockpit (map + lanes) fills the viewport
// without the page scrolling; the user opens a panel on demand.
const activeTab = ref<DockTabId | null>(null)
const dockDialogRef = ref<HTMLElement | null>(null)
const dockReturnFocus = ref<HTMLElement | null>(null)
const roomToolsRef = ref<HTMLElement | null>(null)
const roomToolsTriggerRef = ref<HTMLButtonElement | null>(null)
const roomToolsPaletteRef = ref<HTMLElement | null>(null)
const roomToolsOpen = ref(false)
const roomToolsPaletteStyle = ref<CSSProperties>({ top: '0px', left: '0px', visibility: 'hidden' })
const wallCount = ref(0)
const filesCount = ref(0)
const pinnedPost = ref<RoomWallPost | null>(null)

// Direct send from the map popover — same owner identity as the operator tab.
async function sendInlineMessage(message: { to: string; action: 'TASK' | 'INFO' | 'REPLY'; payload: string }) {
  try {
    await sendSessionOperatorMessage(props.slug, props.sessionId, message)
    toast.show(st('sd_map_message_sent', { agent: message.to }), 'success')
  } catch (err) {
    toast.show(getApiErrorMessage(err), 'error')
  }
}

// Read the owner agent's next queued message from the map popover. Errors
// surface as toasts here; the popover only needs message-or-null.
async function receiveInboxForMap() {
  try {
    const result = await receiveSessionOperatorMessage(props.slug, props.sessionId, { timeout_seconds: 0.5 })
    return result.status === 'delivered' ? result.message : null
  } catch (err) {
    toast.show(getApiErrorMessage(err), 'error')
    return null
  }
}

const dockTabs = computed<DockTab[]>(() => [
  { id: 'wall', icon: 'pin', label: t('room_tab_wall'), badge: wallCount.value },
  { id: 'files', icon: 'folder', label: t('room_tab_files'), badge: filesCount.value },
  { id: 'operator', icon: 'send', label: t('room_tab_operator') },
  { id: 'team', icon: 'list', label: t('room_tab_team'), badge: session.members.value.length },
  { id: 'timeline', icon: 'activity', label: t('room_tab_timeline') },
  { id: 'json', icon: 'code', label: t('room_tab_json') },
])

const activeDockLabel = computed(() =>
  dockTabs.value.find(tab => tab.id === activeTab.value)?.label || ''
)

function toggleRoomTools() {
  if (roomToolsOpen.value) {
    closeRoomTools()
    return
  }
  roomToolsPaletteStyle.value = { top: '0px', left: '0px', visibility: 'hidden' }
  roomToolsOpen.value = true
}

function closeRoomTools(restoreFocus = false) {
  if (!roomToolsOpen.value) return
  roomToolsOpen.value = false
  if (restoreFocus) {
    nextTick(() => roomToolsTriggerRef.value?.focus())
  }
}

function openDockFromTools(id: DockTabId) {
  openDock(id, roomToolsTriggerRef.value)
}

function openDock(id: DockTabId, returnFocus?: HTMLElement | null) {
  roomToolsOpen.value = false
  dockReturnFocus.value = returnFocus
    || (document.activeElement instanceof HTMLElement ? document.activeElement : null)
  activeTab.value = id
  if (activeTab.value === 'json') session.showRawJson.value = true
}

function closeDock() {
  activeTab.value = null
}

function dockFocusable(): HTMLElement[] {
  if (!dockDialogRef.value) return []
  return [...dockDialogRef.value.querySelectorAll<HTMLElement>(
    'button:not([disabled]), [href], input:not([disabled]), select:not([disabled]), textarea:not([disabled]), [tabindex]:not([tabindex="-1"])'
  )].filter(element => !element.hidden && element.offsetParent !== null)
}

function onDockKeydown(event: KeyboardEvent) {
  if (event.key === 'Escape') {
    event.preventDefault()
    closeDock()
    return
  }
  if (event.key !== 'Tab' || !dockDialogRef.value) return
  const focusable = dockFocusable()
  if (!focusable.length) {
    event.preventDefault()
    dockDialogRef.value.focus()
    return
  }
  const first = focusable[0]
  const last = focusable[focusable.length - 1]
  if (document.activeElement === dockDialogRef.value || !dockDialogRef.value.contains(document.activeElement)) {
    event.preventDefault()
    ;(event.shiftKey ? last : first)?.focus()
  } else if (event.shiftKey && document.activeElement === first) {
    event.preventDefault()
    last?.focus()
  } else if (!event.shiftKey && document.activeElement === last) {
    event.preventDefault()
    first?.focus()
  }
}

watch(activeTab, async (tab, previous) => {
  if (tab) {
    await nextTick()
    const firstControl = dockFocusable()[0]
    if (firstControl) firstControl.focus()
    else dockDialogRef.value?.focus()
  } else if (previous) {
    await nextTick()
    dockReturnFocus.value?.focus()
    dockReturnFocus.value = null
  }
})

function onRoomToolsPointerDown(event: PointerEvent) {
  const target = event.target as Node
  if (roomToolsRef.value?.contains(target) || roomToolsPaletteRef.value?.contains(target)) return
  closeRoomTools()
}

function onRoomToolsKeydown(event: KeyboardEvent) {
  if (event.key !== 'Escape') return
  event.preventDefault()
  closeRoomTools(true)
}

function roomToolsFocusable(): HTMLButtonElement[] {
  if (!roomToolsPaletteRef.value) return []
  return [...roomToolsPaletteRef.value.querySelectorAll<HTMLButtonElement>(
    'button.room-tool-command:not([disabled])',
  )]
}

function onRoomToolsPaletteKeydown(event: KeyboardEvent) {
  if (event.key !== 'Tab' || !roomToolsPaletteRef.value) return
  const focusable = roomToolsFocusable()
  if (!focusable.length) {
    event.preventDefault()
    roomToolsPaletteRef.value.focus()
    return
  }

  const first = focusable[0]
  const last = focusable[focusable.length - 1]
  if (document.activeElement === roomToolsPaletteRef.value || !roomToolsPaletteRef.value.contains(document.activeElement)) {
    event.preventDefault()
    ;(event.shiftKey ? last : first)?.focus()
  } else if (event.shiftKey && document.activeElement === first) {
    event.preventDefault()
    last?.focus()
  } else if (!event.shiftKey && document.activeElement === last) {
    event.preventDefault()
    first?.focus()
  }
}

function positionRoomToolsPalette() {
  const trigger = roomToolsTriggerRef.value
  const palette = roomToolsPaletteRef.value
  if (!trigger || !palette) return

  const viewportPadding = 12
  const paletteGap = 8
  const triggerRect = trigger.getBoundingClientRect()
  const paletteWidth = palette.offsetWidth
  const paletteHeight = palette.offsetHeight
  const maxLeft = Math.max(viewportPadding, window.innerWidth - paletteWidth - viewportPadding)
  const left = Math.min(
    Math.max(viewportPadding, triggerRect.right - paletteWidth),
    maxLeft,
  )
  const belowTop = triggerRect.bottom + paletteGap
  const aboveTop = triggerRect.top - paletteGap - paletteHeight
  const maxTop = Math.max(viewportPadding, window.innerHeight - paletteHeight - viewportPadding)
  const top = belowTop + paletteHeight <= window.innerHeight - viewportPadding
    ? belowTop
    : aboveTop >= viewportPadding
      ? aboveTop
      : Math.min(Math.max(viewportPadding, belowTop), maxTop)

  roomToolsPaletteStyle.value = {
    top: `${Math.round(top)}px`,
    left: `${Math.round(left)}px`,
    visibility: 'visible',
  }
}

watch(roomToolsOpen, async open => {
  if (open) {
    document.addEventListener('pointerdown', onRoomToolsPointerDown)
    document.addEventListener('keydown', onRoomToolsKeydown)
    window.addEventListener('resize', positionRoomToolsPalette)
    window.addEventListener('scroll', positionRoomToolsPalette, true)
    await nextTick()
    positionRoomToolsPalette()
    await nextTick()
    const firstCommand = roomToolsFocusable()[0]
    if (firstCommand) firstCommand.focus()
    else roomToolsPaletteRef.value?.focus()
  } else {
    document.removeEventListener('pointerdown', onRoomToolsPointerDown)
    document.removeEventListener('keydown', onRoomToolsKeydown)
    window.removeEventListener('resize', positionRoomToolsPalette)
    window.removeEventListener('scroll', positionRoomToolsPalette, true)
  }
})

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
  document.removeEventListener('pointerdown', onRoomToolsPointerDown)
  document.removeEventListener('keydown', onRoomToolsKeydown)
  window.removeEventListener('resize', positionRoomToolsPalette)
  window.removeEventListener('scroll', positionRoomToolsPalette, true)
  clearInterval(clockTimer)
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
/* SessionRoomView owns the viewport height. Every descendant opts into
   min-height:0 so the cockpit consumes that contract instead of growing the
   document. */
.room { height:100%; min-height:0; position:relative; overflow:hidden; }
.room-shell {
  height:100%; min-height:0;
  display:grid;
  grid-template-rows:auto minmax(0, 1fr);
  gap:8px;
  overflow:hidden;
}

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

/* Recent-activity sparkline chip */
.room-chip.spark { padding: 4px 10px; color: #5DCAA5; }
.room-chip.spark.medium { color: #EF9F27; }
.room-chip.spark.high { color: #F0997B; }
.room-chip.spark.critical { color: #AFA9EC; }
.spark-orb { width: 16px; height: 16px; display: block; }
.spark-bars { display: inline-flex; align-items: flex-end; gap: 1.5px; height: 15px; }
.spark-bars i { width: 2px; border-radius: 1px; background: currentColor; opacity: 0.75; min-height: 2px; transition: height 0.4s ease; }

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
  position:absolute;
  z-index:20;
  top:6px;
  left:50%;
  width:min(720px, calc(100% - 24px));
  transform:translateX(-50%);
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

/* Pulse chips (rendered inside the map canvas via the status slot) */
.pulse-chip { display: inline-flex; align-items: center; gap: 6px; min-height: 26px; padding: 4px 12px; border-radius: 999px; border: 1px solid var(--line); background: var(--panel); backdrop-filter: blur(8px); -webkit-backdrop-filter: blur(8px); color: var(--muted); font-size: 10px; font-weight: 800; letter-spacing: 0.05em; text-transform: uppercase; }
.pulse-chip.task { color: #EF9F27; border-color: rgba(239, 159, 39, 0.24); background: rgba(239, 159, 39, 0.1); }
.pulse-chip.info { color: #85B7EB; border-color: rgba(133, 183, 235, 0.24); background: rgba(133, 183, 235, 0.1); }
.pulse-chip.reply { color: #AFA9EC; border-color: rgba(175, 169, 236, 0.24); background: rgba(175, 169, 236, 0.1); }
.pulse-chip.busy { color: #5DCAA5; border-color: rgba(93, 202, 165, 0.22); background: rgba(93, 202, 165, 0.1); }
.pulse-chip.immediate { color: #B5D4F4; border-color: rgba(181, 212, 244, 0.24); background: rgba(133, 183, 235, 0.08); }
.pulse-chip.queued { color: #EF9F27; border-color: rgba(239, 159, 39, 0.2); background: rgba(239, 159, 39, 0.08); opacity: 0.88; }
.pulse-chip.dequeued { color: #f8fafc; border-color: rgba(248, 250, 252, 0.22); background: rgba(148, 163, 184, 0.12); }

/* Cockpit — fills the remaining room height; each column manages its own overflow */
.cockpit-grid { display:grid; gap:10px; grid-template-columns:minmax(0, 1.55fr) minmax(410px, 0.9fr); min-height:0; overflow:hidden; }
.cockpit-grid > * { min-height: 0; }

/* Left column: live map on top, activity feed under it */
.cockpit-left { display:grid; grid-template-rows:minmax(0, 1fr) 148px; gap:10px; min-height:0; overflow:hidden; }
.cockpit-left > :first-child { min-height:0; }

/* Right column: ONE panel — lanes scroll inside, legend pinned at the bottom */
.cockpit-right {
  display: flex; flex-direction: column; gap: 10px; min-height: 0;
  border: 1px solid var(--line); border-radius: 18px;
  background: linear-gradient(180deg, var(--card-bg-soft), var(--soft));
  padding: 12px;
  overflow:hidden;
}
.cockpit-right > :first-child { flex: 1; min-height: 0; }
.cockpit-right :deep(.cockpit-card) { border: none; background: none; padding: 0; border-radius: 0; overflow: visible; }
.cockpit-right :deep(.cockpit-card::before) { display: none; }
.cockpit-right .signal-legend { border: none; border-top: 1px solid var(--line); border-radius: 0; background: transparent; padding: 12px 0 0; flex-shrink: 0; }

/* Activity feed strip: fixed-height recent rows, never another scroller. */
.feed-strip { min-height:0; overflow:hidden; border-radius:14px; }

/* Room-bar clock */
.room-chip.clock { font-variant-numeric: tabular-nums; }

/* Room tools: a compact in-map command palette replaces the height-consuming dock. */
.room-tools { position:relative; }
.room-tools-trigger {
  position:relative;
  display:inline-grid;
  place-items:center;
  width:30px;
  height:30px;
  padding:0;
  border:1px solid rgba(239,159,39,0.32);
  border-radius:50%;
  background:radial-gradient(circle at 35% 30%, rgba(239,159,39,0.22), rgba(239,159,39,0.06) 55%, var(--panel));
  color:#EF9F27;
  box-shadow:0 0 0 1px rgba(239,159,39,0.05), 0 0 16px rgba(239,159,39,0.1);
  backdrop-filter:blur(8px);
  -webkit-backdrop-filter:blur(8px);
  cursor:pointer;
  transition:all 0.15s ease;
}
.room-tools-trigger:hover,
.room-tools-trigger[aria-expanded="true"] { border-color:rgba(239,159,39,0.62); color:#F7B955; background:rgba(239,159,39,0.14); }
.room-tools-trigger:focus-visible,
.room-tool-command:focus-visible { outline:2px solid #EF9F27; outline-offset:2px; }
.room-tools-glyph { display:grid; grid-template-columns:repeat(3, 3px); gap:3px; }
.room-tools-glyph i { width:3px; height:3px; border-radius:50%; background:currentColor; box-shadow:0 0 5px currentColor; }
.room-tools-palette {
  position:fixed;
  z-index:205;
  width:min(252px, calc(100vw - 32px));
  display:grid;
  grid-template-columns:repeat(2, minmax(0, 1fr));
  gap:6px;
  padding:8px;
  border:1px solid rgba(239,159,39,0.26);
  border-radius:14px;
  background:var(--panel);
  box-shadow:0 18px 50px rgba(0,0,0,0.45), 0 0 24px rgba(239,159,39,0.07);
  backdrop-filter:blur(16px);
  -webkit-backdrop-filter:blur(16px);
}
.room-tool-command {
  min-width:0;
  min-height:42px;
  display:grid;
  grid-template-columns:18px minmax(0, 1fr) auto;
  align-items:center;
  gap:7px;
  padding:8px 9px;
  border:1px solid var(--line);
  border-radius:10px;
  background:var(--card-bg-soft);
  color:var(--muted);
  font-size:0.75rem;
  font-weight:750;
  text-align:left;
  cursor:pointer;
  transition:all 0.15s ease;
}
.room-tool-command:hover { color:var(--ink); border-color:rgba(239,159,39,0.36); background:rgba(239,159,39,0.08); }
.room-tool-command > span:not(.dock-badge) { overflow:hidden; text-overflow:ellipsis; white-space:nowrap; }
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
.dock-overlay {
  position:fixed;
  inset:0;
  z-index:210;
  display:flex;
  justify-content:flex-end;
  padding:94px 16px 16px;
  background:rgba(0,0,0,0.5);
  backdrop-filter:blur(4px);
  -webkit-backdrop-filter:blur(4px);
}
.dock-panel {
  width:min(760px, 100%);
  height:100%;
  min-height:0;
  display:grid;
  grid-template-rows:auto minmax(0, 1fr);
  border: 1px solid var(--line);
  border-radius: 18px;
  background: var(--panel);
  backdrop-filter: blur(16px);
  -webkit-backdrop-filter: blur(16px);
  box-shadow: var(--shadow-elev);
  overflow:hidden;
  outline:none;
}
.dock-panel:focus-visible { border-color:var(--accent); box-shadow:0 0 0 3px var(--accent-soft), var(--shadow-elev); }
.dock-panel-head { display:flex; align-items:center; gap:12px; padding:12px 14px; border-bottom:1px solid var(--line); }
.dock-panel-head strong { color:var(--ink); font-size:0.9rem; }
.dock-panel-head .icon-button { margin-left:auto; }
.dock-panel-scroll { min-height:0; overflow:auto; overscroll-behavior:contain; }
.dock-panel-inner { padding: 18px; }
.dock-panel-inner.bare { padding: 0; }
.dock-panel-inner.bare :deep(.panel) { border: none; background: transparent; box-shadow: none; backdrop-filter: none; -webkit-backdrop-filter: none; }

/* Motion accessibility */
html[data-motion="off"] .health-dot.polling { animation: none !important; }
html[data-motion="reduced"] .health-dot.polling { animation-duration: 2.4s !important; }

/* Responsive */
@media (max-width: 1200px) {
  .room { height:auto; overflow:visible; }
  .room-shell { height:auto; overflow:visible; grid-template-rows:auto; }
  .cockpit-grid { grid-template-columns:1fr; overflow:visible; }
  .cockpit-left { grid-template-rows:minmax(360px, 58vh) auto; overflow:visible; }
  .feed-strip { overflow:visible; }
}
@media (max-width: 900px) {
  .room-chips { display: none; }
}
@media (max-width: 768px) {
  .dock-overlay { padding:82px 10px 10px; }
}
@media (prefers-reduced-motion: reduce) {
  *, *::before, *::after { animation-duration: 0.01ms !important; transition-duration: 0.01ms !important; }
}
</style>
