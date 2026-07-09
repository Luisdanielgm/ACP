<template>
  <div class="cockpit-card" :data-load="trafficLevel">
    <div class="cockpit-head">
      <div>
        <div class="cockpit-title">{{ t('sd_member_lanes_title') }}</div>
        <div class="cockpit-sub">{{ t('sd_member_lanes_sub') }}</div>
      </div>
    </div>
    <div v-if="!members.length" class="empty-state">
      <span>{{ problemMode ? t('sd_no_problem_members') : t('sd_no_filtered_events') }}</span>
    </div>
    <div v-else class="lane-stack">
      <article v-for="(member, idx) in members" :key="member.agent_name"
        class="lane-card" :class="laneClasses(member)" :style="memberStyle(member, idx)"
        :data-role="normalizedRole(member.role)">
        <div class="lane-top">
          <div>
            <div class="lane-kicker">{{ translateRole(t, member.role) }}</div>
            <div class="lane-title-row">
              <div class="lane-title">{{ member.agent_name || '-' }}</div>
              <span class="lane-rank-pill" :class="'role-' + normalizedRole(member.role)">{{ roleIcon(member.role) }} {{ translateRole(t, member.role) }}</span>
            </div>
            <div class="lane-session">{{ member.provider || '-' }} · {{ compactPath(member.workspace_path) }}</div>
          </div>
          <span class="lane-role" :style="{ background: memberPalette(member).accent }">{{ roleGlyph(member.role) }}</span>
        </div>
        <div class="lane-meter-grid">
          <div v-for="metric in laneMetrics(member)" :key="metric.key" class="lane-meter-card">
            <div class="lane-meter-top">
              <span class="lane-meter-label">{{ metric.label }}</span>
              <span class="lane-meter-value">{{ metric.value }}</span>
            </div>
            <div class="lane-meter-track">
              <span class="lane-meter-fill" :class="metric.className" :style="{ width: `${metric.percent}%` }"></span>
            </div>
          </div>
        </div>
        <div class="lane-meta">
          <span class="op-state-badge" :class="getOpState(member).tone">{{ t('sd_' + getOpState(member).key) }}</span>
          <span>{{ translateStatus(t, member.status) }}</span>
          <span>{{ t('sd_delivery_mode_label') }}: {{ translateDelivery(t, member.delivery_mode || 'attached') }}</span>
          <span>{{ t('sd_pending_label') }}: {{ member.pending_count || 0 }}</span>
          <span>{{ t('sd_since_short') }} {{ timeAgo(member.last_seen_at || member.joined_at, locale) }}</span>
        </div>
        <div v-if="getMemberIssues(member).length" class="issue-row">
          <span v-for="issue in getMemberIssues(member)" :key="issue.key" class="issue-pill" :class="issue.level">{{ t('sd_' + issue.label) }}</span>
        </div>
        <div class="lane-activity-row">
          <span v-for="chip in activityChips(member)" :key="chip.key" class="activity-chip" :class="chip.className">
            <span v-if="chip.kind === 'working'" class="work-signal" aria-hidden="true"><span></span><span></span><span></span><span></span></span>
            <span>{{ chip.label }}</span>
          </span>
        </div>
        <div class="lane-task">
          <strong>{{ t('sd_current_task_label') }}:</strong> {{ member.current_task || member.status_text || t('sd_no_detail') }}
        </div>
        <div class="lane-meta">
          <span>{{ t('sd_provider_label') }}: {{ member.provider || '-' }}</span>
          <span>{{ t('sd_workspace_label') }}: {{ compactPath(member.workspace_path) }}</span>
        </div>
        <div class="lane-meta">
          <span>{{ t('sd_current_run_label') }}: {{ runSummary(member.current_run) }}</span>
        </div>
        <div class="lane-meta">
          <span>{{ t('sd_last_run_label') }}: {{ runSummary(member.last_run) }}</span>
        </div>
        <div v-if="adminActionsAvailable" class="lane-meta">
          <UiButton type="button" variant="ghost" size="xs" @click="$emit('disconnect-member', member.agent_name)">{{ t('sd_disconnect_member_btn') }}</UiButton>
        </div>
      </article>
    </div>
  </div>
</template>

<script setup lang="ts">
import { useI18n, UiButton } from '@acp/shared'
import { messages } from '../../i18n'
import {
  normalizedRole, roleGlyph, roleIcon, memberPalette, memberStyleVars,
  memberIssues, memberActivity, memberOperationalState, heartbeatState, heartbeatAgeSeconds,
  actionChipClass, compactPath, timeAgo, runSummary,
  type Issue, type MemberActivityData, type TrafficLevel,
} from '../../composables/sessionHelpers'
import { translateRole, translateStatus, translateDelivery } from '../../composables/dashboardTranslations'
import type { SessionMember } from '../../api/sessions'

const props = defineProps<{
  members: SessionMember[]
  activityMap: Map<string, MemberActivityData>
  connectedSet: Set<string>
  trafficLevel: TrafficLevel
  isFirstRender: boolean
  adminActionsAvailable: boolean
  problemMode: boolean
}>()

defineEmits<{
  'disconnect-member': [agentName: string]
}>()

const { locale, t } = useI18n(messages)

interface ActivityChip {
  key: string
  label: string
  className: string
  kind: 'working' | 'status'
}

interface LaneMetric {
  key: string
  label: string
  value: string
  percent: number
  className: string
}

function heartbeatStateFor(member: SessionMember): string {
  return heartbeatState(member, props.connectedSet)
}

function heartbeatAgeSuffix(member: SessionMember): string {
  const age = heartbeatAgeSeconds(member)
  return age === null ? '-' : `${age}s`
}

function getMemberIssues(member: SessionMember): Issue[] {
  return memberIssues(member, props.connectedSet)
}

function getOpState(member: SessionMember) {
  const activity = memberActivity(member, props.activityMap)
  const issues = getMemberIssues(member)
  return memberOperationalState(member, activity, issues)
}

function activityChips(member: SessionMember): ActivityChip[] {
  const activity = memberActivity(member, props.activityMap)
  const chips: ActivityChip[] = []
  if (activity.isBusy) {
    chips.push({ key: 'working', label: t('sd_activity_working'), className: 'busy', kind: 'working' })
  }
  if (activity.hasOutgoing) {
    const action = String(activity.lastActionType || '').toLowerCase()
    const labelKey = action ? `sd_activity_sent_${action}` : 'sd_activity_sending'
    chips.push({
      key: `sent-${action || 'generic'}`,
      label: t(labelKey),
      className: `send ${actionChipClass(activity.lastActionType)}`.trim(),
      kind: 'status',
    })
  }
  if (activity.hasIncoming) {
    chips.push({ key: 'receiving', label: t('sd_activity_receiving'), className: 'receive', kind: 'status' })
  }
  return chips
}

function laneMetrics(member: SessionMember): LaneMetric[] {
  const hbState = heartbeatStateFor(member)
  const hbPercent = hbState === 'live' ? 100 : hbState === 'quiet' ? 58 : hbState === 'stale' ? 18 : 34
  const pending = Number(member.pending_count || 0)
  const queuePercent = Math.min(100, pending * 24)
  const activity = memberActivity(member, props.activityMap)
  const flowCount = activity.sentTotal + activity.receivedTotal
  const flowPercent = Math.min(100, (activity.isBusy ? 36 : 12) + flowCount * 18)

  return [
    {
      key: 'heartbeat',
      label: t('sd_last_seen_label'),
      value: heartbeatAgeSuffix(member),
      percent: hbPercent,
      className: hbState,
    },
    {
      key: 'queue',
      label: t('sd_pending_label'),
      value: String(pending),
      percent: queuePercent,
      className: pending >= 3 ? 'hot' : pending > 0 ? 'warm' : 'idle',
    },
    {
      key: 'flow',
      label: t('sd_traffic_recent_events', { count: String(flowCount) }),
      value: activity.isBusy ? t('sd_activity_working') : translateStatus(t, member.status),
      percent: flowPercent,
      className: activity.isBusy ? 'active' : activity.hasOutgoing || activity.hasIncoming ? 'signal' : 'idle',
    },
  ]
}

function memberStyle(member: SessionMember, index?: number): string {
  let style = memberStyleVars(member)
  if (props.isFirstRender && index !== undefined) {
    style += `animation-delay:${index * 50}ms;`
  }
  return style
}

function laneClasses(member: SessionMember): string[] {
  const activity = memberActivity(member, props.activityMap)
  const classes: string[] = [`role-${normalizedRole(member.role)}`]
  if (props.isFirstRender) classes.push('fade-in')
  if (activity.hasOutgoing) classes.push('activity-send')
  if (activity.hasIncoming) classes.push('activity-receive')
  if (activity.isBusy) classes.push('is-busy')
  return classes
}
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

/* Lane stack */
.lane-stack { display:grid; gap:12px; }
.lane-stack::-webkit-scrollbar { width:6px; }
.lane-stack::-webkit-scrollbar-track { background:var(--scroll-track); border-radius:10px; }
.lane-stack::-webkit-scrollbar-thumb { background:var(--scroll-thumb); border-radius:10px; }
.lane-stack::-webkit-scrollbar-thumb:hover { background:var(--scroll-thumb-hover); }
.lane-card { border:1px solid var(--line); border-radius:12px; padding:14px; background:var(--card-bg-strong); position:relative; overflow:hidden; transition:all 0.25s ease; }
.lane-card.role-chief { background:linear-gradient(180deg, color-mix(in srgb, var(--member-soft, transparent) 55%, var(--card-bg-strong)), var(--card-bg-strong)); }
.lane-card.role-collaborator { background:linear-gradient(180deg, color-mix(in srgb, var(--member-soft, transparent) 42%, var(--card-bg-strong)), var(--card-bg-strong)); }
.lane-card:hover { border-color:var(--accent); transform:translateY(-2px); box-shadow:var(--shadow-glow); }
.lane-top { display:flex; justify-content:space-between; gap:12px; align-items:flex-start; }
.lane-kicker { font-size:10px; font-weight:800; letter-spacing:0.12em; text-transform:uppercase; color:var(--muted); }
.lane-title-row { display:flex; gap:8px; align-items:center; flex-wrap:wrap; margin-top:6px; }
.lane-title { font-size:14px; font-weight:700; }
.lane-session { font-size:11px; color:var(--muted); text-transform:uppercase; letter-spacing:0.08em; margin-top:6px; }
.lane-rank-pill { display:inline-flex; align-items:center; gap:6px; min-height:24px; padding:4px 10px; border-radius:999px; border:1px solid var(--line); background:var(--soft); font-size:10px; font-weight:800; letter-spacing:0.05em; text-transform:uppercase; }
.lane-rank-pill.role-chief { color:#facc15; border-color:rgba(250,204,21,0.24); background:rgba(250,204,21,0.09); }
.lane-rank-pill.role-collaborator { color:#818cf8; border-color:rgba(129,140,248,0.24); background:rgba(129,140,248,0.09); }
.lane-rank-pill.role-member { color:#22d3ee; border-color:rgba(34,211,238,0.24); background:rgba(34,211,238,0.09); }
.lane-role { display:inline-flex; align-items:center; justify-content:center; min-width:34px; height:26px; padding:0 10px; border-radius:999px; font-size:10px; font-weight:800; letter-spacing:0.08em; color:var(--glyph-ink); }
.lane-meter-grid { display:grid; gap:10px; grid-template-columns:repeat(3, minmax(0,1fr)); margin-top:14px; }
.lane-meter-card { border:1px solid var(--line); border-radius:12px; padding:10px 12px; background:var(--card-bg-soft); }
.lane-meter-top { display:flex; justify-content:space-between; gap:8px; align-items:baseline; }
.lane-meter-label { font-size:10px; font-weight:700; letter-spacing:0.06em; text-transform:uppercase; color:var(--muted); }
.lane-meter-value { font-size:11px; font-weight:700; color:var(--ink); text-align:right; }
.lane-meter-track { margin-top:10px; height:7px; border-radius:999px; background:rgba(148,163,184,0.12); overflow:hidden; }
.lane-meter-fill { display:block; height:100%; border-radius:inherit; background:rgba(148,163,184,0.35); transition:width 0.35s ease; }
.lane-meter-fill.live { background:linear-gradient(90deg, rgba(52,211,153,0.78), rgba(110,231,183,0.92)); }
.lane-meter-fill.quiet, .lane-meter-fill.warm { background:linear-gradient(90deg, rgba(251,191,36,0.76), rgba(253,224,71,0.92)); }
.lane-meter-fill.stale, .lane-meter-fill.hot { background:linear-gradient(90deg, rgba(248,113,113,0.78), rgba(252,165,165,0.92)); }
.lane-meter-fill.active, .lane-meter-fill.signal { background:linear-gradient(90deg, rgba(34,211,238,0.78), rgba(125,211,252,0.92)); }
.lane-meter-fill.idle { background:linear-gradient(90deg, rgba(148,163,184,0.54), rgba(203,213,225,0.8)); }
.lane-meta { margin-top:10px; font-size:11px; color:var(--muted); display:flex; flex-wrap:wrap; gap:10px; }
.lane-card::after { content:''; position:absolute; inset:0; pointer-events:none; border-radius:inherit; background:linear-gradient(135deg, var(--member-soft, transparent) 0%, transparent 42%); opacity:0.9; }
.lane-card.activity-send { box-shadow: inset 3px 0 0 var(--member-accent, transparent), 0 0 0 1px rgba(34,211,238,0.08), 0 0 22px var(--member-glow, transparent); }
.lane-card.activity-receive { box-shadow: inset 3px 0 0 var(--member-accent, transparent), 0 0 0 1px rgba(34,211,238,0.08), 0 0 26px rgba(34,211,238,0.14); }
.lane-card.is-busy { border-color: color-mix(in srgb, var(--member-accent, var(--accent)) 40%, var(--line)); }
.lane-task { margin-top:12px; border-radius:12px; border:1px solid rgba(34,211,238,0.16); background:rgba(34,211,238,0.08); padding:14px; font-size:12px; line-height:1.6; }
.lane-task strong { color:var(--accent); }
.lane-activity-row { display:flex; gap:8px; flex-wrap:wrap; align-items:center; margin-top:10px; }
.activity-chip { display:inline-flex; align-items:center; gap:6px; padding:4px 10px; border-radius:999px; font-size:10px; font-weight:800; letter-spacing:0.05em; text-transform:uppercase; border:1px solid transparent; }
.activity-chip.busy { color:#34d399; background:rgba(52,211,153,0.12); border-color:rgba(52,211,153,0.22); }
.activity-chip.send { color:var(--member-accent, var(--accent)); background:color-mix(in srgb, var(--member-accent, var(--accent)) 14%, transparent); border-color:color-mix(in srgb, var(--member-accent, var(--accent)) 22%, transparent); }
.activity-chip.receive { color:#67e8f9; background:rgba(34,211,238,0.12); border-color:rgba(34,211,238,0.22); }
.activity-chip.task { color:#fbbf24; }
.activity-chip.info { color:#22d3ee; }
.activity-chip.reply { color:#a78bfa; }
.work-signal { display:inline-flex; align-items:flex-end; gap:3px; height:14px; }
.work-signal span { display:inline-block; width:4px; border-radius:999px; background:var(--member-accent, var(--accent)); box-shadow:0 0 12px var(--member-glow, rgba(34,211,238,0.18)); animation:work-bars 1s steps(3, end) infinite; transform-origin:bottom; }
.work-signal span:nth-child(1) { height:6px; animation-delay:0s; }
.work-signal span:nth-child(2) { height:12px; animation-delay:0.16s; }
.work-signal span:nth-child(3) { height:8px; animation-delay:0.32s; }
.work-signal span:nth-child(4) { height:13px; animation-delay:0.48s; }

/* Operational state */
.op-state-badge { display:inline-flex; align-items:center; gap:4px; border-radius:999px; padding:4px 10px; font-size:10px; font-weight:700; letter-spacing:0.04em; text-transform:uppercase; }
.op-state-badge.idle { color:#a1a1aa; background:rgba(161,161,170,0.08); border:1px solid rgba(161,161,170,0.18); }
.op-state-badge.listening { color:#34d399; background:rgba(52,211,153,0.08); border:1px solid rgba(52,211,153,0.18); }
.op-state-badge.alert { color:#fbbf24; background:rgba(251,191,36,0.08); border:1px solid rgba(251,191,36,0.18); }
.op-state-badge.working { color:#22d3ee; background:rgba(34,211,238,0.08); border:1px solid rgba(34,211,238,0.18); }
.op-state-badge.warning { color:#f87171; background:rgba(248,113,113,0.08); border:1px solid rgba(248,113,113,0.18); }

/* Issues */
.issue-row { display:flex; gap:6px; flex-wrap:wrap; margin-top:8px; }
.issue-pill { display:inline-flex; align-items:center; gap:4px; border-radius:999px; padding:4px 10px; font-size:10px; font-weight:700; letter-spacing:0.04em; border:1px solid transparent; }
.issue-pill.high { color:#f87171; border-color:rgba(248,113,113,0.22); background:rgba(248,113,113,0.08); }
.issue-pill.medium { color:#fbbf24; border-color:rgba(251,191,36,0.22); background:rgba(251,191,36,0.08); }
.issue-pill.low { color:#c084fc; border-color:rgba(192,132,252,0.22); background:rgba(192,132,252,0.08); }

/* Empty state */
.empty-state { display:flex; flex-direction:column; align-items:center; gap:16px; padding:60px 24px; text-align:center; }
.empty-state span { color:var(--muted); font-size:14px; }

/* Animations */
@keyframes work-bars { 0%, 100% { transform:scaleY(0.72); opacity:0.52; } 45% { transform:scaleY(1.08); opacity:1; } }
.fade-in { animation:fadeIn 0.4s ease forwards; opacity:0; }
@keyframes fadeIn { to { opacity:1; } }

html[data-motion="reduced"] .work-signal span { animation-duration: 1.8s !important; }
html[data-motion="off"] .work-signal span { animation: none !important; }

/* Responsive */
@media (max-width:1080px) { .lane-meter-grid { grid-template-columns:1fr; } }
@media (max-width:768px) {
  .lane-title-row { align-items:flex-start; }
  .cockpit-card { padding:16px; border-radius:14px; }
}
@media (max-width:480px) {
  .cockpit-card { padding:12px; border-radius:12px; }
  .lane-card { padding:10px; border-radius:10px; }
}
@media (prefers-reduced-motion: reduce) {
  *, *::before, *::after { animation-duration:0.01ms !important; transition-duration:0.01ms !important; }
}
</style>
