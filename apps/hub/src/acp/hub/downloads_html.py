"""Downloads page HTML for ACP agent releases."""

from __future__ import annotations

from acp.hub.css_shared import marketing_shared_css

import json
from typing import Any


_DOWNLOADS_HTML = """<!doctype html>
<html lang="es">
  <head>
    <meta charset="utf-8" />
    <meta name="viewport" content="width=device-width, initial-scale=1" />
    <title>ACP Hub | ACP Agent Downloads</title>
    <link rel="icon" href="data:image/svg+xml,<svg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 100 100'><circle cx='50' cy='50' r='38' fill='none' stroke='%2322d3ee' stroke-width='6'/><circle cx='50' cy='28' r='7' fill='%2322d3ee'/><circle cx='30' cy='65' r='7' fill='%2322d3ee'/><circle cx='70' cy='65' r='7' fill='%2322d3ee'/><line x1='50' y1='35' x2='33' y2='59' stroke='%2322d3ee' stroke-width='3'/><line x1='50' y1='35' x2='67' y2='59' stroke='%2322d3ee' stroke-width='3'/><line x1='33' y1='65' x2='67' y2='65' stroke='%2322d3ee' stroke-width='3'/></svg>">
    <link rel="preconnect" href="https://fonts.googleapis.com" />
    <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin />
    <link href="https://fonts.googleapis.com/css2?family=Outfit:wght@400;500;600;700;800&family=Manrope:wght@400;500;600;700&display=swap" rel="stylesheet" />
    """ + marketing_shared_css() + """
      .wrap { width: min(1160px, calc(100% - 28px)); margin: 0 auto; padding: 16px 0 32px; }
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

      .brand { display: flex; align-items: center; gap: 10px; font-family: "Outfit", sans-serif; font-weight: 800; letter-spacing: 0.04em; text-transform: uppercase; }
      .mark { width: 14px; height: 14px; border-radius: 999px; background: radial-gradient(circle at 30% 30%, #dff9ff 0%, var(--accent) 45%, var(--accent-deep) 100%); box-shadow: 0 0 18px rgba(34, 211, 238, 0.35); }
      .controls, .links, .hero-actions { display: flex; align-items: center; gap: 10px; flex-wrap: wrap; }
      a { color: inherit; text-decoration: none; }
      .link { color: var(--muted); font-size: 0.9rem; font-weight: 500; transition: color 0.2s ease; }
      .link:hover { color: var(--text); }

      .toggle {
        display: inline-flex;
        gap: 4px;
        border: 1px solid var(--line);
        border-radius: 999px;
        padding: 3px;
        background: var(--toggle-bg);
      }

      .toggle button {
        border: 0;
        background: transparent;
        color: var(--muted);
        border-radius: 999px;
        padding: 5px 12px;
        font-family: "Outfit", sans-serif;
        font-size: 11px;
        font-weight: 700;
        letter-spacing: 0.05em;
        cursor: pointer;
        transition: all 0.2s ease;
      }

      .toggle button:hover {
        color: var(--text);
      }

      .toggle button.active {
        background: var(--accent);
        color: var(--button-ink);
        box-shadow: 0 2px 12px var(--accent-glow);
      }

      .hero {
        margin-top: 18px;
        padding: 22px;
        display: grid;
        grid-template-columns: minmax(0, 1.1fr) minmax(290px, 0.9fr);
        gap: 22px;
      }

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

      h1, h2, h3, h4 { margin: 0; letter-spacing: -0.03em; font-family: "Outfit", sans-serif; }
      h1 { margin-top: 14px; font-size: clamp(2.2rem, 5vw, 4.2rem); line-height: 0.96; }
      p { color: var(--muted); line-height: 1.7; }

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

      .button:hover {
        transform: translateY(-2px);
      }

      .button-primary { background: var(--accent); color: var(--button-ink); }
      .button-primary:hover { background: var(--accent-deep); box-shadow: var(--shadow-glow); }
      .button-secondary { border: 1px solid var(--line); background: var(--panel); }

      .meta-grid, .cards { display: grid; gap: 14px; }
      .meta-grid { grid-template-columns: repeat(2, minmax(0, 1fr)); }
      .cards { margin-top: 18px; grid-template-columns: repeat(3, minmax(0, 1fr)); }
      .card { padding: 18px; }
      .meta-k { color: var(--muted); font-size: 0.75rem; text-transform: uppercase; letter-spacing: 0.08em; }
      .meta-v { margin-top: 6px; font-size: 1rem; font-weight: 700; word-break: break-word; }
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

      .section { margin-top: 18px; }
      .list { margin: 14px 0 0; padding-left: 18px; color: var(--muted); line-height: 1.7; }
      .list li + li { margin-top: 8px; }
      .entry + .entry { margin-top: 16px; padding-top: 16px; border-top: 1px solid var(--line); }
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

      .warning {
        margin-top: 12px;
        padding: 12px 14px;
        border-radius: 14px;
        border: 1px solid rgba(239, 68, 68, 0.2);
        background: rgba(239, 68, 68, 0.08);
        color: var(--text);
        font-size: 0.9rem;
      }

      .footer {
        margin-top: 18px;
        padding: 16px 20px;
        display: flex;
        justify-content: space-between;
        gap: 12px;
        flex-wrap: wrap;
      }

      html[data-theme="system"] {
        --bg: #030303;
        --panel: rgba(255, 255, 255, 0.02);
        --line: rgba(255, 255, 255, 0.06);
        --text: #f0f0f0;
        --muted: #888888;
        --accent: #22d3ee;
        --accent-deep: #06b6d4;
        --accent-hover: #06b6d4;
        --accent-glow: rgba(34, 211, 238, 0.25);
        --accent-soft: rgba(34, 211, 238, 0.08);
        --danger: #ef4444;
        --toggle-bg: rgba(0, 0, 0, 0.3);
        --button-ink: #000;
        --shadow: 0 8px 32px rgba(0, 0, 0, 0.2);
        --shadow-glow: 0 4px 24px rgba(34, 211, 238, 0.15);
        --gradient-start: #1e1e3f;
        --gradient-end: #0d0d1a;
      }
      @media (prefers-color-scheme: light) {
        html[data-theme="system"] {
          --bg: #f4f7fb;
          --panel: rgba(255, 255, 255, 0.78);
          --line: rgba(15, 23, 42, 0.08);
          --text: #0f172a;
          --muted: #5b6474;
          --accent: #0891b2;
          --accent-deep: #0e7490;
          --accent-hover: #0e7490;
          --accent-glow: rgba(8, 145, 178, 0.2);
          --accent-soft: rgba(8, 145, 178, 0.08);
          --danger: #dc2626;
          --toggle-bg: rgba(255, 255, 255, 0.6);
          --button-ink: #03131a;
          --shadow: 0 10px 40px rgba(15, 23, 42, 0.08);
          --shadow-glow: 0 4px 20px rgba(8, 145, 178, 0.12);
          --gradient-start: #f1f5f9;
          --gradient-end: #e2e8f0;
        }
        html[data-theme="system"] body {
          background:
            radial-gradient(circle at 50% -20%, rgba(34, 211, 238, 0.12) 0%, transparent 58%),
            linear-gradient(180deg, var(--gradient-start), var(--gradient-end));
        }
        html[data-theme="system"] .code {
          background: rgba(255, 255, 255, 0.92);
          color: #0f172a;
        }
        html[data-theme="system"] .button-secondary {
          background: rgba(15, 23, 42, 0.03);
        }
      }

      html[data-theme="light"] body {
        background:
          radial-gradient(circle at 50% -20%, rgba(34, 211, 238, 0.12) 0%, transparent 58%),
          linear-gradient(180deg, var(--gradient-start), var(--gradient-end));
      }

      .card {
        transition: transform 0.25s cubic-bezier(0.16, 1, 0.3, 1), border-color 0.25s ease, box-shadow 0.25s ease;
      }
      .card:hover {
        border-color: var(--accent-glow);
        transform: translateY(-2px);
        box-shadow: var(--shadow-glow);
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
        .toggle button { padding: 4px 10px; font-size: 10px; }
        .footer { padding: 14px 16px; border-radius: 14px; flex-direction: column; gap: 10px; }
      }
    </style>
  </head>
  <body>
    <div class="wrap">
      <header class="nav">
        <div class="brand"><span class="mark"></span><span>ACP Hub</span></div>
        <div class="controls">
          <div class="toggle" role="radiogroup" aria-label="Language switch" id="lang-toggle">
            <button id="lang-es" type="button">ES</button>
            <button id="lang-en" type="button">EN</button>
          </div>
          <div class="toggle" role="radiogroup" aria-label="Theme switch" id="theme-toggle">
            <button id="theme-dark" type="button"></button>
            <button id="theme-light" type="button"></button>
            <button id="theme-system" type="button">Auto</button>
          </div>
        </div>
        <div class="links">
          <a class="link" href="/" id="nav-landing"></a>
          <a class="link" href="/dashboard" id="nav-dashboard"></a>
          <a class="link" href="/downloads/ACP_AGENT.json" id="nav-manifest"></a>
        </div>
      </header>

      <main class="hero">
        <section>
          <div class="eyebrow" id="eyebrow"></div>
          <h1 id="hero-title"></h1>
          <p id="hero-body"></p>
          <div class="hero-actions">
            <a class="button button-primary" href="/downloads/ACP_AGENT.zip" id="download-btn"></a>
            <a class="button button-secondary" href="/downloads/ACP_AGENT.json" id="manifest-btn"></a>
          </div>
          <div class="warning" id="warning-box"></div>
        </section>
        <aside class="card">
          <span class="badge" id="release-badge"></span>
          <div class="meta-grid section">
            <div>
              <div class="meta-k" id="meta-version-k"></div>
              <div class="meta-v" id="meta-version-v"></div>
            </div>
            <div>
              <div class="meta-k" id="meta-date-k"></div>
              <div class="meta-v" id="meta-date-v"></div>
            </div>
            <div>
              <div class="meta-k" id="meta-size-k"></div>
              <div class="meta-v" id="meta-size-v"></div>
            </div>
            <div>
              <div class="meta-k" id="meta-sha-k"></div>
              <div class="meta-v" id="meta-sha-v"></div>
            </div>
          </div>
        </aside>
      </main>

      <section class="cards">
        <article class="card download-card">
          <div class="card-icon">
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-linecap="round" stroke-linejoin="round"><path d="M22 11.08V12a10 10 0 11-5.93-9.14"/><path d="M22 4L12 14.01l-3-3"/></svg>
          </div>
          <h3 id="check-title"></h3>
          <p id="check-body"></p>
          <div class="code" id="check-code"></div>
        </article>
        <article class="card download-card">
          <div class="card-icon">
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-linecap="round" stroke-linejoin="round"><path d="M21 15v4a2 2 0 01-2 2H5a2 2 0 01-2-2v-4M7 10l5 5 5-5M12 15V3"/></svg>
          </div>
          <h3 id="update-title"></h3>
          <p id="update-body"></p>
          <div class="code" id="update-code"></div>
        </article>
        <article class="card download-card">
          <div class="card-icon">
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-linecap="round" stroke-linejoin="round"><path d="M19 21H5a2 2 0 01-2-2V5a2 2 0 012-2h11l5 5v11a2 2 0 01-2 2z"/><path d="M17 21v-8H7v8M7 3v5h8"/></svg>
          </div>
          <h3 id="preserve-title"></h3>
          <p id="preserve-body"></p>
          <ul class="list" id="preserve-list"></ul>
        </article>
      </section>

      <section class="card section">
        <h2 id="changelog-title"></h2>
        <p id="changelog-body"></p>
        <div id="changelog-list" class="section"></div>
      </section>

      <footer class="footer">
        <div>
          <h3>ACP Hub</h3>
          <p id="footer-body"></p>
        </div>
        <div class="links">
          <a class="link" href="/runtime" id="footer-runtime"></a>
          <a class="link" href="/health" id="footer-health"></a>
        </div>
      </footer>
    </div>
    <script>
      const RELEASE = __RELEASE_JSON__;
      const I18N = {
        es: {
          page_title: 'ACP Hub | Descargas de ACP Agent',
          eyebrow: 'canal oficial del bundle ACP',
          hero_title: 'Descargas y changelog de ACP Agent',
          hero_body: 'Aqui vive la version oficial del bundle. Los agentes pueden comparar su instalacion local con el manifest, descargar el ZIP y actualizarse preservando el estado operativo del proyecto.',
          nav_landing: 'Inicio',
          nav_dashboard: 'Dashboard',
          nav_manifest: 'Manifest',
          download_btn: 'Descargar ACP_AGENT.zip',
          manifest_btn: 'Ver manifest JSON',
          warning_box: 'Si actualizas un proyecto ya instalado, conserva agents/, inbox/, outbox/ y sent/. El updater oficial ya lo hace por ti.',
          release_badge: 'Release oficial',
          meta_version_k: 'Version',
          meta_date_k: 'Fecha',
          meta_size_k: 'Tamano',
          meta_sha_k: 'SHA256',
          check_title: 'Comparar version local',
          check_body: 'Usa este comando para que el agente vea si hay una release mas nueva sin modificar el proyecto.',
          update_title: 'Actualizar en sitio',
          update_body: 'Si hay una version nueva, descarga el bundle oficial y reemplaza los archivos del cliente sin tocar tus colas ni configs activos.',
          preserve_title: 'Lo que se preserva',
          preserve_body: 'El protocolo de update no debe destruir el estado operativo del proyecto.',
          preserve_agents: 'agents/ con las identidades locales',
          preserve_inbox: 'inbox/ con mensajes ya recibidos',
          preserve_outbox: 'outbox/ con mensajes pendientes',
          preserve_sent: 'sent/ con historico local',
          changelog_title: 'Changelog reciente',
          changelog_body: 'Ultimas versiones publicadas del bundle ACP_AGENT.',
          footer_runtime: 'Runtime',
          footer_health: 'Health',
          footer_body: 'Canal oficial de descarga, comparacion y actualizacion del cliente ACP.',
          theme_dark: 'Oscuro',
          theme_light: 'Claro',
          theme_system: 'Auto',
          lang_switch_aria: 'Cambiar idioma',
          theme_switch_aria: 'Cambiar tema',
          no_date: 'sin fecha',
        },
        en: {
          page_title: 'ACP Hub | ACP Agent Downloads',
          eyebrow: 'official ACP bundle channel',
          hero_title: 'ACP Agent downloads and changelog',
          hero_body: 'This is the official bundle surface. Agents can compare their local install against the manifest, download the ZIP, and update in place while preserving the project operational state.',
          nav_landing: 'Landing',
          nav_dashboard: 'Dashboard',
          nav_manifest: 'Manifest',
          download_btn: 'Download ACP_AGENT.zip',
          manifest_btn: 'View manifest JSON',
          warning_box: 'If you update an already installed project, preserve agents/, inbox/, outbox/, and sent/. The official updater already does this for you.',
          release_badge: 'Official release',
          meta_version_k: 'Version',
          meta_date_k: 'Date',
          meta_size_k: 'Size',
          meta_sha_k: 'SHA256',
          check_title: 'Compare local version',
          check_body: 'Use this command so the agent can detect whether a newer release exists without modifying the project.',
          update_title: 'Update in place',
          update_body: 'When a newer version exists, download the official bundle and replace the client files without touching active queues or configs.',
          preserve_title: 'What is preserved',
          preserve_body: 'The update protocol should not destroy the project operational state.',
          preserve_agents: 'agents/ with local identities',
          preserve_inbox: 'inbox/ with already received messages',
          preserve_outbox: 'outbox/ with pending messages',
          preserve_sent: 'sent/ with local history',
          changelog_title: 'Recent changelog',
          changelog_body: 'Latest published ACP_AGENT bundle versions.',
          footer_runtime: 'Runtime',
          footer_health: 'Health',
          footer_body: 'Official download, comparison, and update channel for the ACP client.',
          theme_dark: 'Dark',
          theme_light: 'Light',
          theme_system: 'Auto',
          lang_switch_aria: 'Switch language',
          theme_switch_aria: 'Switch theme',
          no_date: 'no date',
        }
      };

      const langEsBtn = document.getElementById('lang-es');
      const langEnBtn = document.getElementById('lang-en');
      const themeDarkBtn = document.getElementById('theme-dark');
      const themeLightBtn = document.getElementById('theme-light');
      const themeSystemBtn = document.getElementById('theme-system');
      let currentLang = localStorage.getItem('acp_downloads_lang') || 'es';
      let currentTheme = localStorage.getItem('acp_downloads_theme') || 'system';

      function t(key) {
        return (I18N[currentLang] && I18N[currentLang][key]) || I18N.es[key] || key;
      }

      function noteText(note) {
        if (note && typeof note === 'object') {
          return note[currentLang] || note.en || note.es || '';
        }
        return String(note || '');
      }

      function applyTheme() {
        document.documentElement.dataset.theme = currentTheme;
        themeDarkBtn.classList.toggle('active', currentTheme === 'dark');
        themeLightBtn.classList.toggle('active', currentTheme === 'light');
        themeSystemBtn.classList.toggle('active', currentTheme === 'system');
        themeDarkBtn.textContent = t('theme_dark');
        themeLightBtn.textContent = t('theme_light');
        themeSystemBtn.textContent = t('theme_system');
      }

      function render() {
        langEsBtn.classList.toggle('active', currentLang === 'es');
        langEnBtn.classList.toggle('active', currentLang === 'en');
        document.documentElement.lang = currentLang;
        document.title = t('page_title');
        document.getElementById('lang-toggle').setAttribute('aria-label', t('lang_switch_aria'));
        document.getElementById('theme-toggle').setAttribute('aria-label', t('theme_switch_aria'));
        document.getElementById('nav-landing').textContent = t('nav_landing');
        document.getElementById('nav-dashboard').textContent = t('nav_dashboard');
        document.getElementById('nav-manifest').textContent = t('nav_manifest');
        document.getElementById('eyebrow').textContent = t('eyebrow');
        document.getElementById('hero-title').textContent = t('hero_title');
        document.getElementById('hero-body').textContent = t('hero_body');
        document.getElementById('download-btn').textContent = t('download_btn');
        document.getElementById('manifest-btn').textContent = t('manifest_btn');
        document.getElementById('warning-box').textContent = t('warning_box');
        document.getElementById('release-badge').textContent = `${t('release_badge')} · ${RELEASE.version}`;
        document.getElementById('meta-version-k').textContent = t('meta_version_k');
        document.getElementById('meta-version-v').textContent = RELEASE.version || '-';
        document.getElementById('meta-date-k').textContent = t('meta_date_k');
        document.getElementById('meta-date-v').textContent = RELEASE.released_at || t('no_date');
        document.getElementById('meta-size-k').textContent = t('meta_size_k');
        document.getElementById('meta-size-v').textContent = `${RELEASE.size_mb} MB`;
        document.getElementById('meta-sha-k').textContent = t('meta_sha_k');
        document.getElementById('meta-sha-v').textContent = (RELEASE.sha256 || '-').slice(0, 16) + ((RELEASE.sha256 || '').length > 16 ? '...' : '');
        document.getElementById('check-title').textContent = t('check_title');
        document.getElementById('check-body').textContent = t('check_body');
        document.getElementById('check-code').textContent = RELEASE.check_command;
        document.getElementById('update-title').textContent = t('update_title');
        document.getElementById('update-body').textContent = t('update_body');
        document.getElementById('update-code').textContent = RELEASE.update_command;
        document.getElementById('preserve-title').textContent = t('preserve_title');
        document.getElementById('preserve-body').textContent = t('preserve_body');
        document.getElementById('preserve-list').innerHTML = [
          t('preserve_agents'),
          t('preserve_inbox'),
          t('preserve_outbox'),
          t('preserve_sent'),
        ].map((item) => `<li>${item}</li>`).join('');
        document.getElementById('changelog-title').textContent = t('changelog_title');
        document.getElementById('changelog-body').textContent = t('changelog_body');
        document.getElementById('footer-body').textContent = t('footer_body');
        document.getElementById('footer-runtime').textContent = t('footer_runtime');
        document.getElementById('footer-health').textContent = t('footer_health');

        const changelogList = document.getElementById('changelog-list');
        changelogList.innerHTML = (Array.isArray(RELEASE.changelog) ? RELEASE.changelog : []).map((entry) => `
          <article class="entry">
            <h4>${entry.version || '-'}</h4>
            <p>${entry.date || t('no_date')}</p>
            <ul class="list">${(Array.isArray(entry.notes) ? entry.notes : []).map((note) => `<li>${noteText(note)}</li>`).join('')}</ul>
          </article>
        `).join('');
      }

      langEsBtn.addEventListener('click', () => {
        currentLang = 'es';
        localStorage.setItem('acp_downloads_lang', currentLang);
        applyTheme();
        render();
      });
      langEnBtn.addEventListener('click', () => {
        currentLang = 'en';
        localStorage.setItem('acp_downloads_lang', currentLang);
        applyTheme();
        render();
      });
      themeDarkBtn.addEventListener('click', () => {
        currentTheme = 'dark';
        localStorage.setItem('acp_downloads_theme', currentTheme);
        applyTheme();
      });
      themeLightBtn.addEventListener('click', () => {
        currentTheme = 'light';
        localStorage.setItem('acp_downloads_theme', currentTheme);
        applyTheme();
      });
      themeSystemBtn.addEventListener('click', () => {
        currentTheme = 'system';
        localStorage.setItem('acp_downloads_theme', currentTheme);
        applyTheme();
      });

      applyTheme();
      render();
    </script>
  </body>
</html>
"""


def render_downloads_html(release: dict[str, Any]) -> str:
    brand_name = str(release.get("brand_name") or "ACP Hub")
    payload = json.dumps(release, ensure_ascii=True)
    return _DOWNLOADS_HTML.replace("ACP Hub", brand_name).replace("__RELEASE_JSON__", payload)
