<template>
  <div class="page">
    <!-- Hero -->
    <section class="hero">
      <div class="hero-top">
        <div style="display:flex;align-items:center;gap:12px">
          <div class="title">{{ t('sd_hero_title') }}</div>
          <button class="info-toggle" type="button" :title="t('sd_info_toggle_title')" @click="showSub = !showSub">i</button>
        </div>
        <div class="hero-controls">
          <LangToggle :messages="messages" />
          <ThemeToggle :messages="messages" />
          <MotionToggle :messages="messages" />
        </div>
      </div>
      <div class="hero-status-row">
        <div class="motion-status">{{ motionStatus }}</div>
        <UiButton type="button" variant="ghost" size="sm" @click="resetVisuals">{{ t('sd_visual_reset_btn') }}</UiButton>
      </div>
      <div class="sub" :class="{ show: showSub }">{{ t('sd_hero_sub') }}</div>
    </section>

    <!-- Access Strip -->
    <AccessStrip
      v-model:session-id="session.sessionIdInput.value"
      v-model:agent-name="session.agentNameInput.value"
      v-model:member-token="session.memberTokenInput.value"
      v-model:admin-token="session.adminTokenInput.value"
      v-model:access-mode="session.accessMode.value"
      v-model:access-compact="session.accessCompact.value"
      :dashboard-authenticated="session.dashboardAuthenticated.value"
      :has-payload="!!session.payload.value"
      :loading="session.loading.value"
      :polling="session.polling.value"
      :status-text="statusText"
      :status-is-error="session.statusIsError.value"
      @load="doLoad"
      @copy="onCopy"
    />

    <!-- Initial loading skeleton -->
    <section v-if="session.loading.value && !session.payload.value" class="panel">
      <div class="panel-body">
        <div class="empty-state">
          <span>{{ t('sd_session_waiting_load') }}</span>
        </div>
      </div>
    </section>

    <!-- Content (only when session loaded) -->
    <template v-if="session.payload.value">
      <!-- Layout: Summary + Health -->
      <div class="layout">
        <SessionSummary :payload="session.payload.value" @copy="onCopy" />
        <SessionHealth
          :health-state="session.healthState.value"
          :admin-actions-available="session.adminActionsAvailable.value"
          @copy-invite="copyInvite"
          @close-session="confirmCloseSession"
        />
      </div>

      <!-- Cockpit -->
      <div class="sections-stack">
        <section class="panel">
          <div class="panel-head">
            <div>
              <div class="panel-title">{{ t('sd_session_cockpit_title') }}</div>
              <div class="muted">{{ t('sd_session_cockpit_sub') }}</div>
            </div>
            <div class="traffic-status">
              <span class="traffic-chip" :class="session.trafficSnapshot.value.level">{{ t('sd_traffic_level_' + session.trafficSnapshot.value.level) }}</span>
              <span class="traffic-chip">{{ t('sd_traffic_recent_events', { count: String(session.trafficSnapshot.value.count) }) }}</span>
            </div>
          </div>
          <div class="panel-body">
            <!-- Signal legend -->
            <div class="signal-legend" role="img" :aria-label="t('sd_squad_map_title')">
              <span class="legend-chip"><span class="legend-line" style="background:#fbbf24"></span>{{ t('sd_legend_task') }}</span>
              <span class="legend-chip"><span class="legend-line" style="background:#22d3ee"></span>{{ t('sd_legend_info') }}</span>
              <span class="legend-chip"><span class="legend-line" style="background:#a78bfa"></span>{{ t('sd_legend_reply') }}</span>
              <span class="legend-chip">
                <span class="legend-work" aria-hidden="true"><span></span><span></span><span></span><span></span></span>
                {{ t('sd_legend_working') }}
              </span>
              <span class="legend-chip" :title="t('sd_legend_issue_low_help')"><span class="legend-dot" style="background:#c084fc"></span>{{ t('sd_legend_issue_low') }}</span>
              <span class="legend-chip" :title="t('sd_legend_issue_medium_help')"><span class="legend-dot" style="background:#fbbf24"></span>{{ t('sd_legend_issue_medium') }}</span>
              <span class="legend-chip" :title="t('sd_legend_issue_high_help')"><span class="legend-dot" style="background:#f87171"></span>{{ t('sd_legend_issue_high') }}</span>
            </div>
            <div v-if="pulseChips.length" class="pulse-strip">
              <span class="pulse-strip-label">{{ t('sd_session_cockpit_title') }}</span>
              <span v-for="chip in pulseChips" :key="chip.key" class="pulse-chip" :class="chip.className">{{ chip.label }}</span>
            </div>

            <div class="cockpit-grid">
              <SquadMap
                :payload="session.payload.value"
                :connected-set="session.connectedSet.value"
                :traffic-level="session.trafficSnapshot.value.level"
              />
              <MemberLanes
                :members="session.visibleMembers.value"
                :activity-map="session.activityMap.value"
                :connected-set="session.connectedSet.value"
                :traffic-level="session.trafficSnapshot.value.level"
                :is-first-render="session.isFirstRender.value"
                :admin-actions-available="session.adminActionsAvailable.value"
                :problem-mode="session.problemMode.value"
                @disconnect-member="confirmDisconnect"
              />
            </div>
          </div>
        </section>

        <!-- Member Roster -->
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

        <!-- Timeline -->
        <EventTimeline
          :events="session.filteredHistory.value"
          :members="session.members.value"
          v-model:timeline-filter="session.timelineFilter.value"
          :effective-motion="effectiveMotion"
        />

        <!-- Raw JSON -->
        <RawJsonPanel
          :payload="session.payload.value"
          v-model:show-raw-json="session.showRawJson.value"
        />
      </div>
    </template>
  </div>
</template>

<script setup lang="ts">
import { computed, ref, watchEffect } from 'vue'
import { useI18n, useTheme, useMotion, ThemeToggle, LangToggle, MotionToggle, UiButton } from '@acp/shared'
import { messages } from '../i18n'
import { useSessionDashboard } from '../composables/useSessionDashboard'
import { buildInvitePrompt, messageActionType, deliveryMode, actionChipClass, memberActivity } from '../composables/sessionHelpers'
import { translateDelivery } from '../composables/dashboardTranslations'
import AccessStrip from '../components/dashboard/AccessStrip.vue'
import SessionSummary from '../components/dashboard/SessionSummary.vue'
import SessionHealth from '../components/dashboard/SessionHealth.vue'
import SquadMap from '../components/dashboard/SquadMap.vue'
import MemberLanes from '../components/dashboard/MemberLanes.vue'
import MemberRoster from '../components/dashboard/MemberRoster.vue'
import EventTimeline from '../components/dashboard/EventTimeline.vue'
import RawJsonPanel from '../components/dashboard/RawJsonPanel.vue'

const props = defineProps<{
  authEndpoint?: string
  redirectPath?: string
}>()

const { locale, t } = useI18n(messages)
useTheme()
const { motion, resolveEffectiveMode, setMotion, applyMotion } = useMotion()

const session = useSessionDashboard({
  authEndpoint: props.authEndpoint,
  redirectPath: props.redirectPath,
})

const showSub = ref(false)

// ── Computed helpers ──

const statusText = computed(() => {
  if (session.statusMessage.value) return session.statusMessage.value
  if (!session.payload.value) return t('sd_status_not_loaded')
  return t('sd_session_loaded')
})

const motionStatus = computed(() => {
  const effective = resolveEffectiveMode(session.trafficSnapshot.value.level)
  if (motion.value === 'auto') {
    return `${t('sd_traffic_auto_hint')} ${effective.toUpperCase()}`
  }
  return `Motion: ${effective.toUpperCase()}`
})

const effectiveMotion = computed(() => resolveEffectiveMode(session.trafficSnapshot.value.level))

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
      label: `${t('sd_action_' + action)} ${count}`,
      className: actionChipClass(action),
    })
  })

  ;(['immediate', 'queued', 'dequeued'] as const).forEach(delivery => {
    const count = deliveryCounts.get(delivery) || 0
    if (!count) return
    chips.push({
      key: `delivery-${delivery}`,
      label: `${translateDelivery(t, delivery)} ${count}`,
      className: delivery,
    })
  })

  if (busyCount) {
    chips.push({
      key: 'busy-members',
      label: `${t('sd_activity_working')} ${busyCount}`,
      className: 'busy',
    })
  }

  if (!chips.length && recentEvents.length) {
    chips.push({
      key: 'recent-events',
      label: t('sd_traffic_recent_events', { count: String(recentEvents.length) }),
      className: 'neutral',
    })
  }

  return chips
})

// ── Actions ──

async function doLoad() {
  const sessionId = session.sessionIdInput.value.trim()
  const agentName = session.agentNameInput.value.trim()
  const memberToken = session.memberTokenInput.value.trim()
  const adminAccess = Boolean(session.adminTokenInput.value.trim() || session.dashboardAuthenticated.value)
  const memberAccess = Boolean(agentName && memberToken)

  if (!sessionId) {
    session.setStatus(t('sd_missing_session_id_status'), true)
    return
  }
  if (session.accessMode.value === 'member' && !memberAccess) {
    session.setStatus(t('sd_access_member_requirements'), true)
    return
  }
  if (session.accessMode.value === 'admin' && !adminAccess) {
    session.setStatus(t('sd_access_admin_requirements'), true)
    return
  }
  if (session.accessMode.value === 'hybrid' && (!memberAccess || !adminAccess)) {
    session.setStatus(t('sd_access_hybrid_requirements'), true)
    return
  }

  const ok = await session.loadSession(true)
  if (ok) {
    session.accessCompact.value = true
    session.startPolling()
  }
}

async function copyValue(value: string, label: string) {
  try {
    await navigator.clipboard.writeText(value)
    session.setStatus(t('sd_copied_value', { label }))
  } catch {
    session.setStatus(t('sd_copy_failed', { label }), true)
  }
}

function onCopy(payload: { value: string; label: string }) {
  copyValue(payload.value, payload.label)
}

async function copyInvite() {
  if (!session.payload.value) return
  const text = buildInvitePrompt(session.payload.value, locale.value)
  copyValue(text, t('sd_invite_prompt_label'))
}

async function confirmCloseSession() {
  if (!confirm(t('sd_confirm_close_session'))) return
  const ok = await session.doCloseSession()
  if (ok) session.setStatus(t('sd_session_closed_admin'))
}

async function confirmDisconnect(agentName: string) {
  if (!confirm(t('sd_confirm_disconnect_member', { agent: agentName }))) return
  const ok = await session.doDisconnectMember(agentName)
  if (ok) session.setStatus(t('sd_member_disconnected_admin', { agent: agentName }))
}

function resetVisuals() {
  session.resetFilters()
  setMotion('auto')
  applyMotion(session.trafficSnapshot.value.level)
}

// ── Page title ──
watchEffect(() => {
  document.title = t('sd_page_title')
})

watchEffect(() => {
  applyMotion(session.trafficSnapshot.value.level)
})
</script>

<style src="../../../shared/src/tokens/dashboard.css"></style>
<style src="../../../shared/src/tokens/semantic.css"></style>
<style scoped>
.page { max-width: 1400px; margin: 0 auto; padding: 24px; position: relative; z-index: 1; }
.hero {
  background: var(--panel);
  border: 1px solid var(--line);
  border-radius: 20px;
  backdrop-filter: blur(16px);
  -webkit-backdrop-filter: blur(16px);
  box-shadow: var(--shadow-elev);
  transition: transform 0.25s cubic-bezier(0.16, 1, 0.3, 1), border-color 0.25s ease, box-shadow 0.25s ease;
}
.hero:hover { border-color: var(--hover-line); box-shadow: var(--shadow-glow); }
.hero { padding: 14px 24px; margin-bottom: 18px; position: relative; overflow: hidden; }
.hero::after { content:''; position:absolute; top:0; left:0; right:0; height:1px; background:linear-gradient(90deg,transparent,var(--accent-glow),transparent); }
.hero-top { display:flex; justify-content:space-between; gap:16px; align-items:center; flex-wrap:wrap; }
.title { font-size:22px; font-weight:800; line-height:1.2; letter-spacing:-0.03em; background:linear-gradient(90deg,var(--title-start),var(--title-end)); -webkit-background-clip:text; -webkit-text-fill-color:transparent; }
.sub { margin-top:0; color:var(--muted); max-width:920px; line-height:1.5; font-size:13px; font-weight:300; display:none; }
.sub.show { display:block; }
.hero-status-row { margin-top:12px; display:flex; justify-content:space-between; gap:12px; align-items:center; flex-wrap:wrap; }
.motion-status { font-size:11px; font-weight:700; color:var(--muted); letter-spacing:0.04em; text-transform:uppercase; }
.info-toggle { background:none; border:1px solid var(--line); color:var(--muted); width:28px; height:28px; border-radius:50%; font-size:14px; padding:0; display:inline-flex; align-items:center; justify-content:center; cursor:pointer; transition:all 0.15s ease; flex-shrink:0; }
.info-toggle:hover { color:var(--ink); border-color:var(--hover-line); background:var(--trace-hover); transform:none; box-shadow:none; }
.hero-controls { display:inline-flex; gap:8px; align-items:center; flex-wrap:wrap; }
.layout { display:grid; gap:20px; grid-template-columns:1fr 1fr; margin-top:20px; }
.sections-stack { display:grid; gap:18px; margin-top:18px; }

.panel {
  background: var(--panel);
  border: 1px solid var(--line);
  border-radius: 20px;
  backdrop-filter: blur(16px);
  -webkit-backdrop-filter: blur(16px);
  box-shadow: var(--shadow-elev);
  transition: transform 0.25s cubic-bezier(0.16, 1, 0.3, 1), border-color 0.25s ease, box-shadow 0.25s ease;
}
.panel:hover { border-color: var(--hover-line); box-shadow: var(--shadow-glow); }
.panel-head { padding:12px 18px; border-bottom:1px solid var(--line); display:flex; justify-content:space-between; gap:10px; align-items:center; flex-wrap:wrap; }
.panel-title { font-weight:700; font-size:11px; text-transform:uppercase; letter-spacing:0.12em; color:var(--muted); position:relative; padding-left:12px; }
.panel-title::before { content:''; position:absolute; left:0; top:50%; transform:translateY(-50%); width:4px; height:4px; border-radius:50%; background:var(--accent); box-shadow:0 0 6px var(--accent-glow); }
.panel-body { padding:20px; }
.muted { color:var(--muted); }

/* Traffic */
.traffic-status { display:flex; gap:8px; flex-wrap:wrap; align-items:center; justify-content:flex-end; }
.traffic-chip { display:inline-flex; align-items:center; gap:6px; padding:6px 12px; border-radius:999px; border:1px solid var(--line); background:var(--soft); font-size:10px; font-weight:800; letter-spacing:0.05em; text-transform:uppercase; color:var(--muted); }
.traffic-chip.low { color:#34d399; border-color:rgba(52,211,153,0.22); background:rgba(16,185,129,0.08); }
.traffic-chip.medium { color:#fbbf24; border-color:rgba(251,191,36,0.24); background:rgba(251,191,36,0.1); }
.traffic-chip.high { color:#f87171; border-color:rgba(248,113,113,0.24); background:rgba(248,113,113,0.1); }
.traffic-chip.critical { color:#c084fc; border-color:rgba(192,132,252,0.24); background:rgba(192,132,252,0.1); }

/* Signal legend */
.signal-legend { display:flex; flex-wrap:wrap; gap:10px; margin-bottom:18px; padding:12px 16px; border:1px solid var(--line); border-radius:12px; background:var(--card-bg-soft); }
.legend-chip { display:inline-flex; align-items:center; gap:6px; font-size:10px; font-weight:700; color:var(--muted); letter-spacing:0.05em; }
.legend-line { width:18px; height:3px; border-radius:2px; }
.legend-dot { width:8px; height:8px; border-radius:50%; }
.legend-work { display:inline-flex; align-items:flex-end; gap:3px; height:14px; }
.legend-work span { display:inline-block; width:4px; border-radius:999px; background:#34d399; box-shadow:0 0 12px rgba(52,211,153,0.26); animation:work-bars 1s steps(3, end) infinite; transform-origin:bottom; }
.legend-work span:nth-child(1) { height:5px; animation-delay:0s; }
.legend-work span:nth-child(2) { height:11px; animation-delay:0.16s; }
.legend-work span:nth-child(3) { height:7px; animation-delay:0.32s; }
.legend-work span:nth-child(4) { height:12px; animation-delay:0.48s; }
.pulse-strip { display:flex; flex-wrap:wrap; align-items:center; gap:10px; margin:-2px 0 18px; padding:10px 14px; border:1px solid var(--line); border-radius:14px; background:linear-gradient(180deg,var(--card-bg-soft),transparent); }
.pulse-strip-label { font-size:10px; font-weight:800; letter-spacing:0.12em; text-transform:uppercase; color:var(--muted); margin-right:4px; }
.pulse-chip { display:inline-flex; align-items:center; gap:6px; min-height:28px; padding:6px 12px; border-radius:999px; border:1px solid var(--line); background:var(--soft); color:var(--muted); font-size:10px; font-weight:800; letter-spacing:0.05em; text-transform:uppercase; }
.pulse-chip.task { color:#fbbf24; border-color:rgba(251,191,36,0.24); background:rgba(251,191,36,0.1); }
.pulse-chip.info { color:#22d3ee; border-color:rgba(34,211,238,0.24); background:rgba(34,211,238,0.1); }
.pulse-chip.reply { color:#a78bfa; border-color:rgba(167,139,250,0.24); background:rgba(167,139,250,0.1); }
.pulse-chip.busy { color:#34d399; border-color:rgba(52,211,153,0.22); background:rgba(52,211,153,0.1); }
.pulse-chip.immediate { color:#67e8f9; border-color:rgba(103,232,249,0.24); background:rgba(34,211,238,0.08); }
.pulse-chip.queued { color:#fbbf24; border-color:rgba(251,191,36,0.2); background:rgba(251,191,36,0.08); opacity:0.88; }
.pulse-chip.dequeued { color:#f8fafc; border-color:rgba(248,250,252,0.22); background:rgba(148,163,184,0.12); }
.pulse-chip.neutral { color:var(--ink); }

/* Cockpit */
.cockpit-grid { display:grid; gap:16px; grid-template-columns:minmax(0,1.6fr) minmax(280px,0.9fr); }

/* Empty state */
.empty-state { display:flex; flex-direction:column; align-items:center; gap:16px; padding:60px 24px; text-align:center; }
.empty-state span { color:var(--muted); font-size:14px; }

/* Animations */
@keyframes work-bars { 0%, 100% { transform:scaleY(0.72); opacity:0.52; } 45% { transform:scaleY(1.08); opacity:1; } }

html[data-motion="reduced"] .legend-work span { animation-duration: 1.8s !important; }
html[data-motion="off"] .legend-work span { animation: none !important; }

/* Responsive */
@media (max-width:1400px) { .page { max-width:1200px; } }
@media (max-width:1200px) { .cockpit-grid { grid-template-columns:1fr; } }
@media (max-width:1080px) { .layout { grid-template-columns:1fr; } }
@media (max-width:900px) { .page { padding:20px; } .hero { padding:20px; } .hero-top { flex-direction:column; align-items:flex-start; gap:16px; } .hero-controls { width:100%; } }
@media (max-width:768px) {
  .page { padding:16px; } .hero { padding:18px; border-radius:16px; }
  .panel-head { padding:14px 18px; flex-direction:column; align-items:flex-start; gap:10px; }
  .panel-body { padding:16px; } .title { font-size:20px; }
  .traffic-status { justify-content:flex-start; }
}
@media (max-width:600px) {
  .page { padding:12px; } .hero { padding:16px; border-radius:14px; } .title { font-size:18px; }
  .panel { border-radius:14px; } .panel-head { padding:12px 14px; } .panel-body { padding:14px; }
}
@media (max-width:480px) {
  .page { padding:10px; } .hero { padding:14px; border-radius:12px; } .title { font-size:16px; }
  .panel { border-radius:12px; }
}
@media (prefers-reduced-motion: reduce) {
  *, *::before, *::after { animation-duration:0.01ms !important; transition-duration:0.01ms !important; }
}
</style>
