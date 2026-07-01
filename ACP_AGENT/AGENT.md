# ACP Agent Bootstrap

Si un agente encuentra esta carpeta dentro de un proyecto, debe tratarla como la carpeta operativa de ACP para ese proyecto.

## Objetivo

Usar una sola carpeta copiada al proyecto para resolver todo:

1. instalar la skill global `acp-session-coordinator`
2. instalar la dependencia Python `websockets` desde `ACP_AGENT/requirements.txt`
3. configurar el bridge local del proyecto
4. dejar los configs y colas del proyecto listos
5. operar sesiones ACP usando el hub por defecto definido por el bundle, o un hub propio si el usuario lo pide
6. poder comparar y actualizar esta carpeta contra la release asociada a este bundle sin perder estado local

## Default del bundle

El bundle puede traer un hub por defecto y un manifest de release por defecto.

Revisar estos valores en:

- `ACP_AGENT/DISTRIBUTION.json`

Si el bundle define `default_hub_mode = official`, usar ese hub por defecto.
Si el bundle define `default_hub_mode = explicit`, pedir `hub_http` y `hub_ws`.

## Inicio rapido con un ACP workspace del cliente

Si el humano te da una URL de workspace ACP, por ejemplo `https://acp.aerocostos.com`, tratala como `hub_http`.

Datos minimos para un agente:

- `hub_http`: URL publica del ACP workspace del cliente, sin ruta extra. Ejemplo: `https://acp.aerocostos.com`
- `agent-token`: token del workspace emitido desde el dashboard ACP del cliente.
- `agent`: nombre unico para este proceso/config. Ejemplo: `codex-chief`, `worker-1`, `claude-review`.
- `project`: identificador de proyecto/sala cuando el flujo managed lo pida.

Comandos recomendados:

```powershell
python ACP_AGENT/acp.py health --hub-http https://acp.aerocostos.com
python ACP_AGENT/acp.py managed-sessions --hub-http https://acp.aerocostos.com --agent-token TOKEN
python ACP_AGENT/acp.py coordinate --agent worker-1 --hub-http https://acp.aerocostos.com --agent-token TOKEN --project PROJECT_ID
```

Si solo tenes la URL y no tenes token, no inventes credenciales: pedile al humano el workspace token o que lo rote/copie desde el dashboard del ACP workspace.

## Que debe hacer el agente

1. Localizar esta carpeta.
2. Verificar si la skill global `acp-session-coordinator` ya existe para el host del agente: `~/.codex/skills/acp-session-coordinator` para Codex y `~/.claude/skills/acp-session-coordinator` para Claude Code.
3. Si la skill no existe en el host actual, instalarla desde esta misma carpeta. El instalador por defecto sincroniza ambas ubicaciones cuando no se usa `--skill-home`.
4. Verificar si el entorno Python ya tiene la dependencia del bridge:
- `python -m pip install -r ACP_AGENT/requirements.txt`
5. Verificar si esta carpeta ya esta inicializada. Deben existir al menos:
- `ACP_AGENT/agents/`
- `ACP_AGENT/inbox/`
- `ACP_AGENT/outbox/`
- `ACP_AGENT/sent/`
6. Si falta inicializacion o faltan configs, pedir solo los datos que falten en este orden:
- si el bundle define un hub hosted por defecto, preguntar si usara ese hub o uno propio
- si el bundle esta en modo `explicit`, pedir directamente `hub_http` y `hub_ws`
- si usa hub propio: `hub_http` y `hub_ws`
- nombre(s) de agente a crear
- token ACP si existe
7. Ejecutar el instalador local sobre esta misma carpeta. Si el bundle trae un hub hosted por defecto y va a usarlo, no necesita pasar URLs:

```powershell
python ACP_AGENT/install_from_bundle.py --force
```

o, si ya conoce el agente:

```powershell
python ACP_AGENT/install_from_bundle.py --agent codex-chief --force
```

o, si usara un hub propio:

```powershell
python ACP_AGENT/install_from_bundle.py --hub-mode custom --hub-http https://TU_HUB --hub-ws wss://TU_HUB/ws --agent codex-chief --force
```

Para entornos sin TTY/headless, no debe depender de prompts. Usar flags completos y `--non-interactive`:

```powershell
python ACP_AGENT/acp.py init --hub-mode custom --hub-http https://TU_HUB --agent codex-chief --non-interactive --force
```

Si solo se pasa `--hub-http`, el instalador deriva `hub_ws` como `/ws` (`https` -> `wss`, `http` -> `ws`). `--hub-mode official` tambien acepta `--hub-http/--hub-ws` explicitos cuando el bundle no trae un hosted hub embebido.

8. Confirmar que quedaron:
- `ACP_AGENT/acp.py`
- `ACP_AGENT/requirements.txt`
- `ACP_AGENT/VERSION`
- `ACP_AGENT/CHANGELOG.md`
- `ACP_AGENT/RELEASE_CHECKLIST.md`
- `ACP_AGENT/update_from_release.py`
- `ACP_AGENT/BUNDLE_INFO.json`
- `ACP_AGENT/agents/*.json`
- skill global en `~/.codex/skills/acp-session-coordinator` y, para Claude Code, `~/.claude/skills/acp-session-coordinator`
- dependencia `websockets` instalada en el entorno Python del agente
9. A partir de ahi, usar la skill y los comandos ACP desde esta carpeta:
- `init`
- `start`
- `join`
- `task`
- `reply`
- `create-session`
- `join-session`
- `wait`
- `cancel-wait`
- `wait-window`
- `listen`
- `send`
- `status`
- `session-info`
- `leave-session`
10. El wrapper local `ACP_AGENT/acp.py` cubre el flujo operativo principal, pero el Hub expone mas contexto operativo que el agente puede consultar si lo necesita por HTTP directo. Ademas de `session-info`, recordar estas superficies:
- `GET /health`
- `GET /agents`
- `GET /dashboard/overview`
- `GET /sessions/{session_id}`
- `GET /sessions/{session_id}/detail`
- `GET /replay/events`
- `GET /replay/messages/{message_id}`
11. Ese contexto extra sirve para inspeccionar:
- snapshot de sesion
- detalle de sesion
- miembros y estados
- historial de sesion
- overview global
- replay de eventos
- timeline de un mensaje
- lista de agentes conectados
- salud del Hub
12. Cuando cree o se una a una sesion, no debe limitarse a dar solo el `join_code`. Debe comunicar tambien:
- `session_id`
- `hub_http`
- `hub_ws` si existe
- `session_dashboard_url` propio
- `current_member_dashboard_url` como alias directo listo para pegar en chat
- `session_dashboard_url_template` para otros miembros
- `shareable_dashboard_url_template` como alias explicito del link plantilla a compartir
- `shareable_session_access` con los datos y comandos de acceso
12.1. Si el flujo es managed, el link compartible debe apuntar a `/managed/dashboard/session`; si es una sesion core normal, debe usar la ruta configurada para el dashboard core.
13. Cuando empiece el flujo de sesion, preguntar lo minimo segun el caso:
- si sera jefe o colaborador
- si es jefe: titulo/proyecto de la sesion si hacen falta
- si es colaborador core: `join_code`
- si es colaborador managed: `session_id` + agent-token de workspace; no usar `join-session --code` con agent-token managed
- si el Hub requiere token ACP y no esta configurado
14. Si crea la sesion, ejecutar `create-session`, guardar `session_id`, `member_token`, `join_code` y `member_role` en el config, y dejar publicado `waiting` de inmediato.
15. Si se une a una sesion core, ejecutar `join-session`, guardar `session_id`, `member_token`, `join_code` y `member_role` en el config, y dejar publicado `waiting` de inmediato. Si se une a una sesion managed, ejecutar `managed-join --agent-token TOKEN --session-id SESSION_ID --no-listen`; `join-session --code` usa auth core y puede devolver 401 con un agent-token managed valido.
16. Despues de `create-session` o `join-session`, elegir el modo correcto de escucha segun el tipo de agente. Si sos un agente LLM turn-based que tambien ejecuta trabajo, NO te quedes en `managed-join` ni `listen` persistente porque el proceso no devuelve el control al LLM. `managed-join` debe usarse para attach inicial + guardar config + salir. Usar el loop de un mensaje:

```powershell
python ACP_AGENT/acp.py listen --config ACP_AGENT/agents/<agent>.json --stop-after-message --timeout-seconds 300
```

Recibir un mensaje, trabajar, responder con `send`/`reply`, publicar `waiting`, y volver a ejecutar el mismo `listen --stop-after-message`. Si el agente debe quedar siempre disponible sin que el humano lo despierte, el default correcto es `runner start`. `listen` persistente queda reservado para consumidores/daemons externos no-LLM que pueden bloquearse sin congelar el razonamiento del agente.

16.1. Para flujo humano rapido, preferir los atajos:
- `python ACP_AGENT/acp.py start --agent codex-chief --title "Short task"`
- `python ACP_AGENT/acp.py join --agent claude-review ABC123`
- `python ACP_AGENT/acp.py managed-start --agent codex-chief --agent-token TOKEN --title "Short task"`
- `python ACP_AGENT/acp.py managed-join --agent claude-review --agent-token TOKEN --session-id SESSION_ID`
- `python ACP_AGENT/acp.py listen --agent claude-review --stop-after-message --timeout-seconds 300`
- `python ACP_AGENT/acp.py cancel-wait --agent claude-review`
- `python ACP_AGENT/acp.py managed-close --agent codex-chief --agent-token TOKEN --session-id SESSION_ID`
- `python ACP_AGENT/acp.py task --agent codex-chief --to claude-review "Revisa auth"`
- `python ACP_AGENT/acp.py reply --agent claude-review --to codex-chief "Listo"`
16.2. Si en `ACP_AGENT/agents/` existe un solo config, los comandos pueden omitir `--config` y `--agent`.
16.3. En flujo managed, el token ahora puede autodetectar el workspace. `--workspace` queda como compatibilidad para hubs viejos o debugging, pero ya no debe ser un requisito operativo normal.
17. En operacion ACP continua, publicar `waiting` cuando el agente este disponible y escuchando; no publicar `idle` mientras siga operativo. Para agentes interactivos, la escucha continua se implementa como loop de `listen --stop-after-message`; para daemons LLM always-on, usar `runner start`; para consumidores externos no-LLM, se puede usar `listen` persistente.
18. `wait` queda reservado para una espera foreground de una sola entrega. Para la politica operativa por defecto, usar `wait-window`: si acaba de cerrar una tarea y se espera otra instruccion inmediata, o si el siguiente paso depende de una decision/instruccion externa despues de enviar el `REPLY` y actualizar `status`, abrir de inmediato una ventana activa de hasta **20 minutos** con `python ACP_AGENT/acp.py wait-window --config ACP_AGENT/agents/<agent>.json --window-minutes 20`. Esa espera externa cuenta como parte del cierre operativo. Internamente la ventana encadena long-polls de hasta **300 segundos**. Si no llega nada en esa ventana, publicar `waiting`; si necesita disponibilidad real sin humano, pasar a `runner start`.
19. `idle` solo debe usarse si el agente quedo realmente desacoplado de ACP o si la sesion termino. En una sesion viva, `waiting` + `listen` es el estado operativo correcto.
20. Si el Hub fue reiniciado o redeployado y la sesion deja de existir, no debe insistir con tokens viejos. Debe informar que la sesion murio y pedir o crear una sesion nueva.
21. Nunca reutilizar el config del jefe para entrar como colaborador, ni reutilizar el config de un colaborador para otra identidad. Si un config sigue ligado a una sesion viva, `create-session` y `join-session` deben fallar y obligar a usar otro config o `leave-session`.
22. En sesiones creadas desde workspaces managed, si un nombre comun como `codex-chief` o `claude-chief` ya esta ocupado por otra sesion activa, el sistema puede resolverlo con un nombre efectivo unico ligado al workspace en lugar de fallar en silencio. El agente debe reportar el nombre efectivo que quedo asignado.
23. En REST `/sessions/send`, `to: "all"` y `to: "*"` son broadcast a los otros miembros de la sala; el emisor queda excluido a proposito.

## Do / Don't de mensajeria y ejecucion

DO:

- usar un `agent_name` unico por proceso/config
- usar `managed-join` solo para unirse/guardar credenciales y salir
- turn-based executor: `listen --stop-after-message --timeout-seconds 300` -> trabajar -> `send --action REPLY|INFO` -> volver a escuchar
- daemon/always-on LLM: `runner start`; consumidor externo no-LLM: `listen` persistente
- setear `status waiting` cuando estas disponible y `status busy` cuando ejecutas
- respetar el file boundary/tarea asignada por el chief

DON'T:

- no reutilizar un `agent_name` en dos sesiones vivas
- no dejar un agente LLM executor bloqueado en `managed-join` o `listen` persistente
- no correr dos waits/listens concurrentes con el mismo `agent_name` y `member_token`
- no mandar contenido fuera de `payload`; `action` debe ser `TASK`, `REPLY` o `INFO`
- no asumir contratos no pineados por el chief

## Atajos compuestos (usar primero)

Antes de encadenar `create-session` / `join-session` / `status` / `send` a mano,
usa un comando compuesto: cada uno es UNA sola llamada que colapsa ~5 round-trips,
persiste las credenciales en config y te deja listo para trabajar. Despues, nunca
re-pases `session_id` ni `member_token`: se cargan solos desde config.

- worker turn-based en sesion managed: `coordinate --agent <agent> --agent-token <ACPAGT_TOKEN> --hub-http https://YOUR_HUB --project <project>` (bootstrap + match + join + READY al chief + waiting + espera un mensaje y sale).
- worker always-on en sesion managed por proyecto: `onboard --agent <agent> --agent-token <ACPAGT_TOKEN> --hub-http https://YOUR_HUB --project <project>` (bootstrap + match + join + READY al chief + waiting + prep runner).
- no sabes si sos worker o chief: `connect --role auto` infiere el rol.
- chief crea sesion: `managed-start --agent <agent> --agent-token <ACPAGT_TOKEN> --hub-http https://YOUR_HUB --title "..." --no-listen` (sin `--no-listen` entra en listen persistente y se bloquea).
- ya tenes session-id + member-token: `attach-session --session-id <id> --member-token <token> --no-listen`.

Tras conectar, el turno worker es `coordinate ...` la primera vez, o `listen --stop-after-message --timeout-seconds 300` si ya tenes config -> trabajar -> `reply --to <chief> "..."` (agrega `--agent <agent>` solo si hay mas de un config).

## Primitivas de escucha

| Primitiva | Uso correcto | No usar para |
| --- | --- | --- |
| `join-session --code` | Sesion core/no-managed con join code. | Sesion managed con agent-token de workspace. |
| `managed-join` | Attach inicial managed, guardar `session_id`/`member_token`, salir. | Escuchar tareas en un agente turn-based. |
| `listen --stop-after-message --timeout-seconds 300` | Loop canonico de recepcion para agentes que razonan y ejecutan. | Daemon permanente sin supervisor. |
| `wait` | Espera foreground de una sola entrega. | Mantener un agente conectado en paralelo con otro wait/listen. |
| `cancel-wait` | Limpiar un wait/listen activo o zombie del mismo miembro antes de reintentar. | Cancelar waits de otros miembros o reemplazar `leave-session`. |
| `listen` persistente | Listener/daemon externo que puede bloquearse sin congelar al LLM. | Agente LLM que necesita actuar despues de recibir. |
| `runner start` | Default para worker/chief always-on que spawnea el provider local por cada TASK. | Turno interactivo manual. |

Mapa de modelos:

| Modelo | Receptor | Uso correcto |
| --- | --- | --- |
| LLM turn-based interactivo | `managed-join --no-listen` o `join-session`, luego `listen --stop-after-message` / `wait-window` | Agentes invocados por el humano que deben recuperar control tras cada mensaje. |
| Worker/chief always-on | `runner start` | Pools de agentes y jefes reactivos que deben quedar disponibles. |
| Consumidor externo daemon | `listen` persistente | Servicio no-LLM que solo transmite/procesa eventos. |

Si `/sessions/wait` devuelve `WAIT_ALREADY_ACTIVE` o HTTP 409, ya hay un wait/listen activo para ese miembro. El error incluye `details.wait_ttl_seconds` para saber cuanto falta para que expire. Primero corta el proceso anterior (`managed-join`, `listen` o `wait`) si sigue vivo. Si quedo zombie o no controlas ese proceso, limpia tu propio wait activo:

```powershell
python ACP_AGENT/acp.py cancel-wait --config ACP_AGENT/agents/<agent>.json
```

Despues vuelve al loop canonico:

```powershell
python ACP_AGENT/acp.py listen --config ACP_AGENT/agents/<agent>.json --stop-after-message --timeout-seconds 300
```

Si el Hub ya no tiene la sesion (cerrada sin notice vivo, member token rotado, o Hub redeployado con store en memoria), `listen` no hace loop ni lanza un 403/404 opaco: sale con `status: session_ended`, limpia el `session_id`/`member_token` local y te indica volver a `create-session`/`join-session` antes de escuchar de nuevo.

Si el Hub/gateway devuelve HTTP 502/503/504, no asumir que la sesion murio. El CLI reintenta con backoff las operaciones seguras (`wait`, `status`, `heartbeat`, `session-info`). `send` no se reintenta automaticamente porque un POST de mensaje no-idempotente podria duplicar entrega si el servidor proceso el envio antes del 5xx.

`managed-sessions` y `managed-close` pueden operar sin elegir un config cuando se pasan flags puros:

```powershell
python ACP_AGENT/acp.py managed-sessions --hub-http https://TU_HUB --agent-token TOKEN
python ACP_AGENT/acp.py managed-close --hub-http https://TU_HUB --agent-token TOKEN --session-id SESSION_ID
```

Si se selecciona un config, estos comandos tambien pueden usar `managed_agent_token` guardado en ese config. `managed-start` y `managed-join` guardan ese token para que todos los agentes del workspace puedan resolver credenciales de forma simetrica sin copiar secretos entre archivos a mano.

## Onboarding autonomo de workers managed

Si no queres recordar el flujo, usa el entrypoint self-describing:

```powershell
python ACP_AGENT/acp.py coordinate --agent worker-1 --agent-token TOKEN --hub-http https://YOUR_HUB --project PROJECT_ID --workspace C:\ruta\proyecto --capabilities backend,python
python ACP_AGENT/acp.py connect --role worker --agent worker-1 --agent-token TOKEN --hub-http https://YOUR_HUB --project PROJECT_ID --workspace C:\ruta\proyecto --capabilities backend,python
```

`coordinate` es el camino corto para un worker turn-based: conecta/onboardea y espera un mensaje en una sola llamada. `connect` decide el camino operativo: como worker corre `onboard`; como chief retoma o crea la sala managed y devuelve el comando `chief start`. Si un runtime no tiene la skill instalada globalmente, eso no bloquea ACP: corre `python ACP_AGENT/acp.py onboard-help` y usa el `acp.py` del bundle + la skill bundleada como documentacion opcional. Para generar un prompt listo para otro agente, usa:

```powershell
python ACP_AGENT/acp.py invite --role worker --agent worker-1 --capabilities backend,python --session-id SESSION_ID --project PROJECT_ID
```

Para agentes always-on que solo tienen un token managed de workspace, `onboard` es el camino corto y no bloqueante:

```powershell
python ACP_AGENT/acp.py onboard --agent worker-1 --agent-token TOKEN --project PROJECT_ID --workspace C:\ruta\proyecto --capabilities backend,python
```

Hace todo el bootstrap operativo: valida el token con `/managed/agent/bootstrap`, lista las sesiones managed, encuentra la sala por `project` (o por `--session-id`), ejecuta `managed-join`, manda un `INFO` tipo `READY` al chief, publica `waiting` y deja el config preparado como `delivery_mode=runner`. Si pasas `--capabilities`, el miembro las publica en `session-info` y las reutiliza en status/heartbeat/runner.

Si hay varias salas con el mismo `project`, falla a proposito para evitar unirse a la sala equivocada; usar `--session-id` o `--prefer-latest`. Para deteccion de proyecto, prioriza `--project`, luego `.acp/project-id`, luego el nombre del root git/carpeta.

Por defecto `onboard` imprime el `runner_command` y devuelve control. Si realmente queres dejar el proceso vivo en el mismo comando, usar:

```powershell
python ACP_AGENT/acp.py onboard --agent worker-1 --agent-token TOKEN --project PROJECT_ID --workspace C:\ruta\proyecto --start-runner
```

## Chief autonomo con backlog de archivos

`chief start` mantiene al coordinador vivo, drena reportes de workers y reparte unidades desde una cola local de archivos. Es el primer chief deterministico: no inventa estrategia con LLM; toma tareas ya definidas y las manda a workers disponibles.

Estructura default:

```text
coord/backlog/
  pending/   # opcional; si existe, se usa como fuente
  assigned/
  done/
  failed/
```

Tambien acepta tareas directamente en `coord/backlog/*.task.md` si no existe `pending/`. Cada archivo `.task.md`, `.md`, `.txt` o `.json` representa una unidad. En JSON se aceptan `task_id`, `instructions`, `provider`, `workspace_path`, `metadata`, `required_capabilities`, `required_role`, `tags`, `verify_command`, `verify_timeout_seconds`, `acceptance_criteria`/`verify_prompt`, `judge_provider`, `judge_timeout_seconds` y `max_attempts`; en Markdown/texto el contenido completo son las instrucciones.

El dispatch ahora es role-aware por capacidades: si una tarea pide `required_capabilities: ["backend"]`, el chief prefiere un worker `waiting` que haya publicado `backend`. Si no hay match, cae al fallback actual y usa cualquier worker disponible para no bloquear el pool. Un worker con `current_task` no se considera disponible aunque su estado visible siga en `waiting`.

El chief despacha como maximo una tarea por worker por tick. Esto evita vaciar toda la cola en el primer worker que aparece y deja margen para que otros workers se unan o reciban tareas en el siguiente tick.

Cuando una tarea JSON define `verify_command`, el chief no confia ciegamente en un `REPLY` exitoso. Ejecuta la verificacion localmente; si falla, registra el resultado en `failed/`, reencola la tarea con feedback explicito y vuelve a despacharla. Preferi `verify_command` como lista de argumentos para evitar quoting ambiguo; el formato string se ejecuta con shell y debe usarse solo en tareas locales confiables.

Cuando una tarea define `acceptance_criteria` o `verify_prompt`, el chief ejecuta un juez LLM local despues del gate mecanico. El juez debe devolver JSON `{ "pass": true|false, "feedback": "..." }`; si rechaza, el chief reencola con feedback especifico. `max_attempts` limita los reintentos antes de mover la tarea a `failed/`.

Arranque:

```powershell
python ACP_AGENT/acp.py chief start --config ACP_AGENT/agents/codex-chief.json --backlog-dir coord/backlog --provider claude_local --workspace C:\ruta\proyecto
```

Para CI o debugging:

```powershell
python ACP_AGENT/acp.py chief once --config ACP_AGENT/agents/codex-chief.json --backlog-dir coord/backlog
```

Flujo: lee snapshot de la sala, reencola asignaciones vencidas por TTL, elige miembros `waiting` con heartbeat vivo y sin pendientes, mueve la tarea a `assigned/`, manda `TASK` con `task_id` + `reply_to`, registra replies con `task_id` (o lo infiere si el worker tiene exactamente una asignacion en vuelo), verifica si corresponde y mueve la tarea a `done/`, `failed/` o la reencola con feedback. Si el chief encuentra su propio `WAIT_ALREADY_ACTIVE`, cancela ese wait y reintenta una vez. Si no hay backlog pendiente ni dispatch nuevo, reporta `escalation: backlog_empty`.

Para tareas largas, prefija las instrucciones con `[long]` o `[busy-hold:30]`. El runner detecta ese marcador incluso dentro del payload JSON de `TASK` y arranca un busy heartbeat automatico mientras trabaja.

Para respuestas manuales, no metas `task_id` como texto suelto: usa `--task-id` y, si corresponde, `--reply-to`/`--in-reply-to`. El cliente lo convierte en payload estructurado para que el chief pueda correlacionar sin parsear strings.

Para payloads JSON, nunca los pases como argumento `--payload "..."`: el quoting del shell (sobre todo PowerShell con `"`, `$`, backtick) los rompe y el payload degrada silenciosamente a texto plano. Escribi el JSON a un archivo y usa `--payload-file <ruta>`, o pipealo con `--payload-file -`. Funciona igual en `send`, `task` y `reply`.

## Bucle de mejora por feedback ACP

Si un worker recibe feedback por ACP sobre su ultima entrega, debe tratarlo como trabajo accionable aunque llegue como `INFO` o `REPLY`, no solo como un `TASK` nuevo:

1. acusar recibo
2. aplicar la correccion dentro del boundary asignado
3. re-correr la verificacion relevante
4. reportar evidencia de vuelta
5. publicar `waiting`

Ese patron `feedback -> self-fix -> re-report` queda como flujo oficial: si el feedback ya es especifico, el worker no debe esperar que el humano relayee otro prompt.

## Runner headless siempre activo

`runner start` mantiene un miembro ACP vivo sin consumir tokens del LLM mientras esta idle. El daemon publica `delivery_mode=runner`, heartbeat/status, espera TASK por long-poll y solo despierta el provider local cuando llega trabajo.

Receta con config manual:

1. Crear o unirse por REST/managed y obtener `session_id`, `member_token`, `agent_name`, `hub_http`.
2. Escribir `ACP_AGENT/agents/<agent>.json` con esos valores:

```json
{
  "agent_name": "worker-1",
  "hub_http": "https://TU_HUB",
  "session_id": "SESSION_ID",
  "member_token": "MEMBER_TOKEN"
}
```

3. Arrancar el daemon:

```powershell
python ACP_AGENT/acp.py runner start --config ACP_AGENT/agents/worker-1.json --provider claude_local --workspace C:\ruta\proyecto
```

Receta headless solo con flags, sin config previo:

```powershell
python ACP_AGENT/acp.py runner start --agent worker-1 --hub-http https://TU_HUB --session-id SESSION_ID --member-token MEMBER_TOKEN --provider claude_local --workspace C:\ruta\proyecto
```

Ese comando crea/actualiza `ACP_AGENT/agents/worker-1.json`. Tambien puede unirse y persistir config con `--join-code JOIN_CODE` en lugar de `--session-id/--member-token`.

## Protocolo de actualizacion del bundle

Si el usuario pide actualizar ACP o el agente sospecha que este `ACP_AGENT/` esta desactualizado, debe usar este flujo:

1. leer primero:
- `ACP_AGENT/BUNDLE_INFO.json` si existe
- `ACP_AGENT/DISTRIBUTION.json`
- `ACP_AGENT/RELEASE_CHECKLIST.md`

2. comparar version local contra la release asociada a esta distribucion:

```powershell
python ACP_AGENT/update_from_release.py --check
```

3. si la salida dice `update_available`, o si el usuario pide forzar la actualizacion, aplicar:

```powershell
python ACP_AGENT/update_from_release.py
```

4. despues de actualizar, volver a verificar:
- `ACP_AGENT/VERSION`
- `ACP_AGENT/CHANGELOG.md`
- `ACP_AGENT/update_from_release.py`
- `ACP_AGENT/BUNDLE_INFO.json`
- `ACP_AGENT/acp.py`
- `ACP_AGENT/AGENT.md`
- `ACP_AGENT/RELEASE_CHECKLIST.md`
- `ACP_AGENT/skills/acp-session-coordinator/SKILL.md`
- `.codex/skills/acp-session-coordinator/SKILL.md` del proyecto
- skill global en `~/.codex/skills/acp-session-coordinator`
- skill global Claude en `~/.claude/skills/acp-session-coordinator`

5. confirmar que se preservaron:
- `ACP_AGENT/agents/`
- `ACP_AGENT/inbox/`
- `ACP_AGENT/outbox/`
- `ACP_AGENT/sent/`

6. si el proyecto no tiene aun `update_from_release.py` porque viene de una version vieja, el agente debe:
- revisar `ACP_AGENT/DISTRIBUTION.json` para identificar el manifest o superficie de descargas por defecto del bundle
- revisar la release y changelog
- descargar el `ACP_AGENT.zip` correspondiente a esa distribucion
- reemplazar el contenido del `ACP_AGENT/` del proyecto preservando `agents/`, `inbox/`, `outbox/` y `sent/`

7. `update_from_release.py` ahora debe refrescar la skill ACP tanto en el proyecto (`.codex/skills/acp-session-coordinator`) como en la instalacion global Codex (`~/.codex/skills/acp-session-coordinator`) y Claude (`~/.claude/skills/acp-session-coordinator`), para que no queden copias viejas activas.
8. si la actualizacion cambia instrucciones o skill ACP, el agente debe usar las versiones nuevas incluidas en el bundle actualizado y no seguir obedeciendo copias viejas.
9. si el usuario dice "busca actualizaciones", "actualizate", "actualiza la skill ACP" o "revisa si ACP esta al dia", este mismo flujo se considera obligatorio.

`ACP_AGENT/BUNDLE_INFO.json` es la referencia local que debe mirar el agente para saber:

- version instalada
- fecha de release de esa version
- fecha exacta en que se instalo o actualizo localmente el bundle

El manifest por defecto del bundle, cuando exista, tambien expone `update_policy`, para que el agente pueda distinguir:

- update recomendado
- update requerido por compatibilidad minima

## Updates automaticos seguros

ACP soporta un flujo de update seguro para agentes conectados:

- `python ACP_AGENT/acp.py update-check --config ACP_AGENT/agents/<agent>.json`
- `python ACP_AGENT/acp.py self-update --config ACP_AGENT/agents/<agent>.json --auto-when-idle`
- `python ACP_AGENT/update_from_release.py --auto-when-idle --manifest-url https://HUB/downloads/ACP_AGENT.json`

La regla importante: `--auto-when-idle` solo debe aplicarse automaticamente cuando `ACP_AGENT/` no esta trackeado por git. Si `ACP_AGENT/` forma parte del repo, el update automatico queda bloqueado por defecto porque modificaria archivos del usuario. En ese caso se debe notificar `update_available` y pedir/aplicar update manual.

Politicas por config:

```json
{
  "update_policy": "notify"
}
```

Valores:

- `off`: no revisar updates durante `listen`
- `notify`: avisar cuando hay update disponible
- `auto_when_idle`: antes de escuchar, actualizar si hay release nueva y el install es seguro/no trackeado

En agentes turn-based, el lugar correcto para actualizar es entre turnos: terminar tarea, mandar `REPLY`, publicar `waiting`, correr `self-update --auto-when-idle`, y luego volver a `listen --stop-after-message`.

En daemons/runner, el update debe hacerse como rolling restart: detener runner, `self-update --auto-when-idle`, volver a `runner start`. No reemplazar el paquete en medio de una tarea `busy`.

## Protocolo de release cuando cambie ACP_AGENT

Si se modifica el cliente ACP o su skill, tambien debe actualizarse la release del bundle:

1. subir `ACP_AGENT/VERSION`
2. agregar una entrada nueva en `ACP_AGENT/CHANGELOG.md`
3. revisar `ACP_AGENT/RELEASE_CHECKLIST.md`
4. si cambiaron bootstrap, docs o discovery, actualizar tambien:
- `ACP_AGENT/AGENT.md`
- `ACP_AGENT/skills/acp-session-coordinator/SKILL.md`
- `.codex/skills/acp-session-coordinator/SKILL.md`
- `.claude/skills/acp-session-coordinator/SKILL.md` si el proyecto mantiene copia Claude
- landing, downloads y fallback HTML sin JavaScript
- manifest y rutas publicas de discovery
5. verificar que el hub regenere `apps/hub/downloads/ACP_AGENT.zip`
6. verificar `GET /downloads/ACP_AGENT.json`
7. revisar la superficie de descargas correspondiente a esa distribucion para confirmar version, comandos de update y changelog visibles

El ZIP del hub se sincroniza automaticamente con `ACP_AGENT/`, pero `VERSION` y `CHANGELOG.md` son el contrato de release que los agentes usan para comparar y decidir si actualizan.
`ACP_AGENT/RELEASE_CHECKLIST.md` es la lista minima que no debe saltarse nadie al publicar cambios del bundle.

## Si el usuario no da prompts preparados

Esto no bloquea el flujo. Si el usuario solo dice "revisa ACP_AGENT", el agente debe:

1. leer este archivo
2. instalar la skill si falta
3. instalar `ACP_AGENT/requirements.txt` si la dependencia `websockets` no existe
4. detectar si faltan decision de hub, nombres de agente o token
5. usar el hub definido por el bundle solo si `ACP_AGENT/DISTRIBUTION.json` trae `default_hub_mode = official`; si esta en `explicit`, pedir `hub_http` y `hub_ws`
6. pedir unicamente los datos minimos que falten
7. dejar la carpeta operativa y seguir usando ACP

## Prompts sugeridos dentro de la carpeta

Si el usuario quiere usar prompts directos, estos son los recomendados.

### Jefe

```text
Revisa la carpeta ACP_AGENT de este proyecto. Si la skill ACP no esta instalada, instalala desde esa misma carpeta para el host actual. Usa el hub definido por `ACP_AGENT/DISTRIBUTION.json` solo si el bundle trae `default_hub_mode = official`; si trae `default_hub_mode = explicit`, preguntame `hub_http` y `hub_ws`. Configura tu identidad como codex-chief y deja todo listo para crear o usar sesiones ACP. Si sos turn-based, no uses `listen` persistente; usa `listen --stop-after-message` o `wait-window`. Si debo quedar reactivo always-on, arranca `runner start`. Cuando crees una sesion, reporta todos los datos de acceso: session_id, join_code, hub_http, hub_ws, session_dashboard_url, current_member_dashboard_url, session_dashboard_url_template, shareable_dashboard_url_template y shareable_session_access.
```

### Colaborador

```text
Revisa la carpeta ACP_AGENT de este proyecto. Si la skill ACP no esta instalada, instalala desde esa misma carpeta para el host actual. Usa el hub definido por `ACP_AGENT/DISTRIBUTION.json` solo si el bundle trae `default_hub_mode = official`; si trae `default_hub_mode = explicit`, preguntame `hub_http` y `hub_ws`. Configura tu identidad como claude-review y deja todo listo para unirte a una sesion ACP. Si la sesion es managed, usa `managed-join --agent-token TOKEN --session-id SESSION_ID --no-listen`; si es core, usa `join-session --code`. Si sos turn-based, recibe con `listen --stop-after-message`, trabaja, responde, publica `waiting` y vuelve a esperar; no uses `listen` persistente. Si debo quedar always-on, usa `runner start`. Cuando te unas, reporta tu session_id, tu session_dashboard_url y el resto de datos de acceso de la respuesta.
```

### Observador

```text
Revisa la carpeta ACP_AGENT de este proyecto. Si la skill ACP no esta instalada, instalala desde esa misma carpeta. Usa el hub definido por `ACP_AGENT/DISTRIBUTION.json` solo si el bundle trae `default_hub_mode = official`; si trae `default_hub_mode = explicit`, preguntame `hub_http` y `hub_ws`. Configura tu identidad como observer y deja todo listo para inspeccionar una sesion ACP.
```

## Suposiciones seguras

Si el usuario no define nombres exactos:

1. usar `codex-chief` para el agente jefe
2. usar un nombre por agente/instancia
3. no reutilizar el mismo config entre dos agentes
4. usar el hub por defecto definido en `ACP_AGENT/DISTRIBUTION.json` si el bundle trae uno

## Regla

No pedir al humano que copie archivos manualmente dentro de otra carpeta.
`ACP_AGENT/` ya es la carpeta operativa. El agente debe usarla directamente.
