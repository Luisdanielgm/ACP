<template>
  <div class="wrap">
    <header class="nav">
      <div class="brand"><span class="mark"></span><span>ACP Hub</span></div>
      <div class="controls">
        <LangToggle :messages="messages" />
        <ThemeToggle :messages="messages" />
      </div>
      <div class="links">
        <router-link class="link" to="/">{{ t('dl_nav_landing') }}</router-link>
        <router-link class="link" to="/dashboard">{{ t('dl_nav_dashboard') }}</router-link>
        <a class="link" href="/downloads/ACP_AGENT.json">{{ t('dl_nav_manifest') }}</a>
      </div>
    </header>

    <main class="hero">
      <section>
        <div class="eyebrow">{{ t('dl_eyebrow') }}</div>
        <h1>{{ t('dl_hero_title') }}</h1>
        <p>{{ t('dl_hero_body') }}</p>
        <div class="hero-actions">
          <a class="button button-primary" href="/downloads/ACP_AGENT.zip">{{ t('dl_download_btn') }}</a>
          <a class="button button-secondary" href="/downloads/ACP_AGENT.json">{{ t('dl_manifest_btn') }}</a>
          <a class="button button-secondary" href="/downloads/ACP_AGENT/AGENT.md">{{ t('dl_guide_btn') }}</a>
        </div>
        <div class="warning">{{ t('dl_warning') }}</div>
      </section>
      <aside class="card">
        <span class="badge">{{ t('dl_release_badge') }} · {{ release?.version ?? '-' }}</span>
        <div class="meta-grid section">
          <div>
            <div class="meta-k">{{ t('dl_meta_version') }}</div>
            <div class="meta-v">{{ release?.version ?? '-' }}</div>
          </div>
          <div>
            <div class="meta-k">{{ t('dl_meta_date') }}</div>
            <div class="meta-v">{{ release?.released_at ?? t('dl_no_date') }}</div>
          </div>
          <div>
            <div class="meta-k">{{ t('dl_meta_size') }}</div>
            <div class="meta-v">{{ release?.size_mb ? `${release.size_mb} MB` : '-' }}</div>
          </div>
          <div>
            <div class="meta-k">{{ t('dl_meta_sha') }}</div>
            <div class="meta-v">{{ shaShort }}</div>
          </div>
        </div>
      </aside>
    </main>

    <section class="cards">
      <article class="card download-card">
        <div class="card-icon">
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-linecap="round" stroke-linejoin="round"><path d="M22 11.08V12a10 10 0 11-5.93-9.14"/><path d="M22 4L12 14.01l-3-3"/></svg>
        </div>
        <h3>{{ t('dl_check_title') }}</h3>
        <p>{{ t('dl_check_body') }}</p>
        <div class="code">{{ release?.check_command ?? '-' }}</div>
      </article>
      <article class="card download-card">
        <div class="card-icon">
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-linecap="round" stroke-linejoin="round"><path d="M21 15v4a2 2 0 01-2 2H5a2 2 0 01-2-2v-4M7 10l5 5 5-5M12 15V3"/></svg>
        </div>
        <h3>{{ t('dl_update_title') }}</h3>
        <p>{{ t('dl_update_body') }}</p>
        <div class="code">{{ release?.update_command ?? '-' }}</div>
      </article>
      <article class="card download-card">
        <div class="card-icon">
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-linecap="round" stroke-linejoin="round"><path d="M19 21H5a2 2 0 01-2-2V5a2 2 0 012-2h11l5 5v11a2 2 0 01-2 2z"/><path d="M17 21v-8H7v8M7 3v5h8"/></svg>
        </div>
        <h3>{{ t('dl_preserve_title') }}</h3>
        <p>{{ t('dl_preserve_body') }}</p>
        <ul class="list">
          <li>{{ t('dl_preserve_agents') }}</li>
          <li>{{ t('dl_preserve_inbox') }}</li>
          <li>{{ t('dl_preserve_outbox') }}</li>
          <li>{{ t('dl_preserve_sent') }}</li>
        </ul>
      </article>
    </section>

    <section class="cards docs-grid">
      <article class="card download-card">
        <div class="card-icon">
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-linecap="round" stroke-linejoin="round"><path d="M4 19.5A2.5 2.5 0 016.5 17H20"/><path d="M6.5 2H20v20H6.5A2.5 2.5 0 014 19.5v-15A2.5 2.5 0 016.5 2z"/></svg>
        </div>
        <h3>{{ t('dl_agent_guide_title') }}</h3>
        <p>{{ t('dl_agent_guide_body') }}</p>
        <div class="code">{{ release?.agent_guide_url ?? '/downloads/ACP_AGENT/AGENT.md' }}</div>
      </article>
      <article class="card download-card">
        <div class="card-icon">
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-linecap="round" stroke-linejoin="round"><path d="M8 6h13"/><path d="M8 12h13"/><path d="M8 18h13"/><path d="M3 6h.01"/><path d="M3 12h.01"/><path d="M3 18h.01"/></svg>
        </div>
        <h3>{{ t('dl_skill_title') }}</h3>
        <p>{{ t('dl_skill_body') }}</p>
        <div class="code">{{ release?.skill_url ?? '/downloads/ACP_AGENT/skills/acp-session-coordinator/SKILL.md' }}</div>
      </article>
      <article class="card download-card">
        <div class="card-icon">
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-linecap="round" stroke-linejoin="round"><path d="M3 3h18v18H3z"/><path d="M7 7h10v10H7z"/></svg>
        </div>
        <h3>{{ t('dl_runtime_title') }}</h3>
        <p>{{ t('dl_runtime_body') }}</p>
        <div class="code">{{ release?.runtime_url ?? '/runtime' }}</div>
        <div class="code">{{ release?.health_url ?? '/health' }}</div>
      </article>
    </section>

    <section class="card section">
      <h2>{{ t('dl_bootstrap_title') }}</h2>
      <p>{{ t('dl_bootstrap_body') }}</p>
      <ol class="list ordered">
        <li>{{ t('dl_bootstrap_step_manifest') }}</li>
        <li>{{ t('dl_bootstrap_step_guide') }}</li>
        <li>{{ t('dl_bootstrap_step_skill') }}</li>
        <li>{{ t('dl_bootstrap_step_validate') }}</li>
      </ol>
      <div class="meta-grid section">
        <div>
          <div class="meta-k">{{ t('dl_meta_hub_http') }}</div>
          <div class="meta-v">{{ release?.official_hub_http ?? '-' }}</div>
        </div>
        <div>
          <div class="meta-k">{{ t('dl_meta_hub_ws') }}</div>
          <div class="meta-v">{{ release?.official_hub_ws ?? '-' }}</div>
        </div>
        <div>
          <div class="meta-k">{{ t('dl_meta_manifest_url') }}</div>
          <div class="meta-v">{{ release?.manifest_url ?? '/downloads/ACP_AGENT.json' }}</div>
        </div>
        <div>
          <div class="meta-k">{{ t('dl_meta_downloads_url') }}</div>
          <div class="meta-v">{{ release?.downloads_page_url ?? '/downloads' }}</div>
        </div>
      </div>
      <div class="warning">{{ t('dl_bootstrap_note') }}</div>
    </section>

    <section class="card section">
      <h2>{{ t('dl_changelog_title') }}</h2>
      <p>{{ t('dl_changelog_body') }}</p>
      <div class="section">
        <article v-for="entry in changelog" :key="entry.version" class="entry">
          <h4>{{ entry.version || '-' }}</h4>
          <p>{{ entry.date || t('dl_no_date') }}</p>
          <ul class="list">
            <li v-for="(note, i) in entry.notes ?? []" :key="i">{{ noteText(note) }}</li>
          </ul>
        </article>
      </div>
    </section>

    <footer class="footer">
      <div>
        <h3>ACP Hub</h3>
        <p>{{ t('dl_footer_body') }}</p>
      </div>
      <div class="links">
        <a class="link" href="/runtime">{{ t('dl_footer_runtime') }}</a>
        <a class="link" href="/health">{{ t('dl_footer_health') }}</a>
      </div>
    </footer>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted, watchEffect } from 'vue'
import { useI18n, useTheme, ThemeToggle, LangToggle } from '@acp/shared'
import { messages } from '../i18n'
import { apiFetch } from '../api/client'

interface ChangelogEntry {
  version: string
  date?: string
  notes?: (string | Record<string, string>)[]
}

interface ReleaseData {
  version: string
  released_at?: string
  size_mb?: number
  sha256?: string
  check_command?: string
  update_command?: string
  manifest_url?: string
  downloads_page_url?: string
  runtime_url?: string
  health_url?: string
  agent_guide_url?: string
  skill_url?: string
  official_hub_http?: string
  official_hub_ws?: string
  changelog?: ChangelogEntry[]
}

const { locale, t } = useI18n(messages)
useTheme()

const release = ref<ReleaseData | null>(null)

onMounted(async () => {
  try {
    release.value = await apiFetch<ReleaseData>('/api/release')
  } catch {
    // release info unavailable
  }
})

const shaShort = computed(() => {
  const sha = release.value?.sha256 ?? ''
  if (!sha) return '-'
  return sha.length > 16 ? sha.slice(0, 16) + '...' : sha
})

const changelog = computed(() => {
  return Array.isArray(release.value?.changelog) ? release.value!.changelog : []
})

function noteText(note: string | Record<string, string>): string {
  if (note && typeof note === 'object') {
    return note[locale.value] || note.en || note.es || ''
  }
  return String(note || '')
}

watchEffect(() => {
  document.title = t('dl_page_title')
})
</script>

<style scoped>
.wrap {
  width: min(1160px, calc(100% - 28px));
  margin: 0 auto;
  padding: 16px 0 32px;
}

.nav, .hero, .card, .footer {
  background: var(--panel);
  border: 1px solid var(--line);
  border-radius: 20px;
  box-shadow: var(--shadow);
  backdrop-filter: blur(16px);
}

.nav {
  padding: 14px 18px;
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  flex-wrap: wrap;
}

.brand {
  display: flex;
  align-items: center;
  gap: 10px;
  font-family: "Outfit", sans-serif;
  font-weight: 800;
  letter-spacing: 0.04em;
  text-transform: uppercase;
}

.mark {
  width: 14px;
  height: 14px;
  border-radius: 999px;
  background: radial-gradient(circle at 30% 30%, #dff9ff 0%, var(--accent) 45%, var(--accent-deep) 100%);
  box-shadow: 0 0 18px rgba(34, 211, 238, 0.35);
}

.controls, .links, .hero-actions {
  display: flex;
  align-items: center;
  gap: 10px;
  flex-wrap: wrap;
}

a { color: inherit; text-decoration: none; }

.link {
  color: var(--muted);
  font-size: 0.9rem;
  font-weight: 500;
  transition: color 0.2s ease;
}

.link:hover { color: var(--text); }

h1, h2, h3, h4 {
  margin: 0;
  letter-spacing: -0.03em;
  font-family: "Outfit", sans-serif;
}

h1 {
  margin-top: 14px;
  font-size: clamp(2.2rem, 5vw, 4.2rem);
  line-height: 0.96;
}

p { color: var(--muted); line-height: 1.7; }

.eyebrow {
  display: inline-flex;
  align-items: center;
  gap: 8px;
  padding: 7px 12px;
  border-radius: 999px;
  border: 1px solid rgba(34, 211, 238, 0.24);
  background: rgba(34, 211, 238, 0.1);
  color: var(--accent);
  font-size: 0.78rem;
  letter-spacing: 0.08em;
  text-transform: uppercase;
}

.button {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  border-radius: 999px;
  padding: 9px 16px;
  font-family: "Outfit", sans-serif;
  font-size: 0.9rem;
  font-weight: 700;
  transition: transform 0.2s cubic-bezier(0.16, 1, 0.3, 1), border-color 0.2s ease, background 0.2s ease, box-shadow 0.2s ease;
}

.button:hover { transform: translateY(-2px); }
.button-primary { background: var(--accent); color: var(--button-ink); }
.button-primary:hover { background: var(--accent-deep); box-shadow: var(--shadow-glow); }
.button-secondary { border: 1px solid var(--line); background: var(--panel); }

.hero {
  margin-top: 18px;
  padding: 22px;
  display: grid;
  grid-template-columns: minmax(0, 1.1fr) minmax(290px, 0.9fr);
  gap: 22px;
}

.badge {
  display: inline-flex;
  align-items: center;
  gap: 8px;
  padding: 7px 10px;
  border-radius: 999px;
  border: 1px solid rgba(34, 211, 238, 0.22);
  background: rgba(34, 211, 238, 0.1);
  color: var(--accent);
  font-size: 0.78rem;
  font-weight: 700;
}

.meta-grid, .cards { display: grid; gap: 14px; }
.meta-grid { grid-template-columns: repeat(2, minmax(0, 1fr)); }
.cards { margin-top: 18px; grid-template-columns: repeat(3, minmax(0, 1fr)); }
.card { padding: 18px; }

.meta-k {
  color: var(--muted);
  font-size: 0.75rem;
  text-transform: uppercase;
  letter-spacing: 0.08em;
}

.meta-v {
  margin-top: 6px;
  font-size: 1rem;
  font-weight: 700;
  word-break: break-word;
}

.code {
  margin-top: 10px;
  padding: 12px 14px;
  border-radius: 14px;
  border: 1px solid rgba(34, 211, 238, 0.16);
  background: rgba(0, 0, 0, 0.18);
  color: #b8f4ff;
  font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, monospace;
  font-size: 0.85rem;
  white-space: pre-wrap;
  line-height: 1.6;
}

html[data-theme="light"] .code {
  background: rgba(255, 255, 255, 0.92);
  color: #0f172a;
}

.warning {
  margin-top: 12px;
  padding: 12px 14px;
  border-radius: 14px;
  border: 1px solid rgba(239, 68, 68, 0.2);
  background: rgba(239, 68, 68, 0.08);
  color: var(--text);
  font-size: 0.9rem;
}

.section { margin-top: 18px; }
.list { margin: 14px 0 0; padding-left: 18px; color: var(--muted); line-height: 1.7; }
.list.ordered { padding-left: 20px; }
.list li + li { margin-top: 8px; }

.docs-grid {
  margin-top: 18px;
}

.entry + .entry {
  margin-top: 16px;
  padding-top: 16px;
  border-top: 1px solid var(--line);
}

.card-icon {
  width: 44px;
  height: 44px;
  border-radius: 12px;
  background: linear-gradient(135deg, var(--accent-soft), rgba(34, 211, 238, 0.06));
  border: 1px solid rgba(34, 211, 238, 0.12);
  display: flex;
  align-items: center;
  justify-content: center;
  margin-bottom: 14px;
}

.card-icon svg {
  width: 22px;
  height: 22px;
  color: var(--accent);
  stroke-width: 1.75;
}

.card h3 { margin: 0 0 10px; font-size: 1rem; }
.card p { margin: 0 0 14px; font-size: 0.88rem; }

.download-card {
  display: flex;
  flex-direction: column;
  gap: 0;
}

.download-card .card-icon { margin-bottom: 16px; }

.card {
  transition: transform 0.25s cubic-bezier(0.16, 1, 0.3, 1), border-color 0.25s ease, box-shadow 0.25s ease;
}

.card:hover {
  border-color: var(--accent-glow);
  transform: translateY(-2px);
  box-shadow: var(--shadow-glow);
}

.footer {
  margin-top: 18px;
  padding: 16px 20px;
  display: flex;
  justify-content: space-between;
  gap: 12px;
  flex-wrap: wrap;
}

@media (max-width: 920px) {
  .hero, .cards { grid-template-columns: 1fr; }
}

@media (max-width: 768px) {
  .wrap { width: min(100% - 24px, 960px); padding: 14px 0 28px; }
  .nav { padding: 12px 16px; }
  .hero { padding: 18px; gap: 18px; }
  .card { padding: 16px; border-radius: 16px; }
  .cards { gap: 12px; }
  .meta-grid { gap: 12px; }
  .code { padding: 10px 12px; font-size: 0.8rem; }
}

@media (max-width: 600px) {
  .wrap { width: min(100% - 20px, 960px); padding: 12px 0 24px; }
  .nav { padding: 10px 14px; border-radius: 16px; }
  .hero { padding: 16px; border-radius: 16px; }
  .card { padding: 14px; border-radius: 14px; }
  h1 { font-size: clamp(1.8rem, 5vw, 3rem); }
  .eyebrow { font-size: 0.7rem; padding: 5px 10px; }
  .button { padding: 8px 14px; font-size: 0.85rem; }
  .meta-k { font-size: 0.7rem; }
  .meta-v { font-size: 0.9rem; }
  .meta-grid { grid-template-columns: 1fr; }
}

@media (max-width: 480px) {
  .wrap { width: min(100% - 16px, 960px); padding: 10px 0 20px; }
  .nav { padding: 10px 12px; border-radius: 14px; flex-direction: column; gap: 10px; }
  .nav .controls, .nav .links { width: 100%; justify-content: center; }
  .hero { padding: 14px; border-radius: 14px; }
  .card { padding: 12px; border-radius: 12px; }
  h1 { font-size: clamp(1.6rem, 5vw, 2.4rem); }
  p { font-size: 0.9rem; }
  .footer { padding: 14px 16px; border-radius: 14px; flex-direction: column; gap: 10px; }
}

@media (prefers-reduced-motion: reduce) {
  *, *::before, *::after {
    animation-duration: 0.01ms !important;
    animation-iteration-count: 1 !important;
    transition-duration: 0.01ms !important;
  }
}
</style>
