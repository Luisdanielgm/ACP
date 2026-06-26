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
        <button type="button" class="ghost compact-action" @click="resetVisuals">{{ t('sd_visual_reset_btn') }}</button>
      </div>
      <div class="sub" :class="{ show: showSub }">{{ t('sd_hero_sub') }}</div>
    </section>

    <!-- Access Strip -->
    <section class="panel access-strip" :class="{ compact: session.accessCompact.value }">
      <div class="panel-head">
        <div class="panel-title">{{ t('sd_access_title') }}</div>
        <span class="pill" v-if="session.payload.value">{{ t('sd_session_detail_pill') }}</span>
      </div>
      <div class="panel-body">
        <div class="stack">
          <!-- Compact summary -->
          <div class="access-summary">
            <div class="access-summary-copy">
              <div class="access-summary-title">{{ t('sd_access_active_title') }}</div>
              <div class="access-summary-primary">
                <span class="access-summary-primary-value">{{ session.sessionIdInput.value || '-' }}</span>
                <button type="button" class="ghost summary-copy-btn" @click="copyValue(session.sessionIdInput.value, t('sd_session_id_meta'))">{{ t('sd_copy_btn') }}</button>
              </div>
              <div class="access-summary-secondary">
                <span class="access-summary-chip">
                  <span class="access-summary-chip-label">{{ t('sd_access_mode_' + session.accessMode.value) }}</span>
                </span>
                <span v-if="session.agentNameInput.value" class="access-summary-chip">
                  {{ t('sd_access_summary_agent') }}: {{ session.agentNameInput.value }}
                </span>
                <span v-if="session.dashboardAuthenticated.value" class="access-summary-chip">
                  {{ t('sd_access_summary_via_dashboard') }}
                </span>
              </div>
            </div>
            <button type="button" class="ghost compact-action" @click="session.accessCompact.value = false">{{ t('sd_edit_access_btn') }}</button>
          </div>

          <!-- Full form -->
          <div class="access-form" :data-mode="session.accessMode.value">
            <div class="access-mode-row">
              <button v-for="mode in (['member', 'admin', 'hybrid'] as const)" :key="mode"
                type="button" class="access-mode-btn" :class="{ active: session.accessMode.value === mode }"
                @click="session.accessMode.value = mode">
                {{ t('sd_access_mode_' + mode) }}
              </button>
            </div>
            <div class="access-guide" :class="`mode-${session.accessMode.value}`">
              <div class="access-guide-head">
                <strong>{{ accessGuide.title }}</strong>
                <span v-if="session.dashboardAuthenticated.value" class="access-guide-badge">{{ t('sd_access_dashboard_session_active') }}</span>
              </div>
              <p>{{ accessGuide.body }}</p>
            </div>
            <div class="access-grid">
              <div class="access-credentials">
                <label class="access-field">
                  <span>{{ t('sd_session_id_label') }}</span>
                  <input v-model="session.sessionIdInput.value" type="text" />
                  <small class="access-field-hint">{{ t('sd_session_id_hint') }}</small>
                </label>
                <label class="access-field member-access-field">
                  <span>{{ t('sd_agent_name_label') }}</span>
                  <input v-model="session.agentNameInput.value" type="text" />
                  <small class="access-field-hint">{{ t('sd_agent_name_hint') }}</small>
                </label>
                <label class="access-field member-access-field">
                  <span>{{ t('sd_member_token_label') }}</span>
                  <input v-model="session.memberTokenInput.value" type="password" />
                  <small class="access-field-hint">{{ t('sd_member_token_hint') }}</small>
                </label>
                <label class="access-field admin-access-field">
                  <span>{{ t('sd_admin_token_label') }}</span>
                  <input v-model="session.adminTokenInput.value" type="password" />
                  <small class="access-field-hint">
                    {{ session.dashboardAuthenticated.value ? t('sd_admin_token_hint_authenticated') : t('sd_admin_token_hint') }}
                  </small>
                </label>
              </div>
              <div class="access-actions">
                <button :disabled="session.loading.value" @click="doLoad">{{ t('sd_load_session_btn') }}</button>
              </div>
            </div>
          </div>

          <!-- Status -->
          <div class="status-line" :class="{ danger: session.statusIsError.value }">
            <span v-if="session.polling.value" class="poll-spinner" :title="t('sd_poll_active_title')">
              <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><polyline points="23 4 23 10 17 10"/><polyline points="1 20 1 14 7 14"/><path d="M3.51 9a9 9 0 0 1 14.85-3.36L23 10M1 14l4.64 4.36A9 9 0 0 0 20.49 15"/></svg>
            </span>
            {{ statusText }}
          </div>
        </div>
      </div>
    </section>

    <!-- Content (only when session loaded) -->
    <template v-if="session.payload.value">
      <!-- Layout: Summary + Health -->
      <div class="layout">
        <!-- Session Summary -->
        <section class="panel">
          <div class="panel-head">
            <div class="panel-title">{{ t('sd_session_summary_title') }}</div>
            <div class="muted">{{ t('sd_session_summary_sub') }}</div>
          </div>
          <div class="panel-body">
            <div class="grid" @click="handleMetaCopy">
              <div class="meta-card" v-for="meta in metaCards" :key="meta.label" :data-copy="meta.value">
                <div class="meta-k">{{ meta.label }}</div>
                <div class="meta-v">{{ meta.value }}</div>
              </div>
            </div>
          </div>
        </section>

        <!-- Session Health -->
        <section class="panel">
          <div class="panel-head">
            <div class="panel-title">{{ t('sd_session_health_' + session.healthState.value) }}</div>
            <span class="summary-health" :class="session.healthState.value">{{ t('sd_session_health_' + session.healthState.value) }}</span>
          </div>
          <div class="panel-body">
            <!-- Admin actions -->
            <div v-if="session.adminActionsAvailable.value" class="admin-actions">
              <div class="muted" style="font-size:11px;margin-bottom:10px">{{ t('sd_admin_actions_hint') }}</div>
              <div class="access-actions">
                <button type="button" class="ghost" @click="copyInvite">{{ t('sd_invite_prompt_btn') }}</button>
                <button type="button" class="ghost danger-ghost" @click="confirmCloseSession">{{ t('sd_close_session_btn') }}</button>
              </div>
            </div>
          </div>
        </section>
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
              <!-- Squad Map -->
              <div class="cockpit-card" :data-load="session.trafficSnapshot.value.level">
                <div class="cockpit-head">
                  <div>
                    <div class="cockpit-title">{{ t('sd_squad_map_title') }}</div>
                    <div class="cockpit-sub">{{ t('sd_squad_map_sub') }}</div>
                  </div>
                </div>
                <div class="squad-map">
                  <div v-if="!session.members.value.length" class="empty-state">
                    <span>{{ t('sd_no_problem_members') }}</span>
                  </div>
                  <div v-else class="squad-canvas" v-html="squadMapSvg"></div>
                </div>
              </div>

              <!-- Member Lanes -->
              <div class="cockpit-card" :data-load="session.trafficSnapshot.value.level">
                <div class="cockpit-head">
                  <div>
                    <div class="cockpit-title">{{ t('sd_member_lanes_title') }}</div>
                    <div class="cockpit-sub">{{ t('sd_member_lanes_sub') }}</div>
                  </div>
                </div>
                <div v-if="!session.visibleMembers.value.length" class="empty-state">
                  <span>{{ session.problemMode.value ? t('sd_no_problem_members') : t('sd_no_filtered_events') }}</span>
                </div>
                <div v-else class="lane-stack">
                  <article v-for="(member, idx) in session.visibleMembers.value" :key="member.agent_name"
                    class="lane-card" :class="laneClasses(member)" :style="memberStyle(member, idx)"
                    :data-role="normalizedRole(member.role)">
                    <div class="lane-top">
                      <div>
                        <div class="lane-kicker">{{ translateRole(member.role) }}</div>
                        <div class="lane-title-row">
                          <div class="lane-title">{{ member.agent_name || '-' }}</div>
                          <span class="lane-rank-pill" :class="'role-' + normalizedRole(member.role)">{{ roleIcon(member.role) }} {{ translateRole(member.role) }}</span>
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
                      <span>{{ translateStatus(member.status) }}</span>
                      <span>{{ t('sd_delivery_mode_label') }}: {{ translateDelivery(member.delivery_mode || 'attached') }}</span>
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
                    <div v-if="session.adminActionsAvailable.value" class="lane-meta">
                      <button type="button" class="ghost member-action" @click="confirmDisconnect(member.agent_name)">{{ t('sd_disconnect_member_btn') }}</button>
                    </div>
                  </article>
                </div>
              </div>
            </div>
          </div>
        </section>

        <!-- Member Roster -->
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
                  <select v-model="session.agentFilter.value">
                    <option value="">{{ t('sd_agent_filter_all') }}</option>
                    <option v-for="m in session.members.value" :key="m.agent_name" :value="m.agent_name">{{ m.agent_name }}</option>
                  </select>
                </label>
                <button type="button" class="filter-chip" :class="{ active: session.problemMode.value }" @click="session.problemMode.value = !session.problemMode.value">
                  {{ session.problemMode.value ? t('sd_problems_filter_on') : t('sd_problems_filter_off') }}
                </button>
              </div>
              <div class="problem-summary muted">
                {{ session.problemSummary.value.memberCount || session.problemSummary.value.eventCount
                  ? t('sd_issue_summary_members_events', { members: String(session.problemSummary.value.memberCount), events: String(session.problemSummary.value.eventCount) })
                  : t('sd_problem_summary_clear') }}
              </div>
            </div>
          </div>
          <div class="panel-body">
            <div v-if="!session.visibleMembers.value.length" class="empty-state">
              <span>{{ session.problemMode.value ? t('sd_no_problem_members') : t('sd_no_filtered_events') }}</span>
            </div>
            <div v-else class="members">
              <div v-for="member in session.visibleMembers.value" :key="member.agent_name"
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
                      <div class="member-tier">{{ translateRole(member.role) }} · {{ member.provider || '-' }}</div>
                    </div>
                  </div>
                  <div class="member-signals">
                    <span class="status-dot" :class="String(member.status || '').toLowerCase()"></span>
                    <div class="pill status-badge" :class="String(member.status || '').toLowerCase()">{{ translateStatus(member.status) }}</div>
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
                  <span class="member-quick-role">{{ translateRole(member.role) }}</span>
                  <span>·</span>
                  <span>{{ translateDelivery(member.delivery_mode || 'attached') }}</span>
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

        <!-- Timeline -->
        <section class="panel">
          <div class="panel-head">
            <div>
              <div class="panel-title">{{ t('sd_timeline_title') }}</div>
              <div class="muted">{{ t('sd_timeline_sub') }}</div>
            </div>
            <div class="filter-tools">
              <div class="filter-row">
                <button v-for="f in timelineFilters" :key="f" type="button" class="filter-chip" :class="{ active: session.timelineFilter.value === f }" @click="session.timelineFilter.value = f">
                  {{ t('sd_timeline_filter_' + f) }}
                </button>
                <button type="button" class="filter-chip" :class="{ active: session.timelineDensity.value === 'compact' }" @click="session.timelineDensity.value = session.timelineDensity.value === 'compact' ? 'detailed' : 'compact'">
                  {{ session.timelineDensity.value === 'compact' ? t('sd_timeline_density_compact') : t('sd_timeline_density_detailed') }}
                </button>
              </div>
            </div>
          </div>
          <div class="panel-body">
            <div :class="['timeline', session.timelineDensity.value === 'compact' ? 'compact' : '']">
              <div v-if="!session.filteredHistory.value.length" class="empty-state">
                <span>{{ session.timelineFilter.value === 'all' ? t('sd_no_session_events') : t('sd_no_filtered_events') }}</span>
              </div>
              <div v-for="(event, i) in session.filteredHistory.value" :key="i"
                class="event-card" :class="eventCardClasses(event)">
                <div class="event-top">
                  <div style="display:flex;gap:8px;align-items:center">
                    <div class="event-name">{{ translateEvent(event.event) }}</div>
                    <span v-if="messageActionType(event)" class="pill flow-pill" :class="actionChipClass(messageActionType(event))">
                      {{ t('sd_action_' + messageActionType(event)) }}
                    </span>
                    <span class="actor-badge" :class="'role-' + (roleByAgent.get(event.actor || '') || 'member')">{{ event.actor || '-' }}</span>
                    <span class="muted" style="font-size:11px">→ {{ event.target || '-' }}</span>
                  </div>
                  <div class="pill">{{ timeAgo(event.ts, locale) }}</div>
                </div>
                <div v-if="eventThreadText(event) || eventIssueSummary(event) || deliveryMode(event)" class="event-thread">
                  <span class="event-marker" :class="eventMarkerClasses(event)"></span>
                  <span v-if="eventThreadText(event)" class="event-thread-copy">{{ eventThreadText(event) }}</span>
                  <span v-if="deliveryMode(event)" class="pill flow-pill delivery" :class="deliveryClass(deliveryMode(event))">
                    {{ translateDelivery(deliveryMode(event)) }}
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

        <!-- Raw JSON -->
        <section class="panel raw-panel" :class="{ collapsed: !session.showRawJson.value }">
          <div class="panel-head">
            <div>
              <div class="panel-title">{{ t('sd_raw_json_title') }}</div>
              <div class="muted">{{ t('sd_raw_json_sub') }}</div>
            </div>
            <button type="button" class="ghost raw-toggle" @click="session.showRawJson.value = !session.showRawJson.value">
              {{ session.showRawJson.value ? t('sd_raw_toggle_hide') : t('sd_raw_toggle_show') }}
            </button>
          </div>
          <div v-if="session.showRawJson.value" class="panel-body">
            <pre class="raw-json" v-if="session.payload.value">{{ JSON.stringify(session.payload.value, null, 2) }}</pre>
            <div v-else class="empty-state"><span>{{ t('sd_raw_waiting') }}</span></div>
          </div>
        </section>
      </div>
    </template>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, watchEffect } from 'vue'
import { useI18n, useTheme, useMotion, ThemeToggle, LangToggle, MotionToggle } from '@acp/shared'
import { messages } from '../i18n'
import { useSessionDashboard } from '../composables/useSessionDashboard'
import {
  normalizedRole, roleGlyph, roleIcon, roleTone, statusTone,
  heartbeatState, heartbeatAgeSeconds, memberPalette, memberStyleVars,
  memberIssues, eventIssues, maxIssueLevel, primaryIssueLabel, eventClass,
  messageActionType, actionChipClass, deliveryMode, floatTagLabel, actionTone, deliveryClass,
  recentMemberActivity, memberActivity, memberOperationalState,
  mapRoutePath, mapAnimationEvents, sortedMembers,
  escapeHtml, timeAgo, compactPath, runSummary, buildInvitePrompt,
  type Issue, type MemberActivityData,
} from '../composables/sessionHelpers'
import type { SessionMember, SessionEvent, SessionDetailPayload } from '../api/sessions'

const props = defineProps<{
  authEndpoint?: string
  redirectPath?: string
}>()

const { locale, t } = useI18n(messages)
useTheme()
const { motion, setMotion, resolveEffectiveMode, applyMotion } = useMotion()

const session = useSessionDashboard({
  authEndpoint: props.authEndpoint,
  redirectPath: props.redirectPath,
})

const showSub = ref(false)
const timelineFilters = ['all', 'session', 'message', 'wait', 'status'] as const

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

const accessGuide = computed(() => {
  if (session.accessMode.value === 'admin') {
    return {
      title: t('sd_access_admin_title'),
      body: session.dashboardAuthenticated.value
        ? t('sd_access_admin_body_authenticated')
        : t('sd_access_admin_body'),
    }
  }
  if (session.accessMode.value === 'hybrid') {
    return {
      title: t('sd_access_hybrid_title'),
      body: t('sd_access_hybrid_body'),
    }
  }
  return {
    title: t('sd_access_member_title'),
    body: t('sd_access_member_body'),
  }
})

const metaCards = computed(() => {
  const p = session.payload.value
  if (!p) return []
  const summary = p.summary || {}
  return [
    { label: t('sd_session_context_meta'), value: p.title || p.project || '-' },
    { label: t('sd_members_meta'), value: String(summary.member_count || (p.members || []).length) },
    { label: t('sd_pending_total_meta'), value: String(summary.pending_total || 0) },
    { label: t('sd_last_event_meta'), value: timeAgo(summary.last_event_at || p.created_at, locale.value) },
  ]
})

const roleByAgent = computed(() => {
  const map = new Map<string, string>()
  for (const m of session.members.value) {
    map.set(m.agent_name, normalizedRole(m.role))
  }
  return map
})

// ── Squad Map SVG ──

const squadMapSvg = computed(() => {
  const p = session.payload.value
  if (!p || !p.members?.length) return ''

  const members = sortedMembers(p)
  const cs = session.connectedSet.value
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
        <text class="node-subtext" x="${node.x}" y="${node.y + 66}" text-anchor="middle">${escapeHtml(m.current_task || translateStatus(m.status) || '-')}</text>
      </g>`
  })

  return `<svg viewBox="0 0 ${width} ${height}" role="img" aria-label="${escapeHtml(t('sd_squad_map_title'))}">${markup}</svg>`
})

// ── Member helpers ──

function getHeartbeatState(member: SessionMember): string {
  return heartbeatState(member, session.connectedSet.value)
}

function heartbeatAgeSuffix(member: SessionMember): string {
  const age = heartbeatAgeSeconds(member)
  return age === null ? '-' : `${age}s`
}

function getMemberIssues(member: SessionMember): Issue[] {
  return memberIssues(member, session.connectedSet.value)
}

function getOpState(member: SessionMember) {
  const activity = memberActivity(member, session.activityMap.value)
  const issues = getMemberIssues(member)
  return memberOperationalState(member, activity, issues)
}

function getEventIssues(event: SessionEvent): Issue[] {
  const membersByName = new Map(session.members.value.map(m => [m.agent_name, m]))
  return eventIssues(event, membersByName)
}

interface ActivityChip {
  key: string
  label: string
  className: string
  kind: 'working' | 'status'
}

interface PulseChip {
  key: string
  label: string
  className: string
}

interface LaneMetric {
  key: string
  label: string
  value: string
  percent: number
  className: string
}

function activityChips(member: SessionMember): ActivityChip[] {
  const activity = memberActivity(member, session.activityMap.value)
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
  const activity = memberActivity(member, session.activityMap.value)
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
      value: activity.isBusy ? t('sd_activity_working') : translateStatus(member.status),
      percent: flowPercent,
      className: activity.isBusy ? 'active' : activity.hasOutgoing || activity.hasIncoming ? 'signal' : 'idle',
    },
  ]
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
      label: `${t('sd_action_' + action.toLowerCase())} ${count}`,
      className: actionChipClass(action),
    })
  })

  ;(['immediate', 'queued', 'dequeued'] as const).forEach(delivery => {
    const count = deliveryCounts.get(delivery) || 0
    if (!count) return
    chips.push({
      key: `delivery-${delivery}`,
      label: `${translateDelivery(delivery)} ${count}`,
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

function memberStyle(member: SessionMember, index?: number): string {
  let style = memberStyleVars(member)
  if (session.isFirstRender.value && index !== undefined) {
    style += `animation-delay:${index * 50}ms;`
  }
  return style
}

function laneClasses(member: SessionMember): string[] {
  const activity = memberActivity(member, session.activityMap.value)
  const classes: string[] = [`role-${normalizedRole(member.role)}`]
  if (session.isFirstRender.value) classes.push('fade-in')
  if (activity.hasOutgoing) classes.push('activity-send')
  if (activity.hasIncoming) classes.push('activity-receive')
  if (activity.isBusy) classes.push('is-busy')
  return classes
}

function rosterMemberClasses(member: SessionMember): string[] {
  const activity = memberActivity(member, session.activityMap.value)
  const classes = [`role-${normalizedRole(member.role)}`]
  if (session.isFirstRender.value) classes.push('fade-in')
  if (activity.hasOutgoing) classes.push('activity-send')
  if (activity.hasIncoming) classes.push('activity-receive')
  if (activity.isBusy) classes.push('is-busy')
  return classes
}

function eventCardClasses(event: SessionEvent): string[] {
  const classes = [eventClass(event.event)]
  const role = roleByAgent.value.get(event.actor || '') || 'member'
  classes.push(`actor-${role}`)
  const membersByName = new Map(session.members.value.map(m => [m.agent_name, m]))
  const issues = eventIssues(event, membersByName)
  const level = maxIssueLevel(issues)
  if (level) classes.push(`severity-${level}`)
  return classes
}

function eventThreadText(event: SessionEvent): string {
  const actor = event.actor || ''
  const target = event.target || ''
  if (actor && target) return `${actor} → ${target}`
  if (actor) return actor
  if (target) return target
  return ''
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

// ── Translation helpers ──

function translateStatus(value: string | undefined): string {
  const s = String(value || '').toLowerCase()
  if (s === 'idle') return t('sd_idle_status')
  if (s === 'waiting') return t('sd_waiting_status')
  if (s === 'busy') return t('sd_busy_status')
  return value || '-'
}

function translateRole(value: string | undefined): string {
  const r = normalizedRole(value)
  if (r === 'chief') return t('sd_role_chief')
  if (r === 'collaborator') return t('sd_role_collaborator')
  return t('sd_role_member')
}

function translateDelivery(value: string | undefined): string {
  const d = String(value || '').toLowerCase()
  if (d === 'attached') return t('sd_delivery_attached')
  if (d === 'runner') return t('sd_delivery_runner')
  if (d === 'immediate') return t('sd_delivery_immediate')
  if (d === 'queued') return t('sd_delivery_queued')
  if (d === 'dequeued') return t('sd_delivery_dequeued')
  return value || '-'
}

function translateEvent(value: string | undefined): string {
  const key = `sd_event_${value || ''}`
  const result = t(key)
  return result !== key ? result : (value || '-')
}

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

function handleMetaCopy(e: Event) {
  const target = (e.target as HTMLElement).closest('[data-copy]')
  if (!target) return
  const value = target.getAttribute('data-copy') || ''
  copyValue(value, target.querySelector('.meta-k')?.textContent || '')
}

async function copyValue(value: string, label: string) {
  try {
    await navigator.clipboard.writeText(value)
    session.setStatus(t('sd_copied_value', { label }))
  } catch {
    session.setStatus(t('sd_copy_failed', { label }), true)
  }
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
<style scoped>
.page { max-width: 1400px; margin: 0 auto; padding: 24px; position: relative; z-index: 1; }
.hero, .panel {
  background: var(--panel);
  border: 1px solid var(--line);
  border-radius: 20px;
  backdrop-filter: blur(16px);
  -webkit-backdrop-filter: blur(16px);
  box-shadow: var(--shadow-elev);
  transition: transform 0.25s cubic-bezier(0.16, 1, 0.3, 1), border-color 0.25s ease, box-shadow 0.25s ease;
}
.hero:hover, .panel:hover { border-color: var(--hover-line); box-shadow: var(--shadow-glow); }
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
.panel-head { padding:12px 18px; border-bottom:1px solid var(--line); display:flex; justify-content:space-between; gap:10px; align-items:center; flex-wrap:wrap; }
.panel-title { font-weight:700; font-size:11px; text-transform:uppercase; letter-spacing:0.12em; color:var(--muted); position:relative; padding-left:12px; }
.panel-title::before { content:''; position:absolute; left:0; top:50%; transform:translateY(-50%); width:4px; height:4px; border-radius:50%; background:var(--accent); box-shadow:0 0 6px var(--accent-glow); }
.panel-body { padding:20px; }
.stack { display:grid; gap:12px; }
.grid { display:grid; gap:10px; grid-template-columns:repeat(2, minmax(0,1fr)); }
.muted { color:var(--muted); }

/* Access strip */
.access-strip { margin-bottom:20px; }
.access-summary { display:none; align-items:center; justify-content:space-between; gap:16px; }
.access-strip.compact .access-summary { display:flex; }
.access-strip.compact .access-form { display:none; }
.access-summary-copy { min-width:0; display:grid; gap:6px; }
.access-summary-title { font-size:10px; font-weight:700; letter-spacing:0.12em; text-transform:uppercase; color:var(--muted); }
.access-summary-primary { display:flex; align-items:center; gap:10px; flex-wrap:wrap; font-size:16px; font-weight:800; letter-spacing:-0.02em; color:var(--ink); word-break:break-word; }
.access-summary-primary-value { min-width:0; word-break:break-word; }
.access-summary-secondary { display:flex; gap:8px; flex-wrap:wrap; align-items:center; color:var(--muted); font-size:12px; }
.access-summary-chip { display:inline-flex; align-items:center; gap:6px; padding:5px 10px; border-radius:999px; border:1px solid var(--line); background:var(--soft); }
.access-summary-chip-label { font-size:10px; font-weight:700; letter-spacing:0.08em; text-transform:uppercase; color:var(--muted); }
.summary-copy-btn { padding:6px 10px; font-size:10px; border-radius:999px; line-height:1; }
.access-form { display:block; }
.access-mode-row { display:flex; gap:8px; flex-wrap:wrap; margin-bottom:14px; }
.access-mode-btn { background:var(--soft); color:var(--muted); border:1px solid var(--line); border-radius:999px; padding:6px 10px; font-size:11px; font-weight:800; letter-spacing:0.05em; text-transform:uppercase; box-shadow:none; cursor:pointer; }
.access-mode-btn:hover { background:var(--trace-hover); color:var(--ink); border-color:var(--hover-line); box-shadow:none; transform:none; }
.access-mode-btn.active { background:var(--ink); color:var(--bg); border-color:var(--ink); }
.access-guide { margin-bottom:14px; padding:12px 14px; border-radius:14px; border:1px solid var(--line); background:var(--card-bg-soft); display:grid; gap:6px; }
.access-guide.mode-member { border-color:rgba(34,211,238,0.22); background:rgba(34,211,238,0.08); }
.access-guide.mode-admin { border-color:rgba(251,191,36,0.22); background:rgba(251,191,36,0.08); }
.access-guide.mode-hybrid { border-color:rgba(167,139,250,0.22); background:rgba(167,139,250,0.08); }
.access-guide-head { display:flex; align-items:center; justify-content:space-between; gap:10px; flex-wrap:wrap; color:var(--ink); }
.access-guide-head strong { font-size:12px; letter-spacing:0.02em; }
.access-guide p { margin:0; color:var(--muted-strong, var(--muted)); font-size:12px; line-height:1.6; }
.access-guide-badge { display:inline-flex; align-items:center; padding:4px 10px; border-radius:999px; border:1px solid rgba(34,211,238,0.22); background:rgba(34,211,238,0.14); color:var(--accent); font-size:10px; font-weight:800; letter-spacing:0.05em; text-transform:uppercase; }
.access-grid { display:grid; gap:10px; }
.access-credentials { display:grid; gap:12px; grid-template-columns:repeat(2, minmax(0,1fr)); min-width:0; }
.access-form[data-mode="member"] .admin-access-field { display:none; }
.access-form[data-mode="admin"] .member-access-field { display:none; }
.access-form[data-mode="admin"] .access-credentials { grid-template-columns:1fr; }
.access-form[data-mode="hybrid"] .access-credentials { grid-template-columns:repeat(3, minmax(0,1fr)); }
.access-actions { display:flex; gap:10px; flex-wrap:wrap; align-items:center; }

/* Buttons & inputs */
label { display:grid; gap:6px; font-size:12px; font-weight:500; color:var(--muted); }
label.access-field { align-content:start; }
label.access-field span { color:var(--ink); font-weight:700; }
label.access-field .access-field-hint { color:var(--muted); font-size:11px; line-height:1.45; font-weight:500; }
input, select { width:100%; border:1px solid var(--line); border-radius:10px; padding:8px 12px; font:inherit; font-size:13px; background:var(--input-bg,transparent); color:var(--ink); transition:all 0.2s ease; outline:none; }
input:focus, select:focus { border-color:var(--accent); box-shadow:0 0 0 3px var(--accent-glow); }
button { border:0; border-radius:10px; padding:9px 16px; font:inherit; font-size:13px; font-weight:600; background:var(--accent); color:var(--button-ink); cursor:pointer; transition:all 0.25s cubic-bezier(0.16,1,0.3,1); }
button:hover { background:var(--accent-hover); transform:translateY(-2px); box-shadow:0 6px 20px rgba(34,211,238,0.35); }
.ghost { background:var(--soft); color:var(--ink); border:1px solid var(--line); box-shadow:none; }
.ghost:hover { background:var(--trace-hover); border-color:var(--accent); box-shadow:var(--shadow-glow); transform:translateY(-1px); }
.danger-ghost { color:#f87171; border-color:rgba(248,113,113,0.3); }
.danger-ghost:hover { background:rgba(248,113,113,0.08); border-color:#f87171; }
.compact-action { padding:8px 14px; font-size:11px; border-radius:10px; }
.pill { display:inline-flex; align-items:center; gap:6px; border-radius:999px; padding:4px 12px; font-size:10px; font-weight:700; letter-spacing:0.05em; background:var(--accent-soft); color:var(--accent); border:1px solid var(--accent-glow); text-decoration:none; }

/* Status */
.status-line { font-size:13px; color:var(--muted); display:flex; align-items:center; gap:8px; }
.status-line.danger { color:var(--danger); }
.poll-spinner { display:inline-flex; align-items:center; justify-content:center; width:18px; height:18px; flex-shrink:0; }
.poll-spinner svg { width:16px; height:16px; color:var(--accent); opacity:0.6; animation:poll-spin 2.8s cubic-bezier(0.22,1,0.36,1) infinite; }

/* Meta grid */
.meta-card { border:1px solid var(--line); border-radius:12px; padding:14px 16px; background:var(--card-bg); cursor:pointer; transition:all 0.2s ease; }
.meta-card:hover { border-color:var(--accent); transform:translateY(-2px); box-shadow:var(--shadow-glow); }
.meta-k { font-size:10px; font-weight:600; letter-spacing:0.08em; text-transform:uppercase; color:var(--muted); }
.meta-v { margin-top:6px; font-size:16px; font-weight:700; color:var(--ink); word-break:break-all; }

/* Health */
.summary-health { display:inline-flex; align-items:center; gap:6px; border-radius:999px; padding:6px 14px; font-size:11px; font-weight:800; letter-spacing:0.06em; text-transform:uppercase; }
.summary-health.healthy { color:#34d399; background:rgba(52,211,153,0.08); border:1px solid rgba(52,211,153,0.22); }
.summary-health.warning { color:#fbbf24; background:rgba(251,191,36,0.08); border:1px solid rgba(251,191,36,0.22); }
.summary-health.critical { color:#f87171; background:rgba(248,113,113,0.08); border:1px solid rgba(248,113,113,0.22); }

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
.squad-canvas { width:100%; min-height:300px; border:1px solid var(--canvas-border); border-radius:18px; background:radial-gradient(circle at top,var(--accent-glow),transparent 38%),linear-gradient(180deg,var(--canvas-top),var(--canvas-bottom)); overflow:hidden; position:relative; }
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

/* Lane stack */
.lane-stack { display:grid; gap:12px; }
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
.lane-card::after, .member::after { content:''; position:absolute; inset:0; pointer-events:none; border-radius:inherit; background:linear-gradient(135deg, var(--member-soft, transparent) 0%, transparent 42%); opacity:0.9; }
.lane-card.activity-send, .member.activity-send { box-shadow: inset 3px 0 0 var(--member-accent, transparent), 0 0 0 1px rgba(34,211,238,0.08), 0 0 22px var(--member-glow, transparent); }
.lane-card.activity-receive, .member.activity-receive { box-shadow: inset 3px 0 0 var(--member-accent, transparent), 0 0 0 1px rgba(34,211,238,0.08), 0 0 26px rgba(34,211,238,0.14); }
.lane-card.is-busy, .member.is-busy { border-color: color-mix(in srgb, var(--member-accent, var(--accent)) 40%, var(--line)); }
.lane-task { margin-top:12px; border-radius:12px; border:1px solid rgba(34,211,238,0.16); background:rgba(34,211,238,0.08); padding:14px; font-size:12px; line-height:1.6; }
.lane-task strong { color:var(--accent); }
.member-action { padding:6px 12px; font-size:11px; border-radius:8px; }
.lane-activity-row, .member-activity-row { display:flex; gap:8px; flex-wrap:wrap; align-items:center; margin-top:10px; }
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

/* Members roster */
.members { display:grid; gap:8px; }
.member { border:1px solid var(--line); border-radius:12px; padding:14px 16px; background:var(--card-bg-soft); position:relative; overflow:hidden; transition:all 0.2s ease; }
.member[data-role="chief"] { background:linear-gradient(180deg, color-mix(in srgb, var(--member-soft, transparent) 48%, var(--card-bg-soft)), var(--card-bg-soft)); }
.member[data-role="collaborator"] { background:linear-gradient(180deg, color-mix(in srgb, var(--member-soft, transparent) 34%, var(--card-bg-soft)), var(--card-bg-soft)); }
.member:hover { border-color:var(--hover-line); }
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

/* Filters */
.filter-row { display:flex; gap:8px; flex-wrap:wrap; align-items:center; }
.filter-chip { background:var(--soft); color:var(--muted); border:1px solid var(--line); border-radius:999px; padding:6px 14px; font-size:11px; font-weight:700; cursor:pointer; transition:all 0.2s ease; }
.filter-chip:hover { color:var(--ink); border-color:var(--accent); }
.filter-chip.active { background:var(--accent); color:var(--button-ink); border-color:var(--accent); }
.filter-tools { display:flex; flex-direction:column; gap:8px; align-items:flex-end; }
.filter-tools-group { display:flex; gap:8px; align-items:center; }
.inline-filter { display:inline-flex; align-items:center; gap:8px; color:var(--muted); font-size:11px; font-weight:700; letter-spacing:0.04em; text-transform:uppercase; }
.inline-filter select { min-width:140px; padding:6px 10px; border-radius:999px; font-size:12px; text-transform:none; }
.problem-summary { font-size:11px; }

/* Timeline */
.timeline { display:grid; gap:10px; max-height:65vh; overflow:auto; padding-right:8px; }
.timeline::-webkit-scrollbar, .lane-stack::-webkit-scrollbar { width:6px; }
.timeline::-webkit-scrollbar-track, .lane-stack::-webkit-scrollbar-track { background:var(--scroll-track); border-radius:10px; }
.timeline::-webkit-scrollbar-thumb, .lane-stack::-webkit-scrollbar-thumb { background:var(--scroll-thumb); border-radius:10px; }
.timeline::-webkit-scrollbar-thumb:hover, .lane-stack::-webkit-scrollbar-thumb:hover { background:var(--scroll-thumb-hover); }
.timeline.compact .event-detail, .timeline.compact .task { display:none; }
.event-card { border:1px solid var(--line); border-radius:14px; padding:14px; background:var(--card-bg); position:relative; overflow:hidden; transition:all 0.25s cubic-bezier(0.16,1,0.3,1); }
.event-card::before { content:''; position:absolute; left:0; top:0; bottom:0; width:3px; background:rgba(148,163,184,0.35); }
.event-card.message::before { background:#22d3ee; }
.event-card.wait::before { background:#fbbf24; }
.event-card.status::before { background:#818cf8; }
.event-card.session::before { background:#34d399; }
.event-card.severity-low { box-shadow:0 0 0 1px rgba(192,132,252,0.08) inset; }
.event-card.severity-medium { border-color:rgba(251,191,36,0.22); box-shadow:0 0 0 1px rgba(251,191,36,0.08) inset; }
.event-card.severity-high { border-color:rgba(248,113,113,0.24); box-shadow:0 0 0 1px rgba(248,113,113,0.1) inset, 0 12px 28px rgba(248,113,113,0.08); }
.event-card:hover { border-color:var(--accent); transform:translateY(-3px); box-shadow:var(--shadow-glow); }
.event-top { display:flex; justify-content:space-between; gap:8px; align-items:center; }
.event-name { font-weight:600; font-size:12px; letter-spacing:0.04em; color:var(--accent); }
.event-thread { display:flex; flex-wrap:wrap; align-items:center; gap:8px; margin-top:10px; color:var(--muted); font-size:11px; }
.event-thread-copy { font-weight:600; color:var(--event-ink, var(--ink)); }
.event-marker { width:10px; height:10px; border-radius:50%; flex-shrink:0; background:rgba(148,163,184,0.5); box-shadow:0 0 0 4px rgba(148,163,184,0.08); }
.event-marker.message { background:#22d3ee; box-shadow:0 0 0 4px rgba(34,211,238,0.12); }
.event-marker.wait { background:#fbbf24; box-shadow:0 0 0 4px rgba(251,191,36,0.12); }
.event-marker.status { background:#818cf8; box-shadow:0 0 0 4px rgba(129,140,248,0.12); }
.event-marker.session { background:#34d399; box-shadow:0 0 0 4px rgba(52,211,153,0.12); }
.event-marker.severity-high { box-shadow:0 0 0 4px rgba(248,113,113,0.14), 0 0 14px rgba(248,113,113,0.22); }
.event-marker.severity-medium { box-shadow:0 0 0 4px rgba(251,191,36,0.14), 0 0 12px rgba(251,191,36,0.18); }
.event-marker.severity-low { box-shadow:0 0 0 4px rgba(192,132,252,0.14), 0 0 12px rgba(192,132,252,0.18); }
.event-detail { margin-top:8px; font-size:12px; color:var(--muted); }
.task { margin-top:8px; padding:10px 14px; border-radius:10px; border:1px solid var(--line); background:var(--card-bg-soft); font-size:12px; line-height:1.5; font-family:'JetBrains Mono',monospace; white-space:pre-wrap; }
.actor-badge { display:inline-flex; align-items:center; gap:4px; padding:3px 10px; border-radius:999px; font-size:10px; font-weight:700; border:1px solid var(--line); background:var(--soft); }
.actor-badge.role-chief { color:#facc15; border-color:rgba(250,204,21,0.25); background:rgba(250,204,21,0.08); }
.actor-badge.role-collaborator { color:#818cf8; border-color:rgba(129,140,248,0.25); background:rgba(129,140,248,0.08); }
.actor-badge.role-member { color:#22d3ee; border-color:rgba(34,211,238,0.25); background:rgba(34,211,238,0.08); }
.flow-pill { font-size:10px; }
.flow-pill.task { background:rgba(251,191,36,0.12); color:#fbbf24; border-color:rgba(251,191,36,0.25); }
.flow-pill.info { background:rgba(34,211,238,0.12); color:#22d3ee; border-color:rgba(34,211,238,0.25); }
.flow-pill.reply { background:rgba(167,139,250,0.12); color:#a78bfa; border-color:rgba(167,139,250,0.25); }
.flow-pill.delivery.immediate { background:rgba(34,211,238,0.08); color:#67e8f9; border-color:rgba(103,232,249,0.2); }
.flow-pill.delivery.queued { background:rgba(251,191,36,0.08); color:#fbbf24; border-color:rgba(251,191,36,0.18); }
.flow-pill.delivery.dequeued { background:rgba(148,163,184,0.14); color:#f8fafc; border-color:rgba(248,250,252,0.18); }
.issue-echo.low { color:#c084fc; border-color:rgba(192,132,252,0.18); background:rgba(192,132,252,0.08); }
.issue-echo.medium { color:#fbbf24; border-color:rgba(251,191,36,0.18); background:rgba(251,191,36,0.08); }
.issue-echo.high { color:#f87171; border-color:rgba(248,113,113,0.18); background:rgba(248,113,113,0.08); }

/* Admin */
.admin-actions { margin-top:8px; }

/* Raw JSON */
.raw-panel.collapsed .panel-body { display:none; }
.raw-toggle { font-size:11px; padding:6px 14px; border-radius:999px; }
.raw-json { padding:16px; border-radius:12px; border:1px solid var(--line); background:var(--card-bg-soft); font-family:'JetBrains Mono',monospace; font-size:11px; line-height:1.5; overflow-x:auto; white-space:pre-wrap; max-height:600px; overflow-y:auto; }

/* Empty state */
.empty-state { display:flex; flex-direction:column; align-items:center; gap:16px; padding:60px 24px; text-align:center; }
.empty-state span { color:var(--muted); font-size:14px; }

/* Animations */
@keyframes poll-spin { 0% { transform:rotate(0deg); opacity:0.28; } 18% { opacity:0.82; } 76% { opacity:0.52; } 100% { transform:rotate(360deg); opacity:0.28; } }
@keyframes route-pulse { 0% { stroke-dashoffset:0; opacity:0.18; } 18% { opacity:0.95; } 100% { stroke-dashoffset:-36; opacity:0.24; } }
@keyframes work-bars { 0%, 100% { transform:scaleY(0.72); opacity:0.52; } 45% { transform:scaleY(1.08); opacity:1; } }
@keyframes dashboard-scan { 0% { transform:translate3d(0, -18%, 0); opacity:0.08; } 30% { opacity:0.24; } 100% { transform:translate3d(0, 210%, 0); opacity:0; } }
@keyframes node-aura-pulse { 0% { transform:scale(0.92); opacity:0.14; } 55% { transform:scale(1.12); opacity:0.34; } 100% { transform:scale(1.22); opacity:0; } }
@keyframes node-aura-ripple { 0% { transform:scale(0.88); opacity:0.2; } 50% { transform:scale(1.08); opacity:0.3; } 100% { transform:scale(1.26); opacity:0; } }
@keyframes node-impact-task { 0% { r:18; opacity:0.45; } 100% { r:44; opacity:0; } }
@keyframes node-impact-info { 0% { r:16; opacity:0.38; } 100% { r:42; opacity:0; } }
@keyframes node-impact-reply { 0% { r:14; opacity:0.42; } 100% { r:40; opacity:0; } }
@keyframes node-impact-spark { 0% { r:10; opacity:0.18; } 100% { r:34; opacity:0; } }
@keyframes node-float-tag { 0% { opacity:0; transform:translateY(10px); } 16% { opacity:1; } 100% { opacity:0; transform:translateY(-8px); } }
.fade-in { animation:fadeIn 0.4s ease forwards; opacity:0; }
@keyframes fadeIn { to { opacity:1; } }

html[data-motion="reduced"] .work-signal span,
html[data-motion="reduced"] .legend-work span,
html[data-motion="reduced"] .squad-canvas::after,
html[data-motion="reduced"] .squad-canvas :deep(.route-pulse),
html[data-motion="reduced"] .squad-canvas :deep(.node-aura),
html[data-motion="reduced"] .squad-canvas :deep(.node-impact),
html[data-motion="reduced"] .squad-canvas :deep(.node-float-tag) {
  animation-duration: 1.8s !important;
}

html[data-motion="off"] .work-signal span,
html[data-motion="off"] .legend-work span,
html[data-motion="off"] .squad-canvas::after,
html[data-motion="off"] .squad-canvas :deep(.route-pulse),
html[data-motion="off"] .squad-canvas :deep(.node-aura),
html[data-motion="off"] .squad-canvas :deep(.node-impact),
html[data-motion="off"] .squad-canvas :deep(.node-float-tag) {
  animation: none !important;
}

/* Responsive */
@media (max-width:1400px) { .page { max-width:1200px; } }
@media (max-width:1200px) { .cockpit-grid { grid-template-columns:1fr; } }
@media (max-width:1080px) { .layout { grid-template-columns:1fr; } .grid { grid-template-columns:1fr; } .lane-meter-grid, .member-trace-grid { grid-template-columns:1fr; } }
@media (max-width:900px) { .page { padding:20px; } .hero { padding:20px; } .hero-top { flex-direction:column; align-items:flex-start; gap:16px; } .hero-controls { width:100%; } }
@media (max-width:768px) {
  .page { padding:16px; } .hero { padding:18px; border-radius:16px; }
  .panel-head { padding:14px 18px; flex-direction:column; align-items:flex-start; gap:10px; }
  .panel-body { padding:16px; } .title { font-size:20px; }
  .member-quick-top { flex-direction:column; align-items:flex-start; gap:8px; }
  .member-signals { flex-wrap:wrap; }
  .lane-title-row { align-items:flex-start; }
  .access-credentials { grid-template-columns:1fr !important; }
  .access-mode-row { flex-direction:column; }
  .traffic-status { justify-content:flex-start; }
  .cockpit-card { padding:16px; border-radius:14px; }
  .filter-tools { align-items:flex-start; }
  .filter-tools-group { flex-direction:column; align-items:flex-start; }
}
@media (max-width:600px) {
  .page { padding:12px; } .hero { padding:16px; border-radius:14px; } .title { font-size:18px; }
  .panel { border-radius:14px; } .panel-head { padding:12px 14px; } .panel-body { padding:14px; }
  .squad-map { min-height:240px; } .squad-canvas { min-height:240px; }
}
@media (max-width:480px) {
  .page { padding:10px; } .hero { padding:14px; border-radius:12px; } .title { font-size:16px; }
  .panel { border-radius:12px; }
  .cockpit-card { padding:12px; border-radius:12px; }
  .lane-card { padding:10px; border-radius:10px; }
  .member { padding:10px 12px; }
}
@media (prefers-reduced-motion: reduce) {
  *, *::before, *::after { animation-duration:0.01ms !important; transition-duration:0.01ms !important; }
}
</style>
