# ACP Agent Release Checklist

Esta guia es obligatoria cuando cambie cualquiera de estas piezas:

- `ACP_AGENT/acp.py`
- `ACP_AGENT/update_from_release.py`
- `ACP_AGENT/install_from_bundle.py`
- `ACP_AGENT/AGENT.md`
- `ACP_AGENT/skills/acp-session-coordinator/SKILL.md`
- `.codex/skills/acp-session-coordinator/SKILL.md`
- `apps/hub/frontend/packages/public-app/src/views/LandingView.vue`
- `apps/hub/frontend/packages/public-app/src/views/DownloadsView.vue`
- `apps/hub/frontend/packages/public-app/index.html`
- `apps/hub/frontend/packages/managed-app/index.html`
- `apps/hub/src/acp/hub/app.py`
- `apps/hub/src/acp/hub/bundle_release.py`

## Regla no negociable

No publicar cambios de ACP sin revisar si tambien deben cambiar:

- `ACP_AGENT/VERSION`
- `ACP_AGENT/CHANGELOG.md`
- `ACP_AGENT/AGENT.md`
- `ACP_AGENT/skills/acp-session-coordinator/SKILL.md`
- `.codex/skills/acp-session-coordinator/SKILL.md`
- `apps/hub/downloads/ACP_AGENT.zip`
- landing, downloads y fallback HTML sin JavaScript
- manifest y rutas publicas de descubrimiento

Si el cambio altera bootstrap, discovery, update, links de dashboard, manifest, nombres de comandos, o textos que un humano/agente usaria para instalarse o actualizarse, entonces todas esas superficies deben actualizarse en el mismo cambio.

## Checklist minima de release

1. Subir `ACP_AGENT/VERSION`.
2. Agregar una entrada nueva en `ACP_AGENT/CHANGELOG.md`.
3. Si cambio el flujo de uso, bootstrap o update:
- actualizar `ACP_AGENT/AGENT.md`
- actualizar `ACP_AGENT/skills/acp-session-coordinator/SKILL.md`
- actualizar `.codex/skills/acp-session-coordinator/SKILL.md`
4. Si cambio discovery publico, landing, downloads o bootstrap para scrapers/agentes:
- revisar `apps/hub/frontend/packages/public-app/src/views/LandingView.vue`
- revisar `apps/hub/frontend/packages/public-app/src/views/DownloadsView.vue`
- revisar `apps/hub/frontend/packages/public-app/index.html`
- revisar `apps/hub/frontend/packages/managed-app/index.html`
- revisar `apps/hub/src/acp/hub/app.py`
- revisar `apps/hub/src/acp/hub/bundle_release.py`
5. Regenerar o verificar `apps/hub/downloads/ACP_AGENT.zip`.
6. Confirmar que el bundle instalado siga copiando o preservando la documentacion nueva que se agregue.
7. Verificar que el updater siga refrescando la skill del proyecto y la skill global.

## Validacion minima antes de publicar

Ejecutar segun corresponda:

```powershell
python -m compileall ACP_AGENT apps/hub/src/acp/hub apps/hub/src/acp_managed
npm run build --workspace=packages/public-app
npm run build --workspace=packages/managed-app
python ACP_AGENT/update_from_release.py --check
```

Si el bundle o el manifest cambiaron, regenerar el ZIP y validar las superficies publicas:

```powershell
python -c "from acp.hub.bundle_archive import ensure_bundle_archive; print(ensure_bundle_archive())"
python -c "from acp.hub.bundle_release import build_bundle_release; import json; print(json.dumps(build_bundle_release(base_url='https://YOUR_HOST'), indent=2))"
```

## Endpoints y archivos que deben quedar coherentes

Cuando la distribucion hosted este activa, verificar:

- `/downloads/ACP_AGENT.zip`
- `/downloads/ACP_AGENT.json`
- `/downloads/ACP_AGENT/AGENT.md`
- `/downloads/ACP_AGENT/skills/acp-session-coordinator/SKILL.md`
- `/downloads`
- `/runtime`
- `/health`

El `VERSION`, el changelog, el manifest, el ZIP y la pagina de descargas deben describir la misma release.

## Protocolo para agentes cuando se les pida buscar updates

Si un agente recibe instrucciones como "busca actualizaciones", "actualizate", "revisa si ACP esta al dia" o "actualiza la skill ACP", debe:

1. leer `ACP_AGENT/BUNDLE_INFO.json` si existe
2. leer `ACP_AGENT/DISTRIBUTION.json`
3. leer `ACP_AGENT/AGENT.md`
4. comparar version local con:

```powershell
python ACP_AGENT/update_from_release.py --check
```

5. si la salida dice `update_available`, o si el usuario pidio forzar la actualizacion, ejecutar:

```powershell
python ACP_AGENT/update_from_release.py
```

6. despues de actualizar, volver a leer:
- `ACP_AGENT/VERSION`
- `ACP_AGENT/CHANGELOG.md`
- `ACP_AGENT/AGENT.md`
- `ACP_AGENT/RELEASE_CHECKLIST.md`
- `ACP_AGENT/skills/acp-session-coordinator/SKILL.md`
- `.codex/skills/acp-session-coordinator/SKILL.md`
- `~/.codex/skills/acp-session-coordinator/SKILL.md` si existe

7. usar las instrucciones nuevas del bundle actualizado y no seguir obedeciendo copias viejas.

## Si el proyecto es muy viejo

Si no existe `ACP_AGENT/update_from_release.py`, el agente debe:

1. revisar `ACP_AGENT/DISTRIBUTION.json`
2. localizar el manifest o la pagina oficial de downloads de esa distribucion
3. descargar el ZIP correcto
4. reemplazar el core del bundle preservando:
- `ACP_AGENT/agents/`
- `ACP_AGENT/inbox/`
- `ACP_AGENT/outbox/`
- `ACP_AGENT/sent/`
5. refrescar la skill local y la global

## Criterio de cierre

Una actualizacion solo se considera completa si:

- el cliente ACP funciona
- la skill local y global quedaron alineadas
- `VERSION` y changelog describen lo nuevo
- el ZIP publicado corresponde al contenido real del bundle
- landing y downloads explican correctamente la release actual
- un humano y un agente sin JavaScript pueden descubrir por donde empezar
