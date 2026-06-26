<template>
  <div class="wrap">
    <a href="#main-landing" class="skip-link">Skip to main content</a>
    <header class="nav" role="banner">
      <div class="brand">
        <span class="mark"></span>
        <span>ACP Hub</span>
      </div>
      <div class="control-cluster">
        <LangToggle :messages="messages" />
        <ThemeToggle :messages="messages" />
      </div>
      <div class="nav-links">
        <a class="link" href="#platform">{{ t('nav_platform') }}</a>
        <router-link class="link" to="/downloads">{{ t('nav_download') }}</router-link>
        <router-link class="link" to="/dashboard">{{ t('nav_dashboard') }}</router-link>
        <a class="link" href="/runtime">{{ t('nav_runtime') }}</a>
      </div>
    </header>

    <main id="main-landing">
      <section class="hero">
        <div class="hero-copy">
          <div class="eyebrow">{{ t('eyebrow') }}</div>
          <h1>{{ t('hero_title') }}</h1>
          <p class="lead">{{ t('hero_lead') }}</p>
          <div class="hero-actions">
            <router-link class="button button-primary" to="/downloads">{{ t('hero_cta_download') }}</router-link>
            <router-link class="button button-secondary" to="/dashboard">{{ t('hero_cta_dashboard') }}</router-link>
          </div>
          <div class="hero-signal-row" aria-hidden="true">
            <div class="hero-signal-card">
              <span class="hero-signal-label">{{ t('tile_sessions') }}</span>
              <strong>{{ t('tile_sessions_value') }}</strong>
            </div>
            <div class="hero-signal-card">
              <span class="hero-signal-label">{{ t('tile_tasks') }}</span>
              <strong>{{ t('tile_tasks_value') }}</strong>
            </div>
            <div class="hero-signal-card">
              <span class="hero-signal-label">{{ t('tile_bridge') }}</span>
              <strong>{{ t('tile_bridge_value') }}</strong>
            </div>
          </div>
        </div>

        <aside class="hero-card">
          <span class="label">{{ t('surface_label') }}</span>
          <div class="value">{{ t('surface_value') }}</div>
          <div class="grid">
            <div class="tile">
              <span class="label">{{ t('tile_sessions') }}</span>
              <span class="value">{{ t('tile_sessions_value') }}</span>
            </div>
            <div class="tile">
              <span class="label">{{ t('tile_tasks') }}</span>
              <span class="value">{{ t('tile_tasks_value') }}</span>
            </div>
            <div class="tile">
              <span class="label">{{ t('tile_bridge') }}</span>
              <span class="value">{{ t('tile_bridge_value') }}</span>
            </div>
          </div>
          <div class="release-note">
            <div class="release-head">
              <span class="release-badge">{{ t('release_badge') }}</span>
              <span class="value">{{ release?.version ?? '-' }}</span>
            </div>
            <p class="release-copy">{{ releaseMeta }}</p>
            <p class="release-copy">{{ releaseLatestNote }}</p>
            <router-link class="release-link" to="/downloads">{{ t('release_link') }}</router-link>
          </div>
          <div class="terminal">{{ t('terminal') }}</div>
        </aside>
      </section>

      <section class="section" id="platform">
        <div class="section-head">
          <div>
            <h2>{{ t('platform_title') }}</h2>
          </div>
          <p>{{ t('platform_intro') }}</p>
        </div>
        <div class="panel-grid">
          <article class="panel panel-icon">
            <div class="panel-icon-wrap">
              <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"><path d="M16 3h5v5M8 3H3v5M3 16v5h5M21 16v5h-5M12 8v8M8 12h8"/></svg>
            </div>
            <h3>{{ t('panel_root_title') }}</h3>
            <p>{{ t('panel_root_body') }}</p>
          </article>
          <article class="panel panel-icon">
            <div class="panel-icon-wrap">
              <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"><path d="M22 12h-4l-3 9L9 3l-3 9H2"/></svg>
            </div>
            <h3>{{ t('panel_bundle_title') }}</h3>
            <p>{{ t('panel_bundle_body') }}</p>
          </article>
          <article class="panel panel-icon">
            <div class="panel-icon-wrap">
              <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"><path d="M4 19.5A2.5 2.5 0 016.5 17H20"/><path d="M6.5 2H20v20H6.5A2.5 2.5 0 014 19.5v-15A2.5 2.5 0 016.5 2z"/></svg>
            </div>
            <h3>{{ t('panel_docs_title') }}</h3>
            <p>{{ t('panel_docs_body') }}</p>
          </article>
          <article class="panel panel-icon">
            <div class="panel-icon-wrap">
              <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="12" r="10"/><path d="M12 16v-4M12 8h.01"/></svg>
            </div>
            <h3>{{ t('panel_ops_title') }}</h3>
            <p>{{ t('panel_ops_body') }}</p>
          </article>
        </div>
      </section>

      <section class="section" id="download">
        <div class="section-head">
          <div>
            <h2>{{ t('download_title') }}</h2>
          </div>
          <p>{{ t('download_intro') }}</p>
        </div>
        <div class="panel-grid">
          <article class="panel panel-icon">
            <div class="panel-icon-wrap">
              <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"><path d="M21 15v4a2 2 0 01-2 2H5a2 2 0 01-2-2v-4M7 10l5 5 5-5M12 15V3"/></svg>
            </div>
            <h3>{{ t('download_card_title') }}</h3>
            <p>{{ t('download_card_body') }}</p>
            <p><router-link class="button button-primary" to="/downloads">{{ t('download_card_cta') }}</router-link></p>
          </article>
          <article class="panel panel-icon">
            <div class="panel-icon-wrap">
              <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"><path d="M8 6h13"/><path d="M8 12h13"/><path d="M8 18h13"/><path d="M3 6h.01"/><path d="M3 12h.01"/><path d="M3 18h.01"/></svg>
            </div>
            <h3>{{ t('download_docs_title') }}</h3>
            <p>{{ t('download_docs_body') }}</p>
            <p class="download-links">
              <a class="link-inline" href="/downloads/ACP_AGENT/AGENT.md">{{ t('download_docs_guide') }}</a>
              <a class="link-inline" href="/downloads/ACP_AGENT/skills/acp-session-coordinator/SKILL.md">{{ t('download_docs_skill') }}</a>
            </p>
          </article>
          <article class="panel panel-icon">
            <div class="panel-icon-wrap">
              <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"><path d="M12 2L2 7l10 5 10-5-10-5zM2 17l10 5 10-5M2 12l10 5 10-5"/></svg>
            </div>
            <h3>{{ t('ops_paths_title') }}</h3>
            <p>{{ t('ops_paths_body') }}</p>
          </article>
          <article class="panel panel-icon">
            <div class="panel-icon-wrap">
              <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"><path d="M22 11.08V12a10 10 0 11-5.93-9.14"/><path d="M22 4L12 14.01l-3-3"/></svg>
            </div>
            <h3>{{ t('next_split_title') }}</h3>
            <p>{{ t('next_split_body') }}</p>
          </article>
        </div>
      </section>
    </main>

    <footer class="footer">
      <div class="footer-band">
        <div>
          <h3>ACP Hub</h3>
          <p>{{ t('footer_body') }}</p>
        </div>
        <div>
          <router-link class="button button-secondary" to="/dashboard">{{ t('footer_cta') }}</router-link>
        </div>
      </div>
    </footer>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted, watchEffect } from 'vue'
import { useI18n, useTheme, ThemeToggle, LangToggle } from '@acp/shared'
import { messages } from '../i18n'
import { apiFetch } from '../api/client'

interface ReleaseData {
  version: string
  released_at?: string
  size_mb?: number
  changelog?: { version: string; notes?: (string | Record<string, string>)[] }[]
}

const { t } = useI18n(messages)
useTheme()

const release = ref<ReleaseData | null>(null)

onMounted(async () => {
  try {
    release.value = await apiFetch<ReleaseData>('/api/release')
  } catch {
    // release info unavailable
  }
})

const releaseMeta = computed(() => {
  if (!release.value) return '-'
  const r = release.value
  if (r.released_at) {
    return t('release_meta', { date: r.released_at, size: String(r.size_mb ?? '?') })
  }
  return t('release_meta_no_date', { size: String(r.size_mb ?? '?') })
})

const releaseLatestNote = computed(() => {
  if (!release.value) return '-'
  const r = release.value
  const changelog = Array.isArray(r.changelog) ? r.changelog : []
  const latest = changelog[0]
  const firstNote = latest?.notes?.[0]
  if (firstNote) {
    const noteText = typeof firstNote === 'object' ? (firstNote.en ?? firstNote.es ?? '') : String(firstNote)
    return t('release_latest_note', { version: r.version, note: noteText })
  }
  return t('release_fallback_note', { version: r.version })
})

watchEffect(() => {
  document.title = t('page_title')
})
</script>

<style scoped>
.wrap {
  width: min(1160px, calc(100% - 32px));
  margin: 0 auto;
}

.nav,
.hero,
.hero-card,
.panel,
.footer-band {
  background: var(--panel);
  border: 1px solid var(--line);
  box-shadow: var(--shadow);
  backdrop-filter: blur(16px);
  -webkit-backdrop-filter: blur(16px);
  transition: transform 0.25s cubic-bezier(0.16, 1, 0.3, 1), border-color 0.25s ease, box-shadow 0.25s ease;
}

.nav:hover,
.hero:hover,
.hero-card:hover,
.panel:hover,
.footer-band:hover {
  border-color: var(--line-strong);
}

.nav {
  margin-top: 16px;
  border-radius: 24px;
  padding: 18px 22px;
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 16px;
  flex-wrap: wrap;
}

.brand {
  display: inline-flex;
  align-items: center;
  gap: 12px;
  font-family: "Outfit", sans-serif;
  font-weight: 800;
  letter-spacing: 0.04em;
  text-transform: uppercase;
}

.mark {
  width: 16px;
  height: 16px;
  border-radius: 50%;
  background: radial-gradient(circle at 30% 30%, #dff9ff 0%, var(--accent) 45%, var(--accent-deep) 100%);
  box-shadow: 0 0 22px rgba(34, 211, 238, 0.35);
}

.nav-links,
.control-cluster {
  display: flex;
  align-items: center;
  gap: 12px;
  flex-wrap: wrap;
}

a {
  color: inherit;
  text-decoration: none;
}

.link {
  color: var(--muted);
  font-size: 0.9rem;
  transition: color 0.2s ease;
}

.link:hover {
  color: var(--text);
}

.button {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  padding: 9px 16px;
  border-radius: 999px;
  font-family: "Outfit", sans-serif;
  font-weight: 700;
  font-size: 0.9rem;
  transition: transform 0.2s cubic-bezier(0.16, 1, 0.3, 1), border-color 0.2s ease, background 0.2s ease, box-shadow 0.2s ease;
  position: relative;
  overflow: hidden;
}

.button::after {
  content: '';
  position: absolute;
  inset: 0;
  background: linear-gradient(180deg, rgba(255,255,255,0.15), transparent);
  opacity: 0;
  transition: opacity 0.2s ease;
  pointer-events: none;
}

.button:hover::after {
  opacity: 1;
}

.button:hover,
.link:hover {
  transform: translateY(-2px);
}

.button-primary {
  color: var(--button-ink);
  background: var(--accent);
}

.button-primary:hover {
  background: var(--accent-deep);
  box-shadow: var(--shadow-glow);
}

.button-secondary {
  border: 1px solid var(--line-strong);
  background: var(--panel-soft);
}

.button-secondary:hover {
  border-color: var(--accent);
  background: var(--accent-soft);
}

.hero {
  display: grid;
  grid-template-columns: minmax(0, 1.06fr) minmax(300px, 0.94fr);
  gap: 28px;
  margin-top: 18px;
  padding: 34px 32px 30px;
  border-radius: 30px;
  position: relative;
  overflow: hidden;
}

.hero::before,
.hero::after {
  content: "";
  position: absolute;
  inset: auto;
  pointer-events: none;
}

.hero::before {
  width: 420px;
  height: 420px;
  top: -180px;
  left: -120px;
  border-radius: 50%;
  background: radial-gradient(circle, rgba(34, 211, 238, 0.22) 0%, rgba(34, 211, 238, 0.06) 38%, transparent 72%);
}

.hero::after {
  width: 360px;
  height: 360px;
  right: -120px;
  bottom: -160px;
  border-radius: 50%;
  background: radial-gradient(circle, rgba(6, 182, 212, 0.16) 0%, rgba(6, 182, 212, 0.04) 42%, transparent 72%);
}

.hero-copy,
.hero-card {
  position: relative;
  z-index: 1;
}

.hero-copy {
  display: flex;
  flex-direction: column;
  justify-content: center;
}

.eyebrow {
  display: inline-flex;
  align-items: center;
  gap: 8px;
  padding: 7px 12px;
  border-radius: 999px;
  color: var(--accent);
  background: rgba(34, 211, 238, 0.1);
  border: 1px solid rgba(34, 211, 238, 0.2);
  font-size: 0.78rem;
  letter-spacing: 0.08em;
  text-transform: uppercase;
}

.eyebrow::before {
  content: "";
  width: 7px;
  height: 7px;
  border-radius: 50%;
  background: var(--accent);
}

h1, h2, h3 {
  margin: 0;
  font-family: "Outfit", sans-serif;
  letter-spacing: -0.03em;
}

h1 {
  color: var(--text);
  margin-top: 18px;
  font-size: clamp(3rem, 7vw, 6rem);
  line-height: 0.96;
  max-width: 10ch;
  text-shadow:
    0 12px 34px rgba(3, 7, 18, 0.38),
    0 2px 0 rgba(255, 255, 255, 0.04);
}

p {
  color: var(--muted);
  line-height: 1.75;
}

.lead {
  max-width: 60ch;
  margin: 18px 0 0;
  font-size: 1.06rem;
}

.hero-actions {
  display: flex;
  flex-wrap: wrap;
  gap: 14px;
  margin-top: 28px;
}

.hero-signal-row {
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: 12px;
  margin-top: 24px;
}

.hero-signal-card {
  padding: 14px 16px;
  border-radius: 18px;
  border: 1px solid var(--tile-border);
  background: linear-gradient(180deg, rgba(255, 255, 255, 0.04), var(--panel-soft));
}

.hero-signal-card strong {
  display: block;
  margin-top: 4px;
  font-family: "Outfit", sans-serif;
  font-size: 1rem;
  color: var(--text);
}

.hero-signal-label {
  display: inline-flex;
  color: var(--muted);
  font-size: 0.72rem;
  letter-spacing: 0.08em;
  text-transform: uppercase;
}

.hero-card {
  border-radius: 24px;
  padding: 20px;
  position: relative;
  overflow: hidden;
}

.hero-card::after {
  content: "";
  position: absolute;
  inset: 0;
  pointer-events: none;
  background:
    linear-gradient(145deg, rgba(34, 211, 238, 0.14), transparent 34%),
    radial-gradient(circle at 85% 18%, rgba(34, 211, 238, 0.14), transparent 26%);
}

.hero-card > :deep(*) {
  position: relative;
  z-index: 1;
}

.grid {
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: 10px;
  margin: 18px 0 22px;
}

.tile, .panel {
  border-radius: 20px;
}

.tile {
  padding: 10px 12px;
  border: 1px solid var(--tile-border);
  background: var(--panel-soft);
  transition: all 0.2s ease;
}

.tile:hover {
  border-color: var(--line-strong);
  background: var(--panel-hover);
  transform: translateY(-2px);
}

.label {
  display: block;
  margin-bottom: 8px;
  color: var(--muted);
  font-size: 0.78rem;
  letter-spacing: 0.06em;
  text-transform: uppercase;
}

.value {
  font-family: "Outfit", sans-serif;
  font-weight: 700;
  font-size: 1.08rem;
}

.terminal {
  padding: 16px 18px;
  border-radius: 18px;
  border: 1px solid var(--shell-border);
  background: var(--shell-bg);
  color: var(--shell-ink);
  font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, monospace;
  line-height: 1.7;
  white-space: pre-wrap;
}

.release-note {
  margin-top: 16px;
  padding: 16px 18px;
  border-radius: 18px;
  border: 1px solid var(--shell-border);
  background: var(--panel-soft);
}

.release-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  flex-wrap: wrap;
}

.release-badge {
  display: inline-flex;
  align-items: center;
  gap: 8px;
  padding: 6px 10px;
  border-radius: 999px;
  border: 1px solid rgba(34, 211, 238, 0.2);
  background: rgba(34, 211, 238, 0.1);
  color: var(--accent);
  font-size: 0.76rem;
  letter-spacing: 0.08em;
  text-transform: uppercase;
  font-family: "Outfit", sans-serif;
  font-weight: 700;
}

.release-copy {
  margin: 10px 0 0;
  color: var(--text);
  font-size: 0.98rem;
  line-height: 1.7;
}

.release-link {
  margin-top: 12px;
  display: inline-flex;
  color: var(--accent);
  font-weight: 700;
}

.section {
  padding: 12px 0 26px;
}

.section-head {
  display: flex;
  justify-content: space-between;
  gap: 18px;
  align-items: end;
  margin-bottom: 18px;
}

.section-head p {
  max-width: 58ch;
  margin: 0;
}

.panel-grid {
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: 18px;
}

.panel {
  padding: 18px;
}

.panel.panel-icon {
  display: flex;
  flex-direction: column;
  gap: 14px;
  padding: 28px 24px;
}

.panel-icon-wrap {
  width: 52px;
  height: 52px;
  border-radius: 16px;
  background: linear-gradient(135deg, var(--accent-soft), rgba(34, 211, 238, 0.08));
  border: 1px solid rgba(34, 211, 238, 0.15);
  display: flex;
  align-items: center;
  justify-content: center;
  margin-bottom: 4px;
}

.panel-icon-wrap svg {
  width: 26px;
  height: 26px;
  color: var(--accent);
  stroke-width: 1.75;
}

.panel.panel-icon h3 {
  font-size: 1.05rem;
  margin: 0;
}

.panel.panel-icon p {
  margin: 0;
  font-size: 0.9rem;
  line-height: 1.65;
}

.download-links {
  display: flex;
  gap: 14px;
  flex-wrap: wrap;
}

.link-inline {
  color: var(--accent);
  font-weight: 700;
}

.footer {
  padding: 0 0 34px;
}

.footer-band {
  border-radius: 24px;
  padding: 20px 22px;
  display: flex;
  justify-content: space-between;
  gap: 16px;
  flex-wrap: wrap;
}

@media (max-width: 1200px) {
  .wrap { max-width: 960px; }
  .hero { gap: 24px; }
}

@media (max-width: 960px) {
  .hero,
  .panel-grid {
    grid-template-columns: 1fr;
  }
  h1 { max-width: none; }
  .section-head,
  .footer-band { align-items: flex-start; }
  .hero { padding: 28px 24px; }
  .hero-card { padding: 22px; }
}

@media (max-width: 768px) {
  .wrap { width: min(100% - 24px, 960px); padding: 0 12px; }
  .nav { padding: 14px 18px; margin-top: 12px; }
  .brand { font-size: 14px; gap: 10px; }
  .mark { width: 14px; height: 14px; }
  .nav-links { gap: 10px; }
  .link { font-size: 13px; }
  .hero { padding: 24px 20px; border-radius: 24px; gap: 20px; }
  .eyebrow { padding: 5px 10px; font-size: 11px; }
  .hero-actions { gap: 10px; margin-top: 20px; }
  .hero-signal-row { grid-template-columns: 1fr; gap: 10px; margin-top: 18px; }
  .hero-card { padding: 18px; border-radius: 20px; }
  .grid { gap: 8px; margin: 14px 0 18px; }
  .tile { padding: 12px; }
  .label { font-size: 11px; }
  .value { font-size: 14px; }
  .terminal { padding: 14px; font-size: 12px; line-height: 1.6; }
  .release-note { padding: 14px; }
  .section { padding: 10px 0 20px; }
  .section-head { margin-bottom: 14px; }
  .panel { padding: 18px; }
  .panel-grid { gap: 14px; }
  .footer { padding: 0 0 28px; }
  .footer-band { padding: 16px 18px; border-radius: 20px; }
  .control-cluster { gap: 8px; }
}

@media (max-width: 640px) {
  .wrap { width: min(100% - 20px, 1160px); }
  .grid { grid-template-columns: 1fr; }
  .nav, .hero, .hero-card, .panel, .footer-band { border-radius: 18px; }
  .nav-links, .control-cluster, .hero-actions { width: 100%; }
  .button { width: 100%; }
  .hero { padding: 20px 16px; border-radius: 20px; }
  .hero-card { padding: 16px; border-radius: 18px; }
  .tile { padding: 10px; border-radius: 14px; }
  .terminal { padding: 12px; font-size: 11px; border-radius: 14px; }
  .release-note { padding: 12px; border-radius: 14px; }
  .release-badge { padding: 4px 8px; font-size: 10px; }
  .panel { padding: 16px; border-radius: 16px; }
  .panel-grid { gap: 12px; }
  .section-head { flex-direction: column; gap: 10px; }
  h2 { font-size: 20px; }
  h3 { font-size: 16px; }
  p { font-size: 13px; }
  .footer-band { padding: 14px 16px; border-radius: 18px; flex-direction: column; align-items: stretch; gap: 12px; }
  .footer h3 { font-size: 16px; }
  .footer p { font-size: 12px; }
  .nav { flex-direction: column; gap: 12px; padding: 12px 14px; }
  .nav-links { justify-content: center; flex-wrap: wrap; }
  .control-cluster { justify-content: center; }
  .brand { font-size: 13px; }
  .mark { width: 12px; height: 12px; }
  .link { font-size: 12px; }
}

@media (max-width: 480px) {
  .wrap { width: min(100% - 16px, 1160px); }
  .nav { padding: 10px 12px; border-radius: 14px; margin-top: 10px; }
  .hero { padding: 16px 14px; border-radius: 16px; margin-top: 10px; }
  .eyebrow { font-size: 9px; padding: 3px 6px; }
  .hero-actions { margin-top: 16px; gap: 8px; }
  .button { padding: 10px 16px; font-size: 13px; border-radius: 10px; }
  .hero-card { padding: 14px; border-radius: 14px; }
  .grid { gap: 6px; margin: 10px 0 14px; }
  .tile { padding: 8px; border-radius: 10px; }
  .terminal { padding: 10px; font-size: 10px; border-radius: 10px; }
  .release-note { padding: 10px; border-radius: 10px; }
  .panel { padding: 14px; border-radius: 12px; }
  .panel-grid { gap: 10px; }
  .section { padding: 8px 0 16px; }
  h2 { font-size: 18px; }
  h3 { font-size: 14px; }
  p { font-size: 12px; }
  .footer-band { padding: 12px 14px; border-radius: 14px; }
  .footer h3 { font-size: 14px; }
  .nav-links { gap: 8px; }
  .link { font-size: 11px; }
}

@media (prefers-reduced-motion: reduce) {
  *, *::before, *::after {
    animation-duration: 0.01ms !important;
    animation-iteration-count: 1 !important;
    transition-duration: 0.01ms !important;
  }
}

.skip-link {
  position: absolute;
  top: -100%;
  left: 16px;
  z-index: 1000;
  padding: 8px 16px;
  background: var(--accent);
  color: var(--button-ink);
  border-radius: 0 0 8px 8px;
  font-weight: 700;
  font-size: 0.85rem;
  text-decoration: none;
  transition: top 0.15s;
}
.skip-link:focus {
  top: 0;
}

.button:focus-visible,
.link:focus-visible {
  outline: 2px solid var(--accent);
  outline-offset: 3px;
  border-radius: inherit;
}
</style>
