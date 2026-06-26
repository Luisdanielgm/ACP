"""Public landing page for the ACP hub root."""

from __future__ import annotations

from acp.hub.css_shared import marketing_shared_css

import json


_LANDING_HTML = """<!doctype html>
<html lang="es">
  <head>
    <meta charset="utf-8" />
    <meta name="viewport" content="width=device-width, initial-scale=1" />
    <title>ACP Hub | Coordinacion Multi-Agente</title>
    <link rel="icon" href="data:image/svg+xml,<svg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 100 100'><circle cx='50' cy='50' r='38' fill='none' stroke='%2322d3ee' stroke-width='6'/><circle cx='50' cy='28' r='7' fill='%2322d3ee'/><circle cx='30' cy='65' r='7' fill='%2322d3ee'/><circle cx='70' cy='65' r='7' fill='%2322d3ee'/><line x1='50' y1='35' x2='33' y2='59' stroke='%2322d3ee' stroke-width='3'/><line x1='50' y1='35' x2='67' y2='59' stroke='%2322d3ee' stroke-width='3'/><line x1='33' y1='65' x2='67' y2='65' stroke='%2322d3ee' stroke-width='3'/></svg>">
    <meta
      name="description"
      content="ACP Hub helps coding agents collaborate in shared sessions with task routing, progress visibility, and a portable ACP Agent bundle."
    />
    <link rel="preconnect" href="https://fonts.googleapis.com" />
    <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin />
    <link
      href="https://fonts.googleapis.com/css2?family=Outfit:wght@400;500;600;700;800&family=Manrope:wght@400;500;600;700&display=swap"
      rel="stylesheet"
    />
    """ + marketing_shared_css() + """
      .wrap {
        width: min(1160px, calc(100% - 32px));
        margin: 0 auto;
      }

      .nav,
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
      .actions,
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

      .lang-toggle,
      .theme-toggle {
        display: inline-flex;
        gap: 4px;
        align-items: center;
        border: 1px solid var(--line);
        border-radius: 999px;
        padding: 4px;
        background: var(--toggle-bg);
      }

      .lang-btn,
      .theme-btn {
        background: transparent;
        color: var(--muted);
        border: 0;
        border-radius: 999px;
        padding: 5px 12px;
        font-size: 11px;
        font-weight: 700;
        letter-spacing: 0.05em;
        cursor: pointer;
        transition: all 0.2s;
        font-family: "Outfit", sans-serif;
      }

      .lang-btn:hover,
      .theme-btn:hover {
        color: var(--text);
      }

      .lang-btn.active,
      .theme-btn.active {
        background: var(--text);
        color: var(--bg);
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
        padding: 34px 0 28px;
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

      h1,
      h2,
      h3 {
        margin: 0;
        font-family: "Outfit", sans-serif;
        letter-spacing: -0.03em;
      }

      h1 {
        background: linear-gradient(90deg, var(--text), color-mix(in srgb, var(--text) 58%, var(--accent) 42%));
        -webkit-background-clip: text;
        -webkit-text-fill-color: transparent;
      }

      h1 {
        margin-top: 18px;
        font-size: clamp(3rem, 7vw, 6rem);
        line-height: 0.96;
        max-width: 10ch;
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

      .hero-card > * {
        position: relative;
        z-index: 1;
      }

      .grid {
        display: grid;
        grid-template-columns: repeat(3, minmax(0, 1fr));
        gap: 10px;
        margin: 18px 0 22px;
      }

      .tile,
      .panel {
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

        h1 {
          max-width: none;
        }

        .section-head,
        .footer-band {
          align-items: flex-start;
        }
        
        .hero { padding: 28px 24px; }
        .title { font-size: 28px; }
        .lead { font-size: 16px; }
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
        .title { font-size: 24px; }
        .lead { font-size: 15px; }
        .eyebrow { padding: 5px 10px; font-size: 11px; }
        .hero-actions { gap: 10px; margin-top: 20px; }
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
        .lang-toggle, .theme-toggle { padding: 3px; }
        .lang-btn, .theme-btn { padding: 5px 12px; font-size: 11px; }
      }
      @media (max-width: 640px) {
        .wrap {
          width: min(100% - 20px, 1160px);
        }

        .grid {
          grid-template-columns: 1fr;
        }

        .nav,
        .hero-card,
        .panel,
        .footer-band {
          border-radius: 18px;
        }

        .nav-links,
        .actions,
        .control-cluster,
        .hero-actions {
          width: 100%;
        }

        .button {
          width: 100%;
        }
        
        .hero { padding: 20px 16px; border-radius: 20px; }
        .title { font-size: 20px; line-height: 1.1; }
        .lead { font-size: 14px; margin-top: 14px; }
        .eyebrow { font-size: 10px; padding: 4px 8px; }
        .hero-card { padding: 16px; border-radius: 18px; }
        .tile { padding: 10px; border-radius: 14px; }
        .label { font-size: 10px; }
        .value { font-size: 13px; }
        .terminal { padding: 12px; font-size: 11px; border-radius: 14px; }
        .release-note { padding: 12px; border-radius: 14px; }
        .release-badge { padding: 4px 8px; font-size: 10px; }
        .release-title { font-size: 14px; }
        .release-copy { font-size: 12px; }
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
        .title { font-size: 18px; }
        .lead { font-size: 13px; }
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
        .lang-btn, .theme-btn { padding: 4px 10px; font-size: 10px; }
      }
      @media (prefers-reduced-motion: reduce) {
        *, *::before, *::after {
          animation-duration: 0.01ms !important;
          animation-iteration-count: 1 !important;
          transition-duration: 0.01ms !important;
        }
      }
    </style>
  </head>
  <body>
    <div class="wrap">
      <header class="nav">
        <div class="brand">
          <span class="mark"></span>
          <span>ACP Hub</span>
        </div>
        <div class="control-cluster">
          <div class="lang-toggle" role="radiogroup" aria-label="Language switch">
            <button id="lang-es" class="lang-btn active" type="button" role="radio" aria-checked="true">ES</button>
            <button id="lang-en" class="lang-btn" type="button" role="radio" aria-checked="false">EN</button>
          </div>
          <div class="theme-toggle" role="radiogroup" aria-label="Theme switch">
            <button id="theme-dark" class="theme-btn" type="button" role="radio" aria-checked="false" data-i18n="theme_dark">Dark</button>
            <button id="theme-light" class="theme-btn" type="button" role="radio" aria-checked="false" data-i18n="theme_light">Light</button>
            <button id="theme-system" class="theme-btn" type="button" role="radio" aria-checked="true" data-i18n="theme_system">Auto</button>
          </div>
        </div>
        <div class="nav-links">
          <a class="link" href="#platform" data-i18n="nav_platform">Value</a>
          <a class="link" href="/downloads" data-i18n="nav_download">Download</a>
          <a class="link" href="/dashboard" data-i18n="nav_dashboard">Dashboard</a>
          <a class="link" href="/runtime" data-i18n="nav_runtime">Runtime</a>
        </div>
      </header>

      <main>
        <section class="hero">
          <div>
            <div class="eyebrow" data-i18n="eyebrow">Organize your AI agents</div>
            <h1 data-i18n="hero_title">Make multiple agents work together without losing control.</h1>
            <p class="lead" data-i18n="hero_lead">
              ACP helps you split work between agents, see what each one is doing, and keep everything ordered in one
              place so you can move faster on a project without coordinating everything by hand.
            </p>
            <div class="hero-actions">
              <a class="button button-primary" href="/downloads" data-i18n="hero_cta_download">Get ACP Agent</a>
              <a class="button button-secondary" href="/dashboard" data-i18n="hero_cta_dashboard">View dashboard</a>
            </div>
          </div>

          <aside class="hero-card">
            <span class="label" data-i18n="surface_label">What you get</span>
            <div class="value" data-i18n="surface_value">Less chaos, clearer progress, and better teamwork between agents</div>
            <div class="grid">
              <div class="tile">
                <span class="label" data-i18n="tile_sessions">Work</span>
                <span class="value" data-i18n="tile_sessions_value">Split clearly</span>
              </div>
              <div class="tile">
                <span class="label" data-i18n="tile_tasks">Progress</span>
                <span class="value" data-i18n="tile_tasks_value">Visible</span>
              </div>
              <div class="tile">
                <span class="label" data-i18n="tile_bridge">Control</span>
                <span class="value" data-i18n="tile_bridge_value">In one place</span>
              </div>
            </div>
            <div class="release-note">
              <div class="release-head">
                <span class="release-badge" data-i18n="release_badge">Current release</span>
                <span class="value" id="release-version">-</span>
              </div>
              <p class="release-copy" id="release-meta">-</p>
              <p class="release-copy" id="release-latest-note">-</p>
              <a class="release-link" href="/downloads" data-i18n="release_link">See releases and installation guide</a>
            </div>
            <div class="terminal" data-i18n="terminal">Assign different tasks to different agents
See who is working on what
Keep answers in one place
Follow progress without chasing updates
Move faster with less manual coordination</div>
          </aside>
        </section>

        <section class="section" id="platform">
          <div class="section-head">
            <div>
              <h2 data-i18n="platform_title">What this is for</h2>
            </div>
            <p data-i18n="platform_intro">
              If you use one or many AI agents in a project, ACP helps them work in order so they do not overlap, lose
              context, or leave you guessing what happened.
            </p>
          </div>
          <div class="panel-grid">
            <article class="panel panel-icon">
              <div class="panel-icon-wrap">
                <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"><path d="M16 3h5v5M8 3H3v5M3 16v5h5M21 16v5h-5M12 8v8M8 12h8"/></svg>
              </div>
              <h3 data-i18n="panel_root_title">Split the work</h3>
              <p data-i18n="panel_root_body">
                You can give different tasks to different agents and keep them aligned on the same project instead of
                juggling separate chats with no shared context.
              </p>
            </article>
            <article class="panel panel-icon">
              <div class="panel-icon-wrap">
                <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"><path d="M22 12h-4l-3 9L9 3l-3 9H2"/></svg>
              </div>
              <h3 data-i18n="panel_bundle_title">See the progress</h3>
              <p data-i18n="panel_bundle_body">
                ACP makes it easier to see what each agent is doing, what is still pending, and what already moved
                forward.
              </p>
            </article>
            <article class="panel panel-icon">
              <div class="panel-icon-wrap">
                <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="12" r="10"/><path d="M12 16v-4M12 8h.01"/></svg>
              </div>
              <h3 data-i18n="panel_ops_title">Keep control</h3>
              <p data-i18n-html="panel_ops_body">
                You stay in charge with one view of the work, instead of manually asking every agent for updates.
              </p>
            </article>
          </div>
        </section>

        <section class="section" id="download">
          <div class="section-head">
            <div>
              <h2 data-i18n="download_title">Start simply</h2>
            </div>
            <p data-i18n="download_intro">
              Install ACP Agent in a project and you have the base to connect agents and work with a much clearer flow.
            </p>
          </div>
          <div class="panel-grid">
            <article class="panel panel-icon">
              <div class="panel-icon-wrap">
                <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"><path d="M21 15v4a2 2 0 01-2 2H5a2 2 0 01-2-2v-4M7 10l5 5 5-5M12 15V3"/></svg>
              </div>
              <h3 data-i18n="download_card_title">ACP Agent</h3>
              <p data-i18n-html="download_card_body">
                Download the package, add it to your project, and use it to connect your agents around the same work.
              </p>
              <p><a class="button button-primary" href="/downloads" data-i18n="download_card_cta">Open downloads</a></p>
            </article>
            <article class="panel panel-icon">
              <div class="panel-icon-wrap">
                <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"><path d="M12 2L2 7l10 5 10-5-10-5zM2 17l10 5 10-5M2 12l10 5 10-5"/></svg>
              </div>
              <h3 data-i18n="ops_paths_title">What it saves you</h3>
              <p data-i18n-html="ops_paths_body">
                Less repeated context, fewer crossed messages, and less manual follow-up between agents and people.
              </p>
            </article>
            <article class="panel panel-icon">
              <div class="panel-icon-wrap">
                <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"><path d="M22 11.08V12a10 10 0 11-5.93-9.14"/><path d="M22 4L12 14.01l-3-3"/></svg>
              </div>
              <h3 data-i18n="next_split_title">What you achieve</h3>
              <p data-i18n="next_split_body">
                You can move faster with several agents working in parallel while keeping the work clearer and easier to
                supervise.
              </p>
            </article>
          </div>
        </section>
      </main>

      <footer class="footer">
        <div class="footer-band">
          <div>
            <h3>ACP Hub</h3>
            <p data-i18n="footer_body">A simpler way to organize several agents working on the same project.</p>
          </div>
          <div>
            <a class="button button-secondary" href="/dashboard" data-i18n="footer_cta">Open dashboard</a>
          </div>
        </div>
      </footer>
    </div>
    <script>
      const RELEASE = __RELEASE_JSON__;
      const I18N = {
        es: {
          nav_platform: 'Valor',
          nav_download: 'Descarga',
          nav_dashboard: 'Dashboard',
          nav_runtime: 'Runtime',
          eyebrow: 'Organiza tus agentes de IA',
          hero_title: 'Haz que varios agentes trabajen juntos sin perder el control.',
          hero_lead: 'ACP te ayuda a repartir trabajo entre agentes, ver en que esta cada uno y mantener todo ordenado en un solo lugar para avanzar mas rapido sin coordinar todo a mano.',
          hero_cta_download: 'Obtener ACP Agent',
          hero_cta_dashboard: 'Ver panel',
          surface_label: 'Lo que obtienes',
          surface_value: 'Menos caos, progreso mas claro y mejor trabajo en equipo entre agentes',
          tile_sessions: 'Trabajo',
          tile_sessions_value: 'Bien repartido',
          tile_tasks: 'Progreso',
          tile_tasks_value: 'Visible',
          tile_bridge: 'Control',
          tile_bridge_value: 'En un lugar',
          release_badge: 'Release actual',
          release_link: 'Ver releases y guia de instalacion',
          release_meta: 'Release {date} · ZIP {size} MB',
          release_meta_no_date: 'ZIP {size} MB · fecha de release disponible en descargas',
          release_latest_note: 'Version {version} · ultimo cambio: {note}',
          release_fallback_note: 'Version {version} disponible en el canal oficial.',
          terminal: `Reparte tareas entre distintos agentes
Ve quien esta trabajando en que
Mantiene respuestas en un mismo lugar
Sigue el avance sin perseguir updates
Avanza mas rapido con menos coordinacion manual`,
          platform_title: 'Para que sirve',
          platform_intro: 'Si usas uno o varios agentes de IA en un proyecto, ACP ayuda a que trabajen con orden para que no se pisen, no pierdan contexto y tu no tengas que perseguir cada avance.',
          panel_root_title: 'Repartir el trabajo',
          panel_root_body: 'Puedes dar tareas distintas a distintos agentes y mantenerlos alineados en el mismo proyecto en lugar de manejar chats separados sin relacion entre si.',
          panel_bundle_title: 'Ver el avance',
          panel_bundle_body: 'ACP hace mas facil ver que esta haciendo cada agente, que sigue pendiente y que ya avanzo.',
          panel_ops_title: 'Mantener el control',
          panel_ops_body: 'Tu sigues al mando con una sola vista del trabajo, en vez de pedirle actualizaciones manualmente a cada agente.',
          download_title: 'Empezar es simple',
          download_intro: 'Instalas ACP Agent en un proyecto y ya tienes la base para conectar agentes y trabajar con un flujo mucho mas claro.',
          download_card_title: 'ACP Agent',
          download_card_body: 'Descarga el paquete, agregalo a tu proyecto y usalo para conectar tus agentes alrededor del mismo trabajo.',
          download_card_cta: 'Abrir descargas',
          ops_paths_title: 'Lo que te ahorra',
          ops_paths_body: 'Menos contexto repetido, menos mensajes cruzados y menos seguimiento manual entre agentes y personas.',
          next_split_title: 'Lo que logras',
          next_split_body: 'Puedes avanzar mas rapido con varios agentes trabajando al mismo tiempo, sin que el trabajo se vuelva mas confuso.',
          footer_body: 'Una forma mas simple de organizar varios agentes trabajando sobre el mismo proyecto.',
          footer_cta: 'Ver panel',
          theme_dark: 'Oscuro',
          theme_light: 'Claro',
          theme_system: 'Auto',
          page_title: 'ACP Hub | Coordinacion Multi-Agente'
        },
        en: {
          nav_platform: 'Value',
          nav_download: 'Download',
          nav_dashboard: 'Dashboard',
          nav_runtime: 'Runtime',
          eyebrow: 'Organize your AI agents',
          hero_title: 'Make multiple agents work together without losing control.',
          hero_lead: 'ACP helps you split work between agents, see what each one is doing, and keep everything ordered in one place so you can move faster without coordinating everything by hand.',
          hero_cta_download: 'Get ACP Agent',
          hero_cta_dashboard: 'View dashboard',
          surface_label: 'What you get',
          surface_value: 'Less chaos, clearer progress, and better teamwork between agents',
          tile_sessions: 'Work',
          tile_sessions_value: 'Split clearly',
          tile_tasks: 'Progress',
          tile_tasks_value: 'Visible',
          tile_bridge: 'Control',
          tile_bridge_value: 'In one place',
          release_badge: 'Current release',
          release_link: 'See releases and installation guide',
          release_meta: 'Released {date} · ZIP {size} MB',
          release_meta_no_date: 'ZIP {size} MB · release date available in downloads',
          release_latest_note: 'Version {version} · latest change: {note}',
          release_fallback_note: 'Version {version} is available on the official release channel.',
          terminal: `Assign different tasks to different agents
See who is working on what
Keep answers in one place
Follow progress without chasing updates
Move faster with less manual coordination`,
          platform_title: 'What this is for',
          platform_intro: 'If you use one or many AI agents in a project, ACP helps them work in order so they do not overlap, lose context, or leave you guessing what happened.',
          panel_root_title: 'Split the work',
          panel_root_body: 'You can give different tasks to different agents and keep them aligned on the same project instead of juggling separate chats with no shared context.',
          panel_bundle_title: 'See the progress',
          panel_bundle_body: 'ACP makes it easier to see what each agent is doing, what is still pending, and what already moved forward.',
          panel_ops_title: 'Keep control',
          panel_ops_body: 'You stay in charge with one view of the work, instead of manually asking every agent for updates.',
          download_title: 'Start simply',
          download_intro: 'Install ACP Agent in a project and you have the base to connect agents and work with a much clearer flow.',
          download_card_title: 'ACP Agent',
          download_card_body: 'Download the package, add it to your project, and use it to connect your agents around the same work.',
          download_card_cta: 'Open downloads',
          ops_paths_title: 'What it saves you',
          ops_paths_body: 'Less repeated context, fewer crossed messages, and less manual follow-up between agents and people.',
          next_split_title: 'What you achieve',
          next_split_body: 'You can move faster with several agents working in parallel while keeping the work clearer and easier to supervise.',
          footer_body: 'A simpler way to organize several agents working on the same project.',
          footer_cta: 'Open dashboard',
          theme_dark: 'Dark',
          theme_light: 'Light',
          theme_system: 'Auto',
          page_title: 'ACP Hub | Multi-Agent Coordination'
        }
      };

      const langEsBtn = document.getElementById('lang-es');
      const langEnBtn = document.getElementById('lang-en');
      const themeDarkBtn = document.getElementById('theme-dark');
      const themeLightBtn = document.getElementById('theme-light');
      let currentLang = localStorage.getItem('acp_landing_lang') || 'es';
      let currentTheme = localStorage.getItem('acp_landing_theme') || 'system';

      function t(key) {
        return (I18N[currentLang] && I18N[currentLang][key]) || I18N.es[key] || key;
      }

      function tVars(key, vars = {}) {
        let value = t(key);
        for (const [name, replacement] of Object.entries(vars)) {
          value = value.replaceAll(`{${name}}`, String(replacement));
        }
        return value;
      }

      function renderReleaseSummary() {
        const version = RELEASE.version || '-';
        const changelog = Array.isArray(RELEASE.changelog) ? RELEASE.changelog : [];
        const latest = changelog.length > 0 ? changelog[0] : null;
        const firstNote = latest && Array.isArray(latest.notes) && latest.notes.length > 0 ? latest.notes[0] : null;
        document.getElementById('release-version').textContent = version;
        document.getElementById('release-meta').textContent = RELEASE.released_at
          ? tVars('release_meta', { date: RELEASE.released_at, size: RELEASE.size_mb })
          : tVars('release_meta_no_date', { size: RELEASE.size_mb });
        document.getElementById('release-latest-note').textContent = firstNote
          ? tVars('release_latest_note', { version, note: firstNote })
          : tVars('release_fallback_note', { version });
      }

      function applyTranslations() {
        document.documentElement.lang = currentLang;
        document.title = t('page_title');
        document.querySelectorAll('[data-i18n]').forEach((node) => {
          node.textContent = t(node.dataset.i18n);
        });
        document.querySelectorAll('[data-i18n-html]').forEach((node) => {
          node.innerHTML = t(node.dataset.i18nHtml);
        });
        langEsBtn.classList.toggle('active', currentLang === 'es');
        langEnBtn.classList.toggle('active', currentLang === 'en');
        langEsBtn.setAttribute('aria-checked', currentLang === 'es');
        langEnBtn.setAttribute('aria-checked', currentLang === 'en');
        renderReleaseSummary();
      }

      function applyTheme() {
        document.documentElement.dataset.theme = currentTheme;
        themeDarkBtn.classList.toggle('active', currentTheme === 'dark');
        themeLightBtn.classList.toggle('active', currentTheme === 'light');
        themeDarkBtn.setAttribute('aria-checked', currentTheme === 'dark');
        themeLightBtn.setAttribute('aria-checked', currentTheme === 'light');
        const themeSystemBtn = document.getElementById('theme-system');
        if (themeSystemBtn) {
          themeSystemBtn.classList.toggle('active', currentTheme === 'system');
          themeSystemBtn.setAttribute('aria-checked', currentTheme === 'system');
        }
      }

      function setLanguage(lang) {
        currentLang = lang === 'es' ? 'es' : 'en';
        localStorage.setItem('acp_landing_lang', currentLang);
        applyTranslations();
      }

      function setTheme(theme) {
        currentTheme = theme === 'light' ? 'light' : (theme === 'system' ? 'system' : 'dark');
        localStorage.setItem('acp_landing_theme', currentTheme);
        applyTheme();
      }

      langEsBtn.addEventListener('click', () => setLanguage('es'));
      langEnBtn.addEventListener('click', () => setLanguage('en'));
      themeDarkBtn.addEventListener('click', () => setTheme('dark'));
      themeLightBtn.addEventListener('click', () => setTheme('light'));
      const themeSystemBtn = document.getElementById('theme-system');
      if (themeSystemBtn) {
        themeSystemBtn.addEventListener('click', () => setTheme('system'));
      }

      applyTheme();
      applyTranslations();
    </script>
  </body>
</html>
"""


def render_landing_html(release: dict[str, object]) -> str:
    brand_name = str(release.get("brand_name") or "ACP Hub")
    template = _LANDING_HTML.replace("ACP Hub", brand_name)
    return template.replace("__RELEASE_JSON__", json.dumps(release, ensure_ascii=True))
