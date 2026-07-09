<template>
  <section class="panel raw-panel" :class="{ collapsed: !showRawJson }">
    <div class="panel-head">
      <div>
        <div class="panel-title">{{ t('sd_raw_json_title') }}</div>
        <div class="muted">{{ t('sd_raw_json_sub') }}</div>
      </div>
      <UiButton type="button" variant="ghost" class="raw-toggle" @click="$emit('update:showRawJson', !showRawJson)">
        {{ showRawJson ? t('sd_raw_toggle_hide') : t('sd_raw_toggle_show') }}
      </UiButton>
    </div>
    <div v-if="showRawJson" class="panel-body">
      <pre class="raw-json" v-if="payload">{{ JSON.stringify(payload, null, 2) }}</pre>
      <div v-else class="empty-state"><span>{{ t('sd_raw_waiting') }}</span></div>
    </div>
  </section>
</template>

<script setup lang="ts">
import { useI18n, UiButton } from '@acp/shared'
import { messages } from '../../i18n'
import type { SessionDetailPayload } from '../../api/sessions'

defineProps<{
  payload: SessionDetailPayload | null
  showRawJson: boolean
}>()

defineEmits<{
  'update:showRawJson': [value: boolean]
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

/* Raw JSON */
.raw-panel.collapsed .panel-body { display:none; }
/* Self-chained: see .summary-copy-btn note in AccessStrip.vue. */
.raw-toggle.raw-toggle { font-size:11px; padding:6px 14px; border-radius:999px; }
.raw-json { padding:16px; border-radius:12px; border:1px solid var(--line); background:var(--card-bg-soft); font-family:'JetBrains Mono',monospace; font-size:11px; line-height:1.5; overflow-x:auto; white-space:pre-wrap; max-height:600px; overflow-y:auto; }

/* Empty state */
.empty-state { display:flex; flex-direction:column; align-items:center; gap:16px; padding:60px 24px; text-align:center; }
.empty-state span { color:var(--muted); font-size:14px; }

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
