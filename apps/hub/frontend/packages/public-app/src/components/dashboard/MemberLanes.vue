<template>
  <div class="cockpit-card" :data-load="trafficLevel">
    <div class="cockpit-head">
      <div class="cockpit-title">{{ t('sd_member_lanes_title') }}</div>
    </div>
    <div v-if="!members.length" class="empty-state">
      <span>{{ problemMode ? t('sd_no_problem_members') : t('sd_no_filtered_events') }}</span>
    </div>
    <div v-else class="lane-stack">
      <article
        v-for="member in members"
        :key="member.agent_name"
        class="lane"
        :class="laneClasses(member)"
        :data-role="normalizedRole(member.role)"
        :style="{ '--role-accent': avatarAccent(member) }"
        :title="laneTooltip(member)"
        @click="toggleLane(member.agent_name)"
      >
        <span class="lane-avatar">
          <img class="lane-avatar-face" :class="{ ghost: isStale(member) }" :src="avatarSrc(member)" :alt="member.agent_name" />
          <img class="lane-avatar-badge" :src="presenceSrc(member)" alt="" aria-hidden="true" />
          <span v-if="normalizedRole(member.role) === 'chief'" class="lane-crown" aria-hidden="true">♛</span>
        </span>
        <div class="lane-id">
          <div class="lane-line">
            <span class="lane-name" :title="member.agent_name">{{ displayName(member) }}</span>
            <span v-if="domainOf(member)" class="lane-domain" :style="{ color: avatarAccent(member) }">
              <svg viewBox="0 0 24 24" width="11" height="11" fill="none" stroke="currentColor" stroke-width="2.4" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path :d="domainGlyphPath(domainOf(member)!)" /></svg>
              {{ t('sd_domain_' + domainOf(member)) }}
            </span>
            <span class="op-chip" :class="getOpState(member).tone">
              <img class="op-icon" :src="operationSrc(member)" alt="" aria-hidden="true" />{{ t('sd_' + getOpState(member).key) }}
            </span>
            <span class="lane-role-pill" :class="'role-' + normalizedRole(member.role)">{{ translateRole(t, member.role) }}</span>
            <span
              v-if="topIssue(member)"
              class="lane-issue"
              :class="topIssue(member)!.level"
              :title="t('sd_' + topIssue(member)!.label)"
            ></span>
            <button
              class="lane-expand"
              type="button"
              :aria-expanded="isExpanded(member)"
              :aria-label="t('sd_lane_detail_toggle')"
              :title="t('sd_lane_detail_toggle')"
            >
              <svg width="10" height="10" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="3" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M6 9l6 6 6-6" /></svg>
            </button>
          </div>
        </div>
        <div class="lane-cells">
          <div class="lane-cell" :class="{ warn: pendingOf(member) > 0 }">
            <span class="cell-label">{{ t('sd_pending_label') }}</span>
            <span class="cell-value">{{ pendingOf(member) }}</span>
          </div>
          <div class="lane-cell">
            <span class="cell-label">{{ t('sd_last_event_meta') }}</span>
            <span class="cell-value">{{ lastSeen(member) }}</span>
          </div>
          <div class="lane-cell task-cell">
            <span class="cell-label">{{ t('sd_current_task_label') }}</span>
            <span class="cell-value clamp">{{ member.current_task || member.status_text || t('sd_no_detail') }}</span>
          </div>
        </div>
        <!-- Expanded detail: real snapshot fields the compact row has no room for. -->
        <div v-if="isExpanded(member)" class="lane-detail">
          <div v-if="member.joined_at" class="detail-item">
            <span class="detail-label">{{ t('sd_joined_label') }}</span>
            <span class="detail-value">{{ timeAgo(member.joined_at, locale) }}</span>
          </div>
          <div v-if="member.current_task && member.current_task_from" class="detail-item">
            <span class="detail-label">{{ t('sd_task_from_label') }}</span>
            <span class="detail-value">{{ nameOf(member.current_task_from) }}</span>
          </div>
          <div v-if="member.delivery_mode" class="detail-item">
            <span class="detail-label">{{ t('sd_delivery_mode_label') }}</span>
            <span class="detail-value">{{ deliveryLabel(member.delivery_mode) }}</span>
          </div>
          <div v-if="member.provider && member.provider !== '-'" class="detail-item">
            <span class="detail-label">{{ t('sd_provider_label') }}</span>
            <span class="detail-value">{{ member.provider }}<template v-if="member.workspace_path"> · {{ compactPath(member.workspace_path) }}</template></span>
          </div>
          <div v-if="runSummary(member.last_run) !== '-'" class="detail-item">
            <span class="detail-label">{{ t('sd_last_run_label') }}</span>
            <span class="detail-value">{{ runSummary(member.last_run) }}</span>
          </div>
        </div>
        <button
          v-if="adminActionsAvailable"
          class="lane-kick"
          type="button"
          :title="t('sd_disconnect_member_btn')"
          :aria-label="t('sd_disconnect_member_btn')"
          @click.stop="$emit('disconnect-member', member.agent_name)"
        >
          <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.4" stroke-linecap="round" aria-hidden="true"><path d="M18 6L6 18" /><path d="M6 6l12 12" /></svg>
        </button>
      </article>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed, ref } from 'vue'
import { useI18n } from '@acp/shared'
import { messages } from '../../i18n'
import {
  normalizedRole, memberPalette, isWebOperator,
  memberIssues, memberActivity, memberOperationalState, heartbeatState,
  timeAgo, maxIssueLevel, agentDisplayNames, humanizeAgentName, compactPath, runSummary,
  avatarForMember, presenceIconName, operationIconName, domainForMember, domainGlyphPath,
  type Issue, type MemberActivityData, type TrafficLevel,
} from '../../composables/sessionHelpers'
import { avatarUrl, stateIconUrl } from '../../assets/acp/acpAssets'
import { translateRole, translateDisplayName } from '../../composables/dashboardTranslations'
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

const displayNames = computed(() =>
  agentDisplayNames(props.members.filter(m => !isWebOperator(m.agent_name)).map(m => m.agent_name))
)

function nameOf(agentName: string): string {
  return translateDisplayName(
    locale.value,
    displayNames.value.get(agentName) || humanizeAgentName(agentName)
  )
}

function displayName(member: SessionMember): string {
  return nameOf(member.agent_name)
}

// ── Expandable detail row ──

const expanded = ref(new Set<string>())

function isExpanded(member: SessionMember): boolean {
  return expanded.value.has(member.agent_name)
}

// The whole row toggles; the chevron button rides the same bubbled click and
// only adds keyboard focus + aria-expanded.
function toggleLane(agentName: string) {
  const next = new Set(expanded.value)
  if (next.has(agentName)) next.delete(agentName)
  else next.add(agentName)
  expanded.value = next
}

function deliveryLabel(mode: string): string {
  const known = ['attached', 'runner', 'immediate', 'queued', 'dequeued']
  return known.includes(mode) ? t('sd_delivery_' + mode) : mode
}

function isStale(member: SessionMember): boolean {
  return heartbeatState(member, props.connectedSet) === 'stale'
}

function pendingOf(member: SessionMember): number {
  return Number(member.pending_count || 0)
}

function lastSeen(member: SessionMember): string {
  return timeAgo(member.last_seen_at || member.joined_at, locale.value)
}

function avatarAccent(member: SessionMember): string {
  return isWebOperator(member.agent_name) ? '#a1aab5' : memberPalette(member).accent
}

function domainOf(member: SessionMember): string | null {
  return domainForMember(member)
}

function getMemberIssues(member: SessionMember): Issue[] {
  return memberIssues(member, props.connectedSet)
}

function getOpState(member: SessionMember) {
  const activity = memberActivity(member, props.activityMap)
  return memberOperationalState(member, activity, getMemberIssues(member))
}

function topIssue(member: SessionMember): Issue | null {
  const issues = getMemberIssues(member)
  if (!issues.length) return null
  const level = maxIssueLevel(issues)
  return issues.find(i => i.level === level) || issues[0]
}

function avatarSrc(member: SessionMember): string {
  return avatarUrl(avatarForMember(member), 256)
}

function presenceSrc(member: SessionMember): string {
  return stateIconUrl(presenceIconName(member, props.connectedSet))
}

function operationSrc(member: SessionMember): string {
  return stateIconUrl(operationIconName(getOpState(member), pendingOf(member)))
}

// Full detail on hover: the compact row hides provider/workspace/run info,
// the tooltip keeps it one hover away.
function laneTooltip(member: SessionMember): string {
  const lines = [member.agent_name]
  if (member.provider && member.provider !== '-') lines.push(`${member.provider} · ${compactPath(member.workspace_path)}`)
  const current = runSummary(member.current_run)
  if (current !== '-') lines.push(`run: ${current}`)
  const last = runSummary(member.last_run)
  if (last !== '-') lines.push(`last: ${last}`)
  return lines.join('\n')
}

function laneClasses(member: SessionMember): string[] {
  const activity = memberActivity(member, props.activityMap)
  const classes: string[] = [`role-${normalizedRole(member.role)}`]
  if (props.isFirstRender) classes.push('fade-in')
  if (activity.isBusy) classes.push('is-busy')
  if (isStale(member)) classes.push('is-stale')
  if (isExpanded(member)) classes.push('is-open')
  return classes
}
</script>

<style scoped>
/* Cockpit card */
.cockpit-card { display:flex; flex-direction:column; min-height:0; border:1px solid var(--line); border-radius:18px; padding:16px; background:linear-gradient(180deg,var(--card-bg-soft),var(--soft)); position:relative; overflow:hidden; }
.cockpit-card::before { content:''; position:absolute; top:0; left:0; right:0; height:1px; background:linear-gradient(90deg,transparent,var(--accent-glow),transparent); }
.cockpit-card[data-load="medium"] { border-color:rgba(239,159,39,0.24); }
.cockpit-card[data-load="high"] { border-color:rgba(240,153,123,0.28); }
.cockpit-card[data-load="critical"] { border-color:rgba(175,169,236,0.3); }
.cockpit-head { display:flex; justify-content:space-between; gap:12px; align-items:flex-start; margin-bottom:8px; flex-shrink:0; }
.cockpit-title { font-size:14px; font-weight:700; letter-spacing:-0.02em; }

/* Compact lane rows */
.lane-stack { display:flex; flex-direction:column; gap:8px; overflow-y:auto; min-height:0; padding-right:4px; }
.lane-stack::-webkit-scrollbar { width:6px; }
.lane-stack::-webkit-scrollbar-track { background:var(--scroll-track); border-radius:10px; }
.lane-stack::-webkit-scrollbar-thumb { background:var(--scroll-thumb); border-radius:10px; }
.lane-stack::-webkit-scrollbar-thumb:hover { background:var(--scroll-thumb-hover); }

.lane {
  display:grid;
  grid-template-columns:60px minmax(0, 1fr) auto;
  grid-template-rows:minmax(24px, auto) auto;
  gap:6px 10px;
  padding:8px 10px; border:1px solid var(--line); border-radius:12px;
  background:var(--card-bg-strong); position:relative; overflow:hidden;
  cursor:pointer;
  transition:border-color 0.2s ease, box-shadow 0.2s ease;
}
.lane::after { content:''; position:absolute; inset:0 auto 0 0; width:3px; background:var(--role-accent, transparent); opacity:0.85; }
.lane.is-busy { border-color:color-mix(in srgb, var(--role-accent, var(--accent)) 40%, var(--line)); box-shadow:0 0 18px color-mix(in srgb, var(--role-accent, var(--accent)) 12%, transparent); }
.lane.is-stale { opacity:0.72; }
.lane:hover { border-color:var(--hover-line); }

.lane-avatar { grid-column:1; grid-row:1 / 3; align-self:center; position:relative; width:60px; height:60px; flex-shrink:0; }
.lane-avatar-face { width:60px; height:60px; border-radius:50%; object-fit:cover; border:2px solid var(--role-accent, var(--accent)); display:block; }
.lane-avatar-face.ghost { filter:grayscale(1) brightness(0.7); opacity:0.6; }
.lane-avatar-badge { position:absolute; right:-2px; bottom:-2px; width:17px; height:17px; filter:drop-shadow(0 1px 2px rgba(0,0,0,0.45)); }
.lane-crown { position:absolute; top:-10px; left:50%; transform:translateX(-50%); font-size:14px; color:#EF9F27; line-height:1; text-shadow:0 1px 2px rgba(0,0,0,0.5); }

/* Identity and cells SHARE the row proportionally (mockup ratio ~40/60):
   the name column can never collapse to zero, the cells shrink gracefully. */
.lane-id { grid-column:2; grid-row:1; min-width:0; display:flex; align-items:center; }
.lane-line { width:100%; display:flex; align-items:center; gap:6px; min-width:0; overflow:hidden; }
.lane-name { min-width:0; flex:1; font-size:13px; font-weight:800; color:var(--ink); line-height:1.15; overflow:hidden; display:-webkit-box; -webkit-line-clamp:2; -webkit-box-orient:vertical; overflow-wrap:anywhere; }
/* Domain role chip (from the member's real name) — mockup's coloured "FINANZAS" */
.lane-domain { flex-shrink:0; display:inline-flex; align-items:center; gap:3px; font-size:8.5px; font-weight:800; letter-spacing:0.08em; text-transform:uppercase; white-space:nowrap; }
.lane-role-pill { flex-shrink:0; padding:1px 6px; border-radius:999px; border:1px solid var(--line); background:var(--soft); font-size:8px; font-weight:800; letter-spacing:0.035em; text-transform:uppercase; white-space:nowrap; }
.lane-role-pill.role-chief { color:#EF9F27; border-color:rgba(239,159,39,0.24); background:rgba(239,159,39,0.09); }
.lane-role-pill.role-collaborator { color:#1D9E75; border-color:rgba(29,158,117,0.24); background:rgba(29,158,117,0.09); }
.lane-role-pill.role-member { color:#85B7EB; border-color:rgba(133,183,235,0.24); background:rgba(133,183,235,0.09); }
.lane-issue { flex-shrink:0; width:7px; height:7px; border-radius:50%; }
.lane-issue.high { background:#F0997B; box-shadow:0 0 6px rgba(240,153,123,0.6); }
.lane-issue.medium { background:#EF9F27; }
.lane-issue.low { background:#AFA9EC; }

.op-chip { display:inline-flex; align-items:center; gap:3px; flex-shrink:0; padding:2px 6px; border-radius:999px; font-size:8.5px; font-weight:800; letter-spacing:0.03em; text-transform:uppercase; white-space:nowrap; }
.op-chip.idle { color:#a1a1aa; background:rgba(161,161,170,0.08); border:1px solid rgba(161,161,170,0.18); }
.op-chip.listening { color:#5DCAA5; background:rgba(93,202,165,0.08); border:1px solid rgba(93,202,165,0.18); }
.op-chip.alert { color:#EF9F27; background:rgba(239,159,39,0.08); border:1px solid rgba(239,159,39,0.18); }
.op-chip.working { color:#85B7EB; background:rgba(133,183,235,0.08); border:1px solid rgba(133,183,235,0.18); }
.op-chip.warning { color:#F0997B; background:rgba(240,153,123,0.08); border:1px solid rgba(240,153,123,0.18); }
.op-icon { width:11px; height:11px; display:inline-block; }

/* Boxed stat cells (mockup style): label on top, value below. The cell strip
   flexes with the row — every cell shrinks instead of overflowing the panel. */
.lane-cells { grid-column:2; grid-row:2; min-width:0; display:grid; grid-template-columns:minmax(58px, .68fr) minmax(88px, .95fr) minmax(0, 1.8fr); gap:5px; align-items:stretch; }
.lane-cell { min-width:0; display:flex; flex-direction:column; gap:2px; justify-content:center; padding:5px 7px; border:1px solid var(--line); border-radius:9px; background:var(--card-bg-soft); }
.cell-label { font-size:7.5px; font-weight:750; letter-spacing:0.035em; text-transform:uppercase; color:var(--muted); overflow:hidden; text-overflow:ellipsis; white-space:nowrap; }
.cell-value { font-size:13px; font-weight:850; font-variant-numeric:tabular-nums; color:var(--ink); line-height:1.15; overflow:hidden; text-overflow:ellipsis; white-space:nowrap; }
.lane-cell.warn .cell-value { color:#EF9F27; }
.cell-value.clamp { font-size:10.5px; font-weight:650; color:var(--muted); white-space:normal; display:-webkit-box; -webkit-line-clamp:2; -webkit-box-orient:vertical; overflow:hidden; overflow-wrap:anywhere; }
/* Expand chevron: keyboard-focusable handle for the row toggle (the click
   itself bubbles to the lane handler — no double toggle). */
.lane-expand { flex-shrink:0; display:inline-flex; align-items:center; justify-content:center; width:18px; height:18px; padding:0; border:none; border-radius:6px; background:transparent; color:var(--muted); cursor:pointer; transition:transform 0.2s ease, color 0.15s ease; }
.lane-expand:hover { color:var(--ink); }
.lane.is-open .lane-expand { transform:rotate(180deg); }

/* Expanded detail row: real snapshot fields, shown on demand */
.lane-detail { grid-column:2 / -1; grid-row:3; min-width:0; display:flex; flex-wrap:wrap; gap:6px 16px; padding-top:6px; border-top:1px dashed var(--line); }
.detail-item { display:flex; flex-direction:column; gap:1px; min-width:0; }
.detail-label { font-size:7.5px; font-weight:750; letter-spacing:0.035em; text-transform:uppercase; color:var(--muted); white-space:nowrap; }
.detail-value { font-size:11px; font-weight:650; color:var(--ink); max-width:280px; overflow:hidden; text-overflow:ellipsis; white-space:nowrap; }

.lane-kick { grid-column:3; grid-row:1 / 3; align-self:center; display:inline-flex; align-items:center; justify-content:center; width:28px; height:28px; padding:0; border:1px solid var(--line); border-radius:8px; background:transparent; color:var(--muted); cursor:pointer; transition:all 0.15s ease; }
.lane-kick:hover { color:#F0997B; border-color:rgba(240,153,123,0.4); background:rgba(240,153,123,0.08); }

/* Empty state */
.empty-state { display:flex; flex-direction:column; align-items:center; gap:16px; padding:48px 24px; text-align:center; }
.empty-state span { color:var(--muted); font-size:14px; }

/* Animations */
.fade-in { animation:fadeIn 0.4s ease forwards; opacity:0; }
@keyframes fadeIn { to { opacity:1; } }

/* Responsive */
@media (max-width:768px) {
  .cockpit-card { padding:12px; border-radius:14px; }
  .lane { grid-template-columns:48px minmax(0, 1fr) auto; }
  .lane-avatar, .lane-avatar-face { width:48px; height:48px; }
  .lane-role-pill { display:none; }
  .lane-cells { grid-template-columns:minmax(58px, .8fr) minmax(88px, 1.2fr); }
  .lane-cell.task-cell { display:none; }
}
@media (prefers-reduced-motion: reduce) {
  *, *::before, *::after { animation-duration:0.01ms !important; transition-duration:0.01ms !important; }
}
</style>
