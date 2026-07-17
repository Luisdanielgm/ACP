# ACP_AGENT Changelog

## 0.3.20 - 2026-07-17

- EN: Added `claude_code_cli`, a portable Host Bridge adapter that invokes the official `claude -p --resume <session_id>` surface only after a valid ACP TASK, parses the terminal stream-json result, and does not invoke Claude while the ACP inbox is idle.
- ES: Se agrego `claude_code_cli`, un adapter portable de Host Bridge que invoca la superficie oficial `claude -p --resume <session_id>` solo despues de un TASK ACP valido, procesa el resultado terminal stream-json y no invoca Claude mientras el inbox ACP esta idle.
- EN: The binding requires an explicit absolute Claude executable and existing session id. Retries fail closed because the CLI does not expose durable prompt-level reconciliation; local authentication or an `env:NAME` bearer credential reference is required at delivery time.
- ES: El binding requiere un ejecutable Claude absoluto y explicito y un id de sesion existente. Los reintentos fallan cerrados porque la CLI no expone reconciliacion durable por prompt; se requiere autenticacion local o una referencia bearer `env:NAME` al entregar.
- EN: This release supports Claude Code persisted sessions, not Claude Desktop. It does not claim push delivery into an already-running Claude terminal/IDE session or Claude Channels support.
- ES: Esta release soporta sesiones persistidas de Claude Code, no Claude Desktop. No declara entrega push hacia una sesion terminal/IDE Claude ya activa ni soporte de Claude Channels.

## 0.3.19 - 2026-07-17

- EN: Added the portable `codex_app_server` Host Bridge adapter for an explicit existing Codex thread over a loopback WebSocket, using the official initialize, thread/resume, turn/start, item/completed, turn/completed, and turn/interrupt protocol.
- ES: Se agrego el adapter portable `codex_app_server` de Host Bridge para un thread Codex existente y explicito por WebSocket loopback, usando el protocolo oficial initialize, thread/resume, turn/start, item/completed, turn/completed y turn/interrupt.
- EN: Codex deliveries correlate through `clientUserMessageId`; retries recover a visible correlated turn or fail closed without a second turn because app-server does not promise idempotent turn/start. Internal events and credential values are never persisted in the bridge ledger.
- ES: Las entregas Codex se correlacionan mediante `clientUserMessageId`; los reintentos recuperan un turno correlacionado visible o fallan de forma cerrada sin crear un segundo turno porque app-server no promete idempotencia de turn/start. Los eventos internos y valores de credenciales nunca se persisten en el ledger.
- EN: A read-only local smoke proved that app-server 0.144.5 can list, read, and resume an existing Codex Desktop task with the same thread id and zero turn/start calls; live Desktop activation remains intentionally untested in this release.
- ES: Un smoke local read-only probo que app-server 0.144.5 puede listar, leer y reanudar una tarea existente de Codex Desktop con el mismo thread id y cero llamadas turn/start; la activacion real de Desktop permanece intencionalmente sin probar en esta release.

## 0.3.18 - 2026-07-17

- EN: Added explicit `host-bridge start|once` commands that lease ACP TASK messages without an idle provider/model, deliver one at a time to a bound OpenCode or Kilo session, send an idempotent correlated REPLY, and ACK only after Hub-confirmed durable progress.
- ES: Se agregaron los comandos explicitos `host-bridge start|once`, que reciben TASK de ACP sin proveedor/modelo en espera, entregan de a uno a una sesion OpenCode o Kilo vinculada, envian un REPLY correlacionado e idempotente y confirman ACK solo despues del progreso durable validado por el Hub.
- EN: Host bindings are explicit and fail closed: loopback endpoint, existing host session id, trusted senders, optional directory, and optional `env:NAME` Basic credential reference; no host autodiscovery or literal credential is supported.
- ES: Los bindings del host son explicitos y fail-closed: endpoint loopback, id de sesion existente, remitentes confiables, directorio opcional y referencia opcional `env:NAME` a credencial Basic; no se admite autodiscovery ni credencial literal.
- EN: Malformed receive envelopes fail closed, interrupts stop cleanly, an exclusive binding lock rejects concurrent bridge processes, and the Hub lease expiry budgets host work, correlated REPLY, ACK, and a final safety buffer under one end-to-end deadline.
- ES: Los envelopes de recepcion invalidos fallan de forma cerrada, las interrupciones terminan limpiamente, un lock exclusivo por binding rechaza procesos concurrentes y el vencimiento del lease del Hub distribuye host, REPLY correlacionado, ACK y un buffer final bajo un unico deadline end-to-end.

## 0.3.17 - 2026-07-16

- EN: Added the portable Host Bridge core with durable delivery state, correlated idempotent replies, and host-neutral manifests, opaque session bindings, results, and adapter registry contracts. Before POST, adapters reconcile the deterministic host message ID against session history so restart after remote acceptance cannot activate the prompt twice.
- ES: Se agrego el nucleo portable de Host Bridge con estado durable de entregas, respuestas correlacionadas e idempotentes y contratos neutrales de manifest, binding opaco de sesion, resultado y registry de adapters. Antes del POST, los adapters reconcilian el ID determinista contra el historial de la sesion para que un reinicio despues de la aceptacion remota no active dos veces el prompt.
- EN: Added conformant existing-session HTTP adapters for OpenCode server and Kilo Code `kilo serve`; bindings are explicit, loopback-only in this first slice, and resolve optional Basic credentials by reference without persisting secrets.
- ES: Se agregaron adapters HTTP conformantes para sesiones existentes de OpenCode server y Kilo Code `kilo serve`; los bindings son explicitos, limitados a loopback en este primer slice y resuelven credenciales Basic opcionales por referencia sin persistir secretos.
- EN: Fresh drop-in installation now copies the Host Bridge module together with the advertised 0.3.17 runtime.
- ES: La instalacion drop-in nueva ahora copia el modulo Host Bridge junto con el runtime 0.3.17 anunciado.

## 0.3.16 - 2026-07-15

- EN: Join-code invitations now require a verified 0.3.16+ client, use shell-neutral one-line commands, and provide guarded official update recovery for old or Git-tracked installs.
- ES: Las invitaciones con join code ahora exigen un cliente 0.3.16+ verificado, usan comandos de una linea compatibles entre shells y ofrecen recuperacion oficial protegida para instalaciones antiguas o tracked por Git.
- EN: The release updater compares semantic versions and refuses to replace a newer local client with an older manifest unless `--force` is explicit.
- ES: El updater compara versiones semanticas y se niega a reemplazar un cliente local mas nuevo por un manifest anterior salvo que `--force` sea explicito.
- EN: `join-session` reserves and rechecks its config path across the join request, preventing concurrent first-use joins from overwriting one another and releasing the reservation on failure.
- ES: `join-session` reserva y vuelve a comprobar la ruta del config durante el join, evitando que uniones concurrentes de primer uso se sobrescriban y liberando la reserva ante fallos.
- EN: Managed connect/join responses now embed the room's durable context (`room_context` with wall posts and files), and session hints, bootstrap examples, and the coordinator skill teach `room-wall`/`room-files` so agents actually discover and use the wall.
- ES: Las respuestas managed de connect/join ahora incluyen el contexto durable de la sala (`room_context` con muro y archivos), y los hints de sesion, ejemplos de bootstrap y la skill del coordinador enseñan `room-wall`/`room-files` para que los agentes realmente descubran y usen el muro.

## 0.3.15 - 2026-07-15

- EN: `join-session` now creates a distinct agent config when the requested path does not exist, so a join-code invitation works without a destructive bundle reinitialization.
- ES: `join-session` ahora crea un config distinto para el agente cuando la ruta solicitada no existe, por lo que una invitacion con join code funciona sin reinicializar destructivamente el bundle.
- EN: HTTP, download, and multipart requests now send a stable versioned ACP user agent without overriding caller-provided headers, avoiding gateways that reject Python urllib's default identity.
- ES: Las solicitudes HTTP, descargas y multipart ahora envian un user agent ACP estable y versionado sin reemplazar headers del llamador, evitando gateways que rechazan la identidad default de Python urllib.

## 0.3.14 - 2026-07-15

- EN: New runners require an explicit trusted-sender allowlist, pin local provider/workspace by default, and can pin the reply target so TASK payloads cannot redirect execution or responses.
- ES: Los runners nuevos requieren una allowlist explicita de remitentes confiables, fijan provider/workspace locales por defecto y pueden fijar el destinatario de respuesta para que un TASK no redirija ejecucion ni respuestas.
- EN: Runner configs without an explicit security version fail closed; only pre-0.3.14 configs with persisted runner metadata may opt into versioned compatibility with `--legacy-runner-policy`. Managed onboarding trusts the selected room owner independently from the optional READY notification recipient.
- ES: Las configuraciones runner sin version de seguridad explicita fallan de forma cerrada; solo las anteriores a 0.3.14 con metadata runner persistida pueden optar por compatibilidad versionada mediante `--legacy-runner-policy`. El onboarding managed confia en el owner de la sala independientemente del destinatario opcional de la notificacion READY.

## 0.3.13 - 2026-07-12

- EN: Added workspace-admin room message reset through `room-reset`, preserving the room, members, operator, wall, and files while clearing pending deliveries and coordination message history.
- ES: Se agrego el reinicio administrativo de mensajes mediante `room-reset`, conservando sala, miembros, operador, muro y archivos mientras limpia entregas pendientes e historial de coordinacion.
- EN: Reset emits a one-shot `MESSAGES_RESET` system notice so connected clients can rotate or clear their local room chat safely.
- ES: El reinicio emite un aviso de sistema `MESSAGES_RESET` de una sola entrega para que los clientes conectados limpien o roten su chat local de forma segura.

## 0.3.12 - 2026-07-10

- EN: Added first-class managed room collaboration commands: `room-wall list|post` and `room-files list|upload|download`, with workspace auto-discovery, Bearer agent-token scoping, atomic local downloads, and artifact/instruction upload purpose.
- ES: Se agregaron comandos first-class de colaboracion de sala managed: `room-wall list|post` y `room-files list|upload|download`, con autodeteccion del workspace, alcance por agent-token Bearer, descargas locales atomicas y proposito artifact/instruction al subir.
- EN: Managed agents can now upload room artifacts through the public generic API under the same 256 KiB/file, 20-file, and 1 MiB/room quotas already enforced for owners; owner-only pin/delete controls remain unchanged.
- ES: Los agentes managed ahora pueden subir artefactos de sala mediante la API publica generica con las mismas cuotas de 256 KiB/archivo, 20 archivos y 1 MiB/sala ya aplicadas a owners; fijar/eliminar sigue reservado al owner.

## 0.3.11 - 2026-07-10

- EN: Session receive commands now request explicit delivery leases, persist each inbound message atomically under `ACP_AGENT/inbox/`, and acknowledge it only after durable local acceptance; acknowledging clears unread delivery without completing an open TASK.
- ES: Los comandos de recepcion ahora solicitan leases explicitos, guardan cada mensaje entrante de forma atomica en `ACP_AGENT/inbox/` y solo lo confirman tras aceptarlo durablemente; el ack limpia la entrega no leida sin completar una TASK abierta.
- EN: Restored distribution parity by keeping the compact bundled and project-local ACP session coordinator skills byte-identical, while installer and updater coverage continues to synchronize downstream project, Codex, and Claude skill installs.
- ES: Se restauro la paridad de distribucion manteniendo identicas byte a byte las skills ACP compactas del bundle y del proyecto, mientras las pruebas del instalador y updater siguen garantizando la sincronizacion downstream para proyectos, Codex y Claude.

## 0.3.10 - 2026-05-30

- EN: Slimmed the bundled ACP session coordinator skill into a short command router with a test guardrail, so agents use `connect`/`coordinate`/`onboard`/`chief`/`runner` instead of re-reasoning through a long recipe.
- ES: Se redujo la skill bundleada del coordinador ACP a un router corto de comandos con guardrail de test, para que los agentes usen `connect`/`coordinate`/`onboard`/`chief`/`runner` en lugar de re-razonar una receta larga.
- EN: Fixed isolated `ACP_AGENT/acp.py` imports by adding the bundle root to `sys.path` before local helper imports.
- ES: Se corrigieron imports aislados de `ACP_AGENT/acp.py` agregando la raiz del bundle a `sys.path` antes de importar helpers locales.
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
