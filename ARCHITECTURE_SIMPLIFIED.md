# Arquitectura Simplificada

Este documento fija el modelo canónico del proyecto para evitar mezclar administración de plataforma con coordinación real entre agentes.

## Idea Central

El producto real es `ACP core`, no el workspace.

- El `workspace` organiza.
- La `session` trabaja.
- El `join_code` deja entrar a una sesión.
- El `member_token` permite operar dentro de una sesión.
- El `workspace token` permite crear o administrar sesiones desde el contexto de un workspace.

## Capas

### 1. ACP core

Responsabilidad:

- crear sesiones
- unir agentes a sesiones
- enrutar mensajes
- guardar estados
- exponer dashboard de sesión

Objetos principales:

- `Session`
- `SessionMember`
- `Message`
- `join_code`
- `member_token`

Preguntas que responde:

- qué sesión existe
- qué agentes están dentro
- qué mensajes viajan
- qué estado tiene cada miembro

### 2. VPS admin

Responsabilidad:

- crear workspaces
- invitar al admin humano de un workspace
- desactivar workspaces

Objeto principal:

- `Workspace`

Preguntas que responde:

- qué workspaces existen
- quién administra cada workspace
- qué workspace está activo o deshabilitado

### 3. Workspace admin

Responsabilidad:

- entrar al dashboard del workspace
- rotar o revocar el token único del workspace
- crear sesiones ACP
- ver sesiones del workspace
- abrir el detalle administrativo de una sesión

Objetos principales:

- `workspace token`
- relación `workspace -> sessions`

Preguntas que responde:

- qué sesiones pertenecen a este workspace
- cuál es el token activo
- qué sesión debo abrir o crear

## Roles

### `instance_admin`

- crea workspaces
- invita exactamente un `workspace_admin`
- puede desactivar un workspace

No debe operar sesiones del día a día.

### `workspace_admin`

- acepta una invitación
- crea o vincula su cuenta VPS
- entra al dashboard del workspace
- rota el token único
- crea y revisa sesiones

### colaboradores de sesión

- no son usuarios web del workspace
- no necesitan cuenta en el panel
- entran a una sesión con `join_code`
- operan dentro de la sesión con `member_token`

## Tokens y Credenciales

### Invitation link

Sirve para activar al admin humano del workspace.

- lo emite el `instance_admin`
- contiene un token interno
- no sirve para entrar a sesiones ACP

### Workspace token

Sirve para crear o administrar sesiones desde el ACP client o automatizaciones del workspace.

- existe uno activo por workspace
- rotarlo revoca el anterior
- revocarlo deja al workspace sin acceso de cliente externo hasta generar uno nuevo

### `join_code`

Sirve para unirse a una sesión concreta.

- lo comparte el jefe o admin que creó la sesión
- no da acceso al workspace

### `member_token`

Sirve para operar dentro de la sesión.

- lo entrega el Hub al entrar
- se usa en `wait`, `listen`, `send`, `status` y `leave`
- no da acceso al workspace

## Flujo Canónico

1. El `instance_admin` crea un workspace.
2. El `instance_admin` invita al `workspace_admin`.
3. El invitado acepta el link y crea o vincula su cuenta VPS.
4. El `workspace_admin` entra al dashboard del workspace.
5. El `workspace_admin` rota el token único del workspace.
6. El `workspace_admin` crea una sesión ACP desde el panel o desde ACP client.
7. El sistema devuelve `session_id`, `join_code` y credenciales del miembro inicial.
8. Otros agentes entran con `join_code`.
9. ACP core continúa con mensajes, estados y dashboard de sesión.

## Regla de Oro

Si una decisión te hace preguntar "esto pertenece al workspace o a la sesión?", la respuesta normal debe ser:

- si es acceso humano, ownership administrativo o token del espacio: `workspace`
- si es colaboración activa entre agentes: `session`

## Pantallas Canónicas

### VPS admin

- `/managed/login`
- `/managed/dashboard`
- `/managed/admin/workspaces/ui`
- `/managed/invitations/{token}`

### Workspace admin

- `/managed/ui/workspaces`
- `/managed/ui/workspaces/{slug}`
- `/managed/ui/workspaces/{slug}/sessions`
- `/managed/ui/workspaces/{slug}/sessions/{session_id}`

### ACP core

- `/dashboard/session`
- endpoints de sesión y mensajería del Hub

## Rutas Auxiliares o Legacy

Estas rutas no deben usarse para explicar el producto:

- `/managed/admin/users/ui`
- `/managed/admin/workspaces/{slug}/agent-tokens/create`
- `/managed/admin/workspaces/{slug}/presets/create`

Pueden existir por compatibilidad o ayudas de transición, pero no forman parte del contrato principal.

## Invariantes de v1

- un solo admin humano por workspace
- un solo token activo por workspace
- los colaboradores no son miembros web del workspace
- el centro del sistema es la sesión ACP
- `join_code` da acceso a sesión, no a workspace
- `member_token` da acceso a operaciones de sesión, no a workspace

## Qué No Debe Volver a Pasar

No mezclar en una misma explicación:

- usuarios humanos del panel
- agentes que colaboran dentro de sesiones
- tokens de workspace
- credenciales internas de sesión

Cuando eso se mezcla, la UI se vuelve difícil de entender aunque el backend funcione.
