<template>
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
</template>

<script setup lang="ts">
import { computed } from 'vue'
import { useI18n } from '@acp/shared'
import { messages } from '../../i18n'
import { timeAgo } from '../../composables/sessionHelpers'
import type { SessionDetailPayload } from '../../api/sessions'

const props = defineProps<{
  payload: SessionDetailPayload | null
}>()

const emit = defineEmits<{
  copy: [payload: { value: string; label: string }]
}>()

const { locale, t } = useI18n(messages)

const metaCards = computed(() => {
  const p = props.payload
  if (!p) return []
  const summary = p.summary || {}
  return [
    { label: t('sd_session_context_meta'), value: p.title || p.project || '-' },
    { label: t('sd_members_meta'), value: String(summary.member_count || (p.members || []).length) },
    { label: t('sd_pending_total_meta'), value: String(summary.pending_total || 0) },
    { label: t('sd_last_event_meta'), value: timeAgo(summary.last_event_at || p.created_at, locale.value) },
  ]
})

function handleMetaCopy(e: Event) {
  const target = (e.target as HTMLElement).closest('[data-copy]')
  if (!target) return
  const value = target.getAttribute('data-copy') || ''
  emit('copy', { value, label: target.querySelector('.meta-k')?.textContent || '' })
}
</script>

<style scoped>
.panel { background: var(--panel); border: 1px solid var(--line); border-radius: 20px; backdrop-filter: blur(16px); -webkit-backdrop-filter: blur(16px); box-shadow: var(--shadow-elev); transition: transform 0.25s cubic-bezier(0.16, 1, 0.3, 1), border-color 0.25s ease, box-shadow 0.25s ease; }
.panel:hover { border-color: var(--hover-line); box-shadow: var(--shadow-glow); }
.panel-head { padding:12px 18px; border-bottom:1px solid var(--line); display:flex; justify-content:space-between; gap:10px; align-items:center; flex-wrap:wrap; }
.panel-title { font-weight:700; font-size:11px; text-transform:uppercase; letter-spacing:0.12em; color:var(--muted); position:relative; padding-left:12px; }
.panel-title::before { content:''; position:absolute; left:0; top:50%; transform:translateY(-50%); width:4px; height:4px; border-radius:50%; background:var(--accent); box-shadow:0 0 6px var(--accent-glow); }
.panel-body { padding:20px; }
.grid { display:grid; gap:10px; grid-template-columns:repeat(2, minmax(0,1fr)); }
.muted { color:var(--muted); }

/* Meta grid */
.meta-card { border:1px solid var(--line); border-radius:12px; padding:14px 16px; background:var(--card-bg); cursor:pointer; transition:all 0.2s ease; }
.meta-card:hover { border-color:var(--accent); transform:translateY(-2px); box-shadow:var(--shadow-glow); }
.meta-k { font-size:10px; font-weight:600; letter-spacing:0.08em; text-transform:uppercase; color:var(--muted); }
.meta-v { margin-top:6px; font-size:16px; font-weight:700; color:var(--ink); word-break:break-all; }

/* Responsive */
@media (max-width:1080px) { .grid { grid-template-columns:1fr; } }
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
