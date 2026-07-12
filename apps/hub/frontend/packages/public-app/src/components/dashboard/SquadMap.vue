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
      <div v-else class="squad-canvas" @click="onCanvasClick">
        <!-- In-canvas chrome: live status chips (top-left) and the expand
             toggle (top-right) live ON the map — the map needs no header. -->
        <div class="canvas-status">
          <slot name="status" />
        </div>
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
        <svg :viewBox="`0 0 ${graph.width} ${graph.height}`" role="img" :aria-label="t('sd_squad_map_title')">
          <circle
            v-for="(ring, ri) in graph.rings"
            :key="'ring-' + ri"
            class="radar-ring"
            :cx="graph.cx"
            :cy="graph.cy"
            :r="ring"
          />

          <g v-for="edge in graph.edges" :key="edge.id" class="relation" :class="[edge.heat, { held: edge.held }]">
            <title>{{ edge.title }}</title>
            <path :d="edge.path" />
            <text
              v-if="edge.showLabel"
              class="relation-label"
              :class="edge.freshness"
              :x="edge.labelX"
              :y="edge.labelY"
              text-anchor="middle"
            >{{ edge.label }}</text>
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
              <path v-if="node.isChief" class="node-crown" :transform="`translate(0, ${-node.shellR - 10 * node.crownScale}) scale(${node.crownScale})`" d="M-9 4 L-6 -4 L-3 0 L0 -6 L3 0 L6 -4 L9 4 Z" />
              <text class="node-label" :x="node.label.nameX" :y="node.label.nameY" :text-anchor="node.label.anchor">{{ node.labelName }}</text>
              <text class="node-subtext" :x="node.label.subX" :y="node.label.subY" :text-anchor="node.label.anchor">{{ node.labelSub }}</text>
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
            <g class="flight-tag" :transform="`translate(${flight.tagX}, ${flight.tagY})`">
              <rect class="node-float-pill" x="-4" y="-14" :width="flight.pillW" height="20" rx="10" />
              <text class="node-float-text" :x="flight.pillW / 2 - 4" y="0" text-anchor="middle">{{ flight.tag }}</text>
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
  recentMemberActivity, memberActivity, mapRoutePath, sortedMembers,
  eventClass, hashValue, agentDisplayNames, humanizeAgentName, type TrafficLevel,
  avatarForMember, presenceIconName, operationIconName, memberOperationalState, memberIssues,
  linkFreshness, type LinkFreshness,
} from '../../composables/sessionHelpers'
import { avatarUrl, stateIconUrl } from '../../assets/acp/acpAssets'
import { translateStatus } from '../../composables/dashboardTranslations'
import type { SessionMember, SessionDetailPayload } from '../../api/sessions'

const props = defineProps<{
  payload: SessionDetailPayload | null
  connectedSet: Set<string>
  trafficLevel: TrafficLevel
  adminActionsAvailable?: boolean
  canMessage?: boolean
  fitHeight?: boolean
}>()

const emit = defineEmits<{
  invite: []
  'send-message': [message: { to: string; action: 'TASK' | 'INFO' | 'REPLY'; payload: string }]
  'disconnect-member': [agentName: string]
}>()

const { t } = useI18n(messages)

function clipText(value: string, max = 26): string {
  return value.length > max ? value.slice(0, max - 1) + '…' : value
}

// ── War-room mode + member quick card ──

const cardRef = ref<HTMLElement | null>(null)
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
  return rosterDisplayNames.value.get(name) || humanizeAgentName(name)
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
  const POPOVER_H = 350
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
function labelFor(ux: number, uy: number, shellR: number, isChief: boolean, ringSize: number): NodeLabel {
  if (!isChief) {
    const sideThreshold = ringSize > 8 ? 0.25 : 0.55
    if (Math.abs(ux) > sideThreshold) {
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
  labelName: string
  labelSub: string
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
  showLabel: boolean
  label: string
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
  tag: string
  pillW: number
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
  interface PairStat { a: string; b: string; lastTs: number; count: number; queuedTo: string }
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
    const stat = pairs.get(key) || { a: actor, b: target, lastTs: 0, count: 0, queuedTo: '' }
    stat.count += 1
    if (ts >= stat.lastTs) {
      stat.lastTs = ts
      stat.a = actor
      stat.b = target
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
  const scale = crowd <= 2 ? 1.5 : crowd <= 4 ? 1.22 : 1
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
  const outerR = crowd ? occupiedR + memberShellR + 64 : 0
  const gutterX = crowd <= 2 ? 280 : 420
  const gutterY = crowd <= 2 ? 130 : 180
  const width = crowd ? Math.round(outerR * 2 + gutterX) : 1040
  const height = crowd ? Math.round(outerR * 2 + gutterY) : 530
  const cx = width / 2
  const cy = height / 2
  const rings = crowd ? tierRadii.slice(0, maxTier + 1) : [90, 150, 210]

  const positions = new Map<string, { x: number; y: number; tier: number; member: SessionMember }>()
  positions.set(chiefMember.agent_name, { x: cx, y: cy, tier: 0, member: chiefMember })

  const startAngle = orbiting.length <= 2 ? 0 : -Math.PI / 2
  orbiting.forEach((member, mi) => {
    const angle = startAngle + (mi * 2 * Math.PI) / orbiting.length
    const tier = tiersByName.get(member.agent_name) ?? 2
    positions.set(member.agent_name, {
      x: cx + tierRadii[tier] * Math.cos(angle),
      y: cy + tierRadii[tier] * Math.sin(angle),
      tier,
      member,
    })
  })

  // ── Relationship edges ──
  // Chief-involved edges radiate from the center and stay straight; edges
  // between two orbiting members ARC AWAY from the center so they never cut
  // through the chief sitting in the middle.
  const edges: MapEdge[] = []
  pairs.forEach((pair, key) => {
    const na = positions.get(pair.a)
    const nb = positions.get(pair.b)
    if (!na || !nb) return
    const age = now - pair.lastTs
    const queuedTarget = pair.queuedTo ? positions.get(pair.queuedTo) : undefined
    const held = Boolean(queuedTarget && Number(queuedTarget.member.pending_count || 0) > 0)
    if (age > EDGE_WINDOW && !held) return
    let heat: MapEdge['heat'] = age <= 45_000 ? 'fresh' : age <= 3 * 60_000 ? 'warm' : 'cold'
    if (held && heat === 'cold') heat = 'warm'

    const involvesChief = pair.a === chiefMember.agent_name || pair.b === chiefMember.agent_name
    const freshness = linkFreshness(Math.round(age / 1000))
    let path: string
    let labelX: number
    let labelY: number
    if (involvesChief) {
      path = `M ${na.x.toFixed(1)} ${na.y.toFixed(1)} L ${nb.x.toFixed(1)} ${nb.y.toFixed(1)}`
      labelX = (na.x + nb.x) / 2
      labelY = (na.y + nb.y) / 2
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
      path = `M ${na.x.toFixed(1)} ${na.y.toFixed(1)} Q ${ctrlX.toFixed(1)} ${ctrlY.toFixed(1)} ${nb.x.toFixed(1)} ${nb.y.toFixed(1)}`
      // Quadratic bezier midpoint (t=0.5): 0.25·A + 0.5·ctrl + 0.25·B.
      labelX = 0.25 * na.x + 0.5 * ctrlX + 0.25 * nb.x
      labelY = 0.25 * na.y + 0.5 * ctrlY + 0.25 * nb.y
    }
    // Only the chief's spokes carry a freshness label — mirrors the reference
    // and keeps member-member arcs uncluttered (their heat colour already reads).
    edges.push({
      id: key, path, heat, held, freshness,
      showLabel: involvesChief,
      label: t('sd_link_' + freshness),
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
    const from = positions.get(String(event.actor || ''))
    const to = positions.get(String(event.target || ''))
    if (!from || !to) return
    const id = `${event.ts}|${event.event}|${event.actor}|${event.target}`
    if (seenFlightIds.has(id)) return
    seenFlightIds.add(id)
    const ts = Date.parse(String(event.ts || ''))
    // Curvature seed derives from the event itself, not the slice index, so a
    // flight's route never changes shape as the window slides under it.
    const seed = Number.isNaN(ts) ? ri : Math.abs(ts) % 6
    const action = messageActionType(event)
    const delivery = deliveryMode(event)
    const preview = clipText(String(event.payload_preview || '').trim(), 22)
    const tag = preview ? `${floatTagLabel(action, delivery)} ${preview}` : floatTagLabel(action, delivery)
    const pillW = Math.max(42, 14 + tag.length * 5.6)
    // The tag floats ABOVE the receiver, clear of its shell and clamped to the
    // canvas, so it never covers the node it lands on.
    const receiverShell = (String(event.target || '') === chiefMember.agent_name ? 38 : 32) * scale
    flights.push({
      id,
      markerId: `fm${hashValue(id)}`,
      path: mapRoutePath(from, to, seed),
      tone: actionTone(action),
      classes: `${actionChipClass(action)} ${deliveryClass(delivery)}`,
      title: preview ? `${action || 'MSG'} · ${preview}` : action || 'MSG',
      tag,
      pillW,
      tagX: Math.max(8, Math.min(to.x - pillW / 2, width - pillW - 8)),
      tagY: Math.max(24, to.y - receiverShell - 26),
      toX: to.x,
      toY: to.y,
      fromX: from.x,
      fromY: from.y,
      glyphScale: +(1.25 * scale).toFixed(2),
    })
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
    const coreR = (isChief ? 27 : 22) * scale
    const shellR = (isChief ? 38 : 32) * scale
    const pending = Number(m.pending_count || 0)
    const statusLabel = translateStatus(t, m.status) || m.status || '-'
    const dxRaw = pos.x - cx
    const dyRaw = pos.y - cy
    const len = Math.max(1, Math.hypot(dxRaw, dyRaw))
    const lbl = labelFor(dxRaw / len, dyRaw / len, shellR, isChief, others.length)
    const displayName = displayNames.get(m.agent_name) || humanizeAgentName(m.agent_name)
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
      badgeSize: Math.round(18 * scale),
      crownScale: scale,
      label: lbl,
      labelName: clipText(displayName, lbl.clip),
      labelSub: clipText(m.current_task || statusLabel, lbl.clip + 4),
      title: `${m.agent_name || '-'} · ${statusLabel}${pending ? ` · +${pending}` : ''}`,
      dx: `${[0, 1.6, -1.6][idx % 3]}px`,
      dy: `${idx % 2 === 0 ? -2.4 : 2.4}px`,
      driftDelay: `${-(idx * 0.9).toFixed(1)}s`,
    })
  })

  return { width, height, cx, cy, rings, nodes, edges, queueDots, flights }
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
.canvas-expand { position:absolute; top:12px; right:12px; z-index:3; background:var(--panel); backdrop-filter:blur(8px); -webkit-backdrop-filter:blur(8px); }

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
.cockpit-card.fit .squad-map { flex:1; min-height:0; display:flex; }
.cockpit-card.fit .squad-canvas { flex:1; min-height:0; }
.cockpit-card.fit .squad-canvas svg { width:100%; height:100%; }
.node-label { font-size:15px; font-weight:700; fill:var(--ink); letter-spacing:-0.01em; }
.node-subtext { font-size:12px; fill:var(--muted); }
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
.node-crown { fill:#EF9F27; stroke:var(--node-core); stroke-width:1; }

/* Freshness label on the chief's spokes */
.relation-label {
  font-size:10px; font-weight:800; letter-spacing:0.08em; text-transform:uppercase;
  paint-order:stroke; stroke:var(--canvas-bottom, #0c1414); stroke-width:3px; stroke-linejoin:round;
}
.relation-label.current { fill:#5DCAA5; }
.relation-label.recent { fill:#EF9F27; }
.relation-label.old { fill:var(--muted); }
.relation-label.expired { fill:#F0997B; }

/* Relationship edges: heat = recency. Fresh conversations glow, cooling ones
   fade to a thin dashed whisper, held ones stay warm while work is unread.
   New edges ease in instead of popping. */
.relation path { fill:none; stroke-linecap:round; animation:edge-in 0.5s ease both; transition:stroke 0.6s ease, stroke-width 0.6s ease; }
.relation.fresh path { stroke:rgba(93, 202, 165, 0.75); stroke-width:2.6; }
.relation.warm path { stroke:rgba(93, 202, 165, 0.38); stroke-width:1.8; }
.relation.cold path { stroke:var(--signal-line); stroke-width:1.2; stroke-dasharray:5 7; }
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
