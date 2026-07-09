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
  normalizedRole, roleGlyph, memberPalette, heartbeatState, statusTone,
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
  const width = 1080
  const height = Math.max(300, 160 + others.length * 30)
  const chiefX = 200
  const chiefY = height / 2

  const nodes = new Map<string, { x: number; y: number; member: SessionMember }>()
  let markup = ''

  nodes.set(chiefMember.agent_name, { x: chiefX, y: chiefY, member: chiefMember })

  others.forEach((member, mi) => {
    const total = Math.max(1, others.length - 1)
    const baseX = others.length === 1 ? 760 : 470 + (mi * 420) / total
    const offset = others.length === 1 ? 0 : (mi % 2 === 0 ? -40 : 40)
    const y = chiefY + offset
    nodes.set(member.agent_name, { x: baseX, y, member })
    markup += `<line class="signal-line" x1="${chiefX}" y1="${chiefY}" x2="${baseX}" y2="${y}" />`
  })

  // Animated routes
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
  })

  // Nodes
  nodes.forEach(node => {
    const m = node.member
    const palette = memberPalette(m)
    const hbState = heartbeatState(m, cs)
    const liveClass = hbState === 'stale' ? 'offline' : 'online'
    const activity = memberActivity(m, activityMap)
    const activityClasses = [
      activity.isBusy ? 'busy' : '',
      activity.hasOutgoing ? 'message-send' : '',
      activity.hasIncoming ? 'message-receive' : '',
    ].filter(Boolean).join(' ')
    markup += `
      <g class="node-ring ${liveClass} ${activityClasses}">
        <circle class="node-aura" cx="${node.x}" cy="${node.y}" r="36"/>
        <circle class="node-shell" cx="${node.x}" cy="${node.y}" r="28"/>
        <circle cx="${node.x}" cy="${node.y}" r="19" fill="${palette.accent}"/>
        <circle cx="${node.x + 22}" cy="${node.y - 18}" r="5" fill="${statusTone(m.status)}"/>
        <text class="node-glyph" x="${node.x}" y="${node.y + 4}" text-anchor="middle">${escapeHtml(roleGlyph(m.role))}</text>
        <text class="node-label" x="${node.x}" y="${node.y + 50}" text-anchor="middle">${escapeHtml(m.agent_name || '-')}</text>
        <text class="node-subtext" x="${node.x}" y="${node.y + 66}" text-anchor="middle">${escapeHtml(m.current_task || translateStatus(t, m.status) || '-')}</text>
      </g>`
  })

  return `<svg viewBox="0 0 ${width} ${height}" role="img" aria-label="${escapeHtml(t('sd_squad_map_title'))}">${markup}</svg>`
})
</script>

<style scoped>
/* Cockpit card */
.cockpit-card { border:1px solid var(--line); border-radius:18px; padding:20px; background:linear-gradient(180deg,var(--card-bg-soft),var(--soft)); position:relative; overflow:hidden; }
.cockpit-card::before { content:''; position:absolute; top:0; left:0; right:0; height:1px; background:linear-gradient(90deg,transparent,var(--accent-glow),transparent); }
.cockpit-card::after { content:''; position:absolute; inset:-20% auto auto -10%; width:180px; height:180px; border-radius:50%; background:radial-gradient(circle, color-mix(in srgb, var(--accent) 16%, transparent) 0%, transparent 70%); opacity:0.22; pointer-events:none; filter:blur(6px); transition:transform 0.4s ease, opacity 0.3s ease; }
.cockpit-card[data-load="medium"] { border-color:rgba(251,191,36,0.24); box-shadow:0 10px 28px rgba(251,191,36,0.08); }
.cockpit-card[data-load="high"] { border-color:rgba(248,113,113,0.28); box-shadow:0 12px 32px rgba(248,113,113,0.1); }
.cockpit-card[data-load="critical"] { border-color:rgba(192,132,252,0.3); box-shadow:0 14px 40px rgba(192,132,252,0.14); }
.cockpit-card[data-load="medium"]::after { background:radial-gradient(circle, rgba(251,191,36,0.18) 0%, transparent 72%); opacity:0.26; }
.cockpit-card[data-load="high"]::after { background:radial-gradient(circle, rgba(248,113,113,0.2) 0%, transparent 74%); opacity:0.3; transform:translate3d(16px, 8px, 0); }
.cockpit-card[data-load="critical"]::after { background:radial-gradient(circle, rgba(192,132,252,0.24) 0%, transparent 76%); opacity:0.34; transform:translate3d(24px, 12px, 0) scale(1.05); }
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
.squad-canvas :deep(.node-label) { font-size:12px; font-weight:700; fill:var(--ink); }
.squad-canvas :deep(.node-subtext) { font-size:10px; fill:var(--muted); }
.squad-canvas :deep(.signal-line) { stroke:var(--signal-line); stroke-width:2; }
.squad-canvas :deep(.signal-line.route-pulse) { stroke-width:3; stroke-dasharray:8 10; stroke-linecap:round; animation:route-pulse 1.45s cubic-bezier(0.22,1,0.36,1) infinite; }
.squad-canvas :deep(.signal-line.route-pulse.queued) { opacity:0.42; animation-duration:1.95s; }
.squad-canvas :deep(.signal-line.route-pulse.dequeued) { opacity:0.74; animation-duration:1.1s; }
.squad-canvas :deep(.node-shell) { fill:var(--node-core); stroke:var(--shell-stroke); stroke-width:2; }
.squad-canvas :deep(.node-ring.online) { filter:drop-shadow(0 0 10px rgba(34,211,238,0.35)); }
.squad-canvas :deep(.node-ring.offline) { opacity:0.55; }
.squad-canvas :deep(.node-aura) { fill:none; stroke:var(--member-accent, var(--accent)); stroke-width:2; opacity:0.2; transform-origin:center; }
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
html[data-motion="reduced"] .squad-canvas :deep(.node-float-tag) {
  animation-duration: 1.8s !important;
}

html[data-motion="off"] .squad-canvas::after,
html[data-motion="off"] .squad-canvas :deep(.route-pulse),
html[data-motion="off"] .squad-canvas :deep(.node-aura),
html[data-motion="off"] .squad-canvas :deep(.node-impact),
html[data-motion="off"] .squad-canvas :deep(.node-float-tag) {
  animation: none !important;
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
