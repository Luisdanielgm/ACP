"""Generic example of mounting a custom extension over the public ACP core."""

from __future__ import annotations

from fastapi import FastAPI
from fastapi.responses import HTMLResponse, JSONResponse

from acp.hub.app import HubRuntime, create_app

_OVERLAY_COMMON_STYLE = (
    "<style>"
    ":root {"
    "--bg: #030303; --panel: rgba(255,255,255,0.025); --line: rgba(255,255,255,0.06);"
    "--text: #f0f0f0; --muted: #8b94a7; --accent: #22d3ee; --accent-deep: #06b6d4;"
    "--accent-glow: rgba(34,211,238,0.25); --button-ink: #000;"
    "--toggle-bg: rgba(0,0,0,0.3); --shadow: 0 8px 32px rgba(0,0,0,0.2);"
    "--gradient-start: #1e1e3f; --gradient-end: #0d0d1a;"
    "}"
    "html[data-theme='light'] {"
    "--bg: #f4f7fb; --panel: rgba(255,255,255,0.78); --line: rgba(15,23,42,0.08);"
    "--text: #0f172a; --muted: #5b6474; --accent: #0891b2; --accent-deep: #0e7490;"
    "--accent-glow: rgba(8,145,178,0.2); --button-ink: #03131a;"
    "--toggle-bg: rgba(255,255,255,0.6); --shadow: 0 10px 40px rgba(15,23,42,0.08);"
    "--gradient-start: #f1f5f9; --gradient-end: #e2e8f0;"
    "}"
    "html[data-theme='system'] {"
    "--bg: #030303; --panel: rgba(255,255,255,0.02); --line: rgba(255,255,255,0.06);"
    "--text: #f0f0f0; --muted: #888; --accent: #22d3ee; --accent-deep: #06b6d4;"
    "--accent-glow: rgba(34,211,238,0.25); --button-ink: #000;"
    "--toggle-bg: rgba(0,0,0,0.3); --shadow: 0 8px 32px rgba(0,0,0,0.2);"
    "--gradient-start: #1e1e3f; --gradient-end: #0d0d1a;"
    "}"
    "@media (prefers-color-scheme: light) { html[data-theme='system'] {"
    "--bg: #f4f7fb; --panel: rgba(255,255,255,0.78); --line: rgba(15,23,42,0.08);"
    "--text: #0f172a; --muted: #5b6474; --accent: #0891b2; --accent-deep: #0e7490;"
    "--accent-glow: rgba(8,145,178,0.2); --button-ink: #03131a;"
    "--toggle-bg: rgba(255,255,255,0.6); --shadow: 0 10px 40px rgba(15,23,42,0.08);"
    "--gradient-start: #f1f5f9; --gradient-end: #e2e8f0;"
    "}"
    "html[data-theme='system'] body {"
    "background: radial-gradient(circle at 50% -20%, rgba(34,211,238,0.12) 0%, transparent 58%),"
    "linear-gradient(180deg, var(--gradient-start), var(--gradient-end)); }"
    "}"
    "* { box-sizing: border-box; margin: 0; padding: 0; }"
    "body { margin: 0; min-height: 100vh; font-family: 'Outfit', system-ui, sans-serif;"
    "background: radial-gradient(circle at 50% -20%, rgba(21,21,37,0.95) 0%, transparent 60%),"
    "linear-gradient(180deg, var(--gradient-start), var(--gradient-end));"
    "background-attachment: fixed; color: var(--text); -webkit-font-smoothing: antialiased; }"
    "html[data-theme='light'] body {"
    "background: radial-gradient(circle at 50% -20%, rgba(34,211,238,0.12) 0%, transparent 58%),"
    "linear-gradient(180deg, var(--gradient-start), var(--gradient-end)); }"
    ".wrap { max-width: 900px; margin: 0 auto; padding: 24px; }"
    ".nav { background: var(--panel); border: 1px solid var(--line); border-radius: 20px;"
    "padding: 14px 18px; display: flex; align-items: center; justify-content: space-between;"
    "gap: 12px; flex-wrap: wrap; box-shadow: var(--shadow); backdrop-filter: blur(16px); }"
    ".brand { display: flex; align-items: center; gap: 10px; font-weight: 800;"
    "letter-spacing: 0.04em; text-transform: uppercase; }"
    ".mark { width: 14px; height: 14px; border-radius: 50%;"
    "background: radial-gradient(circle at 30% 30%, #dff9ff 0%, var(--accent) 45%, var(--accent-deep) 100%);"
    "box-shadow: 0 0 18px rgba(34,211,238,0.35); }"
    ".nav-links { display: flex; gap: 12px; align-items: center; }"
    ".nav-links a { color: var(--muted); font-size: 0.9rem; text-decoration: none; transition: color 0.2s; }"
    ".nav-links a:hover { color: var(--text); }"
    ".control-cluster { display: flex; gap: 8px; align-items: center; }"
    ".lang-toggle, .theme-toggle { display: inline-flex; gap: 4px; align-items: center;"
    "border: 1px solid var(--line); border-radius: 999px; padding: 3px; background: var(--toggle-bg); }"
    ".lang-btn, .theme-btn { background: transparent; color: var(--muted); border: 0;"
    "border-radius: 999px; padding: 5px 12px; font-size: 11px; font-weight: 700;"
    "letter-spacing: 0.05em; cursor: pointer; transition: all 0.2s; font-family: 'Outfit', sans-serif; }"
    ".lang-btn:hover, .theme-btn:hover { color: var(--text); }"
    ".lang-btn.active, .theme-btn.active { background: var(--accent); color: var(--button-ink);"
    "box-shadow: 0 2px 12px var(--accent-glow); }"
    ".panel { background: var(--panel); border: 1px solid var(--line); border-radius: 20px;"
    "padding: 24px; margin-top: 20px; box-shadow: var(--shadow); backdrop-filter: blur(16px); }"
    "h1 { font-family: 'Outfit', sans-serif; font-size: 28px; font-weight: 800; letter-spacing: -0.03em;"
    "background: linear-gradient(90deg, var(--text), var(--accent));"
    "-webkit-background-clip: text; -webkit-text-fill-color: transparent; }"
    "p { color: var(--muted); line-height: 1.7; margin-top: 12px; }"
    "</style>"
)

_OVERLAY_I18N_SCRIPT = (
    "<script>"
    "const I18N={es:{nav_home:'Inicio',nav_downloads:'Descargas',nav_auth:'Modo Auth',"
    "theme_dark:'Oscuro',theme_light:'Claro',theme_system:'Auto',"
    "overlay_title:'Custom Overlay Example',overlay_body:'Esta ruta es servida por un overlay de extension personalizado, no por la superficie publica predeterminada.',"
    "downloads_title:'Descargas Gestionadas',downloads_body:'Una extension personalizada podria servir descargas de paquetes branded aqui.',"
    "page_overlay:'Custom Overlay | Example',page_downloads:'Custom Overlay | Descargas'},"
    "en:{nav_home:'Home',nav_downloads:'Downloads',nav_auth:'Auth Mode',"
    "theme_dark:'Dark',theme_light:'Light',theme_system:'Auto',"
    "overlay_title:'Custom Overlay Example',overlay_body:'This route is served by a custom extension overlay, not the default public web surface.',"
    "downloads_title:'Managed Downloads',downloads_body:'A custom extension could serve branded bundle downloads here.',"
    "page_overlay:'Custom Overlay | Example',page_downloads:'Custom Overlay | Downloads'}};"
    "let curLang=localStorage.getItem('acp_overlay_lang')||'es';"
    "let curTheme=localStorage.getItem('acp_overlay_theme')||'system';"
    "function t(k){return(I18N[curLang]&&I18N[curLang][k])||I18N.es[k]||k;}"
    "function applyI18n(){"
    "document.documentElement.lang=curLang;"
    "const pg=document.documentElement.dataset.page;if(pg){document.title=t(pg);}"
    "document.querySelectorAll('[data-i18n]').forEach(n=>{n.textContent=t(n.dataset.i18n);});"
    "document.querySelectorAll('[data-i18n-title]').forEach(n=>{n.title=t(n.dataset.i18nTitle);});"
    "document.querySelectorAll('.lang-btn').forEach(b=>{b.classList.toggle('active',b.dataset.lang===curLang);});"
    "document.querySelectorAll('.theme-btn').forEach(b=>{b.classList.toggle('active',b.dataset.theme===curTheme);});"
    "}"
    "function setLang(l){curLang=l==='en'?'en':'es';localStorage.setItem('acp_overlay_lang',curLang);applyI18n();}"
    "function setTheme(th){curTheme=th==='light'?'light':(th==='system'?'system':'dark');"
    "localStorage.setItem('acp_overlay_theme',curTheme);document.documentElement.dataset.theme=curTheme;applyI18n();}"
    "applyI18n();setTheme(curTheme);"
    "</script>"
)


def _lang_toggle() -> str:
    return (
        "<div class='lang-toggle'>"
        "<button class='lang-btn active' data-lang='es' onclick=\"setLang('es')\" type='button'>ES</button>"
        "<button class='lang-btn' data-lang='en' onclick=\"setLang('en')\" type='button'>EN</button>"
        "</div>"
    )


def _theme_toggle() -> str:
    return (
        "<div class='theme-toggle'>"
        "<button class='theme-btn' data-theme='dark' data-i18n='theme_dark' onclick=\"setTheme('dark')\" type='button'>Dark</button>"
        "<button class='theme-btn' data-theme='light' data-i18n='theme_light' onclick=\"setTheme('light')\" type='button'>Light</button>"
        "<button class='theme-btn active' data-theme='system' data-i18n='theme_system' onclick=\"setTheme('system')\" type='button'>Auto</button>"
        "</div>"
    )


def create_overlay_example_app() -> FastAPI:
    """Build an app that reuses the core hub while replacing the public web surface."""

    runtime = HubRuntime(public_web_enabled=False)
    app = create_app(runtime=runtime)

    @app.get("/", response_class=HTMLResponse)
    async def managed_home() -> HTMLResponse:
        return HTMLResponse(
            content=(
                "<!doctype html>"
                '<html lang="es" data-theme="system" data-page="page_overlay">'
                "<head>"
                '<meta charset="utf-8" />'
                '<meta name="viewport" content="width=device-width, initial-scale=1" />'
                "<title>Custom Overlay Example</title>"
                '<link rel="preconnect" href="https://fonts.googleapis.com" />'
                '<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin />'
                '<link href="https://fonts.googleapis.com/css2?family=Outfit:wght@400;500;600;700;800&display=swap" rel="stylesheet" />'
                f"{_OVERLAY_COMMON_STYLE}"
                "</head>"
                "<body>"
                '<div class="wrap">'
                '<header class="nav">'
                '<div class="brand"><span class="mark"></span><span>ACP Managed</span></div>'
                '<div class="nav-links">'
                '<a href="/" data-i18n="nav_home">Inicio</a>'
                '<a href="/downloads" data-i18n="nav_downloads">Descargas</a>'
                '<a href="/managed/login" data-i18n="nav_auth">Modo Auth</a>'
                "</div>"
                '<div class="control-cluster">'
                f"{_lang_toggle()}"
                f"{_theme_toggle()}"
                "</div>"
                "</header>"
                '<div class="panel">'
                '<h1 data-i18n="overlay_title">Custom Overlay Example</h1>'
                '<p data-i18n="overlay_body">Esta ruta es servida por un overlay de extension personalizado, no por la superficie publica predeterminada.</p>'
                "</div>"
                "</div>"
                f"{_OVERLAY_I18N_SCRIPT}"
                "</body></html>"
            )
        )

    @app.get("/downloads", response_class=HTMLResponse)
    async def managed_downloads() -> HTMLResponse:
        return HTMLResponse(
            content=(
                "<!doctype html>"
                '<html lang="es" data-theme="system" data-page="page_downloads">'
                "<head>"
                '<meta charset="utf-8" />'
                '<meta name="viewport" content="width=device-width, initial-scale=1" />'
                "<title>ACP Managed Downloads</title>"
                '<link rel="preconnect" href="https://fonts.googleapis.com" />'
                '<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin />'
                '<link href="https://fonts.googleapis.com/css2?family=Outfit:wght@400;500;600;700;800&display=swap" rel="stylesheet" />'
                f"{_OVERLAY_COMMON_STYLE}"
                "</head>"
                "<body>"
                '<div class="wrap">'
                '<header class="nav">'
                '<div class="brand"><span class="mark"></span><span>ACP Managed</span></div>'
                '<div class="nav-links">'
                '<a href="/" data-i18n="nav_home">Inicio</a>'
                '<a href="/downloads" data-i18n="nav_downloads">Descargas</a>'
                '<a href="/managed/login" data-i18n="nav_auth">Modo Auth</a>'
                "</div>"
                '<div class="control-cluster">'
                f"{_lang_toggle()}"
                f"{_theme_toggle()}"
                "</div>"
                "</header>"
                '<div class="panel">'
                '<h1 data-i18n="downloads_title">Descargas Gestionadas</h1>'
                '<p data-i18n="downloads_body">Una extension personalizada podria servir descargas de paquetes branded aqui.</p>'
                "</div>"
                "</div>"
                f"{_OVERLAY_I18N_SCRIPT}"
                "</body></html>"
            )
        )

    @app.get("/managed/auth/mode")
    async def managed_auth_mode() -> JSONResponse:
        return JSONResponse({"mode": "overlay", "public_web_enabled": False})

    return app
