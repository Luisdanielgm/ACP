<template>
  <div ref="cardRef" class="cockpit-card" :class="{ expanded, fit: fitHeight }" :data-load="trafficLevel">
    <div class="squad-map">
      <div v-if="!graph" class="empty-state">
        <span>{{ t('sd_map_empty') }}</span>
        <button v-if="payload" class="map-invite-cta" type="button" @click="$emit('invite')">
          {{ t('sd_invite_prompt_btn') }}
        </button>
      </div>
      <!--
        Template-rendered SVG with keyed elements: the DOM PERSISTS across the
        2s poll, so looping animations never restart mid-cycle, nodes GLIDE
        between orbits via a CSS transition, and per-event effects (envelope,
        ripples) play exactly once when their event first appears.
      -->
      <div v-else ref="canvasRef" class="squad-canvas" @click="onCanvasClick">
        <!-- In-canvas chrome: live status chips (top-left) and the expand
             toggle (top-right) live ON the map — the map needs no header. -->
        <div class="canvas-status">
          <slot name="status" />
        </div>
        <div class="canvas-tools">
          <slot name="tools" />
          <button
            class="map-tool canvas-expand"
            type="button"
            :aria-label="t(expanded ? 'sd_map_collapse' : 'sd_map_expand')"
            :title="t(expanded ? 'sd_map_collapse' : 'sd_map_expand')"
            @click.stop="expanded = !expanded"
          >
            <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">
              <template v-if="expanded">
                <path d="M18 6L6 18" /><path d="M6 6l12 12" />
              </template>
              <template v-else>
                <path d="M8 3H5a2 2 0 0 0-2 2v3" /><path d="M16 3h3a2 2 0 0 1 2 2v3" />
                <path d="M16 21h3a2 2 0 0 0 2-2v-3" /><path d="M8 21H5a2 2 0 0 1-2-2v-3" />
              </template>
            </svg>
          </button>
        </div>
        <svg :viewBox="`0 0 ${graph.width} ${graph.height}`" role="img" :aria-label="t('sd_squad_map_title')">
          <defs>
            <marker
              v-for="k in ['fresh', 'warm', 'cold', 'expired']"
              :key="'ea-' + k"
              :id="`edge-arrow-${k}`"
              viewBox="0 0 10 10"
              refX="7.5"
              refY="5"
              markerWidth="8"
              markerHeight="8"
              orient="auto-start-reverse"
            >
              <path class="edge-arrow" :class="k" d="M0 0 L10 5 L0 10 z" />
            </marker>
          </defs>

          <ellipse
            v-for="(ring, ri) in graph.rings"
            :key="'ring-' + ri"
            class="radar-ring"
            :cx="graph.cx"
            :cy="graph.cy"
            :rx="ring.rx"
            :ry="ring.ry"
          />

          <g v-for="edge in graph.edges" :key="edge.id" class="relation" :class="[edge.heat, edge.freshness, { held: edge.held }]">
            <title>{{ edge.title }}</title>
            <path :d="edge.path" :marker-end="`url(#edge-arrow-${edge.markerKey})`" />
            <image
              class="edge-icon"
              :href="edge.iconUrl"
              :x="edge.labelX - graph.orbSize / 2"
              :y="edge.labelY - graph.orbSize / 2"
              :width="graph.orbSize"
              :height="graph.orbSize"
            />
            <text
              v-if="edge.showLabel"
              class="relation-label"
              :class="edge.freshness"
              :x="edge.labelX"
              :y="edge.labelY - graph.orbSize / 2 - 9"
              text-anchor="middle"
            >{{ edge.label }}</text>
            <text
              v-if="edge.actionLabel"
              class="relation-action"
              :x="edge.labelX"
              :y="edge.labelY + graph.orbSize / 2 + 13"
              text-anchor="middle"
              :style="{ fill: edge.actionColor }"
            >{{ edge.actionLabel }}</text>
          </g>

          <circle
            v-for="dot in graph.queueDots"
            :key="dot.id"
            class="queue-dot"
            :cx="dot.x"
            :cy="dot.y"
            r="3"
            :style="{ animationDelay: dot.delay }"
          />

          <g
            v-for="node in graph.nodes"
            :key="node.name"
            class="node-pos"
            :data-agent="node.name"
            :style="{ transform: `translate(${node.x}px, ${node.y}px)` }"
          >
            <g
              class="node-ring"
              :class="node.classes"
              :style="{ '--member-accent': node.accent, '--dx': node.dx, '--dy': node.dy, animationDelay: node.driftDelay }"
            >
              <title>{{ node.title }}</title>
              <circle class="node-aura" :r="node.auraR" />
              <circle class="node-shell" :r="node.shellR" />
              <!-- Portrait clipped to the core; the warm accent stays on the ring. -->
              <image
                class="node-avatar"
                :class="{ ghost: node.isGhost }"
                :href="node.avatarUrl"
                :x="-node.coreR"
                :y="-node.coreR"
                :width="node.coreR * 2"
                :height="node.coreR * 2"
                :style="{ clipPath: `circle(${node.coreR}px at center)` }"
                preserveAspectRatio="xMidYMid slice"
              />
              <circle class="node-core-ring" :r="node.coreR" :style="{ stroke: node.accent }" />
              <circle
                v-if="node.showHalo"
                class="node-live-halo"
                :cx="node.shellR - 9"
                :cy="-node.shellR + 9"
                r="7"
                :style="{ stroke: node.statusColor }"
              />
              <!-- Presence badge (top-right) + operational badge (bottom-right) -->
              <image
                class="node-badge"
                :href="node.presenceUrl"
                :x="node.shellR - node.badgeSize"
                :y="-node.shellR"
                :width="node.badgeSize"
                :height="node.badgeSize"
              />
              <image
                v-if="!node.isOperator"
                class="node-badge"
                :href="node.operationUrl"
                :x="node.shellR - node.badgeSize"
                :y="node.shellR - node.badgeSize"
                :width="node.badgeSize"
                :height="node.badgeSize"
              />
              <g v-if="node.pending" class="node-pending" :transform="`translate(${-node.shellR + 4 * node.crownScale}, ${-node.shellR + 6 * node.crownScale}) scale(${node.crownScale})`">
                <circle r="9.5" />
                <text y="3.5" text-anchor="middle">{{ node.pendingLabel }}</text>
              </g>
              <image
                v-if="node.isChief"
                class="node-crown"
                :href="crownUrl"
                :x="-15 * node.crownScale"
                :y="-node.shellR - 26 * node.crownScale"
                :width="30 * node.crownScale"
                :height="24 * node.crownScale"
              />
              <!-- Domain role line (from the member's real name): glyph + label -->
              <g v-if="node.domainLabel" class="node-domain" :style="{ '--dom-accent': node.accent }">
                <path :d="node.domainGlyph" :transform="`translate(${node.domIconX}, ${node.domY - 9}) scale(${0.46 * node.labelScale})`" />
                <text :x="node.domTextX" :y="node.domY" :text-anchor="node.label.anchor" :font-size="9.5 * node.labelScale">{{ node.domainLabel }}</text>
              </g>
              <text class="node-label" :x="node.label.nameX" :y="node.label.nameY" :text-anchor="node.label.anchor" :font-size="15 * node.labelScale">
                <tspan :x="node.label.nameX" dy="0">{{ node.nameLines[0] }}</tspan>
                <tspan v-if="node.nameLines[1]" :x="node.label.nameX" :dy="14 * node.labelScale">{{ node.nameLines[1] }}</tspan>
              </text>
              <g class="node-state" :class="node.stateTone" :transform="`translate(${node.label.subX}, ${node.label.subY}) scale(${node.labelScale})`">
                <rect :x="node.statePillX" y="-11" :width="node.statePillW" height="16" rx="8" />
                <text x="0" y="1" :text-anchor="node.label.anchor">{{ node.stateLabel }}</text>
              </g>
              <g class="node-hb">
                <image :href="node.hbIconUrl" :x="node.hbIconX" :y="node.hbY - 14 * node.labelScale" :width="18 * node.labelScale" :height="18 * node.labelScale" />
                <text :x="node.hbTextX" :y="node.hbY" :text-anchor="node.label.anchor" :font-size="11.5 * node.labelScale">{{ node.hbLabel }}</text>
              </g>
              <g v-if="node.showQueue" class="node-queue">
                <rect class="node-queue-track" :x="node.queueX" :y="node.queueY" :width="node.queueW" height="5" rx="2.5" />
                <rect class="node-queue-fill" :x="node.queueX" :y="node.queueY" :width="node.queueFillW" height="5" rx="2.5" />
                <text class="node-queue-text" :x="node.queueX + node.queueW + 6" :y="node.queueY + 5.5">{{ node.pendingLabel }}</text>
              </g>
            </g>
          </g>

          <g v-for="flight in graph.flights" :key="flight.id" class="flight" :class="flight.classes" :style="{ '--impact-accent': flight.tone }">
            <defs>
              <marker :id="flight.markerId" viewBox="0 0 10 10" refX="7.5" refY="5" markerWidth="6.5" markerHeight="6.5" orient="auto-start-reverse">
                <path d="M0 0 L10 5 L0 10 z" :fill="flight.tone" />
              </marker>
            </defs>
            <!-- Route reads sender → receiver: dashes flow forward and an
                 arrowhead lands on the receiver; the sender flashes a ring. -->
            <path class="flight-route" :d="flight.path" :style="{ stroke: flight.tone }" :marker-end="`url(#${flight.markerId})`" />
            <circle class="flight-origin" :cx="flight.fromX" :cy="flight.fromY" r="6" :style="{ stroke: flight.tone }" />
            <circle class="flight-impact" :cx="flight.toX" :cy="flight.toY" r="20" />
            <g v-if="flight.tagLines.length" class="flight-tag" :transform="`translate(${flight.tagX}, ${flight.tagY})`">
              <rect class="node-float-pill" x="-4" y="-14" :width="flight.pillW" :height="flight.pillH" rx="10" />
              <text class="node-float-text" y="0" text-anchor="middle">
                <tspan v-for="(line, li) in flight.tagLines" :key="li" :x="flight.pillW / 2 - 4" :dy="li === 0 ? 0 : 13">{{ line }}</tspan>
              </text>
            </g>
            <g class="mail-glyph">
              <title>{{ flight.title }}</title>
              <g :transform="`scale(${flight.glyphScale})`">
                <rect x="-8" y="-5.5" width="16" height="11" rx="2.5" />
                <path d="M-8 -5.5 L0 1.5 L8 -5.5" />
              </g>
              <!-- SMIL clocks run on the SVG ROOT's timeline, not the element's
                   insertion time: with begin="0s" a late-mounted flight would
                   appear already frozen at its end. begin="indefinite" +
                   beginElement() on mount makes each envelope fly when ITS
                   event arrives. -->
              <animateMotion :ref="startFlightMotion" dur="1.35s" fill="freeze" begin="indefinite" :path="flight.path" />
            </g>
          </g>
        </svg>
      </div>
    </div>

    <!-- Member quick card: teleported to <body> with fixed positioning so the
         card's overflow:hidden can never clip it; its data recomputes live
         from the payload. -->
    <Teleport to="body">
    <div
      v-if="selectedMember"
      class="map-popover"
      :style="{ left: popoverX + 'px', top: popoverY + 'px' }"
      role="dialog"
      :aria-label="selectedMember.agent_name"
    >
      <div class="map-popover-head">
        <img class="map-popover-avatar" :src="selectedAvatarUrl" :alt="selectedMember.agent_name" :style="{ borderColor: selectedAccent }" />
        <div class="map-popover-id">
          <strong>{{ selectedDisplayName }}</strong>
          <span class="map-popover-full" :title="selectedMember.agent_name">{{ selectedMember.agent_name }}</span>
          <span class="map-popover-status">{{ translateStatus(t, selectedMember.status) || selectedMember.status }}</span>
        </div>
        <button class="map-tool" type="button" :aria-label="t('sd_map_close_popover')" @click="closePopover">
          <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" aria-hidden="true">
            <path d="M18 6L6 18" /><path d="M6 6l12 12" />
          </svg>
        </button>
      </div>
      <p v-if="selectedMember.current_task" class="map-popover-task">{{ selectedMember.current_task }}</p>
      <div class="map-popover-meta">
        <span class="map-popover-chip" :class="{ warn: Number(selectedMember.pending_count || 0) > 0 }">
          {{ t('sd_map_pending') }}: {{ selectedMember.pending_count || 0 }}
        </span>
        <span v-if="connectedSet.has(selectedMember.agent_name)" class="map-popover-chip live">{{ t('sd_legend_connected') }}</span>
        <span v-else-if="heartbeatState(selectedMember, connectedSet) === 'stale'" class="map-popover-chip stale">{{ t('sd_legend_stale') }}</span>
      </div>
      <!-- Inline inbox: read the next message queued for the owner agent. -->
      <div v-if="canReadInbox" class="map-popover-inbox">
        <button class="map-popover-btn" type="button" :disabled="inboxReading" @click="readInbox">
          {{ t('sd_map_read_btn') }}{{ Number(selectedMember.pending_count || 0) > 0 ? ` (${selectedMember.pending_count})` : '' }}
        </button>
        <p v-if="inboxEmpty" class="map-inbox-empty">{{ t('sd_map_inbox_empty') }}</p>
        <div v-else-if="inboxMessage" class="map-inbox-message">
          <div class="map-inbox-meta">
            <span class="map-inbox-action" :class="(inboxMessage.action || 'info').toLowerCase()">{{ inboxMessage.action || 'INFO' }}</span>
            <strong>{{ inboxMessage.from }}</strong>
          </div>
          <p class="map-inbox-body">{{ inboxMessage.payload }}</p>
        </div>
      </div>
      <!-- Inline send: message this agent right from the card, no dock trip. -->
      <div v-if="canMessage" class="map-popover-send">
        <div class="map-send-actions" role="radiogroup" :aria-label="t('sd_map_message_btn')">
          <button
            v-for="action in SEND_ACTIONS"
            :key="action"
            type="button"
            class="map-send-action"
            :class="[action.toLowerCase(), { active: sendAction === action }]"
            :aria-pressed="sendAction === action"
            @click="sendAction = action"
          >{{ action }}</button>
        </div>
        <textarea
          v-model="sendText"
          class="map-send-text"
          rows="2"
          :placeholder="t('sd_map_send_placeholder')"
          @keydown.enter.exact.prevent="submitSend"
        ></textarea>
      </div>
      <div v-if="canMessage || adminActionsAvailable" class="map-popover-actions">
        <button v-if="canMessage" class="map-popover-btn" type="button" :disabled="!sendText.trim()" @click="submitSend">
          {{ t('sd_map_message_btn') }}
        </button>
        <button v-if="adminActionsAvailable" class="map-popover-btn danger" type="button" @click="onDisconnectMember">
          {{ t('sd_disconnect_member_btn') }}
        </button>
      </div>
    </div>
    </Teleport>
  </div>
</template>

<script setup lang="ts">
import { computed, onUnmounted, ref, watch } from 'vue'
import { useI18n } from '@acp/shared'
import { messages } from '../../i18n'
import {
  normalizedRole, memberPalette, heartbeatState, statusTone, isWebOperator,
  messageActionType, actionChipClass, deliveryMode, deliveryClass, actionTone, floatTagLabel,
  domainForMember, domainGlyphPath,
  recentMemberActivity, memberActivity, mapRoutePath, sortedMembers,
  eventClass, hashValue, agentDisplayNames, humanizeAgentName, timeAgo, type TrafficLevel,
  avatarForMember, presenceIconName, operationIconName, memberOperationalState, memberIssues,
  heartbeatTier, heartbeatIconName, linkFreshness, type LinkFreshness,
} from '../../composables/sessionHelpers'
import { avatarUrl, stateIconUrl, objectUrl } from '../../assets/acp/acpAssets'
import { translateStatus, translateDisplayName } from '../../composables/dashboardTranslations'
import type { SessionMember, SessionDetailPayload } from '../../api/sessions'

export interface InboxMessage {
  from?: string
  action?: string
  payload?: string
  ts?: string
}

const props = defineProps<{
  payload: SessionDetailPayload | null
  connectedSet: Set<string>
  trafficLevel: TrafficLevel
  adminActionsAvailable?: boolean
  canMessage?: boolean
  fitHeight?: boolean
  /** Agent whose inbox the viewer can read (the dashboard-controlled owner). */
  inboxAgent?: string
  /** Reads the next queued message for inboxAgent; null when the inbox is empty. */
  receiveInbox?: () => Promise<InboxMessage | null>
}>()

const emit = defineEmits<{
  invite: []
  'send-message': [message: { to: string; action: 'TASK' | 'INFO' | 'REPLY'; payload: string }]
  'disconnect-member': [agentName: string]
}>()

const { locale, t } = useI18n(messages)

function clipText(value: string, max = 26): string {
  return value.length > max ? value.slice(0, max - 1) + '…' : value
}

// Wrap a floating tag onto up to two lines, breaking at a word boundary —
// longer previews stay readable without one endless pill.
function wrapTagText(text: string, maxLine = 34): string[] {
  if (text.length <= maxLine) return [text]
  let cut = text.lastIndexOf(' ', maxLine)
  if (cut < maxLine * 0.5) cut = maxLine
  const first = text.slice(0, cut).trim()
  let rest = text.slice(cut).trim()
  if (rest.length > maxLine) rest = rest.slice(0, maxLine - 1) + '…'
  return rest ? [first, rest] : [first]
}

const crownUrl = objectUrl('leader-crown', 128)

// ── War-room mode + member quick card ──

const cardRef = ref<HTMLElement | null>(null)
const canvasRef = ref<HTMLElement | null>(null)
const canvasSize = ref({ width: 0, height: 0 })
let canvasResizeObserver: ResizeObserver | null = null

function observeCanvas(element: HTMLElement | null) {
  canvasResizeObserver?.disconnect()
  canvasResizeObserver = null
  if (!element || typeof ResizeObserver === 'undefined') return
  const updateSize = () => {
    const rect = element.getBoundingClientRect()
    if (rect.width > 0 && rect.height > 0) {
      canvasSize.value = { width: rect.width, height: rect.height }
    }
  }
  canvasResizeObserver = new ResizeObserver(updateSize)
  canvasResizeObserver.observe(element)
  updateSize()
}

watch(canvasRef, observeCanvas, { flush: 'post' })
const expanded = ref(false)
const selectedName = ref('')
const popoverX = ref(0)
const popoverY = ref(0)

const selectedMember = computed<SessionMember | null>(() => {
  if (!selectedName.value) return null
  return props.payload?.members?.find(m => m.agent_name === selectedName.value) || null
})

const selectedAccent = computed(() => {
  const m = selectedMember.value
  if (!m) return 'transparent'
  return isWebOperator(m.agent_name) ? '#a1aab5' : memberPalette(m).accent
})

const selectedAvatarUrl = computed(() => {
  const m = selectedMember.value
  return m ? avatarUrl(avatarForMember(m), 256) : ''
})

const rosterDisplayNames = computed(() =>
  agentDisplayNames(
    (props.payload?.members || []).filter(m => !isWebOperator(m.agent_name)).map(m => m.agent_name)
  )
)

const selectedDisplayName = computed(() => {
  const name = selectedMember.value?.agent_name || ''
  return translateDisplayName(locale.value, rosterDisplayNames.value.get(name) || humanizeAgentName(name))
})

// ── Inline send form ──

const SEND_ACTIONS = ['TASK', 'INFO', 'REPLY'] as const
const sendAction = ref<'TASK' | 'INFO' | 'REPLY'>('INFO')
const sendText = ref('')

function submitSend() {
  const body = sendText.value.trim()
  const to = selectedName.value
  if (!body || !to) return
  emit('send-message', { to, action: sendAction.value, payload: body })
  sendText.value = ''
  closePopover()
}

// ── Inline inbox (owner agent only) ──

const canReadInbox = computed(() =>
  Boolean(props.receiveInbox && props.inboxAgent && selectedName.value === props.inboxAgent)
)
const inboxReading = ref(false)
const inboxMessage = ref<InboxMessage | null>(null)
const inboxEmpty = ref(false)

watch(selectedName, () => {
  inboxMessage.value = null
  inboxEmpty.value = false
})

async function readInbox() {
  if (!props.receiveInbox || inboxReading.value) return
  inboxReading.value = true
  inboxEmpty.value = false
  try {
    const message = await props.receiveInbox()
    if (message) {
      inboxMessage.value = message
    } else {
      inboxEmpty.value = true
    }
  } finally {
    inboxReading.value = false
  }
}

type FlightMotionEl = SVGElement & { beginElement?: () => void; __begun?: boolean }

// Function refs re-fire on every patch with the same element — the __begun
// flag makes the kick-off strictly once per mounted flight.
function startFlightMotion(el: unknown) {
  const node = el as FlightMotionEl | null
  if (!node || node.__begun || typeof node.beginElement !== 'function') return
  node.__begun = true
  try {
    node.beginElement()
  } catch {
    // SMIL unavailable (some headless engines): the envelope simply stays put.
  }
}

function onCanvasClick(event: MouseEvent) {
  const target = (event.target as HTMLElement).closest('[data-agent]')
  if (!target) return
  const agentName = target.getAttribute('data-agent') || ''
  if (!agentName) return
  const POPOVER_W = 280
  const POPOVER_H = 430
  popoverX.value = Math.max(8, Math.min(event.clientX + 8, window.innerWidth - POPOVER_W - 8))
  popoverY.value = Math.max(8, Math.min(event.clientY + 8, window.innerHeight - POPOVER_H - 8))
  selectedName.value = agentName
}

function closePopover() {
  selectedName.value = ''
}

function onDisconnectMember() {
  const name = selectedName.value
  closePopover()
  if (name) emit('disconnect-member', name)
}

function onDocumentClick(event: MouseEvent) {
  const target = event.target as HTMLElement
  if (target.closest('.map-popover') || target.closest('[data-agent]')) return
  closePopover()
}

function onKeydown(event: KeyboardEvent) {
  if (event.key !== 'Escape') return
  if (selectedName.value) {
    closePopover()
  } else if (expanded.value) {
    expanded.value = false
  }
}

watch([selectedName, expanded], ([name, isExpanded]) => {
  const active = Boolean(name) || isExpanded
  document.removeEventListener('click', onDocumentClick, true)
  document.removeEventListener('keydown', onKeydown)
  if (active) {
    document.addEventListener('click', onDocumentClick, true)
    document.addEventListener('keydown', onKeydown)
  }
})

onUnmounted(() => {
  document.removeEventListener('click', onDocumentClick, true)
  document.removeEventListener('keydown', onKeydown)
  canvasResizeObserver?.disconnect()
})

// ── Graph model ──

interface NodeLabel {
  anchor: 'start' | 'middle' | 'end'
  nameX: number
  nameY: number
  subX: number
  subY: number
  clip: number
}

// Labels sit on the OUTER side of each node (relative coordinates: the node
// group is translated to its position, so labels are offsets from 0,0).
function labelFor(ux: number, uy: number, shellR: number, isChief: boolean, ringSize: number, fitWide = false): NodeLabel {
  if (!isChief) {
    const sideThreshold = ringSize > 8 ? 0.25 : 0.55
    if (!fitWide && Math.abs(ux) > sideThreshold) {
      const side = ux > 0 ? 1 : -1
      const lx = side * (shellR + 16)
      return { anchor: side > 0 ? 'start' : 'end', nameX: lx, nameY: -2, subX: lx, subY: 16, clip: 20 }
    }
    if (uy < 0) {
      return { anchor: 'middle', nameX: 0, nameY: -shellR - 26, subX: 0, subY: -shellR - 10, clip: 26 }
    }
  }
  return { anchor: 'middle', nameX: 0, nameY: shellR + 22, subX: 0, subY: shellR + 39, clip: 26 }
}

// Long mixed-family names ("Aero Example Personal…") don't fit one line:
// split at a word boundary into at most two lines, ellipsizing the second.
function wrapNodeName(value: string, maxPerLine: number): string[] {
  const text = String(value || '').trim()
  if (text.length <= maxPerLine) return [text]
  const words = text.split(/\s+/)
  let first = ''
  for (const word of words) {
    const candidate = first ? `${first} ${word}` : word
    if (first && candidate.length > maxPerLine) break
    first = candidate
    if (first.length > maxPerLine) break
  }
  const rest = text.slice(first.length).trim()
  if (!rest) return [clipText(first, maxPerLine)]
  return [first, clipText(rest, maxPerLine)]
}

function pointToSegmentDistance(px: number, py: number, ax: number, ay: number, bx: number, by: number): number {
  const abx = bx - ax
  const aby = by - ay
  const lenSq = abx * abx + aby * aby
  if (lenSq === 0) return Math.hypot(px - ax, py - ay)
  const u = Math.max(0, Math.min(1, ((px - ax) * abx + (py - ay) * aby) / lenSq))
  return Math.hypot(px - (ax + abx * u), py - (ay + aby * u))
}

interface MapNode {
  name: string
  x: number
  y: number
  isChief: boolean
  isOperator: boolean
  isGhost: boolean
  busy: boolean
  classes: string
  accent: string
  statusColor: string
  showHalo: boolean
  pending: number
  pendingLabel: string
  avatarUrl: string
  presenceUrl: string
  operationUrl: string
  coreR: number
  shellR: number
  auraR: number
  badgeSize: number
  crownScale: number
  label: NodeLabel
  nameLines: string[]
  labelScale: number
  stateLabel: string
  stateTone: string
  statePillW: number
  statePillX: number
  domainLabel: string
  domainGlyph: string
  domIconX: number
  domTextX: number
  domY: number
  hbIconUrl: string
  hbLabel: string
  hbIconX: number
  hbTextX: number
  hbY: number
  showQueue: boolean
  queueX: number
  queueY: number
  queueW: number
  queueFillW: number
  title: string
  dx: string
  dy: string
  driftDelay: string
}

interface MapEdge {
  id: string
  path: string
  heat: 'fresh' | 'warm' | 'cold'
  held: boolean
  title: string
  freshness: LinkFreshness
  markerKey: string
  iconUrl: string
  showLabel: boolean
  label: string
  actionLabel: string
  actionColor: string
  labelX: number
  labelY: number
}

interface MapFlight {
  id: string
  markerId: string
  path: string
  tone: string
  classes: string
  title: string
  tagLines: string[]
  pillW: number
  pillH: number
  tagX: number
  tagY: number
  toX: number
  toY: number
  fromX: number
  fromY: number
  glyphScale: number
}

interface MapDot {
  id: string
  x: number
  y: number
  delay: string
}

const graph = computed(() => {
  const p = props.payload
  if (!p || !p.members?.length) return null

  const members = sortedMembers(p)
  const cs = props.connectedSet
  const activityMap = recentMemberActivity(p)

  const chiefMember = members.find(m => normalizedRole(m.role) === 'chief') || members[0]
  if (!chiefMember) return null

  const others = members.filter(m => m.agent_name !== chiefMember.agent_name)
  const now = Date.now()
  const EDGE_WINDOW = 10 * 60_000

  // ── Relationships from the actual message history: the map draws
  // CONVERSATIONS, not topology ──
  interface PairStat { a: string; b: string; lastTs: number; count: number; queuedTo: string; lastAction: string }
  const pairs = new Map<string, PairStat>()
  const lastActivity = new Map<string, number>()

  for (const event of p.history || []) {
    if (eventClass(String(event.event || '')) !== 'message') continue
    const actor = String(event.actor || '')
    const target = String(event.target || '')
    const ts = Date.parse(String(event.ts || ''))
    if (Number.isNaN(ts)) continue
    if (actor) lastActivity.set(actor, Math.max(lastActivity.get(actor) || 0, ts))
    if (target) lastActivity.set(target, Math.max(lastActivity.get(target) || 0, ts))
    if (!actor || !target || actor === target) continue
    const key = actor < target ? `${actor}|${target}` : `${target}|${actor}`
    const stat = pairs.get(key) || { a: actor, b: target, lastTs: 0, count: 0, queuedTo: '', lastAction: '' }
    stat.count += 1
    if (ts >= stat.lastTs) {
      stat.lastTs = ts
      stat.a = actor
      stat.b = target
      stat.lastAction = messageActionType(event) || stat.lastAction
    }
    if (deliveryMode(event) === 'queued') stat.queuedTo = target
    pairs.set(key, stat)
  }

  function activityTier(member: SessionMember): number {
    const age = now - (lastActivity.get(member.agent_name) || 0)
    let tier = age <= 90_000 ? 0 : age <= 5 * 60_000 ? 1 : 2
    // Unread work keeps a member close: they are part of a live relationship.
    if (Number(member.pending_count || 0) > 0) tier = Math.min(tier, 1)
    return tier
  }

  // The canvas adapts to the crowd: a 2-agent room gets a SMALL viewBox with
  // LARGE nodes (so it fills the card instead of two lost dots), a full room
  // gets the wide orbit. `scale` multiplies every node metric.
  const crowd = others.length
  // The ladder keeps shrinking as the room grows: label fonts follow via
  // labelScale so a 10-agent room reorganizes instead of colliding.
  const scale = crowd <= 2 ? 1.5 : crowd <= 4 ? 1.22 : crowd <= 6 ? 1 : crowd <= 9 ? 0.86 : 0.74
  const labelScale = Math.min(1, scale)
  // Mid-wire message orb: large enough to READ (mockup-sized), scales with the room.
  const orbSize = Math.round(36 * scale)
  const ringRadius = crowd ? Math.max(190, Math.min(320, 130 + crowd * 24)) : 0

  // Human-legible display names: drop the branding tokens every agent shares.
  const displayNames = rosterDisplayNames.value

  // Orbit radii ARE the semantics: inner = conversing, mid = recent or with
  // pending work, outer = quiet. The dashed rings mark those bands. Every
  // radius has a FLOOR of the scaled node sizes plus a clear gap, so big
  // nodes in a small room can never touch the chief.
  const tight = others.length > 6
  const chiefShellR = 38 * scale
  const memberShellR = 32 * scale
  const tier0 = Math.max(ringRadius * (tight ? 0.75 : 0.6), chiefShellR + memberShellR + 72 * scale)
  const tier1 = Math.max(ringRadius * (tight ? 0.9 : 0.82), tier0 + 46 * scale)
  const tier2 = Math.max(ringRadius * 1.05, tier1 + 40 * scale)
  const tierRadii = [tier0, tier1, tier2]

  // Angles stay STABLE (alphabetical) so members never swap places — only
  // their distance to the center glides as relationships heat and cool.
  const orbiting = [...others].sort((a, b) => a.agent_name.localeCompare(b.agent_name))
  const tiersByName = new Map(orbiting.map(member => [member.agent_name, activityTier(member)]))
  const maxTier = orbiting.length ? Math.max(...tiersByName.values()) : 0

  // The canvas hugs the outermost OCCUPIED orbit — an empty outer band is
  // dead space that shrinks every node on screen.
  const occupiedR = crowd ? tierRadii[maxTier] : 0
  const measuredAspect = canvasSize.value.height > 0
    ? canvasSize.value.width / canvasSize.value.height
    : 1.75
  const fitAspect = Math.max(1.25, Math.min(2.65, measuredAspect))
  const useAspectLayout = Boolean(props.fitHeight)
  const outerR = crowd ? occupiedR + memberShellR + 104 : 0
  const naturalGutterX = crowd <= 2 ? 280 : 420
  const naturalGutterY = crowd <= 2 ? 150 : 210
  const height = useAspectLayout
    ? 560
    : crowd ? Math.round(outerR * 2 + naturalGutterY) : 530
  const width = useAspectLayout
    ? Math.round(height * fitAspect)
    : crowd ? Math.round(outerR * 2 + naturalGutterX) : 1040
  const cx = width / 2
  const cy = useAspectLayout ? height * 0.46 : height / 2
  const targetStretchX = useAspectLayout ? Math.max(1.1, Math.min(1.55, fitAspect * 0.78)) : 1
  const targetStretchY = useAspectLayout ? 0.62 : 1
  const maxOrbitX = Math.max(1, width / 2 - memberShellR - 38)
  // Vertical budgets cover the FULL label stacks, not just the shell: above a
  // top node lives domain line + (wrapped) name (~64px); below a bottom node
  // lives name + pill + heartbeat (+wrap) (~96px).
  const maxOrbitY = Math.max(1, Math.min(cy - memberShellR - 76, height - cy - memberShellR - 96))
  const stretchX = crowd ? Math.min(targetStretchX, maxOrbitX / Math.max(1, occupiedR)) : 1
  const stretchY = crowd ? Math.min(targetStretchY, maxOrbitY / Math.max(1, occupiedR)) : 1
  const visibleRings = crowd ? tierRadii.slice(0, maxTier + 1) : [90, 150, 210]
  const rings = visibleRings.map(radius => ({ rx: radius * stretchX, ry: radius * stretchY }))

  const positions = new Map<string, { x: number; y: number; tier: number; member: SessionMember }>()
  positions.set(chiefMember.agent_name, { x: cx, y: cy, tier: 0, member: chiefMember })

  const startAngle = orbiting.length <= 2 ? 0 : -Math.PI / 2
  orbiting.forEach((member, mi) => {
    const angle = startAngle + (mi * 2 * Math.PI) / orbiting.length
    const tier = tiersByName.get(member.agent_name) ?? 2
    positions.set(member.agent_name, {
      x: cx + tierRadii[tier] * stretchX * Math.cos(angle),
      y: cy + tierRadii[tier] * stretchY * Math.sin(angle),
      tier,
      member,
    })
  })
  // The chief's label stack (name + pill + heartbeat) hangs ~104px below the
  // centre. A member that lands in the bottom-centre corridor would sit right
  // on top of it — push that node's Y past the stack instead of overlapping.
  const chiefStackBottomY = cy + chiefShellR + 72 * scale
  positions.forEach(pos => {
    if (pos.member.agent_name === chiefMember.agent_name) return
    if (Math.abs(pos.x - cx) >= 110 || pos.y <= cy) return
    const minY = chiefStackBottomY + memberShellR + 10
    if (pos.y < minY) pos.y = minY
  })

  // ── Relationship edges ──
  // Chief-involved edges radiate from the center and stay straight; edges
  // between two orbiting members ARC AWAY from the center so they never cut
  // through the chief sitting in the middle.
  const edges: MapEdge[] = []
  const shellOf = (name: string) => (name === chiefMember.agent_name ? 38 : 32) * scale
  pairs.forEach((pair, key) => {
    const na = positions.get(pair.a)
    const nb = positions.get(pair.b)
    if (!na || !nb) return
    const age = now - pair.lastTs
    const queuedTarget = pair.queuedTo ? positions.get(pair.queuedTo) : undefined
    const held = Boolean(queuedTarget && Number(queuedTarget.member.pending_count || 0) > 0)
    // The chief's spokes never vanish — they age into an "expired" wire (the
    // reference keeps VENCIDO links visible). Member-member arcs still fade
    // out past the window to keep the map uncluttered.
    const involvesChief = pair.a === chiefMember.agent_name || pair.b === chiefMember.agent_name
    if (age > EDGE_WINDOW && !held && !involvesChief) return
    let heat: MapEdge['heat'] = age <= 45_000 ? 'fresh' : age <= 3 * 60_000 ? 'warm' : 'cold'
    if (held && heat === 'cold') heat = 'warm'

    const freshness = linkFreshness(Math.round(age / 1000))
    // Trim the wire to the shell rims: the LAST-direction arrowhead must land
    // ON the receiver's frame, not vanish under the node circle drawn above.
    const dxE = nb.x - na.x
    const dyE = nb.y - na.y
    const distE = Math.hypot(dxE, dyE) || 1
    const uxE = dxE / distE
    const uyE = dyE / distE
    const ax = na.x + uxE * (shellOf(pair.a) + 4)
    const ay = na.y + uyE * (shellOf(pair.a) + 4)
    const bx = nb.x - uxE * (shellOf(pair.b) + 10)
    const by = nb.y - uyE * (shellOf(pair.b) + 10)
    let path: string
    let labelX: number
    let labelY: number
    if (involvesChief) {
      path = `M ${ax.toFixed(1)} ${ay.toFixed(1)} L ${bx.toFixed(1)} ${by.toFixed(1)}`
      labelX = (ax + bx) / 2
      labelY = (ay + by) / 2
    } else {
      const midX = (na.x + nb.x) / 2
      const midY = (na.y + nb.y) / 2
      // Bulge PERPENDICULAR to the segment — the only direction guaranteed to
      // lift the curve off the chord ("away from center" degenerates to along
      // the chord when opposed nodes sit at different orbit radii). Sign
      // points away from the center; on a dead tie, prefer UP (only the crown
      // sits above the chief).
      let px = -(nb.y - na.y)
      let py = nb.x - na.x
      const plen = Math.hypot(px, py) || 1
      const dot = px * (midX - cx) + py * (midY - cy)
      if (dot < 0 || (dot === 0 && py > 0)) {
        px = -px
        py = -py
      }
      // A quadratic bezier only deviates HALF its control offset at the
      // midpoint, so the offset is 2× the clearance still missing. 100px of
      // clearance comfortably clears the chief's shell, crown, and label.
      const clearance = pointToSegmentDistance(cx, cy, na.x, na.y, nb.x, nb.y)
      const bulge = 2 * Math.max(16, 100 - clearance)
      const ctrlX = midX + (px / plen) * bulge
      const ctrlY = midY + (py / plen) * bulge
      path = `M ${ax.toFixed(1)} ${ay.toFixed(1)} Q ${ctrlX.toFixed(1)} ${ctrlY.toFixed(1)} ${bx.toFixed(1)} ${by.toFixed(1)}`
      // Quadratic bezier midpoint (t=0.5): 0.25·A + 0.5·ctrl + 0.25·B.
      labelX = 0.25 * ax + 0.5 * ctrlX + 0.25 * bx
      labelY = 0.25 * ay + 0.5 * ctrlY + 0.25 * by
    }
    // Mid-wire orb: the LAST message type on this relationship — the kit's 3D
    // message orbs, exactly the mockup's floating ℹ/✓/✉ spheres.
    const lastAction = pair.lastAction
    const edgeOrb =
      lastAction === 'TASK' ? 'task-orb'
      : lastAction === 'REPLY' ? 'response-orb'
      : lastAction === 'INFO' ? 'information-orb'
      : 'system-orb'
    // Only the chief's spokes carry a freshness label — mirrors the reference
    // and keeps member-member arcs uncluttered (their heat colour already reads).
    edges.push({
      id: key, path, heat, held, freshness,
      markerKey: freshness === 'expired' ? 'expired' : heat,
      iconUrl: objectUrl(edgeOrb, 128),
      showLabel: involvesChief,
      label: t('sd_link_' + freshness),
      // What travelled last on this wire, spelled out under the orb so the
      // send/return direction reads at a glance (mockup's "TAREA / ORDEN").
      actionLabel: involvesChief && lastAction ? t('sd_action_' + lastAction) : '',
      actionColor: actionTone(lastAction),
      labelX, labelY,
      title: `${pair.a} ⇄ ${pair.b} · ${pair.count}`,
    })
  })

  // Pending messages queue up as amber dots on the freshest INBOUND edge of
  // the member with unread work.
  const inbound = new Map<string, PairStat>()
  pairs.forEach(pair => {
    const current = inbound.get(pair.b)
    if (!current || pair.lastTs > current.lastTs) inbound.set(pair.b, pair)
  })
  const queueDots: MapDot[] = []
  positions.forEach(pos => {
    const pendingN = Math.min(5, Number(pos.member.pending_count || 0))
    if (!pendingN) return
    const pair = inbound.get(pos.member.agent_name)
    if (!pair) return
    const from = positions.get(pair.a === pos.member.agent_name ? pair.b : pair.a)
    if (!from) return
    for (let d = 0; d < pendingN; d++) {
      const tPos = 0.82 - d * 0.07
      queueDots.push({
        id: `${pos.member.agent_name}-q${d}`,
        x: from.x + (pos.x - from.x) * tPos,
        y: from.y + (pos.y - from.y) * tPos,
        delay: `${(d * 0.18).toFixed(2)}s`,
      })
    }
  })

  // ── Per-event flights: keyed by the full event identity (ts + type +
  // endpoints — SENT and DELIVERED of the same message must not collide), so
  // each one mounts ONCE, flies its envelope once, ripples once, and expires
  // when it leaves the 30s window ──
  const flights: MapFlight[] = []
  const seenFlightIds = new Set<string>()
  const flightEvents = (p.history || []).filter(event => {
    if (eventClass(String(event.event || '')) !== 'message') return false
    if (!event.actor || !event.target || event.actor === event.target) return false
    const ts = Date.parse(String(event.ts || ''))
    return !Number.isNaN(ts) && now - ts <= 30_000
  })
  flightEvents.slice(-4).forEach((event, ri) => {
    const actorName = String(event.actor || '')
    const targetName = String(event.target || '')
    const from = positions.get(actorName)
    if (!from) return
    // A broadcast ("all") fans out to every other member at once.
    const isBroadcast = targetName.toLowerCase() === 'all' || targetName === '*'
    const destinations = isBroadcast
      ? [...positions.keys()].filter(name => name !== actorName).slice(0, 6)
      : [targetName]
    for (const destination of destinations) {
    const to = positions.get(destination)
    if (!to) continue
    const id = `${event.ts}|${event.event}|${event.actor}|${destination}`
    if (seenFlightIds.has(id)) continue
    seenFlightIds.add(id)
    const ts = Date.parse(String(event.ts || ''))
    // Curvature seed derives from the event itself, not the slice index, so a
    // flight's route never changes shape as the window slides under it.
    const seed = Number.isNaN(ts) ? ri : Math.abs(ts) % 6
    const action = messageActionType(event)
    const delivery = deliveryMode(event)
    const preview = clipText(String(event.payload_preview || '').trim(), 64)
    // On a broadcast only the FIRST destination carries the floating tag —
    // six identical pills at once would bury the map.
    const showTag = !isBroadcast || destination === destinations[0]
    const tag = showTag
      ? (preview ? `${floatTagLabel(action, delivery)} ${preview}` : floatTagLabel(action, delivery))
      : ''
    const tagLines = tag ? wrapTagText(tag) : []
    const longestLine = tagLines.reduce((max, line) => Math.max(max, line.length), 0)
    const pillW = Math.max(42, 14 + longestLine * 5.6)
    const pillH = 20 + (tagLines.length - 1) * 13
    // The tag floats ABOVE the receiver, clear of its shell and clamped to the
    // canvas, so it never covers the node it lands on.
    const receiverShell = (destination === chiefMember.agent_name ? 38 : 32) * scale
    flights.push({
      id,
      markerId: `fm${hashValue(id)}`,
      path: mapRoutePath(from, to, seed),
      tone: actionTone(action),
      classes: `${actionChipClass(action)} ${deliveryClass(delivery)}`,
      title: preview ? `${action || 'MSG'} · ${preview}` : action || 'MSG',
      tagLines,
      pillW,
      pillH,
      tagX: Math.max(8, Math.min(to.x - pillW / 2, width - pillW - 8)),
      tagY: Math.max(24, to.y - receiverShell - 26),
      toX: to.x,
      toY: to.y,
      fromX: from.x,
      fromY: from.y,
      glyphScale: +(1.25 * scale).toFixed(2),
    })
    }
  })

  // ── Nodes ──
  const nodes: MapNode[] = []
  let nodeIndex = 0
  positions.forEach(pos => {
    const m = pos.member
    const isChief = m.agent_name === chiefMember.agent_name
    const isOperator = isWebOperator(m.agent_name)
    const isConnected = cs.has(m.agent_name)
    const palette = memberPalette(m)
    const accent = isOperator ? '#a1aab5' : palette.accent
    const isGhost = heartbeatState(m, cs) === 'stale'
    const activity = memberActivity(m, activityMap)
    const opState = memberOperationalState(m, activity, memberIssues(m, cs))
    // Motion budget: only nodes that are part of something drift.
    const drifts = !isGhost && (pos.tier <= 1 || activity.isBusy)
    const shellR = (isChief ? 38 : 32) * scale
    // The portrait FILLS the frame: only a slim warm rim remains visible.
    // shows around it, so the agent reads big instead of floating in padding.
    const coreR = shellR - 2 * scale
    const pending = Number(m.pending_count || 0)
    const statusLabel = translateStatus(t, m.status) || m.status || '-'
    const dxRaw = pos.x - cx
    const dyRaw = pos.y - cy
    const len = Math.max(1, Math.hypot(dxRaw, dyRaw))
    const lbl = labelFor(dxRaw / len, dyRaw / len, shellR, isChief, others.length, useAspectLayout)
    const displayName = translateDisplayName(
      locale.value,
      displayNames.get(m.agent_name) || humanizeAgentName(m.agent_name)
    )
    // Long names wrap to two lines; the label BLOCK shifts so the extra line
    // never invades the shell (top zone grows upward, others push the pill
    // and heartbeat down instead).
    const nameLines = wrapNodeName(displayName, lbl.clip)
    const wrapExtra = nameLines.length > 1 ? 14 : 0
    const isTopZone = lbl.anchor === 'middle' && lbl.nameY < 0
    const nameY = isTopZone ? lbl.nameY - wrapExtra : lbl.nameY
    const subY = isTopZone ? lbl.subY : lbl.subY + wrapExtra
    // Status pill under the name (mockup style): coloured chip, not plain text.
    const stateLabel = t('sd_' + opState.key)
    const statePillW = Math.round(stateLabel.length * 6.6 + 18)
    const statePillX = lbl.anchor === 'middle' ? -statePillW / 2 : lbl.anchor === 'start' ? -8 : -statePillW + 8
    // Domain role line above the name (mockup's "FINANZAS / OPERACIONES"):
    // surfaced from the member's real name, same classification as the avatar.
    const domainId = domainForMember(m)
    const domainLabel = domainId ? t('sd_domain_' + domainId) : ''
    const domainGlyph = domainId ? domainGlyphPath(domainId) : ''
    const domTextW = domainLabel.length * 6
    const domY = nameY - 15
    let domIconX: number
    let domTextX: number
    if (lbl.anchor === 'start') {
      domIconX = lbl.nameX
      domTextX = lbl.nameX + 15
    } else if (lbl.anchor === 'end') {
      domTextX = lbl.nameX
      domIconX = lbl.nameX + 4
    } else {
      domTextX = 7
      domIconX = -domTextW / 2 - 9
    }
    // Heartbeat line: pulse-level icon + last-seen age ("hace 10s").
    const hbLabel = timeAgo(m.last_seen_at || m.joined_at, locale.value)
    const hbTextW = hbLabel.length * 5.6
    // Top-zone labels live ABOVE the node, so `subY + 21` would land the
    // heartbeat INSIDE the shell (over the presence badge). Those nodes get
    // their pulse line under the shell instead, like every other node.
    const hbY = isTopZone ? shellR + 20 : subY + 21
    let hbIconX: number
    let hbTextX: number
    if (lbl.anchor === 'start') {
      hbIconX = lbl.subX
      hbTextX = lbl.subX + 23
    } else if (lbl.anchor === 'end') {
      hbTextX = lbl.subX
      hbIconX = lbl.subX - hbTextW - 23
    } else {
      hbTextX = 11
      hbIconX = -hbTextW / 2 - 12
    }
    // Queue bar: honest load — pending messages, only when there are any.
    const showQueue = pending > 0
    const queueW = 44
    const queueX = lbl.anchor === 'start' ? lbl.subX : lbl.anchor === 'end' ? lbl.subX - queueW - 16 : -(queueW + 16) / 2
    const queueY = hbY + 10
    const queueFillW = Math.max(4, Math.round(queueW * Math.min(1, pending / 5)))
    const idx = nodeIndex
    nodeIndex += 1
    nodes.push({
      name: m.agent_name,
      x: pos.x,
      y: pos.y,
      isChief,
      isOperator,
      isGhost,
      busy: activity.isBusy,
      classes: [
        isGhost ? 'offline ghost' : 'online',
        drifts ? 'drift' : '',
        activity.isBusy ? 'busy' : '',
        activity.hasOutgoing ? 'message-send' : '',
        activity.hasIncoming ? 'message-receive' : '',
        isOperator ? 'operator' : '',
      ].filter(Boolean).join(' '),
      accent,
      statusColor: statusTone(m.status),
      showHalo: isConnected && !isGhost,
      pending,
      pendingLabel: pending > 9 ? '9+' : String(pending),
      avatarUrl: avatarUrl(avatarForMember(m), 256),
      presenceUrl: stateIconUrl(presenceIconName(m, cs)),
      operationUrl: stateIconUrl(operationIconName(opState, pending)),
      coreR,
      shellR,
      auraR: (isChief ? 47 : 41) * scale,
      badgeSize: Math.round(24 * scale),
      crownScale: scale,
      label: { ...lbl, nameY, subY },
      nameLines,
      labelScale,
      stateLabel,
      stateTone: opState.tone,
      statePillW,
      statePillX,
      domainLabel,
      domainGlyph,
      domIconX,
      domTextX,
      domY,
      hbIconUrl: stateIconUrl(heartbeatIconName(heartbeatTier(m, cs))),
      hbLabel,
      hbIconX,
      hbTextX,
      hbY,
      showQueue,
      queueX,
      queueY,
      queueW,
      queueFillW,
      title: `${m.agent_name || '-'} · ${statusLabel}${pending ? ` · +${pending}` : ''}`,
      dx: `${[0, 1.6, -1.6][idx % 3]}px`,
      dy: `${idx % 2 === 0 ? -2.4 : 2.4}px`,
      driftDelay: `${-(idx * 0.9).toFixed(1)}s`,
    })
  })

  return { width, height, cx, cy, rings, nodes, edges, queueDots, flights, orbSize }
})
</script>

<style scoped>
/* Cockpit card */
.cockpit-card { border:1px solid var(--line); border-radius:18px; padding:20px; background:linear-gradient(180deg,var(--card-bg-soft),var(--soft)); position:relative; overflow:hidden; }
.cockpit-card::before { content:''; position:absolute; top:0; left:0; right:0; height:1px; background:linear-gradient(90deg,transparent,var(--accent-glow),transparent); }
.cockpit-card[data-load="medium"] { border-color:rgba(239,159,39,0.24); }
.cockpit-card[data-load="high"] { border-color:rgba(240,153,123,0.28); }
.cockpit-card[data-load="critical"] { border-color:rgba(175,169,236,0.3); }

/* In-canvas chrome */
.canvas-status { position:absolute; top:12px; left:12px; z-index:3; display:flex; gap:8px; flex-wrap:wrap; max-width:calc(100% - 110px); pointer-events:none; }
.canvas-status > :deep(*) { pointer-events:auto; }
.canvas-tools { position:absolute; top:12px; right:12px; z-index:4; display:flex; align-items:flex-start; gap:6px; }
.canvas-expand { background:var(--panel); backdrop-filter:blur(8px); -webkit-backdrop-filter:blur(8px); }

/* War-room mode */
.cockpit-card.expanded {
  position:fixed; inset:16px; z-index:180;
  overflow:auto;
  background:var(--bg);
}
.map-tool {
  display:inline-flex; align-items:center; justify-content:center;
  width:30px; height:30px; padding:0; flex-shrink:0;
  border:1px solid var(--line); border-radius:9px;
  background:transparent; color:var(--muted);
  cursor:pointer; transition:all 0.15s ease;
}
.map-tool:hover { color:var(--ink); border-color:var(--hover-line); }
.map-invite-cta {
  padding:9px 18px; border-radius:999px;
  border:1px solid var(--accent-glow); background:var(--accent-soft);
  color:var(--accent); font-size:0.82rem; font-weight:700;
  cursor:pointer; transition:all 0.15s ease;
}
.map-invite-cta:hover { border-color:var(--accent); }

/* Member quick card (teleported to <body>, fixed to the viewport) */
.map-popover {
  position:fixed; z-index:260;
  width:280px; padding:14px;
  display:flex; flex-direction:column; gap:10px;
  border:1px solid var(--line); border-radius:14px;
  background:var(--bg); box-shadow:var(--shadow-elev);
}
.map-popover-head { display:flex; align-items:center; gap:10px; }
.map-popover-avatar {
  width:40px; height:40px; border-radius:50%; flex-shrink:0;
  object-fit:cover; border:2px solid transparent; display:block;
}
.map-popover-id { min-width:0; display:flex; flex-direction:column; gap:1px; flex:1; }
.map-popover-id strong { font-size:0.9rem; color:var(--ink); overflow:hidden; text-overflow:ellipsis; white-space:nowrap; }
.map-popover-full { font-size:0.68rem; color:var(--muted); overflow:hidden; text-overflow:ellipsis; white-space:nowrap; opacity:0.8; }
.map-popover-status { font-size:0.72rem; color:var(--muted); }

/* Inline inbox */
.map-popover-inbox { display:flex; flex-direction:column; gap:8px; }
.map-inbox-empty { margin:0; font-size:0.76rem; color:var(--muted); }
.map-inbox-message { border:1px solid var(--line); border-radius:10px; padding:9px 11px; background:var(--card-bg-soft); }
.map-inbox-meta { display:flex; align-items:center; gap:8px; font-size:0.76rem; color:var(--ink); }
.map-inbox-action { padding:1px 7px; border-radius:999px; border:1px solid var(--line); font-size:0.62rem; font-weight:800; letter-spacing:0.05em; color:var(--muted); }
.map-inbox-action.task { color:#EF9F27; border-color:rgba(239,159,39,0.3); background:rgba(239,159,39,0.08); }
.map-inbox-action.info { color:#85B7EB; border-color:rgba(133,183,235,0.3); background:rgba(133,183,235,0.08); }
.map-inbox-action.reply { color:#AFA9EC; border-color:rgba(175,169,236,0.3); background:rgba(175,169,236,0.08); }
.map-inbox-body { margin:6px 0 0; font-size:0.8rem; line-height:1.5; color:var(--ink); white-space:pre-wrap; word-break:break-word; max-height:140px; overflow-y:auto; }

/* Inline send */
.map-popover-send { display:flex; flex-direction:column; gap:8px; }
.map-send-actions { display:flex; gap:6px; }
.map-send-action {
  padding:4px 11px; border-radius:999px; border:1px solid var(--line);
  background:var(--soft); color:var(--muted);
  font-size:0.66rem; font-weight:800; letter-spacing:0.05em;
  cursor:pointer; transition:all 0.15s ease;
}
.map-send-action.active.task { color:#EF9F27; border-color:rgba(239,159,39,0.4); background:rgba(239,159,39,0.1); }
.map-send-action.active.info { color:#85B7EB; border-color:rgba(133,183,235,0.4); background:rgba(133,183,235,0.1); }
.map-send-action.active.reply { color:#AFA9EC; border-color:rgba(175,169,236,0.4); background:rgba(175,169,236,0.1); }
.map-send-text {
  width:100%; padding:9px 11px; resize:vertical; min-height:44px;
  border:1px solid var(--line); border-radius:10px;
  background:var(--soft); color:var(--ink); font-size:0.82rem; font-family:inherit;
}
.map-send-text:focus { border-color:var(--accent); box-shadow:0 0 0 3px var(--accent-soft); outline:none; }
.map-popover-btn:disabled { opacity:0.5; cursor:default; }
.map-popover-task { margin:0; font-size:0.8rem; color:var(--muted); line-height:1.45; word-break:break-word; }
.map-popover-meta { display:flex; gap:6px; flex-wrap:wrap; }
.map-popover-chip {
  display:inline-flex; align-items:center; padding:3px 9px;
  border-radius:999px; border:1px solid var(--line); background:var(--soft);
  color:var(--muted); font-size:0.68rem; font-weight:700;
}
.map-popover-chip.warn { color:#EF9F27; border-color:rgba(239, 159, 39, 0.3); background:rgba(239, 159, 39, 0.08); }
.map-popover-chip.live { color:#5DCAA5; border-color:rgba(93, 202, 165, 0.3); background:rgba(93, 202, 165, 0.08); }
.map-popover-chip.stale { color:var(--muted); border-style:dashed; }
.map-popover-actions { display:flex; gap:8px; }
.map-popover-btn {
  flex:1; padding:8px 12px;
  border-radius:10px; border:1px solid var(--accent-glow);
  background:var(--accent-soft); color:var(--accent);
  font-size:0.78rem; font-weight:700; cursor:pointer;
  transition:all 0.15s ease;
}
.map-popover-btn:hover { border-color:var(--accent); }
.map-popover-btn.danger { border-color:rgba(240, 153, 123, 0.35); background:rgba(240, 153, 123, 0.08); color:#F0997B; }
.map-popover-btn.danger:hover { border-color:#F0997B; }

/* Squad map */
.squad-map { min-height:300px; }
.squad-canvas { width:100%; min-height:300px; border:1px solid var(--canvas-border); border-radius:18px; background:radial-gradient(circle at top,var(--accent-soft),transparent 45%),linear-gradient(180deg,var(--canvas-top),var(--canvas-bottom)); overflow:hidden; position:relative; }
.squad-canvas svg { width:100%; height:auto; display:block; }

/* Fit-to-height mode (managed cockpit): the card fills its grid cell and the
   SVG scales down to fit the available box (default preserveAspectRatio meet),
   so the whole room fits one viewport without page scroll. */
.cockpit-card.fit { display:flex; flex-direction:column; height:100%; min-height:0; }
.cockpit-card.fit { padding:10px; }
.cockpit-card.fit .squad-map { flex:1; min-height:0; display:flex; }
.cockpit-card.fit .squad-canvas { flex:1; min-height:0; }
.cockpit-card.fit .squad-canvas svg { width:100%; height:100%; }
.node-label { font-size:15px; font-weight:700; fill:var(--ink); letter-spacing:-0.01em; }
/* Domain role line above the name (mockup's coloured "FINANZAS / RRHH") */
.node-domain text {
  font-size:9.5px; font-weight:800; letter-spacing:0.1em; text-transform:uppercase;
  fill:var(--dom-accent, var(--muted));
}
.node-domain path { fill:none; stroke:var(--dom-accent, var(--muted)); stroke-width:2.6; stroke-linecap:round; stroke-linejoin:round; }

/* Status pill under the node name — coloured chip per operational tone */
.node-state text { font-size:9.5px; font-weight:800; letter-spacing:0.07em; text-transform:uppercase; }
.node-state rect { stroke-width:1; }
.node-state.idle rect { fill:rgba(161,161,170,0.1); stroke:rgba(161,161,170,0.25); }
.node-state.idle text { fill:#a1a1aa; }
.node-state.listening rect { fill:rgba(93,202,165,0.12); stroke:rgba(93,202,165,0.3); }
.node-state.listening text { fill:#5DCAA5; }
.node-state.alert rect { fill:rgba(239,159,39,0.12); stroke:rgba(239,159,39,0.3); }
.node-state.alert text { fill:#EF9F27; }
.node-state.working rect { fill:rgba(133,183,235,0.12); stroke:rgba(133,183,235,0.3); }
.node-state.working text { fill:#85B7EB; }
.node-state.warning rect { fill:rgba(240,153,123,0.12); stroke:rgba(240,153,123,0.3); }
.node-state.warning text { fill:#F0997B; }

/* Heartbeat line + queue bar under the node */
.node-hb text { font-size:11.5px; fill:var(--muted); }
.node-queue-track { fill:rgba(148,163,184,0.16); }
.node-queue-fill { fill:#EF9F27; }
.node-queue-text { font-size:9.5px; font-weight:800; fill:#EF9F27; }

/* Edge direction arrows + mid-wire message-type icon */
.edge-arrow.fresh { fill:rgba(93,202,165,0.8); }
.edge-arrow.warm { fill:rgba(93,202,165,0.45); }
.edge-arrow.cold { fill:var(--signal-line); }
.edge-arrow.expired { fill:rgba(240,153,123,0.5); }
.edge-icon { opacity:0.95; }
.relation.cold .edge-icon,
.relation.expired .edge-icon { opacity:0.5; }
.radar-ring { fill:none; stroke:var(--signal-line); stroke-width:1; stroke-dasharray:3 7; opacity:0.55; }

/* Node positioning: the outer group carries the orbit position and GLIDES
   between tiers; the inner group carries state animations. */
.node-pos { cursor:pointer; transition:transform 0.9s cubic-bezier(0.22, 1, 0.36, 1); }
.node-ring.drift { animation:node-drift 4.6s ease-in-out infinite; }

.node-shell { fill:var(--node-core); stroke:var(--shell-stroke); stroke-width:2; }
.node-ring.online { filter:drop-shadow(0 0 8px rgba(133,183,235,0.2)); }
.node-ring.offline { opacity:0.55; }
.node-ring.offline .node-shell { stroke-dasharray:4 5; }
/* Portrait fills the core; a thin accent ring keeps the role colour reading. */
.node-avatar { transition:filter 0.3s ease; }
.node-core-ring { fill:none; stroke-width:2.5; opacity:0.9; }
.node-badge { filter:drop-shadow(0 1px 2px rgba(0,0,0,0.4)); }
/* Ghost: a stale member desaturates and dims — the life drains out. */
.node-ring.ghost { opacity:0.5; }
.node-avatar.ghost { filter:grayscale(1) brightness(0.7); }
.node-ring.ghost .node-core-ring { stroke-dasharray:3 4; opacity:0.5; }
.node-aura { fill:none; stroke:var(--member-accent, var(--accent)); stroke-width:2; opacity:0.16; transform-origin:center; transform-box:fill-box; }
.node-ring.busy .node-aura { animation:node-aura-pulse 1.8s ease-in-out infinite; }
.node-ring.message-send .node-aura { animation:node-aura-ripple 1.2s ease-out infinite; }
.node-ring.message-receive .node-aura { animation:node-aura-ripple 1.35s ease-out infinite reverse; }
.node-live-halo {
  fill:none;
  stroke-width:1.6;
  transform-box:fill-box;
  transform-origin:center;
  animation:node-live-halo 2.1s ease-out infinite;
}
.node-pending circle { fill:#EF9F27; stroke:var(--node-core); stroke-width:2; }
.node-pending text { fill:#231a02; font-size:10px; font-weight:800; }
.node-crown { filter:drop-shadow(0 2px 3px rgba(0,0,0,0.45)); }

/* Freshness label on the chief's spokes */
.relation-label {
  font-size:10px; font-weight:800; letter-spacing:0.08em; text-transform:uppercase;
  paint-order:stroke; stroke:var(--canvas-bottom, #0c1414); stroke-width:3px; stroke-linejoin:round;
}
.relation-label.current { fill:#5DCAA5; }
.relation-label.recent { fill:#EF9F27; }
.relation-label.old { fill:var(--muted); }
.relation-label.expired { fill:#F0997B; }

/* Last message type under the orb (mockup's "TAREA / ORDEN" wire caption) */
.relation-action {
  font-size:9.5px; font-weight:800; letter-spacing:0.09em; text-transform:uppercase;
  paint-order:stroke; stroke:var(--canvas-bottom, #0c1414); stroke-width:3px; stroke-linejoin:round;
}

/* Relationship edges: heat = recency. Fresh conversations glow, cooling ones
   fade to a thin dashed whisper, held ones stay warm while work is unread.
   New edges ease in instead of popping. */
.relation path { fill:none; stroke-linecap:round; animation:edge-in 0.5s ease both; transition:stroke 0.6s ease, stroke-width 0.6s ease; }
.relation.fresh path { stroke:rgba(93, 202, 165, 0.82); stroke-width:3.2; }
.relation.warm path { stroke:rgba(93, 202, 165, 0.48); stroke-width:2.3; }
.relation.cold path { stroke:var(--signal-line); stroke-width:1.7; stroke-dasharray:5 7; }
/* Expired wire: still visible, but clearly dead (mockup's VENCIDO red dash). */
.relation.expired path { stroke:rgba(240, 153, 123, 0.5); stroke-width:1.9; stroke-dasharray:4 8; }
.relation.held path { stroke:rgba(239, 159, 39, 0.5); }
.queue-dot {
  fill:#EF9F27; stroke:var(--node-core); stroke-width:1;
  transform-box:fill-box; transform-origin:center;
  animation:queue-dot 1.6s ease-in-out infinite;
  transition:cx 0.9s cubic-bezier(0.22, 1, 0.36, 1), cy 0.9s cubic-bezier(0.22, 1, 0.36, 1);
}

/* Per-event flight: mounts once when its event appears, so every animation
   here plays a FINITE run — no restarting loops. */
.flight-route { stroke-width:2.5; stroke-dasharray:8 10; stroke-linecap:round; fill:none; animation:route-pulse 1.45s cubic-bezier(0.22,1,0.36,1) 2 both; }
.flight.queued .flight-route { opacity:0.42; }
.flight-impact { fill:none; stroke:var(--impact-accent, var(--accent)); stroke-width:3; opacity:0; animation:flight-impact 1.2s ease-out 2 both; }
.flight-origin { fill:none; stroke-width:2.5; animation:flight-origin 1.1s ease-out 2 both; }
/* Opacity-only fade-in: animating transform here would override the tag's
   positioning transform attribute and fling it to the SVG origin. */
.flight-tag { animation:flight-tag-in 0.5s ease-out 1.2s both; }
.node-float-pill { fill:var(--impact-accent, var(--accent)); fill-opacity:0.88; }
.node-float-text { fill:#03131a; font-size:10px; font-weight:800; letter-spacing:0.05em; }
.mail-glyph rect { fill:var(--impact-accent, var(--accent)); stroke:var(--node-core); stroke-width:1.4; }
.mail-glyph > path { fill:none; stroke:var(--node-core); stroke-width:1.4; stroke-linejoin:round; }
.mail-glyph { opacity:0.95; }
.flight.queued .mail-glyph { opacity:0.55; }

/* Empty state */
.empty-state { display:flex; flex-direction:column; align-items:center; gap:16px; padding:60px 24px; text-align:center; }
.empty-state span { color:var(--muted); font-size:14px; }

/* Animations */
@keyframes edge-in { from { opacity:0; } to { opacity:1; } }
@keyframes route-pulse { 0% { stroke-dashoffset:0; opacity:0.18; } 18% { opacity:0.95; } 100% { stroke-dashoffset:-36; opacity:0.24; } }
@keyframes flight-impact { 0% { r:16; opacity:0.45; } 100% { r:44; opacity:0; } }
@keyframes flight-origin { 0% { r:4; opacity:0.9; } 100% { r:20; opacity:0; } }
@keyframes flight-tag-in { from { opacity:0; } to { opacity:1; } }
@keyframes node-live-halo { 0% { transform:scale(0.7); opacity:0.75; } 100% { transform:scale(2.1); opacity:0; } }
@keyframes node-drift { 0%, 100% { transform:translate(0, 0); } 50% { transform:translate(var(--dx, 0px), var(--dy, -2.4px)); } }
@keyframes queue-dot { 0%, 100% { transform:scale(0.85); opacity:0.55; } 50% { transform:scale(1.1); opacity:1; } }
@keyframes node-aura-pulse { 0% { transform:scale(0.92); opacity:0.14; } 55% { transform:scale(1.12); opacity:0.34; } 100% { transform:scale(1.22); opacity:0; } }
@keyframes node-aura-ripple { 0% { transform:scale(0.88); opacity:0.2; } 50% { transform:scale(1.08); opacity:0.3; } 100% { transform:scale(1.26); opacity:0; } }

html[data-motion="reduced"] .flight-route,
html[data-motion="reduced"] .flight-impact,
html[data-motion="reduced"] .flight-origin,
html[data-motion="reduced"] .node-aura,
html[data-motion="reduced"] .node-live-halo,
html[data-motion="reduced"] .queue-dot {
  animation-duration: 1.8s !important;
}
html[data-motion="reduced"] .node-ring,
html[data-motion="reduced"] .node-pos {
  animation: none !important;
  transition: none !important;
}
html[data-motion="reduced"] .relation path,
html[data-motion="off"] .relation path {
  animation: none !important;
  transition: none !important;
}
html[data-motion="reduced"] .queue-dot,
html[data-motion="off"] .queue-dot {
  transition: none !important;
}

html[data-motion="off"] .flight-route,
html[data-motion="off"] .flight-impact,
html[data-motion="off"] .flight-origin,
html[data-motion="off"] .flight-tag,
html[data-motion="off"] .node-aura,
html[data-motion="off"] .node-live-halo,
html[data-motion="off"] .queue-dot,
html[data-motion="off"] .node-ring {
  animation: none !important;
}
html[data-motion="off"] .node-pos {
  transition: none !important;
}
html[data-motion="off"] .flight-tag { opacity:1; }

/* The envelope rides an SMIL animateMotion, which CSS animation rules can't
   slow down — hide it outright when motion is reduced or off. */
html[data-motion="off"] .mail-glyph,
html[data-motion="reduced"] .mail-glyph {
  display: none;
}
@media (prefers-reduced-motion: reduce) {
  .mail-glyph { display: none; }
}

/* Responsive */
/* On narrow screens the cockpit stacks and scrolls; the map returns to its
   natural height so it never squishes to nothing. */
@media (max-width:1200px) {
  .cockpit-card.fit { height:auto; }
  .cockpit-card.fit .squad-map { display:block; }
  .cockpit-card.fit .squad-canvas { min-height:300px; }
  .cockpit-card.fit .squad-canvas svg { height:auto; }
}
@media (max-width:768px) { .cockpit-card { padding:16px; border-radius:14px; } }
@media (max-width:600px) {
  .squad-map { min-height:240px; } .squad-canvas { min-height:240px; }
}
@media (max-width:480px) {
  .cockpit-card { padding:12px; border-radius:12px; }
}
@media (prefers-reduced-motion: reduce) {
  *, *::before, *::after { animation-duration:0.01ms !important; transition-duration:0.01ms !important; }
}
</style>
