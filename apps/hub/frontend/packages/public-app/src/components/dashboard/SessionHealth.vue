<template>
  <section class="panel">
    <div class="panel-head">
      <div class="panel-title">{{ t('sd_session_health_' + healthState) }}</div>
      <span class="summary-health" :class="healthState">{{ t('sd_session_health_' + healthState) }}</span>
    </div>
    <div class="panel-body">
      <!-- Admin actions -->
      <div v-if="adminActionsAvailable" class="admin-actions">
        <div class="muted" style="font-size:11px;margin-bottom:10px">{{ t('sd_admin_actions_hint') }}</div>
        <div class="access-actions">
          <UiButton type="button" variant="ghost" @click="$emit('copy-invite')">{{ t('sd_invite_prompt_btn') }}</UiButton>
          <UiButton type="button" variant="danger-ghost" @click="$emit('close-session')">{{ t('sd_close_session_btn') }}</UiButton>
        </div>
      </div>
    </div>
  </section>
</template>

<script setup lang="ts">
import { useI18n, UiButton } from '@acp/shared'
import { messages } from '../../i18n'
import type { SessionHealth } from '../../composables/sessionHelpers'

defineProps<{
  healthState: SessionHealth
  adminActionsAvailable: boolean
}>()

defineEmits<{
  'copy-invite': []
  'close-session': []
}>()

const { t } = useI18n(messages)
</script>

<style scoped>
.panel { background: var(--panel); border: 1px solid var(--line); border-radius: 20px; backdrop-filter: blur(16px); -webkit-backdrop-filter: blur(16px); box-shadow: var(--shadow-elev); transition: transform 0.25s cubic-bezier(0.16, 1, 0.3, 1), border-color 0.25s ease, box-shadow 0.25s ease; }
.panel:hover { border-color: var(--hover-line); box-shadow: var(--shadow-glow); }
.panel-head { padding:12px 18px; border-bottom:1px solid var(--line); display:flex; justify-content:space-between; gap:10px; align-items:center; flex-wrap:wrap; }
.panel-title { font-weight:700; font-size:11px; text-transform:uppercase; letter-spacing:0.12em; color:var(--muted); position:relative; padding-left:12px; }
.panel-title::before { content:''; position:absolute; left:0; top:50%; transform:translateY(-50%); width:4px; height:4px; border-radius:50%; background:var(--accent); box-shadow:0 0 6px var(--accent-glow); }
.panel-body { padding:20px; }
.muted { color:var(--muted); }

/* Health */
.summary-health { display:inline-flex; align-items:center; gap:6px; border-radius:999px; padding:6px 14px; font-size:11px; font-weight:800; letter-spacing:0.06em; text-transform:uppercase; }
.summary-health.healthy { color:#34d399; background:rgba(52,211,153,0.08); border:1px solid rgba(52,211,153,0.22); }
.summary-health.warning { color:#fbbf24; background:rgba(251,191,36,0.08); border:1px solid rgba(251,191,36,0.22); }
.summary-health.critical { color:#f87171; background:rgba(248,113,113,0.08); border:1px solid rgba(248,113,113,0.22); }

.access-actions { display:flex; gap:10px; flex-wrap:wrap; align-items:center; }
.admin-actions { margin-top:8px; }

/* Responsive */
@media (max-width:768px) {
  .panel-head { padding:14px 18px; flex-direction:column; align-items:flex-start; gap:10px; }
  .panel-body { padding:16px; }
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
