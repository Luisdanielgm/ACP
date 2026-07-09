<template>
  <section class="panel">
    <div class="panel-head">
      <div>
        <div class="panel-title">{{ t('sd_members_title') }}</div>
        <div class="muted">{{ t('sd_members_sub') }}</div>
      </div>
      <div class="filter-tools">
        <div class="filter-tools-group">
          <label class="inline-filter">
            <span>{{ t('sd_agent_filter_label') }}</span>
            <select :value="agentFilter" @change="$emit('update:agentFilter', ($event.target as HTMLSelectElement).value)">
              <option value="">{{ t('sd_agent_filter_all') }}</option>
              <option v-for="m in members" :key="m.agent_name" :value="m.agent_name">{{ m.agent_name }}</option>
            </select>
          </label>
          <UiButton type="button" variant="filter-chip" :active="problemMode" @click="$emit('update:problemMode', !problemMode)">
            {{ problemMode ? t('sd_problems_filter_on') : t('sd_problems_filter_off') }}
          </UiButton>
        </div>
        <div class="problem-summary muted">
          {{ problemSummary.memberCount || problemSummary.eventCount
            ? t('sd_issue_summary_members_events', { members: String(problemSummary.memberCount), events: String(problemSummary.eventCount) })
            : t('sd_problem_summary_clear') }}
        </div>
      </div>
    </div>
    <div class="panel-body">
      <div v-if="!visibleMembers.length" class="empty-state">
        <span>{{ problemMode ? t('sd_no_problem_members') : t('sd_no_filtered_events') }}</span>
      </div>
      <div v-else class="members">
        <div v-for="member in visibleMembers" :key="member.agent_name"
          class="member" :class="rosterMemberClasses(member)" :style="memberStyle(member)"
          :data-role="normalizedRole(member.role)">
          <div class="member-quick-top">
            <div class="member-title">
              <span class="role-chip" :class="'role-' + normalizedRole(member.role)"
                :style="{ background: memberPalette(member).soft, borderColor: memberPalette(member).glow, color: memberPalette(member).accent }">
                {{ roleIcon(member.role) }}
              </span>
              <div>
                <div class="member-name">{{ member.agent_name }}</div>
                <div class="member-tier">{{ translateRole(t, member.role) }} · {{ member.provider || '-' }}</div>
              </div>
            </div>
            <div class="member-signals">
              <span class="status-dot" :class="String(member.status || '').toLowerCase()"></span>
              <div class="pill status-badge" :class="String(member.status || '').toLowerCase()">{{ translateStatus(t, member.status) }}</div>
              <span class="op-state-badge" :class="getOpState(member).tone">{{ t('sd_' + getOpState(member).key) }}</span>
              <span class="health-badge" :class="getHeartbeatState(member)">{{ t('sd_heartbeat_' + getHeartbeatState(member)) }} · {{ heartbeatAgeSuffix(member) }}</span>
            </div>
          </div>
          <div class="member-trace-grid">
            <div v-for="metric in laneMetrics(member)" :key="metric.key" class="member-trace-card">
              <span class="member-trace-label">{{ metric.label }}</span>
              <strong class="member-trace-value">{{ metric.value }}</strong>
            </div>
          </div>
          <div v-if="getMemberIssues(member).length" class="issue-row">
            <span v-for="issue in getMemberIssues(member)" :key="issue.key" class="issue-pill" :class="issue.level">{{ t('sd_' + issue.label) }}</span>
          </div>
          <div class="member-activity-row">
            <span v-for="chip in activityChips(member)" :key="chip.key" class="activity-chip" :class="chip.className">
              <span v-if="chip.kind === 'working'" class="work-signal" aria-hidden="true"><span></span><span></span><span></span><span></span></span>
              <span>{{ chip.label }}</span>
            </span>
          </div>
          <div class="member-quick-meta">
            <span class="member-quick-role">{{ translateRole(t, member.role) }}</span>
            <span>·</span>
            <span>{{ translateDelivery(t, member.delivery_mode || 'attached') }}</span>
            <span>·</span>
            <span>{{ member.provider || '-' }}</span>
            <span>·</span>
            <span>{{ t('sd_last_seen_label') }}: {{ timeAgo(member.last_seen_at || member.joined_at, locale) }}</span>
          </div>
          <div class="member-quick-meta">
            <span>{{ t('sd_workspace_label') }}: {{ compactPath(member.workspace_path) }}</span>
            <span>·</span>
            <span>{{ t('sd_last_run_label') }}: {{ runSummary(member.last_run) }}</span>
          </div>
        </div>
      </div>
    </div>
  </section>
</template>

<script setup lang="ts">
import { useI18n, UiButton } from '@acp/shared'
import { messages } from '../../i18n'
import {
  normalizedRole, roleIcon, memberPalette, memberStyleVars,
  memberIssues, memberActivity, memberOperationalState, heartbeatState, heartbeatAgeSeconds,
  actionChipClass, compactPath, timeAgo, runSummary,
  type Issue, type MemberActivityData,
} from '../../composables/sessionHelpers'
import { translateRole, translateStatus, translateDelivery } from '../../composables/dashboardTranslations'
import type { SessionMember } from '../../api/sessions'

const props = defineProps<{
  members: SessionMember[]
  visibleMembers: SessionMember[]
  activityMap: Map<string, MemberActivityData>
  connectedSet: Set<string>
  isFirstRender: boolean
  agentFilter: string
  problemMode: boolean
  problemSummary: { memberCount: number; eventCount: number }
}>()

defineEmits<{
  'update:agentFilter': [value: string]
  'update:problemMode': [value: boolean]
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

function getHeartbeatState(member: SessionMember): string {
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
  const hbState = getHeartbeatState(member)
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

function memberStyle(member: SessionMember): string {
  return memberStyleVars(member)
}

function rosterMemberClasses(member: SessionMember): string[] {
  const activity = memberActivity(member, props.activityMap)
  const classes = [`role-${normalizedRole(member.role)}`]
  if (props.isFirstRender) classes.push('fade-in')
  if (activity.hasOutgoing) classes.push('activity-send')
  if (activity.hasIncoming) classes.push('activity-receive')
  if (activity.isBusy) classes.push('is-busy')
  return classes
}
</script>

<style scoped>
.panel { background: var(--panel); border: 1px solid var(--line); border-radius: 20px; backdrop-filter: blur(16px); -webkit-backdrop-filter: blur(16px); box-shadow: var(--shadow-elev); transition: transform 0.25s cubic-bezier(0.16, 1, 0.3, 1), border-color 0.25s ease, box-shadow 0.25s ease; }
.panel:hover { border-color: var(--hover-line); box-shadow: var(--shadow-glow); }
.panel-head { padding:12px 18px; border-bottom:1px solid var(--line); display:flex; justify-content:space-between; gap:10px; align-items:center; flex-wrap:wrap; }
.panel-title { font-weight:700; font-size:11px; text-transform:uppercase; letter-spacing:0.12em; color:var(--muted); position:relative; padding-left:12px; }
.panel-title::before { content:''; position:absolute; left:0; top:50%; transform:translateY(-50%); width:4px; height:4px; border-radius:50%; background:var(--accent); box-shadow:0 0 6px var(--accent-glow); }
.panel-body { padding:20px; }
.muted { color:var(--muted); }
.pill { display:inline-flex; align-items:center; gap:6px; border-radius:999px; padding:4px 12px; font-size:10px; font-weight:700; letter-spacing:0.05em; background:var(--accent-soft); color:var(--accent); border:1px solid var(--accent-glow); text-decoration:none; }

input, select { width:100%; border:1px solid var(--line); border-radius:10px; padding:8px 12px; font:inherit; font-size:13px; background:var(--input-bg,transparent); color:var(--ink); transition:all 0.2s ease; outline:none; }
input:focus, select:focus { border-color:var(--accent); box-shadow:0 0 0 3px var(--accent-glow); }

/* Filters */
.filter-tools { display:flex; flex-direction:column; gap:8px; align-items:flex-end; }
.filter-tools-group { display:flex; gap:8px; align-items:center; }
.inline-filter { display:inline-flex; align-items:center; gap:8px; color:var(--muted); font-size:11px; font-weight:700; letter-spacing:0.04em; text-transform:uppercase; }
.inline-filter select { min-width:140px; padding:6px 10px; border-radius:999px; font-size:12px; text-transform:none; }
.problem-summary { font-size:11px; }

/* Members roster */
.members { display:grid; gap:8px; }
.member { border:1px solid var(--line); border-radius:12px; padding:14px 16px; background:var(--card-bg-soft); position:relative; overflow:hidden; transition:all 0.2s ease; }
.member[data-role="chief"] { background:linear-gradient(180deg, color-mix(in srgb, var(--member-soft, transparent) 48%, var(--card-bg-soft)), var(--card-bg-soft)); }
.member[data-role="collaborator"] { background:linear-gradient(180deg, color-mix(in srgb, var(--member-soft, transparent) 34%, var(--card-bg-soft)), var(--card-bg-soft)); }
.member:hover { border-color:var(--hover-line); }
.member::after { content:''; position:absolute; inset:0; pointer-events:none; border-radius:inherit; background:linear-gradient(135deg, var(--member-soft, transparent) 0%, transparent 42%); opacity:0.9; }
.member.activity-send { box-shadow: inset 3px 0 0 var(--member-accent, transparent), 0 0 0 1px rgba(34,211,238,0.08), 0 0 22px var(--member-glow, transparent); }
.member.activity-receive { box-shadow: inset 3px 0 0 var(--member-accent, transparent), 0 0 0 1px rgba(34,211,238,0.08), 0 0 26px rgba(34,211,238,0.14); }
.member.is-busy { border-color: color-mix(in srgb, var(--member-accent, var(--accent)) 40%, var(--line)); }
.member-quick-top { display:flex; justify-content:space-between; gap:12px; align-items:center; }
.member-title { display:flex; align-items:center; gap:8px; }
.member-name { font-weight:600; font-size:13px; color:var(--ink); white-space:nowrap; overflow:hidden; text-overflow:ellipsis; }
.member-tier { margin-top:4px; font-size:10px; font-weight:700; letter-spacing:0.08em; text-transform:uppercase; color:var(--muted); }
.member-signals { display:flex; gap:8px; align-items:center; white-space:nowrap; font-size:11px; }
.member-trace-grid { display:grid; gap:8px; grid-template-columns:repeat(3, minmax(0,1fr)); margin-top:12px; }
.member-trace-card { border:1px solid var(--line); border-radius:10px; padding:8px 10px; background:var(--soft); display:grid; gap:4px; }
.member-trace-label { font-size:10px; font-weight:700; letter-spacing:0.05em; text-transform:uppercase; color:var(--muted); }
.member-trace-value { font-size:11px; font-weight:700; color:var(--ink); }
.member-quick-meta { display:flex; gap:8px; flex-wrap:wrap; margin-top:8px; font-size:11px; color:var(--muted); }
.member-quick-role { font-weight:600; }
.role-chip { display:inline-flex; align-items:center; justify-content:center; min-width:26px; height:22px; padding:0 8px; border-radius:999px; font-size:11px; font-weight:700; border:1px solid transparent; }
.status-dot { width:10px; height:10px; border-radius:50%; flex-shrink:0; }
.status-dot.idle { background:#34d399; box-shadow:0 0 8px #34d399; }
.status-dot.waiting { background:#fbbf24; box-shadow:0 0 8px #fbbf24; }
.status-dot.busy { background:#f87171; box-shadow:0 0 8px #f87171; }
.status-badge { font-size:10px; padding:3px 10px; }

/* Operational state */
.op-state-badge { display:inline-flex; align-items:center; gap:4px; border-radius:999px; padding:4px 10px; font-size:10px; font-weight:700; letter-spacing:0.04em; text-transform:uppercase; }
.op-state-badge.idle { color:#a1a1aa; background:rgba(161,161,170,0.08); border:1px solid rgba(161,161,170,0.18); }
.op-state-badge.listening { color:#34d399; background:rgba(52,211,153,0.08); border:1px solid rgba(52,211,153,0.18); }
.op-state-badge.alert { color:#fbbf24; background:rgba(251,191,36,0.08); border:1px solid rgba(251,191,36,0.18); }
.op-state-badge.working { color:#22d3ee; background:rgba(34,211,238,0.08); border:1px solid rgba(34,211,238,0.18); }
.op-state-badge.warning { color:#f87171; background:rgba(248,113,113,0.08); border:1px solid rgba(248,113,113,0.18); }

/* Health badge */
.health-badge { display:inline-flex; align-items:center; gap:6px; border-radius:999px; padding:4px 12px; font-size:10px; font-weight:700; letter-spacing:0.05em; border:1px solid transparent; }
.health-badge.live { color:#34d399; border-color:rgba(52,211,153,0.22); background:rgba(52,211,153,0.08); }
.health-badge.quiet { color:#fbbf24; border-color:rgba(251,191,36,0.22); background:rgba(251,191,36,0.08); }
.health-badge.stale { color:#f87171; border-color:rgba(248,113,113,0.22); background:rgba(248,113,113,0.08); }
.health-badge.unknown { color:#a1a1aa; border-color:rgba(161,161,170,0.22); background:rgba(161,161,170,0.08); }

/* Issues */
.issue-row { display:flex; gap:6px; flex-wrap:wrap; margin-top:8px; }
.issue-pill { display:inline-flex; align-items:center; gap:4px; border-radius:999px; padding:4px 10px; font-size:10px; font-weight:700; letter-spacing:0.04em; border:1px solid transparent; }
.issue-pill.high { color:#f87171; border-color:rgba(248,113,113,0.22); background:rgba(248,113,113,0.08); }
.issue-pill.medium { color:#fbbf24; border-color:rgba(251,191,36,0.22); background:rgba(251,191,36,0.08); }
.issue-pill.low { color:#c084fc; border-color:rgba(192,132,252,0.22); background:rgba(192,132,252,0.08); }

/* Activity chips (shared visual language with lane cards) */
.member-activity-row { display:flex; gap:8px; flex-wrap:wrap; align-items:center; margin-top:10px; }
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
@media (max-width:1080px) { .member-trace-grid { grid-template-columns:1fr; } }
@media (max-width:768px) {
  .panel-head { padding:14px 18px; flex-direction:column; align-items:flex-start; gap:10px; }
  .panel-body { padding:16px; }
  .member-quick-top { flex-direction:column; align-items:flex-start; gap:8px; }
  .member-signals { flex-wrap:wrap; }
  .filter-tools { align-items:flex-start; }
  .filter-tools-group { flex-direction:column; align-items:flex-start; }
}
@media (max-width:600px) {
  .panel { border-radius:14px; } .panel-head { padding:12px 14px; } .panel-body { padding:14px; }
}
@media (max-width:480px) {
  .panel { border-radius:12px; }
  .member { padding:10px 12px; }
}
@media (prefers-reduced-motion: reduce) {
  *, *::before, *::after { animation-duration:0.01ms !important; transition-duration:0.01ms !important; }
}
</style>
