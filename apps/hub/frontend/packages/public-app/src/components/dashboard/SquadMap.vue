<template>
  <div class="cockpit-card" :data-load="trafficLevel">
    <div class="cockpit-head">
      <div>
        <div class="cockpit-title">{{ t('sd_squad_map_title') }}</div>
        <div class="cockpit-sub">{{ t('sd_squad_map_sub') }}</div>
      </div>
    </div>
    <div class="squad-map">
      <div v-if="!payload?.members?.length" class="empty-state">
        <span>{{ t('sd_no_problem_members') }}</span>
      </div>
      <div v-else class="squad-canvas" v-html="squadMapSvg"></div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import { useI18n } from '@acp/shared'
import { messages } from '../../i18n'
import {
  normalizedRole, memberPalette, heartbeatState, statusTone,
  messageActionType, actionChipClass, deliveryMode, deliveryClass, actionTone, floatTagLabel,
  recentMemberActivity, memberActivity, mapRoutePath, mapAnimationEvents, sortedMembers,
  escapeHtml, type TrafficLevel,
} from '../../composables/sessionHelpers'
import { translateStatus } from '../../composables/dashboardTranslations'
import type { SessionMember, SessionDetailPayload } from '../../api/sessions'

const props = defineProps<{
  payload: SessionDetailPayload | null
  connectedSet: Set<string>
  trafficLevel: TrafficLevel
}>()

const { t } = useI18n(messages)

function clipText(value: string, max = 26): string {
  return value.length > max ? value.slice(0, max - 1) + '…' : value
}

// Identity initials from the agent name (first + last meaningful segment),
// skipping hex hash suffixes — so two collaborators don't both read "CO".
function nameInitials(name: string): string {
  const parts = String(name || '')
    .split(/[-_.\s]+/)
    .filter(Boolean)
    .filter(part => !/^[0-9a-f]{6,}$/i.test(part))
  if (!parts.length) return '?'
  if (parts.length === 1) return parts[0].slice(0, 2).toUpperCase()
  return (parts[0][0] + parts[parts.length - 1][0]).toUpperCase()
}

interface NodeLabel {
  anchor: 'start' | 'middle' | 'end'
  nameX: number
  nameY: number
  subX: number
  subY: number
  clip: number
}

// Labels sit on the OUTER side of each node (away from the hub) so they can
// never collide with a neighbor's label — the fix for overlapping names.
// Crowded rings push more labels to the sides, where vertical spacing is wide.
function labelFor(x: number, y: number, cx: number, cy: number, shellR: number, isChief: boolean, ringSize: number): NodeLabel {
  if (!isChief) {
    const dx = x - cx
    const dy = y - cy
    const len = Math.max(1, Math.hypot(dx, dy))
    const ux = dx / len
    const uy = dy / len
    const sideThreshold = ringSize > 8 ? 0.25 : 0.55
    if (Math.abs(ux) > sideThreshold) {
      const side = ux > 0 ? 1 : -1
      const lx = x + side * (shellR + 16)
      return { anchor: side > 0 ? 'start' : 'end', nameX: lx, nameY: y - 2, subX: lx, subY: y + 15, clip: 22 }
    }
    if (uy < 0) {
      return { anchor: 'middle', nameX: x, nameY: y - shellR - 26, subX: x, subY: y - shellR - 10, clip: 26 }
    }
  }
  return { anchor: 'middle', nameX: x, nameY: y + shellR + 22, subX: x, subY: y + shellR + 39, clip: 26 }
}

const squadMapSvg = computed(() => {
  const p = props.payload
  if (!p || !p.members?.length) return ''

  const members = sortedMembers(p)
  const cs = props.connectedSet
  const activityMap = recentMemberActivity(p)
  const animEvents = mapAnimationEvents(p)

  const chiefMember = members.find(m => normalizedRole(m.role) === 'chief') || members[0]
  if (!chiefMember) return ''

  const others = members.filter(m => m.agent_name !== chiefMember.agent_name)

  // Radial hub layout: the chief sits at the center and teammates orbit on a
  // ring around it. Reads as a map at a glance and stays balanced whether the
  // room has one member or twelve. Side labels let one or two teammates sit on
  // the horizontal axis inside a much shorter canvas.
  const ringRadius = others.length ? Math.min(240, 170 + others.length * 8) : 0
  const width = 1000
  const height = others.length <= 2 ? 400 : ringRadius * 2 + 230
  const cx = width / 2
  const cy = height / 2

  const nodes = new Map<string, { x: number; y: number; member: SessionMember }>()
  let markup = ''

  // Radar rings give the canvas spatial context even when the room is quiet.
  const rings = others.length
    ? [ringRadius * 0.45, ringRadius * 0.75, ringRadius * 1.06]
    : [70, 120, 170]
  rings.forEach(r => {
    markup += `<circle class="radar-ring" cx="${cx}" cy="${cy}" r="${r.toFixed(1)}" />`
  })

  nodes.set(chiefMember.agent_name, { x: cx, y: cy, member: chiefMember })

  // One or two teammates read best on the horizontal axis; three or more
  // start at 12 o'clock and distribute evenly.
  const startAngle = others.length <= 2 ? 0 : -Math.PI / 2
  others.forEach((member, mi) => {
    const angle = startAngle + (mi * 2 * Math.PI) / others.length
    const x = cx + ringRadius * Math.cos(angle)
    const y = cy + ringRadius * Math.sin(angle)
    nodes.set(member.agent_name, { x, y, member })
    const isOperator = String(member.agent_name || '').startsWith('web-operator-')
    const spokeClasses = [
      'signal-line',
      cs.has(member.agent_name) ? 'live' : '',
      isOperator ? 'operator-spoke' : '',
    ].filter(Boolean).join(' ')
    markup += `<line class="${spokeClasses}" x1="${cx}" y1="${cy}" x2="${x.toFixed(1)}" y2="${y.toFixed(1)}" />`
  })

  // Animated routes: pulse dashes along the wire, impact ripples on arrival,
  // and a little envelope that rides the route and rests on the receiver.
  let mailMarkup = ''
  animEvents.slice(-10).forEach((event, ri) => {
    const from = nodes.get(String(event.actor || ''))
    const to = nodes.get(String(event.target || ''))
    if (!from || !to || event.actor === event.target) return
    const action = messageActionType(event)
    const delivery = deliveryMode(event)
    const path = mapRoutePath(from, to, ri)
    const tone = actionTone(action)
    markup += `<path class="signal-line route-pulse ${actionChipClass(action)} ${deliveryClass(delivery)}" style="animation-delay:${ri * 120}ms;stroke:${tone}" d="${path}" />`
    markup += `
      <circle class="node-impact ${actionChipClass(action)} ${deliveryClass(delivery)}" style="animation-delay:${ri * 120}ms;--impact-accent:${tone}" cx="${to.x}" cy="${to.y}" r="32"></circle>
      <circle class="node-impact spark ${actionChipClass(action)} ${deliveryClass(delivery)}" style="animation-delay:${ri * 120 + 120}ms;--impact-accent:${tone}" cx="${to.x}" cy="${to.y}" r="24"></circle>
      <g class="node-float-tag ${actionChipClass(action)} ${deliveryClass(delivery)}" style="animation-delay:${ri * 120 + 40}ms;--impact-accent:${tone}" transform="translate(${to.x + 30}, ${to.y - 34})">
        <rect class="node-float-pill" x="-4" y="-14" width="42" height="20" rx="10"></rect>
        <text class="node-float-text" x="17" y="0" text-anchor="middle">${escapeHtml(floatTagLabel(action, delivery))}</text>
      </g>`
    mailMarkup += `
      <g class="mail-glyph ${deliveryClass(delivery)}" style="--impact-accent:${tone}">
        <rect x="-8" y="-5.5" width="16" height="11" rx="2.5"/>
        <path d="M-8 -5.5 L0 1.5 L8 -5.5"/>
        <animateMotion dur="1.35s" fill="freeze" path="${path}"/>
      </g>`
  })

  // Nodes
  nodes.forEach(node => {
    const m = node.member
    const isChief = m.agent_name === chiefMember.agent_name
    const isOperator = String(m.agent_name || '').startsWith('web-operator-')
    const isConnected = cs.has(m.agent_name)
    const palette = memberPalette(m)
    const accent = isOperator ? '#a1aab5' : palette.accent
    const hbState = heartbeatState(m, cs)
    const liveClass = hbState === 'stale' ? 'offline' : 'online'
    const activity = memberActivity(m, activityMap)
    const activityClasses = [
      activity.isBusy ? 'busy' : '',
      activity.hasOutgoing ? 'message-send' : '',
      activity.hasIncoming ? 'message-receive' : '',
    ].filter(Boolean).join(' ')
    const coreR = isChief ? 24 : 20
    const shellR = isChief ? 34 : 29
    const auraR = isChief ? 42 : 37
    const pending = Number(m.pending_count || 0)
    const statusLabel = translateStatus(t, m.status) || m.status || '-'
    const label = labelFor(node.x, node.y, cx, cy, shellR, isChief, others.length)
    const pendingBadge = pending
      ? `<g class="node-pending">
          <circle cx="${(node.x - shellR + 4).toFixed(1)}" cy="${(node.y - shellR + 6).toFixed(1)}" r="9.5"/>
          <text x="${(node.x - shellR + 4).toFixed(1)}" y="${(node.y - shellR + 9.5).toFixed(1)}" text-anchor="middle">${pending > 9 ? '9+' : pending}</text>
        </g>`
      : ''
    const crown = isChief
      ? `<path class="node-crown" transform="translate(${node.x}, ${(node.y - shellR - 10).toFixed(1)})" d="M-9 4 L-6 -4 L-3 0 L0 -6 L3 0 L6 -4 L9 4 Z"/>`
      : ''
    const dotX = (node.x + shellR - 8).toFixed(1)
    const dotY = (node.y - shellR + 8).toFixed(1)
    // Live websocket connection = pulsing halo around the status dot; a lost
    // heartbeat hollows the dot out. Simple, glanceable connection states.
    const statusDot = hbState === 'stale'
      ? `<circle class="node-status stale" cx="${dotX}" cy="${dotY}" r="5.5"/>`
      : `<circle class="node-status" cx="${dotX}" cy="${dotY}" r="5.5" fill="${statusTone(m.status)}"/>`
    const liveHalo = isConnected && hbState !== 'stale'
      ? `<circle class="node-live-halo" cx="${dotX}" cy="${dotY}" r="5.5" style="stroke:${statusTone(m.status)}"/>`
      : ''
    // The web operator is a person, not an agent runtime — draw it as one.
    const glyph = isOperator
      ? `<g class="node-person" transform="translate(${node.x}, ${node.y})">
          <circle cy="-4.5" r="3.4"/>
          <path d="M-6.5 8c0-4.2 2.9-6.6 6.5-6.6s6.5 2.4 6.5 6.6"/>
        </g>`
      : `<text class="node-glyph" x="${node.x}" y="${node.y + 4}" text-anchor="middle">${escapeHtml(nameInitials(m.agent_name))}</text>`
    markup += `
      <g class="node-ring ${liveClass} ${activityClasses}${isOperator ? ' operator' : ''}" style="--member-accent:${accent}">
        <title>${escapeHtml(m.agent_name || '-')} · ${escapeHtml(statusLabel)}${pending ? ` · +${pending}` : ''}</title>
        <circle class="node-aura" cx="${node.x}" cy="${node.y}" r="${auraR}"/>
        <circle class="node-shell" cx="${node.x}" cy="${node.y}" r="${shellR}"/>
        <circle cx="${node.x}" cy="${node.y}" r="${coreR}" fill="${accent}"/>
        ${statusDot}
        ${liveHalo}
        ${pendingBadge}
        ${crown}
        ${glyph}
        <text class="node-label" x="${label.nameX.toFixed(1)}" y="${label.nameY.toFixed(1)}" text-anchor="${label.anchor}">${escapeHtml(clipText(m.agent_name || '-', label.clip))}</text>
        <text class="node-subtext" x="${label.subX.toFixed(1)}" y="${label.subY.toFixed(1)}" text-anchor="${label.anchor}">${escapeHtml(clipText(m.current_task || statusLabel, label.clip))}</text>
      </g>`
  })

  // Envelopes render last so a landed letter rests ON TOP of the receiver.
  markup += mailMarkup

  return `<svg viewBox="0 0 ${width} ${height}" role="img" aria-label="${escapeHtml(t('sd_squad_map_title'))}">${markup}</svg>`
})
</script>

<style scoped>
/* Cockpit card */
.cockpit-card { border:1px solid var(--line); border-radius:18px; padding:20px; background:linear-gradient(180deg,var(--card-bg-soft),var(--soft)); position:relative; overflow:hidden; }
.cockpit-card::before { content:''; position:absolute; top:0; left:0; right:0; height:1px; background:linear-gradient(90deg,transparent,var(--accent-glow),transparent); }
.cockpit-card::after { content:''; position:absolute; inset:-20% auto auto -10%; width:180px; height:180px; border-radius:50%; background:radial-gradient(circle, color-mix(in srgb, var(--accent) 16%, transparent) 0%, transparent 70%); opacity:0.22; pointer-events:none; filter:blur(6px); transition:transform 0.4s ease, opacity 0.3s ease; }
.cockpit-card[data-load="medium"] { border-color:rgba(239,159,39,0.24); box-shadow:0 10px 28px rgba(239,159,39,0.08); }
.cockpit-card[data-load="high"] { border-color:rgba(240,153,123,0.28); box-shadow:0 12px 32px rgba(240,153,123,0.1); }
.cockpit-card[data-load="critical"] { border-color:rgba(175,169,236,0.3); box-shadow:0 14px 40px rgba(175,169,236,0.14); }
.cockpit-card[data-load="medium"]::after { background:radial-gradient(circle, rgba(239,159,39,0.18) 0%, transparent 72%); opacity:0.26; }
.cockpit-card[data-load="high"]::after { background:radial-gradient(circle, rgba(240,153,123,0.2) 0%, transparent 74%); opacity:0.3; transform:translate3d(16px, 8px, 0); }
.cockpit-card[data-load="critical"]::after { background:radial-gradient(circle, rgba(175,169,236,0.24) 0%, transparent 76%); opacity:0.34; transform:translate3d(24px, 12px, 0) scale(1.05); }
.cockpit-head { display:flex; justify-content:space-between; gap:12px; align-items:flex-start; margin-bottom:16px; }
.cockpit-title { font-size:15px; font-weight:700; letter-spacing:-0.02em; }
.cockpit-sub { font-size:12px; color:var(--muted); line-height:1.5; margin-top:4px; }

/* Squad map */
.squad-map { min-height:300px; }
.squad-canvas { width:100%; min-height:300px; border:1px solid var(--canvas-border); border-radius:18px; background:radial-gradient(circle at top,var(--accent-soft),transparent 45%),linear-gradient(180deg,var(--canvas-top),var(--canvas-bottom)); overflow:hidden; position:relative; }
.squad-canvas::after { content:''; position:absolute; inset:-20% 0 auto; height:55%; background:linear-gradient(180deg, rgba(255,255,255,0.06), transparent 72%); opacity:0.22; pointer-events:none; mix-blend-mode:screen; animation:dashboard-scan 8s linear infinite; }
.squad-canvas :deep(svg) { width:100%; height:auto; display:block; }
.squad-canvas :deep(.squad-title) { font-size:12px; font-weight:700; fill:var(--ink); }
.squad-canvas :deep(.squad-subtitle) { font-size:11px; fill:var(--muted); }
.squad-canvas :deep(.node-label) { font-size:13.5px; font-weight:700; fill:var(--ink); letter-spacing:-0.01em; }
.squad-canvas :deep(.node-subtext) { font-size:11px; fill:var(--muted); }
.squad-canvas :deep(.radar-ring) { fill:none; stroke:var(--signal-line); stroke-width:1; stroke-dasharray:3 7; opacity:0.55; }
.squad-canvas :deep(.node-status) { stroke:var(--node-core); stroke-width:2; }
.squad-canvas :deep(.node-status.stale) { fill:none; stroke:var(--muted); stroke-width:2; }
.squad-canvas :deep(.node-live-halo) {
  fill:none;
  stroke-width:1.6;
  transform-box:fill-box;
  transform-origin:center;
  animation:node-live-halo 2.1s ease-out infinite;
}
.squad-canvas :deep(.node-pending circle) { fill:#EF9F27; stroke:var(--node-core); stroke-width:2; }
.squad-canvas :deep(.node-pending text) { fill:#231a02; font-size:10px; font-weight:800; }
.squad-canvas :deep(.node-crown) { fill:#EF9F27; stroke:var(--node-core); stroke-width:1; }
.squad-canvas :deep(.node-person) { fill:none; stroke:var(--glyph-ink); stroke-width:1.8; stroke-linecap:round; }
.squad-canvas :deep(.node-person circle) { fill:var(--glyph-ink); stroke:none; }
.squad-canvas :deep(.node-ring.operator .node-shell) { stroke-dasharray:3 4; }
.squad-canvas :deep(.mail-glyph rect) { fill:var(--impact-accent, var(--accent)); stroke:var(--node-core); stroke-width:1.4; }
.squad-canvas :deep(.mail-glyph > path) { fill:none; stroke:var(--node-core); stroke-width:1.4; stroke-linejoin:round; }
.squad-canvas :deep(.mail-glyph) { opacity:0.95; }
.squad-canvas :deep(.mail-glyph.queued) { opacity:0.55; }
.squad-canvas :deep(.signal-line) { stroke:var(--signal-line); stroke-width:2; }
.squad-canvas :deep(line.signal-line.live) { stroke:rgba(93, 202, 165, 0.3); }
.squad-canvas :deep(line.signal-line.operator-spoke) { stroke-dasharray:3 6; }
.squad-canvas :deep(.signal-line.route-pulse) { stroke-width:3; stroke-dasharray:8 10; stroke-linecap:round; animation:route-pulse 1.45s cubic-bezier(0.22,1,0.36,1) infinite; }
.squad-canvas :deep(.signal-line.route-pulse.queued) { opacity:0.42; animation-duration:1.95s; }
.squad-canvas :deep(.signal-line.route-pulse.dequeued) { opacity:0.74; animation-duration:1.1s; }
.squad-canvas :deep(.node-shell) { fill:var(--node-core); stroke:var(--shell-stroke); stroke-width:2; }
.squad-canvas :deep(.node-ring.online) { filter:drop-shadow(0 0 8px rgba(133,183,235,0.2)); }
.squad-canvas :deep(.node-ring.offline) { opacity:0.55; }
.squad-canvas :deep(.node-ring.offline .node-shell) { stroke-dasharray:4 5; }
.squad-canvas :deep(.node-aura) { fill:none; stroke:var(--member-accent, var(--accent)); stroke-width:2; opacity:0.2; transform-origin:center; }
.squad-canvas :deep(.node-ring.online .node-aura) { animation:node-aura-breathe 2.2s ease-in-out infinite; }
.squad-canvas :deep(.node-ring.busy .node-aura) { animation:node-aura-pulse 1.8s ease-in-out infinite; }
.squad-canvas :deep(.node-ring.message-send .node-aura) { animation:node-aura-ripple 1.2s ease-out infinite; }
.squad-canvas :deep(.node-ring.message-receive .node-aura) { animation:node-aura-ripple 1.35s ease-out infinite reverse; }
.squad-canvas :deep(.node-impact) { fill:none; stroke:var(--impact-accent, var(--accent)); stroke-width:3; opacity:0; }
.squad-canvas :deep(.node-impact.task) { animation:node-impact-task 1.2s ease-out infinite; }
.squad-canvas :deep(.node-impact.info) { stroke-dasharray:2 8; animation:node-impact-info 1.4s ease-out infinite; }
.squad-canvas :deep(.node-impact.reply) { stroke-dasharray:12 8; animation:node-impact-reply 1.3s ease-out infinite; }
.squad-canvas :deep(.node-impact.spark) { stroke-width:1.6; opacity:0.32; animation:node-impact-spark 1s ease-out infinite; }
.squad-canvas :deep(.node-impact.queued) { opacity:0.28; animation-duration:1.9s; }
.squad-canvas :deep(.node-impact.dequeued) { opacity:0.48; animation-duration:1.15s; }
.squad-canvas :deep(.node-float-tag) { opacity:0; animation:node-float-tag 1.05s ease-out infinite; }
.squad-canvas :deep(.node-float-pill) { fill:var(--impact-accent, var(--accent)); fill-opacity:0.88; }
.squad-canvas :deep(.node-float-text) { fill:#03131a; font-size:10px; font-weight:800; letter-spacing:0.05em; }
.squad-canvas :deep(.node-glyph) { font-size:11px; font-weight:800; fill:var(--glyph-ink); letter-spacing:0.06em; }

/* Empty state */
.empty-state { display:flex; flex-direction:column; align-items:center; gap:16px; padding:60px 24px; text-align:center; }
.empty-state span { color:var(--muted); font-size:14px; }

/* Animations */
@keyframes dashboard-scan { 0% { transform:translate3d(0, -18%, 0); opacity:0.08; } 30% { opacity:0.24; } 100% { transform:translate3d(0, 210%, 0); opacity:0; } }
@keyframes route-pulse { 0% { stroke-dashoffset:0; opacity:0.18; } 18% { opacity:0.95; } 100% { stroke-dashoffset:-36; opacity:0.24; } }
@keyframes node-aura-breathe { 0%, 100% { transform:scale(0.96); opacity:0.12; } 50% { transform:scale(1.06); opacity:0.3; } }
@keyframes node-live-halo { 0% { transform:scale(0.7); opacity:0.75; } 100% { transform:scale(2.1); opacity:0; } }
@keyframes node-aura-pulse { 0% { transform:scale(0.92); opacity:0.14; } 55% { transform:scale(1.12); opacity:0.34; } 100% { transform:scale(1.22); opacity:0; } }
@keyframes node-aura-ripple { 0% { transform:scale(0.88); opacity:0.2; } 50% { transform:scale(1.08); opacity:0.3; } 100% { transform:scale(1.26); opacity:0; } }
@keyframes node-impact-task { 0% { r:18; opacity:0.45; } 100% { r:44; opacity:0; } }
@keyframes node-impact-info { 0% { r:16; opacity:0.38; } 100% { r:42; opacity:0; } }
@keyframes node-impact-reply { 0% { r:14; opacity:0.42; } 100% { r:40; opacity:0; } }
@keyframes node-impact-spark { 0% { r:10; opacity:0.18; } 100% { r:34; opacity:0; } }
@keyframes node-float-tag { 0% { opacity:0; transform:translateY(10px); } 16% { opacity:1; } 100% { opacity:0; transform:translateY(-8px); } }

html[data-motion="reduced"] .squad-canvas::after,
html[data-motion="reduced"] .squad-canvas :deep(.route-pulse),
html[data-motion="reduced"] .squad-canvas :deep(.node-aura),
html[data-motion="reduced"] .squad-canvas :deep(.node-impact),
html[data-motion="reduced"] .squad-canvas :deep(.node-live-halo),
html[data-motion="reduced"] .squad-canvas :deep(.node-float-tag) {
  animation-duration: 1.8s !important;
}

html[data-motion="off"] .squad-canvas::after,
html[data-motion="off"] .squad-canvas :deep(.route-pulse),
html[data-motion="off"] .squad-canvas :deep(.node-aura),
html[data-motion="off"] .squad-canvas :deep(.node-impact),
html[data-motion="off"] .squad-canvas :deep(.node-live-halo),
html[data-motion="off"] .squad-canvas :deep(.node-float-tag) {
  animation: none !important;
}

/* The envelope rides an SMIL animateMotion, which CSS animation rules can't
   slow down — hide it outright when motion is reduced or off. */
html[data-motion="off"] .squad-canvas :deep(.mail-glyph),
html[data-motion="reduced"] .squad-canvas :deep(.mail-glyph) {
  display: none;
}
@media (prefers-reduced-motion: reduce) {
  .squad-canvas :deep(.mail-glyph) { display: none; }
}

/* Responsive */
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
