"""Shared inline CSS helpers for ACP Hub HTML views."""

from __future__ import annotations


def marketing_shared_css() -> str:
    return """<style>
      :root {
        --bg: #0B0B0A;
        --panel: rgba(255, 255, 255, 0.025);
        --panel-soft: rgba(255, 255, 255, 0.03);
        --panel-hover: rgba(255, 255, 255, 0.045);
        --line: rgba(255, 255, 255, 0.06);
        --line-strong: rgba(133, 183, 235, 0.22);
        --text: #f0f0f0;
        --muted: #8b94a7;
        --muted-strong: #a1aab5;
        --accent: #85B7EB;
        --accent-deep: #378ADD;
        --accent-glow: rgba(133, 183, 235, 0.25);
        --accent-soft: rgba(133, 183, 235, 0.08);
        --button-ink: #000;
        --toggle-bg: rgba(0, 0, 0, 0.3);
        --tile-border: rgba(255, 255, 255, 0.06);
        --shell-bg: rgba(0, 0, 0, 0.3);
        --shell-ink: #b8f4ff;
        --shell-border: rgba(133, 183, 235, 0.14);
        --shadow: 0 8px 32px rgba(0, 0, 0, 0.2);
        --shadow-glow: 0 4px 24px rgba(133, 183, 235, 0.15);
        --gradient-start: #232321;
        --gradient-end: #121211;
        --noise-opacity: 0.015;
      }

      @media (prefers-color-scheme: light) {
        html[data-theme="system"] {
          --bg: #F6F5F1;
          --panel: rgba(255, 255, 255, 0.78);
          --panel-soft: rgba(3, 3, 3, 0.03);
          --panel-hover: rgba(255, 255, 255, 0.88);
          --line: rgba(15, 23, 42, 0.08);
          --line-strong: rgba(133, 183, 235, 0.22);
          --text: #0f172a;
          --muted: #5b6474;
          --accent: #185FA5;
          --accent-deep: #0C447C;
          --accent-glow: rgba(24, 95, 165, 0.2);
          --accent-soft: rgba(24, 95, 165, 0.08);
          --button-ink: #03131a;
          --toggle-bg: rgba(255, 255, 255, 0.6);
          --tile-border: rgba(15, 23, 42, 0.08);
          --shell-bg: rgba(255, 255, 255, 0.9);
          --shell-ink: #0f172a;
          --shell-border: rgba(24, 95, 165, 0.18);
          --shadow: 0 10px 40px rgba(15, 23, 42, 0.08);
          --shadow-glow: 0 4px 20px rgba(24, 95, 165, 0.12);
          --gradient-start: #F1F0EB;
          --gradient-end: #E7E5DE;
          --noise-opacity: 0.02;
        }
        html[data-theme="system"] body {
          background:
            radial-gradient(circle at 50% -20%, rgba(133, 183, 235, 0.12) 0%, transparent 58%),
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
          radial-gradient(circle at 50% -20%, rgba(133, 183, 235, 0.12) 0%, transparent 58%),
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
        --bg: #0B0B0A;
        --panel: rgba(255, 255, 255, 0.025);
        --panel-hover: rgba(255, 255, 255, 0.045);
        --line: rgba(255, 255, 255, 0.06);
        --ink: #f0f0f0;
        --muted: #8b94a7;
        --muted-strong: #a1aab5;
        --accent: #85B7EB;
        --accent-hover: #378ADD;
        --accent-glow: rgba(133, 183, 235, 0.25);
        --accent-soft: rgba(133, 183, 235, 0.08);
        --soft: rgba(255, 255, 255, 0.015);
        --danger: #D85A30;
        --danger-soft: rgba(216, 90, 48, 0.1);
        --warning: #EF9F27;
        --warning-soft: rgba(239, 159, 39, 0.1);
        --success: #1D9E75;
        --success-soft: rgba(29, 158, 117, 0.1);
        --info: #7F77DD;
        --hero-glow: #1A1917;
        --title-start: #ffffff;
        --title-end: #a1a1aa;
        --toggle-bg: rgba(0, 0, 0, 0.3);
        --button-ink: #000;
        --card-bg: rgba(0, 0, 0, 0.2);
        --card-bg-strong: rgba(0, 0, 0, 0.22);
        --card-bg-soft: rgba(255, 255, 255, 0.02);
        --input-bg: rgba(0, 0, 0, 0.3);
        --trace-hover: rgba(255, 255, 255, 0.04);
        --node-core: #0B0B0A;
        --glyph-ink: #0B0B0A;
        --shadow-elev: 0 8px 32px rgba(0, 0, 0, 0.2);
        --shadow-glow: 0 4px 24px rgba(133, 183, 235, 0.15);
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
        --amber-accent: #EF9F27;
        --emerald-accent: #1D9E75;
        --gradient-start: #232321;
        --gradient-end: #121211;
        --noise-opacity: 0.015;
      }
      html[data-theme="light"] {
        --bg: #F6F5F1;
        --panel: rgba(255, 255, 255, 0.78);
        --panel-hover: rgba(255, 255, 255, 0.88);
        --line: rgba(15, 23, 42, 0.08);
        --ink: #0f172a;
        --muted: #5b6474;
        --muted-strong: #475569;
        --accent: #185FA5;
        --accent-hover: #0C447C;
        --accent-glow: rgba(24, 95, 165, 0.2);
        --accent-soft: rgba(24, 95, 165, 0.08);
        --soft: rgba(15, 23, 42, 0.03);
        --danger: #D85A30;
        --danger-soft: rgba(216, 90, 48, 0.06);
        --warning: #BA7517;
        --warning-soft: rgba(217, 119, 6, 0.06);
        --success: #0F6E56;
        --success-soft: rgba(5, 150, 105, 0.06);
        --info: #7c3aed;
        --hero-glow: rgba(133, 183, 235, 0.12);
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
        --shadow-glow: 0 4px 20px rgba(24, 95, 165, 0.12);
        --hover-line: rgba(24, 95, 165, 0.22);
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
        --amber-accent: #BA7517;
        --emerald-accent: #0F6E56;
        --gradient-start: #F1F0EB;
        --gradient-end: #E7E5DE;
        --noise-opacity: 0.02;
      }
      html[data-theme="system"] {
        --bg: #0B0B0A;
        --panel: rgba(255, 255, 255, 0.02);
        --panel-hover: rgba(255, 255, 255, 0.04);
        --line: rgba(255, 255, 255, 0.06);
        --ink: #f0f0f0;
        --muted: #888888;
        --muted-strong: #a1aab5;
        --accent: #85B7EB;
        --accent-hover: #378ADD;
        --accent-glow: rgba(133, 183, 235, 0.25);
        --accent-soft: rgba(133, 183, 235, 0.08);
        --soft: rgba(255, 255, 255, 0.015);
        --danger: #D85A30;
        --danger-soft: rgba(216, 90, 48, 0.1);
        --warning: #EF9F27;
        --warning-soft: rgba(239, 159, 39, 0.1);
        --success: #1D9E75;
        --success-soft: rgba(29, 158, 117, 0.1);
        --info: #7F77DD;
        --hero-glow: #1A1917;
        --title-start: #ffffff;
        --title-end: #a1a1aa;
        --toggle-bg: rgba(0, 0, 0, 0.3);
        --button-ink: #000;
        --card-bg: rgba(0, 0, 0, 0.2);
        --card-bg-strong: rgba(0, 0, 0, 0.22);
        --card-bg-soft: rgba(255, 255, 255, 0.02);
        --input-bg: rgba(0, 0, 0, 0.3);
        --trace-hover: rgba(255, 255, 255, 0.04);
        --node-core: #0B0B0A;
        --glyph-ink: #0B0B0A;
        --shadow-elev: 0 8px 32px rgba(0, 0, 0, 0.2);
        --shadow-glow: 0 4px 24px rgba(133, 183, 235, 0.15);
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
        --amber-accent: #EF9F27;
        --emerald-accent: #1D9E75;
        --gradient-start: #232321;
        --gradient-end: #121211;
        --noise-opacity: 0.015;
      }
      @media (prefers-color-scheme: light) {
        html[data-theme="system"] {
          --bg: #F6F5F1;
          --panel: rgba(255, 255, 255, 0.78);
          --panel-hover: rgba(255, 255, 255, 0.88);
          --line: rgba(15, 23, 42, 0.08);
          --ink: #0f172a;
          --muted: #5b6474;
          --muted-strong: #475569;
          --accent: #185FA5;
          --accent-hover: #0C447C;
          --accent-glow: rgba(24, 95, 165, 0.2);
          --accent-soft: rgba(24, 95, 165, 0.08);
          --soft: rgba(15, 23, 42, 0.03);
          --danger: #D85A30;
          --danger-soft: rgba(216, 90, 48, 0.06);
          --warning: #BA7517;
          --warning-soft: rgba(217, 119, 6, 0.06);
          --success: #0F6E56;
          --success-soft: rgba(5, 150, 105, 0.06);
          --info: #7c3aed;
          --hero-glow: rgba(133, 183, 235, 0.12);
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
          --shadow-glow: 0 4px 20px rgba(24, 95, 165, 0.12);
          --hover-line: rgba(24, 95, 165, 0.22);
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
          --amber-accent: #BA7517;
          --emerald-accent: #0F6E56;
          --gradient-start: #F1F0EB;
          --gradient-end: #E7E5DE;
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
