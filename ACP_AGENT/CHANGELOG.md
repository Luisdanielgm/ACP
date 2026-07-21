# ACP_AGENT Changelog

## 0.3.42 - 2026-07-21

- EN: Expose `--member-token-ref` in HostBridge configure so existing listener configs can be generated deterministically without persisting an ACP member token.
- ES: Expone `--member-token-ref` en HostBridge configure para generar configs de listeners existentes de forma determinista sin persistir un token de miembro ACP.

## 0.3.41 - 2026-07-21

- EN: Allow an explicitly declared HostBridge listener to resolve its existing ACP member token from `member_token_ref: "env:NAME"`, keeping the token out of config files and failing closed when the reference is missing or ambiguous.
- ES: Permite que un listener HostBridge declarado explicitamente resuelva el token de miembro ACP existente mediante `member_token_ref: "env:NAME"`, manteniendo el token fuera de los configs y fallando de forma segura si la referencia falta o es ambigua.

## 0.3.40 - 2026-07-21

- EN: Use the full safe budget of the Hub's 300-second delivery lease for host progress, retaining the reply/ack/lease reserve instead of failing at 240 seconds.
- ES: Usa el presupuesto seguro completo del lease ACP de 300 segundos para el progreso del host, conservando la reserva de reply/ack/lease en lugar de fallar a los 240 segundos.

## 0.3.39 - 2026-07-21

- EN: Allow a product-owned coordinator plan to append dependency-ready pending tasks without invalidating durable state; existing task contracts remain immutable and fail closed on drift.
- ES: Permite que un plan de coordinacion propiedad del producto agregue tareas pendientes listas por dependencia sin invalidar el estado durable; los contratos existentes permanecen inmutables y cualquier deriva falla de forma segura.

## 0.3.38 - 2026-07-21

- EN: Allow an explicitly declared, already-authorized listener config to own the ACP wait/ACK/REPLY lease while the primary HostBridge config keeps the opaque existing host binding; no sessions or members are created.
- ES: Permite declarar una configuracion de listener ya autorizada para que sea dueña del lease ACP de espera/ACK/REPLY mientras la configuracion primaria conserva el binding opaco del host existente; no se crean sesiones ni miembros.

## 0.3.37 - 2026-07-21

- EN: Reconcile a late successful REPLY from the task owner after a terminal host failure without emitting a duplicate turn; dependency continuation remains approval-gated.
- ES: Se reconcilia un REPLY exitoso tardío del dueño de la tarea después de un fallo terminal del host sin emitir un turno duplicado; la continuación de dependencias mantiene sus gates de aprobación.
- EN: Accept durable terminal and approval-blocked statuses in product-owned plan definitions so canonical snapshots remain loadable by the generic coordinator.
- ES: Se aceptan estados terminales y bloqueados por aprobación en definiciones de plan propiedad del producto para que los snapshots canónicos sigan siendo cargables por el coordinador genérico.

## 0.3.36 - 2026-07-21

- EN: Honor the Hub wait lease TTL after `WAIT_ALREADY_ACTIVE` instead of busy-looping concurrent receivers; HostBridge and Reply Collector preserve the existing listener and retry only after it can expire.
- ES: Se respeta el TTL del lease de espera del Hub después de `WAIT_ALREADY_ACTIVE` en vez de girar en busy-loop con receptores concurrentes; HostBridge y Reply Collector preservan el listener existente y reintentan solo después de su expiración.

## 0.3.35 - 2026-07-20

- EN: Defer delivery and reconciliation while an explicitly resumed Codex thread has another active turn, preventing duplicate prompts and false quarantine during chained turns.
- ES: Se difieren la entrega y reconciliacion mientras un thread Codex reanudado tiene otro turno activo, evitando prompts duplicados y cuarentenas falsas durante turnos encadenados.

## 0.3.34 - 2026-07-20

- EN: Consume ACP system notices without host invocation, REPLY, or ACK; cancellation/restart notices no longer masquerade as missing delivery leases and block the next wait.
- ES: Se consumen avisos de sistema ACP sin invocar el host, emitir REPLY ni hacer ACK; los avisos de cancelacion/reinicio ya no se confunden con leases faltantes ni bloquean la siguiente espera.

## 0.3.33 - 2026-07-20

- EN: Keep HostBridge processes alive while a stale Hub wait lease drains; `WAIT_ALREADY_ACTIVE` is retried safely instead of terminating the supervisor child and exhausting restart limits.
- ES: Se mantienen vivos los procesos HostBridge mientras vence un lease de espera obsoleto del Hub; `WAIT_ALREADY_ACTIVE` se reintenta de forma segura en vez de terminar el hijo del supervisor y agotar los límites de reinicio.

## 0.3.32 - 2026-07-20

- EN: Reconcile completed Codex app-server turns when the host normalizes surrounding user-message whitespace, preventing a durable completed turn from being retried indefinitely.
- ES: Se reconcilian turnos Codex app-server completados aunque el host normalice espacios externos del mensaje de usuario, evitando reintentos indefinidos de un turno ya terminado.

## 0.3.31 - 2026-07-20

- EN: Fixed Windows Host Bridge supervisor shutdown for detached bridge processes. Stop/restart now requests a graceful full-tree close first, then uses one bounded native force fallback when the process cannot accept the graceful request; PID health checks remain non-signaling.
- ES: Se corrigio el cierre del supervisor Host Bridge en Windows para procesos bridge detached. Stop/restart solicita primero un cierre graceful de todo el arbol y luego usa un unico fallback nativo forzado y acotado si el proceso no acepta el cierre; los health checks de PID siguen sin enviar senales.

## 0.3.30 - 2026-07-20

- EN: Generalized HostBridge ingress so one existing host task can receive configured `TASK`, `REPLY`, and `INFO` actions through one durable wait. Empty waits still make zero host/model calls; only `TASK` emits an automatic correlated `REPLY`, preventing result loops.
- ES: Se generalizo el ingreso de HostBridge para que una misma tarea existente reciba acciones `TASK`, `REPLY` e `INFO` configuradas mediante un unico wait durable. El idle mantiene cero llamadas al host/modelo; solo `TASK` emite un `REPLY` correlacionado automatico, evitando bucles de resultados.
- EN: Removed the pilot-specific result-router default from profile and supervisor generation. New profiles use explicit generic senders/actions and workers reply directly to their configured coordinator; the separate `reply-collector` command remains only as a backward-compatible optional component.
- ES: Se elimino el result-router especifico del piloto de los defaults de perfiles y supervisor. Los perfiles nuevos usan remitentes/acciones genericos explicitos y los workers responden directamente a su coordinador configurado; el comando separado `reply-collector` queda solo como componente opcional compatible.
- EN: Hardened the public ZIP builder so mutable `agents/`, `inbox/`, `outbox/`, `sent/`, and installed `BUNDLE_INFO.json` state can never enter the portable archive or its fingerprint.
- ES: Se endurecio el generador del ZIP publico para que el estado mutable de `agents/`, `inbox/`, `outbox/`, `sent/` y `BUNDLE_INFO.json` instalado nunca entre al archivo portable ni a su fingerprint.

## 0.3.29 - 2026-07-20

- EN: Fixed terminal coordinator-plan results with no dependency-ready successor so Reply Collector ACKs them without generating a legacy wake TASK. ACK retries remain durable and idempotent.
- ES: Se corrigieron los resultados terminales del plan sin sucesor listo: Reply Collector los ACKea sin generar un TASK legacy de wake. Los reintentos de ACK permanecen durables e idempotentes.

## 0.3.28 - 2026-07-20

- EN: Added explicit per-task `max_attempts` to durable coordinator plans. A failed/interrupted result may emit a new deterministic attempt only when the product declared a retry budget; crash replay within an attempt keeps the same delivery ID and exhausted tasks remain blocked.
- ES: Se agrego `max_attempts` explicito por tarea a los planes durables del coordinador. Un resultado fallido/interrumpido solo puede emitir un nuevo intento determinista cuando el producto declaro ese presupuesto; el replay por crash dentro de un intento conserva el mismo ID y las tareas agotadas permanecen bloqueadas.

## 0.3.27 - 2026-07-20

- EN: Clarified the fail-closed allowlist contract for direct plan dispatch: every worker selected as a plan owner must explicitly trust the Reply Collector/plan-dispatcher identity. ACP never spoofs the coordinator sender; a missing entry fails before host invocation and leaves the TASK unacknowledged for safe retry.
- ES: Se aclaró el contrato fail-closed de allowlist para despacho directo del plan: cada worker seleccionado como owner debe confiar explícitamente en la identidad Reply Collector/plan dispatcher. ACP nunca suplanta al coordinador; una entrada faltante falla antes de invocar el host y deja el TASK sin ACK para reintento seguro.

## 0.3.26 - 2026-07-20

- EN: Wired the durable `CoordinatorPlan` into `reply-collector`: a correlated terminal `REPLY`/`INFO` now records its result, emits exactly one dependency-ready `TASK` with a deterministic id, marks it sent only after Hub acceptance, and ACKs the source only after both durable transitions. Restart after any crash window reuses the same TASK id; unrelated INFO keeps the legacy forwarding path.
- ES: Se conectó el `CoordinatorPlan` durable con `reply-collector`: un `REPLY`/`INFO` terminal correlacionado ahora registra su resultado, emite exactamente un `TASK` listo por dependencias con ID determinista, lo marca enviado sólo después de la aceptación del Hub y confirma el origen únicamente tras ambas transiciones durables. Un reinicio en cualquier ventana de crash reutiliza el mismo ID; los INFO ajenos al plan conservan el forwarding anterior.
- EN: Added explicit plan definition/state configuration, task-owner result correlation, declarative risk levels, mandatory approval gates for high/sensitive tasks, and fake end-to-end conformance proving the planned TASK binds to the same existing Codex Desktop thread while idle waits make zero host/model calls.
- ES: Se agregó configuración explícita de definición/estado del plan, correlación del resultado con el owner, niveles de riesgo declarativos, gates obligatorios para tareas high/sensitive y conformidad fake extremo a extremo que prueba que el TASK planificado usa el mismo thread existente de Codex Desktop mientras el idle hace cero llamadas al host/modelo.

## 0.3.25 - 2026-07-20

- EN: Added the portable `CoordinatorPlan` core: durable result correlation, dependency-aware next-safe-action selection, explicit approval gates, deterministic TASK delivery ids, restart-safe pending emissions, and fail-closed validation. This is the non-model foundation for autonomous coordinator continuation; transport wiring and Codex Desktop wake remain separate acceptance slices.
- ES: Se agrego el nucleo portable `CoordinatorPlan`: correlacion durable de resultados, seleccion de siguiente accion segura por dependencias, gates de aprobacion explicitos, IDs deterministas de entrega TASK, emisiones pendientes seguras ante reinicio y validacion fail-closed. Es la base no-LLM para la continuidad autonoma del coordinador; el cableado de transporte y el wake de Codex Desktop siguen siendo slices de aceptacion separados.

## 0.3.24 - 2026-07-19

- EN: Serialized Codex app-server stdio deliveries by normalized executable and added bounded graceful process shutdown so chained turns cannot overlap an unfinished stdio runtime.
- ES: Se serializaron las entregas stdio de Codex app-server por ejecutable normalizado y se agrego un cierre graceful acotado para evitar solapamientos con un runtime stdio aun finalizando.

## 0.3.23 - 2026-07-19

- EN: Completed the poison-delivery fix for terminally failed turns. When a retried delivery's correlated Codex turn exists but reached a terminal non-success state (`failed`/`interrupted`), the bridge now raises `HostTerminalFailureError`, quarantines with a specific secret-free reason (`codex_turn_failed` / `codex_turn_interrupted`), sends one correlated failure REPLY, and ACKs so the queue continues — with no duplicate `turn/start` and no spurious interrupt. Ambiguous/`inProgress`/disconnect cases still fail closed and retry; Claude CLI stays fail-closed when it cannot prove a durable result. Applies to `codex_app_server` and `codex_app_server_stdio`.
- ES: Se completo el arreglo de poison delivery para turnos terminalmente fallidos. Cuando el turno Codex correlacionado de un delivery reintentado existe pero alcanzo un estado terminal sin exito (`failed`/`interrupted`), el bridge lanza `HostTerminalFailureError`, pone en cuarentena con una razon especifica y sin secretos (`codex_turn_failed` / `codex_turn_interrupted`), envia un unico REPLY de fallo correlacionado y hace ACK para que la cola avance, sin `turn/start` duplicado ni interrupt espurio. Los casos ambiguos/`inProgress`/desconexion siguen fallando cerrados y reintentan; Claude CLI permanece fail-closed cuando no puede probar un resultado durable. Aplica a `codex_app_server` y `codex_app_server_stdio`.
- EN: Added `host-bridge configure`, an idempotent command that generates or migrates a durable HostBridge profile without any host call or new session. It wires compatibility roles automatically: `worker` targets the configured reply-collector member and authorizes its coordinator; `coordinator` authorizes that collector and never routes replies back into it. It requires explicit thread/session id and role (no autodiscovery), preserves hub/room/identity/tokens/unknown keys, writes atomically, stamps `host_profile_schema_version`, migrates legacy Codex profiles (`host_bridge_session_id` -> `host_bridge_thread_id`), validates `reply_to` is not the member's own identity, prints only a secret-free wiring summary, and supports `--check` (doctor mode, no write).
- ES: Se agrego `host-bridge configure`, un comando idempotente que genera o migra un perfil durable de HostBridge sin ninguna llamada al host ni sesion nueva. Cablea roles de compatibilidad automaticamente: `worker` dirige resultados al miembro reply-collector configurado y autoriza a su coordinador; `coordinator` autoriza a ese collector y nunca enruta respuestas de vuelta a el. Exige thread/session id y rol explicitos (sin autodiscovery), preserva hub/sala/identidad/tokens/claves desconocidas, escribe de forma atomica, sella `host_profile_schema_version`, migra perfiles Codex antiguos (`host_bridge_session_id` -> `host_bridge_thread_id`), valida que `reply_to` no sea la propia identidad del miembro, imprime solo un resumen de wiring sin secretos y soporta `--check` (modo doctor, sin escritura).
- EN: Added `host-supervisor generate`, which builds a `host_supervisor_bridges` config for the coordinator, workers, and Reply Collector from their agent configs, reusing the existing non-model supervisor (one command starts/verifies all; configs and ledgers survive restarts). OS autostart is reported as an explicit, un-installed capability (`autostart: not_installed`); nothing is scheduled or activated. Idle stays idle: no Codex process, turn, or token until a valid TASK arrives.
- ES: Se agrego `host-supervisor generate`, que construye una config `host_supervisor_bridges` para el coordinador, los workers y el Reply Collector a partir de sus configs de agente, reutilizando el supervisor no-modelo existente (un comando inicia/verifica todo; configs y ledgers sobreviven reinicios). El autoarranque del SO se reporta como capacidad explicita y no instalada (`autostart: not_installed`); no se agenda ni activa nada. Idle sigue idle: sin proceso Codex, turno ni token hasta que llega un TASK valido.

## 0.3.22 - 2026-07-19

- EN: Fixed a poison-delivery queue block. When a persisted `received` delivery is retried and the host provably never accepted it (the session resumes and its durable history has no correlated turn), the bridge now raises `HostNotAcceptedError`, moves the delivery to a terminal `quarantined` state with traceability (`reason: host_never_accepted`), sends one correlated failure REPLY, and ACKs so the queue continues — without resubmitting a duplicate `turn/start` or losing work silently. Ambiguous/transient failures still fail closed and retry. Applies to `codex_app_server` and `codex_app_server_stdio`.
- ES: Se corrigio el bloqueo de cola por poison delivery. Cuando un delivery persistido como `received` se reintenta y el host probadamente nunca lo acepto (la sesion reanuda y su historial durable no tiene el turno correlacionado), el bridge lanza `HostNotAcceptedError`, mueve el delivery a un estado terminal `quarantined` con trazabilidad (`reason: host_never_accepted`), envia un unico REPLY de fallo correlacionado y hace ACK para que la cola continue, sin reenviar un `turn/start` duplicado ni perder trabajo en silencio. Los fallos ambiguos/transitorios siguen fallando cerrados y reintentan. Aplica a `codex_app_server` y `codex_app_server_stdio`.
- EN: Added an explicit HostBridge `reply_to` target (`host_bridge_reply_to` config or `--reply-to`). Plain-TASK replies can now be routed to a separately named reply-collector member instead of a TASK-only coordinator. A wrapped REPLY/INFO still answers the original worker, so the coordinator never loops back into the collector. Correlation, ACK, idempotency, allowlists, and identity separation are preserved.
- ES: Se agrego un destino `reply_to` explicito para HostBridge (config `host_bridge_reply_to` o `--reply-to`). Las respuestas de un TASK plano ahora pueden enrutarse a un miembro reply-collector con identidad separada en lugar de un coordinador TASK-only. Un REPLY/INFO envuelto sigue respondiendo al worker original, asi el coordinador nunca hace loop de vuelta al collector. Se preservan correlacion, ACK, idempotencia, allowlists y separacion de identidades.

## 0.3.21 - 2026-07-17

- EN: Added `codex_cli`, a portable Host Bridge adapter that resumes an existing Codex session through the official non-interactive `codex exec resume <session_id> --json` surface only after a valid ACP TASK. It correlates on the resumed thread id, requires a single terminal `turn.completed`, never starts a new session, and does not spawn Codex while the ACP inbox is idle. Retries fail closed because the CLI does not expose durable prompt-level reconciliation.
- ES: Se agrego `codex_cli`, un adapter portable de Host Bridge que reanuda una sesion Codex existente mediante la superficie oficial no interactiva `codex exec resume <session_id> --json` solo despues de un TASK ACP valido. Correlaciona por el thread id reanudado, exige un unico `turn.completed` terminal, nunca inicia una sesion nueva y no spawnea Codex mientras el inbox ACP esta idle. Los reintentos fallan cerrados porque la CLI no expone reconciliacion durable por prompt.
- EN: Added an explicit `claude_desktop` fail-closed contract. Claude Desktop exposes no official, stable, testable interface to bind or resume an existing conversation (MCP support does not provide chat resume, and community relays/UI automation are not supported), so any delivery is rejected with `UNSUPPORTED_PENDING_OFFICIAL_INTERFACE` and no conversation, process, or UI action is started as a fallback.
- ES: Se agrego un contrato explicito fail-closed `claude_desktop`. Claude Desktop no expone una interfaz oficial, estable y comprobable para enlazar o reanudar una conversacion existente (MCP no ofrece resume de chat, y los relays/automatizacion de UI de terceros no estan soportados), asi que toda entrega se rechaza con `UNSUPPORTED_PENDING_OFFICIAL_INTERFACE` sin iniciar conversacion, proceso ni accion de UI como fallback.
- EN: `codex_cli` interface details (exact resume flag ordering and JSON event schema) are pinned to current OpenAI Codex docs but remain `VERIFICATION_REQUIRED` until an authorized isolated smoke against a real installed Codex confirms them; all tests use process mocks.
- ES: Los detalles de interfaz de `codex_cli` (orden exacto de flags de resume y schema de eventos JSON) estan fijados a la doc vigente de OpenAI Codex pero quedan `VERIFICATION_REQUIRED` hasta un smoke aislado autorizado contra un Codex real instalado; todas las pruebas usan mocks del proceso.

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
