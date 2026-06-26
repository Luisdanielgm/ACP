"""Shared inline CSS helpers for ACP Hub HTML views."""

from __future__ import annotations


def marketing_shared_css() -> str:
    return """<style>
      :root {
        --bg: #030303;
        --panel: rgba(255, 255, 255, 0.025);
        --panel-soft: rgba(255, 255, 255, 0.03);
        --panel-hover: rgba(255, 255, 255, 0.045);
        --line: rgba(255, 255, 255, 0.06);
        --line-strong: rgba(34, 211, 238, 0.22);
        --text: #f0f0f0;
        --muted: #8b94a7;
        --muted-strong: #a1aab5;
        --accent: #22d3ee;
        --accent-deep: #06b6d4;
        --accent-glow: rgba(34, 211, 238, 0.25);
        --accent-soft: rgba(34, 211, 238, 0.08);
        --button-ink: #000;
        --toggle-bg: rgba(0, 0, 0, 0.3);
        --tile-border: rgba(255, 255, 255, 0.06);
        --shell-bg: rgba(0, 0, 0, 0.3);
        --shell-ink: #b8f4ff;
        --shell-border: rgba(34, 211, 238, 0.14);
        --shadow: 0 8px 32px rgba(0, 0, 0, 0.2);
        --shadow-glow: 0 4px 24px rgba(34, 211, 238, 0.15);
        --gradient-start: #1e1e3f;
        --gradient-end: #0d0d1a;
        --noise-opacity: 0.015;
      }

      @media (prefers-color-scheme: light) {
        html[data-theme="system"] {
          --bg: #f4f7fb;
          --panel: rgba(255, 255, 255, 0.78);
          --panel-soft: rgba(3, 3, 3, 0.03);
          --panel-hover: rgba(255, 255, 255, 0.88);
          --line: rgba(15, 23, 42, 0.08);
          --line-strong: rgba(34, 211, 238, 0.22);
          --text: #0f172a;
          --muted: #5b6474;
          --accent: #0891b2;
          --accent-deep: #0e7490;
          --accent-glow: rgba(8, 145, 178, 0.2);
          --accent-soft: rgba(8, 145, 178, 0.08);
          --button-ink: #03131a;
          --toggle-bg: rgba(255, 255, 255, 0.6);
          --tile-border: rgba(15, 23, 42, 0.08);
          --shell-bg: rgba(255, 255, 255, 0.9);
          --shell-ink: #0f172a;
          --shell-border: rgba(8, 145, 178, 0.18);
          --shadow: 0 10px 40px rgba(15, 23, 42, 0.08);
          --shadow-glow: 0 4px 20px rgba(8, 145, 178, 0.12);
          --gradient-start: #f1f5f9;
          --gradient-end: #e2e8f0;
          --noise-opacity: 0.02;
        }
        html[data-theme="system"] body {
          background:
            radial-gradient(circle at 50% -20%, rgba(34, 211, 238, 0.12) 0%, transparent 58%),
            linear-gradient(180deg, var(--gradient-start), var(--gradient-end));
        }
      }

      * { box-sizing: border-box; margin: 0; padding: 0; }
      html { scroll-behavior: smooth; }
      body {
        margin: 0;
        min-height: 100vh;
        font-family: "Outfit", system-ui, sans-serif;
        color: var(--text);
        background:
          radial-gradient(circle at 50% -20%, rgba(21, 21, 37, 0.95) 0%, transparent 60%),
          linear-gradient(180deg, var(--gradient-start), var(--gradient-end));
      }

      html[data-theme="light"] body {
        background:
          radial-gradient(circle at 50% -20%, rgba(34, 211, 238, 0.12) 0%, transparent 58%),
          linear-gradient(180deg, var(--gradient-start), var(--gradient-end));
      }

      body::before {
        content: "";
        position: fixed;
        inset: 0;
        pointer-events: none;
        background-image:
          linear-gradient(rgba(255, 255, 255, 0.02) 1px, transparent 1px),
          linear-gradient(90deg, rgba(255, 255, 255, 0.02) 1px, transparent 1px);
        background-size: 44px 44px;
        mask-image: radial-gradient(circle at center, black 30%, transparent 80%);
        opacity: var(--noise-opacity);
        z-index: 0;
      }



"""


def realtime_dashboard_shared_css() -> str:
    return """<style>
      :root {
        --bg: #030303;
        --panel: rgba(255, 255, 255, 0.025);
        --panel-hover: rgba(255, 255, 255, 0.045);
        --line: rgba(255, 255, 255, 0.06);
        --ink: #f0f0f0;
        --muted: #8b94a7;
        --muted-strong: #a1aab5;
        --accent: #22d3ee;
        --accent-hover: #06b6d4;
        --accent-glow: rgba(34, 211, 238, 0.25);
        --accent-soft: rgba(34, 211, 238, 0.08);
        --soft: rgba(255, 255, 255, 0.015);
        --danger: #ef4444;
        --danger-soft: rgba(239, 68, 68, 0.1);
        --warning: #f59e0b;
        --warning-soft: rgba(245, 158, 11, 0.1);
        --success: #10b981;
        --success-soft: rgba(16, 185, 129, 0.1);
        --info: #8b5cf6;
        --hero-glow: #151525;
        --title-start: #ffffff;
        --title-end: #a1a1aa;
        --toggle-bg: rgba(0, 0, 0, 0.3);
        --button-ink: #000;
        --card-bg: rgba(0, 0, 0, 0.2);
        --card-bg-strong: rgba(0, 0, 0, 0.22);
        --card-bg-soft: rgba(255, 255, 255, 0.02);
        --input-bg: rgba(0, 0, 0, 0.3);
        --trace-hover: rgba(255, 255, 255, 0.04);
        --node-core: #030303;
        --glyph-ink: #030303;
        --shadow-elev: 0 8px 32px rgba(0, 0, 0, 0.2);
        --shadow-glow: 0 4px 24px rgba(34, 211, 238, 0.15);
        --hover-line: rgba(255, 255, 255, 0.1);
        --canvas-border: rgba(255, 255, 255, 0.07);
        --canvas-top: rgba(255, 255, 255, 0.03);
        --canvas-bottom: rgba(255, 255, 255, 0.01);
        --signal-line: rgba(255, 255, 255, 0.12);
        --shell-stroke: rgba(255, 255, 255, 0.14);
        --chip-bg: rgba(255, 255, 255, 0.05);
        --chip-border: transparent;
        --glass-bg: rgba(255, 255, 255, 0.03);
        --glass-border: rgba(255, 255, 255, 0.08);
        --navy-accent: #0ea5e9;
        --rose-accent: #f43f5e;
        --amber-accent: #f59e0b;
        --emerald-accent: #10b981;
        --gradient-start: #1e1e3f;
        --gradient-end: #0d0d1a;
        --noise-opacity: 0.015;
      }
      html[data-theme="light"] {
        --bg: #f4f7fb;
        --panel: rgba(255, 255, 255, 0.78);
        --panel-hover: rgba(255, 255, 255, 0.88);
        --line: rgba(15, 23, 42, 0.08);
        --ink: #0f172a;
        --muted: #5b6474;
        --muted-strong: #475569;
        --accent: #0891b2;
        --accent-hover: #0e7490;
        --accent-glow: rgba(8, 145, 178, 0.2);
        --accent-soft: rgba(8, 145, 178, 0.08);
        --soft: rgba(15, 23, 42, 0.03);
        --danger: #dc2626;
        --danger-soft: rgba(220, 38, 38, 0.06);
        --warning: #d97706;
        --warning-soft: rgba(217, 119, 6, 0.06);
        --success: #059669;
        --success-soft: rgba(5, 150, 105, 0.06);
        --info: #7c3aed;
        --hero-glow: rgba(34, 211, 238, 0.12);
        --title-start: #0f172a;
        --title-end: #475569;
        --toggle-bg: rgba(255, 255, 255, 0.62);
        --button-ink: #03131a;
        --card-bg: rgba(255, 255, 255, 0.62);
        --card-bg-strong: rgba(255, 255, 255, 0.72);
        --card-bg-soft: rgba(255, 255, 255, 0.82);
        --input-bg: rgba(255, 255, 255, 0.88);
        --trace-hover: rgba(15, 23, 42, 0.04);
        --node-core: rgba(255, 255, 255, 0.92);
        --glyph-ink: #0f172a;
        --shadow-elev: 0 12px 40px rgba(15, 23, 42, 0.08);
        --shadow-glow: 0 4px 20px rgba(8, 145, 178, 0.12);
        --hover-line: rgba(8, 145, 178, 0.22);
        --canvas-border: rgba(15, 23, 42, 0.1);
        --canvas-top: rgba(255, 255, 255, 0.88);
        --canvas-bottom: rgba(226, 232, 240, 0.72);
        --signal-line: rgba(15, 23, 42, 0.14);
        --shell-stroke: rgba(15, 23, 42, 0.12);
        --chip-bg: rgba(15, 23, 42, 0.05);
        --chip-border: rgba(15, 23, 42, 0.08);
        --glass-bg: rgba(255, 255, 255, 0.5);
        --glass-border: rgba(15, 23, 42, 0.1);
        --navy-accent: #0284c7;
        --rose-accent: #e11d48;
        --amber-accent: #d97706;
        --emerald-accent: #059669;
        --gradient-start: #f1f5f9;
        --gradient-end: #e2e8f0;
        --noise-opacity: 0.02;
      }
      html[data-theme="system"] {
        --bg: #030303;
        --panel: rgba(255, 255, 255, 0.02);
        --panel-hover: rgba(255, 255, 255, 0.04);
        --line: rgba(255, 255, 255, 0.06);
        --ink: #f0f0f0;
        --muted: #888888;
        --muted-strong: #a1aab5;
        --accent: #22d3ee;
        --accent-hover: #06b6d4;
        --accent-glow: rgba(34, 211, 238, 0.25);
        --accent-soft: rgba(34, 211, 238, 0.08);
        --soft: rgba(255, 255, 255, 0.015);
        --danger: #ef4444;
        --danger-soft: rgba(239, 68, 68, 0.1);
        --warning: #f59e0b;
        --warning-soft: rgba(245, 158, 11, 0.1);
        --success: #10b981;
        --success-soft: rgba(16, 185, 129, 0.1);
        --info: #8b5cf6;
        --hero-glow: #151525;
        --title-start: #ffffff;
        --title-end: #a1a1aa;
        --toggle-bg: rgba(0, 0, 0, 0.3);
        --button-ink: #000;
        --card-bg: rgba(0, 0, 0, 0.2);
        --card-bg-strong: rgba(0, 0, 0, 0.22);
        --card-bg-soft: rgba(255, 255, 255, 0.02);
        --input-bg: rgba(0, 0, 0, 0.3);
        --trace-hover: rgba(255, 255, 255, 0.04);
        --node-core: #030303;
        --glyph-ink: #030303;
        --shadow-elev: 0 8px 32px rgba(0, 0, 0, 0.2);
        --shadow-glow: 0 4px 24px rgba(34, 211, 238, 0.15);
        --hover-line: rgba(255, 255, 255, 0.1);
        --canvas-border: rgba(255, 255, 255, 0.07);
        --canvas-top: rgba(255, 255, 255, 0.03);
        --canvas-bottom: rgba(255, 255, 255, 0.01);
        --signal-line: rgba(255, 255, 255, 0.12);
        --shell-stroke: rgba(255, 255, 255, 0.14);
        --chip-bg: rgba(255, 255, 255, 0.05);
        --chip-border: transparent;
        --glass-bg: rgba(255, 255, 255, 0.03);
        --glass-border: rgba(255, 255, 255, 0.08);
        --navy-accent: #0ea5e9;
        --rose-accent: #f43f5e;
        --amber-accent: #f59e0b;
        --emerald-accent: #10b981;
        --gradient-start: #1e1e3f;
        --gradient-end: #0d0d1a;
        --noise-opacity: 0.015;
      }
      @media (prefers-color-scheme: light) {
        html[data-theme="system"] {
          --bg: #f4f7fb;
          --panel: rgba(255, 255, 255, 0.78);
          --panel-hover: rgba(255, 255, 255, 0.88);
          --line: rgba(15, 23, 42, 0.08);
          --ink: #0f172a;
          --muted: #5b6474;
          --muted-strong: #475569;
          --accent: #0891b2;
          --accent-hover: #0e7490;
          --accent-glow: rgba(8, 145, 178, 0.2);
          --accent-soft: rgba(8, 145, 178, 0.08);
          --soft: rgba(15, 23, 42, 0.03);
          --danger: #dc2626;
          --danger-soft: rgba(220, 38, 38, 0.06);
          --warning: #d97706;
          --warning-soft: rgba(217, 119, 6, 0.06);
          --success: #059669;
          --success-soft: rgba(5, 150, 105, 0.06);
          --info: #7c3aed;
          --hero-glow: rgba(34, 211, 238, 0.12);
          --title-start: #0f172a;
          --title-end: #475569;
          --toggle-bg: rgba(255, 255, 255, 0.62);
          --button-ink: #03131a;
          --card-bg: rgba(255, 255, 255, 0.62);
          --card-bg-strong: rgba(255, 255, 255, 0.72);
          --card-bg-soft: rgba(255, 255, 255, 0.82);
          --input-bg: rgba(255, 255, 255, 0.88);
          --trace-hover: rgba(15, 23, 42, 0.04);
          --node-core: rgba(255, 255, 255, 0.92);
          --glyph-ink: #0f172a;
          --shadow-elev: 0 12px 40px rgba(15, 23, 42, 0.08);
          --shadow-glow: 0 4px 20px rgba(8, 145, 178, 0.12);
          --hover-line: rgba(8, 145, 178, 0.22);
          --canvas-border: rgba(15, 23, 42, 0.1);
          --canvas-top: rgba(255, 255, 255, 0.88);
          --canvas-bottom: rgba(226, 232, 240, 0.72);
          --signal-line: rgba(15, 23, 42, 0.14);
          --shell-stroke: rgba(15, 23, 42, 0.12);
          --chip-bg: rgba(15, 23, 42, 0.05);
          --chip-border: rgba(15, 23, 42, 0.08);
          --glass-bg: rgba(255, 255, 255, 0.5);
          --glass-border: rgba(15, 23, 42, 0.1);
          --navy-accent: #0284c7;
          --rose-accent: #e11d48;
          --amber-accent: #d97706;
          --emerald-accent: #059669;
          --gradient-start: #f1f5f9;
          --gradient-end: #e2e8f0;
          --noise-opacity: 0.02;
        }
      }
      * { box-sizing: border-box; margin: 0; padding: 0; }
      html { scroll-behavior: smooth; }
      body { 
        margin: 0; 
        font-family: 'Outfit', system-ui, sans-serif; 
        background-color: var(--bg); 
        background-image: 
          radial-gradient(circle at 50% -20%, var(--hero-glow) 0%, transparent 60%),
          linear-gradient(180deg, var(--gradient-start), var(--gradient-end));
        background-attachment: fixed;
        color: var(--ink); 
        -webkit-font-smoothing: antialiased;
        -moz-osx-font-smoothing: grayscale;
        min-height: 100vh;
        line-height: 1.6;
      }
      body::before {
        content: "";
        position: fixed;
        inset: 0;
        pointer-events: none;
        background-image: url("data:image/svg+xml,%3Csvg viewBox='0 0 256 256' xmlns='http://www.w3.org/2000/svg'%3E%3Cfilter id='noise'%3E%3CfeTurbulence type='fractalNoise' baseFrequency='0.9' numOctaves='4' stitchTiles='stitch'/%3E%3C/filter%3E%3Crect width='100%25' height='100%25' filter='url(%23noise)'/%3E%3C/svg%3E");
        opacity: var(--noise-opacity);
        z-index: 0;
      }
"""
