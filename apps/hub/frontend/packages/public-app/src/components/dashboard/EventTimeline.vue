<template>
  <section class="panel" :class="{ 'compact-panel': compact }">
    <div class="panel-head">
      <div>
        <div class="panel-title">{{ t('sd_timeline_title') }}</div>
        <div v-if="!compact" class="muted">{{ t('sd_timeline_sub') }}</div>
      </div>
      <div class="filter-tools">
        <div class="filter-row">
          <UiButton v-for="f in timelineFilters" :key="f" type="button" variant="filter-chip" :active="timelineFilter === f" @click="$emit('update:timelineFilter', f)">
            {{ t('sd_timeline_filter_' + f) }}
          </UiButton>
          <UiButton v-if="!compact" type="button" variant="filter-chip" :active="timelineDensity === 'compact'" @click="timelineDensity = timelineDensity === 'compact' ? 'detailed' : 'compact'">
            {{ timelineDensity === 'compact' ? t('sd_timeline_density_compact') : t('sd_timeline_density_detailed') }}
          </UiButton>
        </div>
      </div>
    </div>
    <div class="panel-body">
      <div ref="timelineEl" :class="['timeline', (compact || timelineDensity === 'compact') ? 'compact' : '']" @scroll="handleTimelineScroll">
        <div v-if="!events.length" class="empty-state">
          <span>{{ timelineFilter === 'all' ? t('sd_no_session_events') : t('sd_no_filtered_events') }}</span>
        </div>
        <div v-for="(event, i) in visibleEvents" :key="`${event.ts || ''}:${event.event || ''}:${i}`"
          class="event-card" :class="eventCardClasses(event)">
          <div class="event-top">
            <div class="event-primary">
              <img class="event-type-icon" :src="stateIconUrl(messageIconNameForEvent(event))" alt="" aria-hidden="true" />
              <div class="event-name">{{ translateEvent(t, event.event) }}</div>
              <span v-if="messageActionType(event)" class="pill flow-pill" :class="actionChipClass(messageActionType(event))">
                {{ t('sd_action_' + messageActionType(event)) }}
              </span>
              <span class="actor-badge" :class="'role-' + (roleByAgent.get(event.actor || '') || 'member')">{{ event.actor || '-' }}</span>
              <span class="muted" style="font-size:11px">→ {{ event.target || '-' }}</span>
            </div>
            <div class="pill result-pill">
              <img v-if="resultIconUrl(event)" class="event-result-icon" :src="resultIconUrl(event)" alt="" aria-hidden="true" />
              {{ timeAgo(event.ts, locale) }}
            </div>
          </div>
          <div v-if="eventIssueSummary(event) || deliveryMode(event)" class="event-thread">
            <span class="event-marker" :class="eventMarkerClasses(event)"></span>
            <span v-if="deliveryMode(event)" class="pill flow-pill delivery" :class="deliveryClass(deliveryMode(event))">
              {{ translateDelivery(t, deliveryMode(event)) }}
            </span>
            <span v-if="eventIssueSummary(event)" class="pill issue-echo" :class="eventIssueSummary(event)?.level">
              {{ eventIssueSummary(event)?.label }}
            </span>
          </div>
          <div v-if="getEventIssues(event).length" class="issue-row">
            <span v-for="issue in getEventIssues(event)" :key="issue.key" class="issue-pill" :class="issue.level">{{ t('sd_' + issue.label) }}</span>
          </div>
          <div v-if="event.detail" class="event-detail">{{ event.detail }}</div>
          <div v-if="event.payload_preview" class="task">{{ event.payload_preview }}</div>
          <div v-if="event.extra?.summary" class="task">{{ event.extra.summary }}</div>
          <div v-if="event.extra?.log_preview" class="task">{{ event.extra.log_preview }}</div>
        </div>
      </div>
    </div>
  </section>
</template>

<script setup lang="ts">
import { ref, computed, watch, nextTick } from 'vue'
import { useI18n, UiButton } from '@acp/shared'
import type { MotionMode } from '@acp/shared'
import { messages } from '../../i18n'
import {
  eventIssues, eventClass, maxIssueLevel, primaryIssueLabel,
  messageActionType, actionChipClass, deliveryMode, deliveryClass,
  normalizedRole, timeAgo, messageIconNameForEvent, resultIconNameForEvent, type Issue,
} from '../../composables/sessionHelpers'
import { stateIconUrl } from '../../assets/acp/acpAssets'
import { translateEvent, translateDelivery } from '../../composables/dashboardTranslations'
import type { SessionEvent, SessionMember } from '../../api/sessions'
import type { TimelineFilter } from '../../composables/useSessionDashboard'

const props = withDefaults(defineProps<{
  events: SessionEvent[]
  members: SessionMember[]
  timelineFilter: TimelineFilter
  effectiveMotion: MotionMode
  compact?: boolean
  compactRows?: number
}>(), {
  compact: false,
  compactRows: 3,
})

defineEmits<{
  'update:timelineFilter': [value: TimelineFilter]
}>()

const { locale, t } = useI18n(messages)

const timelineFilters = ['all', 'session', 'message', 'wait', 'status'] as const
const timelineDensity = ref<'detailed' | 'compact'>(props.compact ? 'compact' : 'detailed')
const visibleEvents = computed(() =>
  props.compact ? props.events.slice(-Math.max(1, props.compactRows)) : props.events
)

const roleByAgent = computed(() => {
  const map = new Map<string, string>()
  for (const m of props.members) {
    map.set(m.agent_name, normalizedRole(m.role))
  }
  return map
})

// Result icon (delivered/pending/completed/rejected) — only for events that
// actually carry an outcome; session lifecycle rows have none.
function resultIconUrl(event: SessionEvent): string {
  const ev = String(event.event || '').toUpperCase()
  const hasOutcome =
    eventClass(event.event) === 'message'
    || ['RUN_FINISHED', 'RUN_REPLY_SENT', 'WAIT_TIMEOUT'].includes(ev)
  return hasOutcome ? stateIconUrl(resultIconNameForEvent(event)) : ''
}

function getEventIssues(event: SessionEvent): Issue[] {
  const membersByName = new Map(props.members.map(m => [m.agent_name, m]))
  return eventIssues(event, membersByName)
}

function eventCardClasses(event: SessionEvent): string[] {
  const classes = [eventClass(event.event)]
  const role = roleByAgent.value.get(event.actor || '') || 'member'
  classes.push(`actor-${role}`)
  const membersByName = new Map(props.members.map(m => [m.agent_name, m]))
  const issues = eventIssues(event, membersByName)
  const level = maxIssueLevel(issues)
  if (level) classes.push(`severity-${level}`)
  return classes
}

function eventIssueSummary(event: SessionEvent): { label: string; level: string } | null {
  const issues = getEventIssues(event)
  const key = primaryIssueLabel(issues)
  if (!key) return null
  return {
    label: t('sd_' + key),
    level: maxIssueLevel(issues),
  }
}

function eventMarkerClasses(event: SessionEvent): string[] {
  const classes = [eventClass(event.event)]
  const action = messageActionType(event)
  if (action) classes.push(actionChipClass(action))
  const delivery = deliveryMode(event)
  if (delivery) classes.push(deliveryClass(delivery))
  const issue = eventIssueSummary(event)
  if (issue?.level) classes.push(`severity-${issue.level}`)
  return classes
}

// ── Timeline auto-scroll ──

const timelineEl = ref<HTMLElement | null>(null)
const timelineStickToBottom = ref(true)
const SCROLL_BOTTOM_THRESHOLD = 40

function handleTimelineScroll() {
  const el = timelineEl.value
  if (!el) return
  timelineStickToBottom.value = el.scrollHeight - el.scrollTop - el.clientHeight <= SCROLL_BOTTOM_THRESHOLD
}

watch(() => props.events.length, () => {
  if (!timelineStickToBottom.value) return
  nextTick(() => {
    const el = timelineEl.value
    if (!el) return
    const behavior = props.effectiveMotion === 'reduced' || props.effectiveMotion === 'off' ? 'auto' : 'smooth'
    el.scrollTo({ top: el.scrollHeight, behavior })
  })
})
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

/* Filters */
.filter-row { display:flex; gap:8px; flex-wrap:wrap; align-items:center; }
.filter-tools { display:flex; flex-direction:column; gap:8px; align-items:flex-end; }

/* Timeline */
.timeline { display:grid; gap:10px; max-height:65vh; overflow:auto; padding-right:8px; }
.timeline::-webkit-scrollbar { width:6px; }
.timeline::-webkit-scrollbar-track { background:var(--scroll-track); border-radius:10px; }
.timeline::-webkit-scrollbar-thumb { background:var(--scroll-thumb); border-radius:10px; }
.timeline::-webkit-scrollbar-thumb:hover { background:var(--scroll-thumb-hover); }
.timeline.compact .event-detail, .timeline.compact .task { display:none; }
.event-card { border:1px solid var(--line); border-radius:14px; padding:14px; background:var(--card-bg); position:relative; overflow:hidden; transition:all 0.25s cubic-bezier(0.16,1,0.3,1); }
.event-card::before { content:''; position:absolute; left:0; top:0; bottom:0; width:3px; background:rgba(148,163,184,0.35); }
.event-card.message::before { background:#85B7EB; }
.event-card.wait::before { background:#EF9F27; }
.event-card.status::before { background:#1D9E75; }
.event-card.session::before { background:#5DCAA5; }
.event-card.severity-low { box-shadow:0 0 0 1px rgba(175,169,236,0.08) inset; }
.event-card.severity-medium { border-color:rgba(239,159,39,0.22); box-shadow:0 0 0 1px rgba(239,159,39,0.08) inset; }
.event-card.severity-high { border-color:rgba(240,153,123,0.24); box-shadow:0 0 0 1px rgba(240,153,123,0.1) inset, 0 12px 28px rgba(240,153,123,0.08); }
.event-card:hover { border-color:var(--accent); transform:translateY(-3px); box-shadow:var(--shadow-glow); }
.event-top { display:flex; justify-content:space-between; gap:8px; align-items:center; }
.event-primary { display:flex; gap:8px; align-items:center; min-width:0; }
.event-name { font-weight:600; font-size:12px; letter-spacing:0.04em; color:var(--accent); }
.event-type-icon { width:17px; height:17px; flex-shrink:0; display:block; }
.result-pill { display:inline-flex; align-items:center; gap:5px; }
.event-result-icon { width:14px; height:14px; display:block; }
.event-thread { display:flex; flex-wrap:wrap; align-items:center; gap:8px; margin-top:10px; color:var(--muted); font-size:11px; }
.event-thread-copy { font-weight:600; color:var(--event-ink, var(--ink)); }
.event-marker { width:10px; height:10px; border-radius:50%; flex-shrink:0; background:rgba(148,163,184,0.5); box-shadow:0 0 0 4px rgba(148,163,184,0.08); }
.event-marker.message { background:#85B7EB; box-shadow:0 0 0 4px rgba(133,183,235,0.12); }
.event-marker.wait { background:#EF9F27; box-shadow:0 0 0 4px rgba(239,159,39,0.12); }
.event-marker.status { background:#1D9E75; box-shadow:0 0 0 4px rgba(129,140,248,0.12); }
.event-marker.session { background:#5DCAA5; box-shadow:0 0 0 4px rgba(93,202,165,0.12); }
.event-marker.severity-high { box-shadow:0 0 0 4px rgba(240,153,123,0.14), 0 0 14px rgba(240,153,123,0.22); }
.event-marker.severity-medium { box-shadow:0 0 0 4px rgba(239,159,39,0.14), 0 0 12px rgba(239,159,39,0.18); }
.event-marker.severity-low { box-shadow:0 0 0 4px rgba(175,169,236,0.14), 0 0 12px rgba(175,169,236,0.18); }
.event-detail { margin-top:8px; font-size:12px; color:var(--muted); }
.task { margin-top:8px; padding:10px 14px; border-radius:10px; border:1px solid var(--line); background:var(--card-bg-soft); font-size:12px; line-height:1.5; font-family:'JetBrains Mono',monospace; white-space:pre-wrap; }
.actor-badge { display:inline-flex; align-items:center; gap:4px; padding:3px 10px; border-radius:999px; font-size:10px; font-weight:700; border:1px solid var(--line); background:var(--soft); }
.actor-badge.role-chief { color:#EF9F27; border-color:rgba(250,204,21,0.25); background:rgba(250,204,21,0.08); }
.actor-badge.role-collaborator { color:#1D9E75; border-color:rgba(129,140,248,0.25); background:rgba(129,140,248,0.08); }
.actor-badge.role-member { color:#85B7EB; border-color:rgba(133,183,235,0.25); background:rgba(133,183,235,0.08); }
.flow-pill { font-size:10px; }
.flow-pill.task { background:rgba(239,159,39,0.12); color:#EF9F27; border-color:rgba(239,159,39,0.25); }
.flow-pill.info { background:rgba(133,183,235,0.12); color:#85B7EB; border-color:rgba(133,183,235,0.25); }
.flow-pill.reply { background:rgba(175,169,236,0.12); color:#AFA9EC; border-color:rgba(175,169,236,0.25); }
.flow-pill.delivery.immediate { background:rgba(133,183,235,0.08); color:#B5D4F4; border-color:rgba(181,212,244,0.2); }
.flow-pill.delivery.queued { background:rgba(239,159,39,0.08); color:#EF9F27; border-color:rgba(239,159,39,0.18); }
.flow-pill.delivery.dequeued { background:rgba(148,163,184,0.14); color:#f8fafc; border-color:rgba(248,250,252,0.18); }
.issue-echo.low { color:#AFA9EC; border-color:rgba(175,169,236,0.18); background:rgba(175,169,236,0.08); }
.issue-echo.medium { color:#EF9F27; border-color:rgba(239,159,39,0.18); background:rgba(239,159,39,0.08); }
.issue-echo.high { color:#F0997B; border-color:rgba(240,153,123,0.18); background:rgba(240,153,123,0.08); }

/* Embedded room presentation: a fixed-height, table-like activity strip.
   It intentionally renders only the newest rows instead of creating a second
   dashboard scroller. The full timeline keeps its existing detailed mode. */
.compact-panel { height:100%; min-height:0; display:flex; flex-direction:column; border-radius:14px; overflow:hidden; }
.compact-panel:hover { transform:none; }
.compact-panel .panel-head { flex-shrink:0; flex-wrap:nowrap; gap:8px; padding:6px 10px; }
.compact-panel .panel-title { font-size:9px; white-space:nowrap; }
.compact-panel .filter-tools { min-width:0; overflow:hidden; }
.compact-panel .filter-row { gap:4px; flex-wrap:nowrap; }
.compact-panel .filter-row :deep(button) { min-height:24px; padding:3px 8px; font-size:9px; white-space:nowrap; }
.compact-panel .panel-body { flex:1; min-height:0; padding:5px 8px; overflow:hidden; }
.compact-panel .timeline { height:100%; max-height:none; display:flex; flex-direction:column; justify-content:flex-end; gap:3px; overflow:hidden; padding:0; }
.compact-panel .event-card { min-height:0; padding:4px 7px 4px 9px; border-radius:7px; }
.compact-panel .event-card:hover { transform:none; }
.compact-panel .event-primary { gap:5px; flex:1; overflow:hidden; }
.compact-panel .event-type-icon { width:14px; height:14px; }
.compact-panel .event-name { flex-shrink:0; max-width:130px; overflow:hidden; text-overflow:ellipsis; white-space:nowrap; font-size:10px; }
.compact-panel .actor-badge { min-width:0; max-width:170px; padding:1px 6px; overflow:hidden; text-overflow:ellipsis; white-space:nowrap; font-size:9px; }
.compact-panel .event-primary > .muted { min-width:0; overflow:hidden; text-overflow:ellipsis; white-space:nowrap; }
.compact-panel .pill { padding:2px 7px; font-size:8.5px; white-space:nowrap; }
.compact-panel .event-thread,
.compact-panel .issue-row,
.compact-panel .event-detail,
.compact-panel .task { display:none; }

/* Issues */
.issue-row { display:flex; gap:6px; flex-wrap:wrap; margin-top:8px; }
.issue-pill { display:inline-flex; align-items:center; gap:4px; border-radius:999px; padding:4px 10px; font-size:10px; font-weight:700; letter-spacing:0.04em; border:1px solid transparent; }
.issue-pill.high { color:#F0997B; border-color:rgba(240,153,123,0.22); background:rgba(240,153,123,0.08); }
.issue-pill.medium { color:#EF9F27; border-color:rgba(239,159,39,0.22); background:rgba(239,159,39,0.08); }
.issue-pill.low { color:#AFA9EC; border-color:rgba(175,169,236,0.22); background:rgba(175,169,236,0.08); }

/* Empty state */
.empty-state { display:flex; flex-direction:column; align-items:center; gap:16px; padding:60px 24px; text-align:center; }
.empty-state span { color:var(--muted); font-size:14px; }

/* Responsive */
@media (max-width:768px) {
  .panel-head { padding:14px 18px; flex-direction:column; align-items:flex-start; gap:10px; }
  .panel-body { padding:16px; }
  .filter-tools { align-items:flex-start; }
}
@media (max-width:600px) {
  .panel { border-radius:14px; } .panel-head { padding:12px 14px; } .panel-body { padding:14px; }
}
@media (max-width:480px) {
  .panel { border-radius:12px; }
}
@media (prefers-reduced-motion: reduce) {
  *, *::before, *::after { animation-duration:0.01ms !important; transition-duration:0.01ms !important; }
}
</style>
