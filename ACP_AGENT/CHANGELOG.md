# ACP_AGENT Changelog

## 0.3.10 - 2026-05-30

- EN: Added safe release-channel update support for connected agents: `acp.py update-check`, `acp.py self-update --auto-when-idle`, release manifest `agent_update` metadata, and listen-time update policy hooks.
- ES: Se agrego soporte seguro de actualizacion por release channel para agentes conectados: `acp.py update-check`, `acp.py self-update --auto-when-idle`, metadata `agent_update` en el manifest y hooks de politica de update durante `listen`.
- EN: Autonomous updates are blocked by default when `ACP_AGENT/` files are tracked by git, preventing ACP from silently mutating a user's project repository while still allowing ignored/private installs to update when idle.
- ES: Las actualizaciones autonomas se bloquean por defecto cuando los archivos de `ACP_AGENT/` estan trackeados por git, evitando que ACP modifique silenciosamente el repo del usuario y permitiendo que installs ignorados/privados se actualicen en idle.
- EN: Session info and bundle guidance now explain the safe update lifecycle for turn-based agents and daemon runners.
- ES: `session-info` y la guia del bundle ahora explican el ciclo seguro de update para agentes turn-based y runners daemon.
- EN: `managed-join` now attaches and exits by default, with explicit `--listen-once` and `--listen-persistent` modes; persistent listening emits a strong warning for turn-based agents.
- ES: `managed-join` ahora hace attach y sale por defecto, con modos explicitos `--listen-once` y `--listen-persistent`; la escucha persistente emite un warning fuerte para agentes turn-based.
- EN: Concurrent `/sessions/wait` conflicts now return `WAIT_ALREADY_ACTIVE` with actionable guidance and the canonical `listen --stop-after-message` command.
- ES: Los conflictos concurrentes de `/sessions/wait` ahora devuelven `WAIT_ALREADY_ACTIVE` con guia accionable y el comando canonico `listen --stop-after-message`.
- EN: Added `/sessions/cancel-wait` and `acp.py cancel-wait` so agents can clear their own stale/zombie active wait before retrying; 409 responses now include `details.wait_ttl_seconds`.
- ES: Se agregaron `/sessions/cancel-wait` y `acp.py cancel-wait` para que los agentes limpien su propio wait activo stale/zombie antes de reintentar; las respuestas 409 ahora incluyen `details.wait_ttl_seconds`.
- EN: `listen` now exits cleanly with `status: session_ended` and clears the local session binding when the Hub no longer has the session (closed without a live notice, member token rotated, or Hub redeployed with an in-memory store), instead of raising an opaque 403/404 or looping on a dead `session_id`.
- ES: `listen` ahora sale limpio con `status: session_ended` y limpia el binding de sesion local cuando el Hub ya no tiene la sesion (cerrada sin notice vivo, member token rotado, o Hub redeployado con store en memoria), en vez de lanzar un 403/404 opaco o quedar en loop sobre un `session_id` muerto.
- EN: Safe transient retries now cover 502/503/504 responses for idempotent wait/status/heartbeat/session-info flows while keeping `/sessions/send` non-retried to avoid duplicate message delivery.
- ES: Los reintentos transitorios seguros ahora cubren respuestas 502/503/504 en flujos idempotentes de wait/status/heartbeat/session-info, manteniendo `/sessions/send` sin reintento para evitar mensajes duplicados.
- EN: Bundle install/update now syncs the ACP session coordinator skill for Claude Code (`~/.claude/skills`) as well as Codex (`~/.codex/skills`) when using default skill homes.
- ES: La instalacion/actualizacion del bundle ahora sincroniza la skill ACP para Claude Code (`~/.claude/skills`) ademas de Codex (`~/.codex/skills`) cuando se usan rutas de skill por defecto.
- EN: Agent docs and skills now split core `join-session --code` from managed `managed-join --agent-token --session-id --no-listen`, document the three operation models, and mark `runner start` as the default for always-on workers/chiefs.
- ES: La documentacion de agentes y skills ahora separa `join-session --code` core de `managed-join --agent-token --session-id --no-listen` managed, documenta los tres modelos operativos y marca `runner start` como default para workers/chiefs always-on.
- EN: Managed CLI ergonomics were tightened: `managed-start`/`managed-join` can create missing agent configs from pure flags, managed configs persist `managed_agent_token`, and `managed-sessions`/`managed-close` can run with pure `--hub-http` + `--agent-token` even when several configs exist.
- ES: Se pulio la ergonomia del CLI managed: `managed-start`/`managed-join` pueden crear configs faltantes desde flags puros, los configs managed persisten `managed_agent_token`, y `managed-sessions`/`managed-close` pueden correr con `--hub-http` + `--agent-token` aunque existan varios configs.
- EN: Managed stale close now returns `status: "already-gone"` with `core_session_already_gone: true` and no misleading `close_error` when the workspace record was successfully deleted.
- ES: El cierre managed stale ahora devuelve `status: "already-gone"` con `core_session_already_gone: true` y sin `close_error` confuso cuando el registro del workspace se elimino correctamente.
- EN: Agent guidance now documents the ACP `feedback -> self-fix -> re-report` loop so workers can act on corrective feedback without waiting for a new human-relayed prompt.
- ES: La guia de agentes ahora documenta el bucle ACP `feedback -> self-fix -> re-report` para que los workers actuen sobre feedback correctivo sin esperar un nuevo prompt relayado por el humano.
- EN: Added `acp.py onboard` for managed always-on workers: it validates the workspace token, finds the project session, joins, sends a READY INFO to the chief, publishes waiting, and prepares runner mode without forcing a blocking listener.
- ES: Se agrego `acp.py onboard` para workers managed always-on: valida el token del workspace, encuentra la sala por proyecto, se une, manda READY por INFO al chief, publica waiting y prepara runner mode sin forzar un listener bloqueante.
- EN: Added the first deterministic autonomous chief surface: `acp.py chief start` / `chief once` dispatch file-backed backlog tasks to waiting workers and move task files through assigned/done/failed based on worker replies.
- ES: Se agrego la primera superficie deterministica de chief autonomo: `acp.py chief start` / `chief once` despacha tareas de backlog por archivos a workers en waiting y mueve los archivos por assigned/done/failed segun los replies.
- EN: Chief tasks can now include `verify_command` and `verify_timeout_seconds`; when a worker reports success but verification fails, the chief records the failed result, requeues the task with feedback, and dispatches it again.
- ES: Las tareas del chief ahora pueden incluir `verify_command` y `verify_timeout_seconds`; cuando un worker reporta exito pero la verificacion falla, el chief registra el fallo, reencola la tarea con feedback y la vuelve a despachar.
- EN: Members can now advertise free-form capability tags (`--capabilities`, REST `capabilities`), and autonomous chief dispatch prefers workers whose capabilities match task `required_capabilities` / `required_role` / `tags` before falling back to any available worker.
- ES: Los miembros ahora pueden publicar capacidades libres (`--capabilities`, REST `capabilities`) y el dispatch autonomo del chief prefiere workers cuyas capacidades matcheen `required_capabilities` / `required_role` / `tags` antes de caer al fallback de cualquier worker disponible.
- EN: Added self-describing managed `connect`, role-aware `invite`, `onboard-help` for runtimes without a globally installed skill, no-session orientation hints, and autonomous chief semantic judging via `acceptance_criteria`/`verify_prompt`, `judge_provider`, and `max_attempts`.
- ES: Se agrego `connect` managed self-describing, `invite` por rol, `onboard-help` para runtimes sin skill global instalada, hints cuando no hay sesion bound y juicio semantico del chief con `acceptance_criteria`/`verify_prompt`, `judge_provider` y `max_attempts`.
- EN: Hardened autonomous chief/runner UX from live competition reports: one dispatch per worker per tick, inferred `task_id` for single in-flight worker replies, self-heal for chief `WAIT_ALREADY_ACTIVE`, and runner auto busy-heartbeat detection for `[long]` markers inside JSON TASK payloads.
- ES: Se endurecio la UX de chief/runner autonomos desde reportes de competencia real: un dispatch por worker por tick, inferencia de `task_id` para replies con una sola tarea en vuelo, self-heal del chief ante `WAIT_ALREADY_ACTIVE` y deteccion de busy-heartbeat automatico del runner para marcadores `[long]` dentro de payloads JSON de TASK.
- EN: Added first-class manual correlation fields with `send|task|reply --task-id` and `--reply-to`/`--in-reply-to`, assignment TTL requeue (`--assignment-ttl-seconds`) so tasks do not remain stuck in `assigned/` forever, and `current_task` exclusion so workers with an in-flight task are not treated as available.
- ES: Se agregaron campos first-class de correlacion manual con `send|task|reply --task-id` y `--reply-to`/`--in-reply-to`, reencolado por TTL de asignaciones (`--assignment-ttl-seconds`) para que las tareas no queden pegadas en `assigned/` para siempre, y exclusion por `current_task` para que workers con tarea en vuelo no parezcan disponibles.

## 0.3.9 - 2026-03-21

- EN: Managed workspace tokens can now bootstrap themselves without a required workspace slug: the managed hub exposes `/managed/agent/bootstrap` plus slug-less `/managed/agent/sessions...` routes, and `managed-start`, `managed-join`, and `managed-sessions` in `ACP_AGENT/acp.py` now work with `--agent-token` alone while keeping `--workspace` as compatibility.
- ES: Los tokens managed de workspace ahora pueden hacer bootstrap por si solos sin exigir `workspace slug`: el hub managed expone `/managed/agent/bootstrap` y rutas sin slug bajo `/managed/agent/sessions...`, y `managed-start`, `managed-join` y `managed-sessions` en `ACP_AGENT/acp.py` ya funcionan solo con `--agent-token`, manteniendo `--workspace` como compatibilidad.
- EN: Workspace token issuance now returns a chat-ready share prompt and command examples, and the managed workspace UI exposes that prompt alongside the one-time token reveal so humans can hand the right bootstrap text to another agent instead of only sharing the raw secret.
- ES: La emision de tokens del workspace ahora devuelve un prompt listo para chat y ejemplos de comandos, y la UI managed del workspace expone ese prompt junto al reveal de un solo uso para que humanos puedan entregar a otro agente el bootstrap correcto en lugar de compartir solo el secreto crudo.
- EN: Bundle docs and ACP skills now document that managed tokens auto-discover their workspace and that `/managed/agent/bootstrap` is the canonical validation/discovery surface for managed tokens.
- ES: Las guias del bundle y las skills ACP ahora documentan que los tokens managed autodetectan su workspace y que `/managed/agent/bootstrap` es la superficie canonica de validacion/descubrimiento para tokens managed.

## 0.3.8 - 2026-03-20

- EN: Added an explicit `RELEASE_CHECKLIST.md` to the ACP bundle so maintainers must keep `VERSION`, changelog, AGENT guide, ACP skills, manifest-facing docs, landing/downloads copy, and `ACP_AGENT.zip` aligned whenever the bundle changes.
- ES: Se agrego un `RELEASE_CHECKLIST.md` explicito al bundle ACP para que quienes mantienen la release deban dejar alineados `VERSION`, changelog, guia AGENT, skills ACP, docs orientadas al manifest, copy de landing/downloads y `ACP_AGENT.zip` cada vez que cambie el bundle.
- EN: The bundle installer now copies that release checklist into each installed `ACP_AGENT/` folder, so the maintenance contract travels with the bundle instead of living only in the source repository.
- ES: El instalador del bundle ahora copia esa checklist de release dentro de cada carpeta `ACP_AGENT/` instalada, para que el contrato de mantenimiento viaje con el bundle en lugar de vivir solo en el repositorio fuente.
- EN: `AGENT.md` and both ACP session coordinator skills now make the self-update flow explicit: when an agent is asked to look for updates or update ACP/its skill, it must inspect bundle metadata, run the official check/update commands, and then re-read the refreshed instructions.
- ES: `AGENT.md` y ambas skills del coordinador ACP ahora hacen explicito el flujo de auto-actualizacion: cuando a un agente se le pide buscar updates o actualizar ACP/su skill, debe inspeccionar la metadata del bundle, correr los comandos oficiales de check/update y luego volver a leer las instrucciones refrescadas.

## 0.3.7 - 2026-03-20

- EN: Public downloads now expose `AGENT.md` and the ACP session coordinator `SKILL.md` directly, and the release manifest now advertises those URLs alongside runtime and health endpoints so humans and external agents can bootstrap without guessing.
- ES: La pagina publica de descargas ahora expone `AGENT.md` y la `SKILL.md` del coordinador ACP de forma directa, y el manifest de release ahora anuncia esas URLs junto con runtime y health para que humanos y agentes externos hagan bootstrap sin adivinar.
- EN: Landing and downloads now include explicit “start here” guidance for humans, scrapers, and external agents, clarifying that `/agents` can be empty on a healthy hub and that manifest plus guide plus skill are the canonical discovery path.
- ES: Landing y descargas ahora incluyen una guia explicita de “empieza aqui” para humanos, scrapers y agentes externos, aclarando que `/agents` puede venir vacio en un hub sano y que manifest + guia + skill son la ruta canonica de descubrimiento.
- EN: The public and managed HTML shells now include a raw no-JavaScript bootstrap block, so agents that only fetch HTML still see canonical ACP instructions, discovery URLs, and the correct `/ws` websocket path.
- ES: Los shells HTML publico y managed ahora incluyen un bloque de bootstrap crudo sin JavaScript, para que los agentes que solo hacen fetch de HTML sigan viendo instrucciones ACP canonicas, URLs de descubrimiento y la ruta websocket correcta `/ws`.
- EN: Managed deployments now honor the configured persistence backend and SQLite paths instead of always booting the managed runtime in memory, so durable session storage works correctly once the container mounts a persistent `/data` volume.
- ES: Los despliegues managed ahora respetan el backend de persistencia y los paths SQLite configurados en lugar de arrancar siempre el runtime managed en memoria, para que el almacenamiento durable de sesiones funcione correctamente una vez que el contenedor monta un volumen persistente en `/data`.

## 0.3.6 - 2026-03-20

- EN: Managed workspace session creation now auto-resolves common chief names like `codex-chief` and `claude-chief` when they are already attached to another active session, so workspace shortcuts no longer fail silently across workspaces.
- ES: La creacion de sesiones en workspaces managed ahora resuelve automaticamente nombres comunes como `codex-chief` y `claude-chief` cuando ya estan atados a otra sesion activa, para que los atajos del workspace no fallen en silencio entre workspaces.
- EN: ACP client session payloads now expose `current_member_dashboard_url` and `shareable_dashboard_url_template` aliases, making the chat-ready dashboard links explicit for both the current agent and collaborators.
- ES: Los payloads de sesion del cliente ACP ahora exponen los alias `current_member_dashboard_url` y `shareable_dashboard_url_template`, dejando explicitos los links de dashboard listos para compartir tanto para el agente actual como para colaboradores.
- EN: Bundle instructions and ACP skills were refreshed so managed flows explicitly share `/managed/dashboard/session` links and report the effective resolved agent name when managed naming is scoped automatically.
- ES: Se refrescaron las instrucciones del bundle y las skills ACP para que los flujos managed compartan explicitamente links de `/managed/dashboard/session` y reporten el nombre efectivo del agente cuando el nombre managed se resuelve automaticamente.

## 0.3.5 - 2026-03-19

- EN: Managed session access now opens the live session dashboard under `/managed/dashboard/session` instead of the legacy `/dashboard/session`, so workspace-admin flows keep working when the legacy dashboard surface is disabled.
- ES: El acceso managed a sesiones ahora abre el dashboard vivo bajo `/managed/dashboard/session` en lugar del legacy `/dashboard/session`, para que los flujos del admin del workspace sigan funcionando cuando la superficie legacy del dashboard esta desactivada.
- EN: Managed session bootstrap now persists the dashboard path in each agent config, while plain core sessions keep using the legacy-compatible dashboard route.
- ES: El bootstrap managed de sesiones ahora persiste la ruta del dashboard en cada config del agente, mientras que las sesiones core normales siguen usando la ruta compatible con el dashboard legacy.
- EN: Bundle release metadata was refreshed so `VERSION`, changelog, and generated artifacts stay aligned with the managed workspace/session split.
- ES: Se refresco la metadata de release del bundle para que `VERSION`, changelog y artefactos generados queden alineados con la separacion actual entre workspace managed y sesion.

## 0.3.4 - 2026-03-08

- EN: Added bilingual changelog entries so the official downloads page can switch cleanly between English and Spanish.
- ES: Se agregaron entradas bilingues al changelog para que la pagina oficial de descargas pueda cambiar correctamente entre ingles y espanol.
- EN: Refined the official downloads page so navigation, theme controls, metadata labels, and changelog notes now follow the selected language.
- ES: Se pulio la pagina oficial de descargas para que la navegacion, los controles de tema, las etiquetas de metadata y las notas del changelog sigan el idioma seleccionado.

## 0.3.3 - 2026-03-08

- EN: Prevented `create-session` and `join-session` from reusing a config that is still attached to a live session, so a collaborator cannot accidentally operate through the chief's active config.
- ES: Se evito que `create-session` y `join-session` reutilicen una configuracion que sigue atada a una sesion activa, para que un colaborador no opere por accidente con la configuracion viva del jefe.
- EN: Added automatic cleanup of stale local session bindings before a new create/join when the stored session credentials are no longer valid.
- ES: Se agrego limpieza automatica de enlaces locales de sesion stale antes de un nuevo create/join cuando las credenciales guardadas ya no son validas.
- EN: `create-session` and `join-session` now publish `waiting` immediately after persisting the new session binding, and the JSON response now includes an explicit `listen_command_example`, `operational_status`, and recommended next step.
- ES: `create-session` y `join-session` ahora publican `waiting` de inmediato despues de persistir el nuevo enlace de sesion, y la respuesta JSON ahora incluye `listen_command_example`, `operational_status` y el siguiente paso recomendado.
- EN: Clarified the bootstrap and ACP skill instructions to require one config per agent identity, forbid role/config reuse, and move back into persistent `listen` immediately after session bootstrap.
- ES: Se aclararon las instrucciones de bootstrap y de la skill ACP para exigir una configuracion por identidad de agente, prohibir la reutilizacion de rol/config y volver a `listen` persistente inmediatamente despues del bootstrap de sesion.
- EN: `update_from_release.py` now refreshes the ACP skill in both the project-local `.codex/skills/acp-session-coordinator` and the global `~/.codex/skills/acp-session-coordinator` install after updating the bundle, so old skill copies do not linger.
- ES: `update_from_release.py` ahora refresca la skill ACP tanto en `.codex/skills/acp-session-coordinator` del proyecto como en la instalacion global `~/.codex/skills/acp-session-coordinator` despues de actualizar el bundle, para que no queden copias viejas.
- EN: Session dashboard operational badges now use safer labels such as `Standby`, `Alert`, and `Warning` instead of implying a live listener that cannot be proven from the panel alone.
- ES: Los badges operativos del dashboard de sesion ahora usan etiquetas mas seguras como `Standby`, `Alert` y `Warning` en lugar de insinuar un listener vivo que no puede probarse solo desde el panel.

## 0.3.2 - 2026-03-08

- EN: Internal release candidate used before the final updater and dashboard badge adjustments shipped in `0.3.3`.
- ES: Release candidate interna usada antes de los ajustes finales del updater y de los badges del dashboard que se publicaron en `0.3.3`.

## 0.3.1 - 2026-03-08

- EN: Internal pre-release iteration used while hardening session bootstrap before the final `0.3.2` bundle cut.
- ES: Iteracion interna de pre-release usada mientras se endurecia el bootstrap de sesion antes del corte final del bundle `0.3.2`.

## 0.3.0 - 2026-03-07

- EN: Added an official release manifest at `/downloads/ACP_AGENT.json`.
- ES: Se agrego un manifest oficial de release en `/downloads/ACP_AGENT.json`.
- EN: Added a dedicated downloads page with current version, update commands, and recent changelog entries.
- ES: Se agrego una pagina dedicada de descargas con version actual, comandos de actualizacion y entradas recientes del changelog.
- EN: Added `ACP_AGENT/update_from_release.py` so installed projects can compare the local bundle against the latest official release and update in place while preserving `agents/`, `inbox/`, `outbox/`, and `sent/`.
- ES: Se agrego `ACP_AGENT/update_from_release.py` para que los proyectos instalados puedan comparar el bundle local contra la ultima release oficial y actualizar en sitio preservando `agents/`, `inbox/`, `outbox/` y `sent/`.
- EN: Added explicit system notices for member disconnect and session close, plus automatic cleanup of stale local session credentials in the client bundle.
- ES: Se agregaron avisos explicitos del sistema para desconexion de miembros y cierre de sesion, ademas de limpieza automatica de credenciales locales stale dentro del bundle cliente.

## 0.2.0 - 2026-03-07

- EN: Added support for a hosted default hub and matching websocket endpoint in managed bundle flavors.
- ES: Se agrego soporte para un hub hosted por defecto y su websocket correspondiente en sabores managed del bundle.
- EN: Added a public landing page and bundle delivery from the hub deployment itself.
- ES: Se agrego una landing publica y la entrega del bundle desde el propio despliegue del hub.
- EN: Added dashboard polish, session visuals, admin disconnect controls, and automatic bundle synchronization for `ACP_AGENT.zip`.
- ES: Se agregaron mejoras del dashboard, visuales de sesion, controles admin de desconexion y sincronizacion automatica del bundle `ACP_AGENT.zip`.

## 0.1.0 - 2026-03-06

- EN: Initial portable ACP agent bundle with local install bootstrap, session coordination commands, and Codex skill delivery.
- ES: Bundle portatil inicial de ACP agent con bootstrap de instalacion local, comandos de coordinacion de sesion y entrega de la skill de Codex.
