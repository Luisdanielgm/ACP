# Handoff — Réplica de mockups "SALA ACP" en la sala viva del hub

> Documento de traspaso para el próximo agente. Estado a 2026-07-12.
> Repo: `acp-public` · rama `main` · **todo commiteado y pusheado** (HEAD `5f86998`, en sync con `origin/main`).

---

## 1. Objetivo global (no perder de vista)

Replicar los mockups de referencia **"SALA ACP / Coordinación y Control de Agentes"** dentro de la
**sala en vivo del managed-app**, pero **adaptando SOLO a datos reales**. Regla dura del usuario,
repetida muchas veces:

> **"No vamos a inventar cosas que no tenemos."**

Toda métrica/estado mostrado debe salir del backend real. Prohibido inventar contadores, KPIs o
estados que no existan en el snapshot de coordinación.

### Decisiones ya tomadas por el usuario (respetarlas)
- **Paleta CÁLIDA**, NO el cian/verde oscuro de los mockups. El cian fue rechazado en sesión previa.
  Se copia **layout + assets** de los mockups, pero con la paleta cálida editorial del sistema.
- **Alcance**: sala managed + el **SquadMap compartido** (que también fluye al dashboard público).
- Idiomas: la UI se traduce a español cuando `locale === 'es'` (Chief→Jefe, Operations Manager→Gerente
  de Personal, etc.). Los identificadores/código/labels internos siguen en inglés.
- Todo debe **caber en UNA ventana sin scroll de página** (scrolls internos sí, dentro de paneles).

---

## 2. Arquitectura relevante

- **Monorepo Vue 3**: `apps/hub/frontend/packages/{shared, public-app, managed-app}`.
  - `managed-app` consume el **código fuente** de `public-app` vía alias Vite `@acp/public-app`
    (ver `apps/hub/frontend/packages/managed-app/vite.config.ts`). Por eso editar un componente en
    `public-app` afecta también al managed.
- **Backend**: Python FastAPI + SQLite en `apps/hub/src` (`acp/hub` + `acp_managed`).
- **Deployment**: Docker (el `apps/hub/Dockerfile` **construye el frontend dentro de la imagen** y
  copia `dist` a `./static/public` y `./static/managed`). Cambios de frontend requieren
  **rebuild de la imagen**. Delante hay **Cloudflare**.

### Cómo validar (⚠️ NO hay test runner de frontend)
- Frontend: `npx vue-tsc --noEmit` en `public-app` + `npm run build --workspace=packages/managed-app`.
  Ambos deben salir verdes. No existe vitest; NO agregarlo (evitar scope creep).
- Backend: **TDD estricto con pytest**. `python -m pytest tests/hub -q` (última corrida: 341 passed, 3 skipped).
- **Screenshots del browser están rotos en este entorno** (timeout). Auditá geometría vía
  `javascript_tool` si hace falta; el usuario revisa haciendo rebuild de Docker.

---

## 3. Qué se construyó (todo commiteado)

### Pipeline de assets
- `apps/hub/frontend/packages/public-app/src/assets/acp/acpAssets.ts`
  - Mapas de URL con `import.meta.glob(..., { eager:true, query:'?url', import:'default' })`
    (funcionan en ambos build roots).
  - Exporta `avatarUrl(id,size)`, `stateIconUrl(name)`, `objectUrl(id,size)`, `AVATAR_LEADER`,
    `AVATAR_HUMAN`, `ROBOT_AVATAR_IDS`, `CROWN_URL`.
  - Assets originales del usuario en `a local design-assets directory`
    (20 avatares, 31 iconos de estado SVG, 12 objetos/orbes/corona + manifests JSON).
  - **Recoloreados** a teal por un script scratchpad `build_assets.py` (hue verde 120–190 con
    sat>0.22 → teal hue 157; `#42e59e`→`#59cea1`) para que peguen con la paleta cálida.

### Helpers puros (dirigidos por datos reales) — `public-app/src/composables/sessionHelpers.ts`
- `agentDisplayNames(names[])`: nombres legibles token-based (quita tokens comunes a TODOS los
  nombres + tokens de marca por prefijo ≥4 chars; con guardas anti-duplicado). Reemplazó al viejo
  prefix-stripping que fallaba porque los nombres derivan ("project-" vs "aero-").
- `humanizeAgentName`, `avatarForMember` (chief→leader, web-operator→human, matchers de dominio por
  keyword → avatar temático, si no name-hash robot; regexes con word-boundaries para no matchear mal
  "example"/"analyst").
- `linkFreshness`, `heartbeatTier`/`heartbeatIconName`, `presenceIconName`, `operationIconName`,
  `messageIconNameForEvent` (incluye error/broadcast/heartbeat), `resultIconNameForEvent`.
- Traducción: `public-app/src/composables/dashboardTranslations.ts` → `translateDisplayName(locale, label)`
  con `ES_PHRASES` y `ES_WORDS`. Solo traduce si `locale === 'es'`.

### Componentes (centro del trabajo)
- **`public-app/src/components/dashboard/SquadMap.vue`** (el más grande):
  - Avatares que **LLENAN el marco** (`coreR = shellR - 3*scale`), tamaño adaptativo por crowd.
  - Canvas adaptativo que abraza la órbita ocupada; pisos de radio de órbita para 2 agentes.
  - Corona (`<image :href="crownUrl">`), badge de presencia (arriba-der) + operación (abajo-der),
    pill de estado bajo el nombre, línea de heartbeat ("hace 10s"), barra de cola (queue) por pendientes.
  - Edges persistentes del jefe; **flechas de dirección** vía `<marker>`; **orbe de tipo de mensaje**
    a mitad de cable (`objectUrl(edgeOrb,128)`); edges recortados a los bordes de los shells.
  - **Broadcast fan-out** (target 'all' → 6 destinos); tags de vuelo a 2 líneas.
  - Form inline de **envío** (`SEND_ACTIONS`, emite `send-message`) e **inbox** inline
    (`receiveInbox` prop, `readInbox`). Popover con avatar real + nombre humano + nombre completo.
  - Botón de expandir in-canvas; prop `fitHeight` para llenar altura.
- **`public-app/src/components/dashboard/MemberLanes.vue`** (carriles estilo mockup):
  - `.lane` = `.lane-id` (avatar + nombre/rol-pill + op-chip/provider) + `.lane-cells` (3 cajitas:
    Pendientes / Último evento / Tarea actual) + `.lane-kick`.
  - **Layout con flex proporcional** (fix clave): `.lane-id{flex:1 1 42%; min-width:150px}`,
    `.lane-cells{flex:1 1 58%}`, `.lane-cell{flex:1; min-width:0}` + ellipsis, `.task-cell{flex:1.6}`.
    Esto arregló el bug donde las celdas de ancho fijo colapsaban el nombre y los pills se
    superponían con "PENDIENTES".
- **`public-app/src/components/dashboard/EventTimeline.vue`**: iconos de tipo + resultado junto a la hora.
- **`managed-app/src/components/room/RoomLive.vue`**: grid cockpit
  (`minmax(0,1.5fr) minmax(380px,1fr)`); columna izquierda = SquadMap + feed-strip (EventTimeline);
  columna derecha = UN panel (MemberLanes con scroll + leyenda fijada abajo). Sidebar colapsado por
  defecto, reloj en vivo, sparkline de actividad, chips.
- **`managed-app/src/views/SessionRoomView.vue`**: `.room-page { max-width:1760px; margin:12px auto }`.

### Chief inbox (backend + frontend, TDD)
- `managed-app/src/components/room/RoomOperatorPanel.vue`: "Bandeja del agente" (Recibir + Escuchar poll 5s + reply).
- `managed-app/src/api/managed.ts`: `receiveSessionOperatorMessage`, tipos `OperatorInboxMessage`,
  `ReceiveSessionOperatorMessageResult`.
- Backend: `POST /managed/workspaces/{slug}/sessions/{session_id}/operator/receive`
  (`acp_managed/routing/workspace_admin.py`), contrato en `acp_managed/contracts.py`
  (`ReceiveRoomOperatorMessageRequest`, timeout 0–20s). Tests en `tests/hub/test_web_operator.py`.
  Baseline `tests/hub/managed_routes_baseline.json` regenerado.

### Último fix de esta sesión — headers de cache SPA (commit `5f86998`) ✅
**Problema**: usuario vio sala managed en blanco: `index-*.js` (200) intentaba precargar
`SessionDashboardView-*.css` → **404 persistente** incluso tras hard refresh.
**Diagnóstico (con curl al server real)**: el ORIGIN estaba sano (JS+CSS ambos 200, mismo build).
El 404 era **cacheado**: hay **Cloudflare** adelante, el hub servía los assets hasheados **sin
`Cache-Control`** (CF aplicaba su default de 4h) e `index.html` sin revalidación. Como
`emptyOutDir:true` borra el build viejo un instante en cada deploy, un 404 de ese hueco se cacheaba.
**Fix aplicado (ambas superficies SPA)**:
- `index.html` → `Cache-Control: no-cache` (siempre revalida el shell).
- assets hasheados → `public, max-age=31536000, immutable` vía subclase `_ImmutableStaticFiles`.
- Archivos: `apps/hub/src/acp_managed/ui/spa.py`, `apps/hub/src/acp/hub/app.py`.
- Tests: `tests/hub/test_managed_spa_fallback.py::test_managed_spa_and_assets_send_correct_cache_headers`
  y `tests/hub/test_public_spa_cache_headers.py` (2 unit tests). Suite verde.
- ⚠️ **El fix NO purga el 404 ya cacheado**: el usuario debe hacer **Cloudflare → Purge Everything**
  una vez + hard refresh para desbloquear el estado actual.

---

## 4. Estado de git
- Rama `main`, **en sync con `origin/main`**, working tree limpio.
- Todo el trabajo (UI + backend + cache fix) está commiteado y pusheado. No hay pendientes de commit.

---

## 5. Próximos pasos / pendientes

1. **Cloudflare purge** (acción del usuario, no de código): purgar cache para limpiar el 404 pegado.
2. El usuario iba a pasar **más mockups de "carriles de operación"** de las otras vistas para sacar
   ideas. Idea ya conversada: columna **"No leídos" → mapear a mensajes `queued`** (honesto, dato real).
3. Decisión pendiente: ¿el toggle **"Escuchar"** del operator inbox debería venir **ON por defecto**?
4. Idea a medias: una **tira de carriles más pequeños bajo el mapa** para "apertura de sesiones,
   mensajes, espera, estados detallados". Hoy está el feed-strip (EventTimeline); podría querer más.
5. Diferido backend (no bloqueante): afinar índice de lease (migración 0008) y test de regresión de
   lease MAJOR-1.

---

## 6. Estilo de trabajo esperado por el usuario
- Español rioplatense en las respuestas; inglés en código/UI/artefactos.
- **Nunca** agregar "Co-Authored-By"/atribución AI a commits. Conventional commits.
- Commits directos a `main` (sin ramas), pero **confirmar antes de commitear**.
- No inventar datos. Preguntar de a una cosa. Verificar antes de afirmar.
- Empujar de vuelta cuando algo se puede hacer mejor, con el porqué técnico.
