<template>
  <section class="panel access-strip" :class="{ compact: accessCompact }">
    <div class="panel-head">
      <div class="panel-title">{{ t('sd_access_title') }}</div>
      <span class="pill" v-if="hasPayload">{{ t('sd_session_detail_pill') }}</span>
    </div>
    <div class="panel-body">
      <div class="stack">
        <!-- Compact summary -->
        <div class="access-summary">
          <div class="access-summary-copy">
            <div class="access-summary-title">{{ t('sd_access_active_title') }}</div>
            <div class="access-summary-primary">
              <span class="access-summary-primary-value">{{ sessionId || '-' }}</span>
              <UiButton type="button" variant="ghost" class="summary-copy-btn" @click="$emit('copy', { value: sessionId, label: t('sd_session_id_meta') })">{{ t('sd_copy_btn') }}</UiButton>
            </div>
            <div class="access-summary-secondary">
              <span class="access-summary-chip">
                <span class="access-summary-chip-label">{{ t('sd_access_mode_' + accessMode) }}</span>
              </span>
              <span v-if="agentName" class="access-summary-chip">
                {{ t('sd_access_summary_agent') }}: {{ agentName }}
              </span>
              <span v-if="dashboardAuthenticated" class="access-summary-chip">
                {{ t('sd_access_summary_via_dashboard') }}
              </span>
            </div>
          </div>
          <UiButton type="button" variant="ghost" size="sm" @click="$emit('update:accessCompact', false)">{{ t('sd_edit_access_btn') }}</UiButton>
        </div>

        <!-- Full form -->
        <div class="access-form" :data-mode="accessMode">
          <div class="access-mode-row">
            <UiButton v-for="mode in (['member', 'admin', 'hybrid'] as const)" :key="mode"
              type="button" variant="access-mode" active-style="invert" :active="accessMode === mode"
              @click="$emit('update:accessMode', mode)">
              {{ t('sd_access_mode_' + mode) }}
            </UiButton>
          </div>
          <div class="access-guide" :class="`mode-${accessMode}`">
            <div class="access-guide-head">
              <strong>{{ accessGuide.title }}</strong>
              <span v-if="dashboardAuthenticated" class="access-guide-badge">{{ t('sd_access_dashboard_session_active') }}</span>
            </div>
            <p>{{ accessGuide.body }}</p>
          </div>
          <div class="access-grid">
            <div class="access-credentials">
              <label class="access-field">
                <span>{{ t('sd_session_id_label') }}</span>
                <input v-model="sessionIdModel" type="text" />
                <small class="access-field-hint">{{ t('sd_session_id_hint') }}</small>
              </label>
              <label class="access-field member-access-field">
                <span>{{ t('sd_agent_name_label') }}</span>
                <input v-model="agentNameModel" type="text" />
                <small class="access-field-hint">{{ t('sd_agent_name_hint') }}</small>
              </label>
              <label class="access-field member-access-field">
                <span>{{ t('sd_member_token_label') }}</span>
                <input v-model="memberTokenModel" type="password" />
                <small class="access-field-hint">{{ t('sd_member_token_hint') }}</small>
              </label>
              <label class="access-field admin-access-field">
                <span>{{ t('sd_admin_token_label') }}</span>
                <input v-model="adminTokenModel" type="password" />
                <small class="access-field-hint">
                  {{ dashboardAuthenticated ? t('sd_admin_token_hint_authenticated') : t('sd_admin_token_hint') }}
                </small>
              </label>
            </div>
            <div class="access-actions">
              <UiButton :disabled="loading" @click="$emit('load')">{{ t('sd_load_session_btn') }}</UiButton>
            </div>
          </div>
        </div>

        <!-- Status -->
        <div class="status-line" :class="{ danger: statusIsError }">
          <span v-if="polling" class="poll-spinner" :title="t('sd_poll_active_title')">
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><polyline points="23 4 23 10 17 10"/><polyline points="1 20 1 14 7 14"/><path d="M3.51 9a9 9 0 0 1 14.85-3.36L23 10M1 14l4.64 4.36A9 9 0 0 0 20.49 15"/></svg>
          </span>
          {{ statusText }}
        </div>
      </div>
    </div>
  </section>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import { useI18n, UiButton } from '@acp/shared'
import { messages } from '../../i18n'
import type { AccessMode } from '../../composables/useSessionDashboard'

const props = defineProps<{
  sessionId: string
  agentName: string
  memberToken: string
  adminToken: string
  accessMode: AccessMode
  accessCompact: boolean
  dashboardAuthenticated: boolean
  hasPayload: boolean
  loading: boolean
  polling: boolean
  statusText: string
  statusIsError: boolean
}>()

const emit = defineEmits<{
  'update:sessionId': [value: string]
  'update:agentName': [value: string]
  'update:memberToken': [value: string]
  'update:adminToken': [value: string]
  'update:accessMode': [value: AccessMode]
  'update:accessCompact': [value: boolean]
  load: []
  copy: [payload: { value: string; label: string }]
}>()

const { t } = useI18n(messages)

const sessionIdModel = computed({ get: () => props.sessionId, set: (v: string) => emit('update:sessionId', v) })
const agentNameModel = computed({ get: () => props.agentName, set: (v: string) => emit('update:agentName', v) })
const memberTokenModel = computed({ get: () => props.memberToken, set: (v: string) => emit('update:memberToken', v) })
const adminTokenModel = computed({ get: () => props.adminToken, set: (v: string) => emit('update:adminToken', v) })

const accessGuide = computed(() => {
  if (props.accessMode === 'admin') {
    return {
      title: t('sd_access_admin_title'),
      body: props.dashboardAuthenticated
        ? t('sd_access_admin_body_authenticated')
        : t('sd_access_admin_body'),
    }
  }
  if (props.accessMode === 'hybrid') {
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
</script>

<style scoped>
.panel { background: var(--panel); border: 1px solid var(--line); border-radius: 20px; backdrop-filter: blur(16px); -webkit-backdrop-filter: blur(16px); box-shadow: var(--shadow-elev); transition: transform 0.25s cubic-bezier(0.16, 1, 0.3, 1), border-color 0.25s ease, box-shadow 0.25s ease; }
.panel:hover { border-color: var(--hover-line); box-shadow: var(--shadow-glow); }
.panel-head { padding:12px 18px; border-bottom:1px solid var(--line); display:flex; justify-content:space-between; gap:10px; align-items:center; flex-wrap:wrap; }
.panel-title { font-weight:700; font-size:11px; text-transform:uppercase; letter-spacing:0.12em; color:var(--muted); position:relative; padding-left:12px; }
.panel-title::before { content:''; position:absolute; left:0; top:50%; transform:translateY(-50%); width:4px; height:4px; border-radius:50%; background:var(--accent); box-shadow:0 0 6px var(--accent-glow); }
.panel-body { padding:20px; }
.stack { display:grid; gap:12px; }
.pill { display:inline-flex; align-items:center; gap:6px; border-radius:999px; padding:4px 12px; font-size:10px; font-weight:700; letter-spacing:0.05em; background:var(--accent-soft); color:var(--accent); border:1px solid var(--accent-glow); text-decoration:none; }

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
/* Self-chained to reliably override UiButton's base padding/font/radius on the
   component root (equal single-class specificity would otherwise depend on
   style-injection order). Sizing delta from UiButton's variants, kept per-site. */
.summary-copy-btn.summary-copy-btn { padding:6px 10px; font-size:10px; border-radius:999px; line-height:1; }
.access-form { display:block; }
.access-mode-row { display:flex; gap:8px; flex-wrap:wrap; margin-bottom:14px; }
.access-guide { margin-bottom:14px; padding:12px 14px; border-radius:14px; border:1px solid var(--line); background:var(--card-bg-soft); display:grid; gap:6px; }
.access-guide.mode-member { border-color:rgba(133,183,235,0.22); background:rgba(133,183,235,0.08); }
.access-guide.mode-admin { border-color:rgba(239,159,39,0.22); background:rgba(239,159,39,0.08); }
.access-guide.mode-hybrid { border-color:rgba(175,169,236,0.22); background:rgba(175,169,236,0.08); }
.access-guide-head { display:flex; align-items:center; justify-content:space-between; gap:10px; flex-wrap:wrap; color:var(--ink); }
.access-guide-head strong { font-size:12px; letter-spacing:0.02em; }
.access-guide p { margin:0; color:var(--muted-strong, var(--muted)); font-size:12px; line-height:1.6; }
.access-guide-badge { display:inline-flex; align-items:center; padding:4px 10px; border-radius:999px; border:1px solid rgba(133,183,235,0.22); background:rgba(133,183,235,0.14); color:var(--accent); font-size:10px; font-weight:800; letter-spacing:0.05em; text-transform:uppercase; }
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

/* Status */
.status-line { font-size:13px; color:var(--muted); display:flex; align-items:center; gap:8px; }
.status-line.danger { color:var(--danger); }
.poll-spinner { display:inline-flex; align-items:center; justify-content:center; width:18px; height:18px; flex-shrink:0; }
.poll-spinner svg { width:16px; height:16px; color:var(--accent); opacity:0.6; animation:poll-spin 2.8s cubic-bezier(0.22,1,0.36,1) infinite; }
@keyframes poll-spin { 0% { transform:rotate(0deg); opacity:0.28; } 18% { opacity:0.82; } 76% { opacity:0.52; } 100% { transform:rotate(360deg); opacity:0.28; } }

/* Responsive */
@media (max-width:768px) {
  .panel-head { padding:14px 18px; flex-direction:column; align-items:flex-start; gap:10px; }
  .panel-body { padding:16px; }
  .access-credentials { grid-template-columns:1fr !important; }
  .access-mode-row { flex-direction:column; }
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
