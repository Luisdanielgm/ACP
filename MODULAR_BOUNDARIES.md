# Modularidad y Frontera Público/Privado

> **Actualizado 2026-06-19 — Opción Y.** La sección "2. Frontera público/privado"
> de abajo quedó desactualizada: ya **no** todo `acp_managed` es privado. La capa
> workspace (auth humana, whitelist, workspaces, invitaciones, tokens, sesiones,
> UI de admin) ahora es **open source** (parte de ACP Manager); solo el overlay
> hosted (página + billing + branding + provisión + distribución `official`) es
> privado. La **frontera funcional** y la **regla de dependencia** de este
> documento siguen 100% vigentes. Fuente de verdad del modelo:
> [OPEN_CORE_MODEL.md](OPEN_CORE_MODEL.md).

Este documento complementa [ARCHITECTURE_SIMPLIFIED.md](ARCHITECTURE_SIMPLIFIED.md) y responde una pregunta distinta:

- no solo "qué hace cada capa"
- sino también "qué código debería vivir junto" y "qué código debe quedarse público o privado"

## Regla Principal

Hay dos fronteras distintas:

1. frontera funcional
2. frontera de visibilidad del producto

No son lo mismo.

## 1. Frontera funcional

### ACP core

Debe contener solo lo reutilizable y estable:

- protocolo
- sesiones
- miembros
- mensajes
- colas
- dashboard de sesión
- endpoints HTTP/WS del Hub

Esto es el motor del producto.

### Managed / VPS

Debe contener solo lo específico del producto hosted:

- login humano
- browser sessions
- whitelist o admisión
- workspaces
- invitaciones
- token único del workspace
- dashboards administrativos
- branding privado

Esto es la capa de operación privada.

## 2. Frontera público/privado

### Código público / open source

Debe ser exportable sin filtrar secretos ni lógica comercial:

- `ACP_AGENT/`
- `apps/hub/src/acp/hub/`
- `apps/hub/src/acp/protocol/`
- tests de contratos públicos
- documentación pública del protocolo

### Código privado

Debe quedarse fuera de una extracción open source:

- `apps/hub/src/acp_managed/`
- login y cuentas humanas
- workspaces y su administración
- invitaciones por email o link
- defaults hosted
- branding privado
- manifiestos privados de distribución

## Qué significa eso en la práctica

No basta con decir "hay un módulo core y uno managed".

También debe cumplirse:

- el código público no importa nada privado
- el código privado sí puede importar el core público
- la UI privada no debe contaminar al core
- la lógica de workspaces no debe meterse dentro del protocolo ACP

## Modelo recomendado de paquetes

### Público

```text
apps/hub/src/acp/
  hub/
    app.py
    coordination_service.py
    coordination_state.py
    coordination_store.py
    http_api.py
    ws_ingress.py
    dashboard_html.py
    session_dashboard_html.py
  protocol/
    models.py
    validators.py
    errors.py
```

### Privado

```text
apps/hub/src/acp_managed/
  app.py
  auth/
    passwords.py
    session.py
    sqlite_store.py
    whitelist.py
  routes/
    admin.py
    auth.py
    workspace.py
    agent.py
  services/
    invitations.py
    workspace_tokens.py
    workspace_sessions.py
    workspace_access.py
  ui/
    shell.py
    landing.py
    dashboard.py
    workspace_pages.py
```

## Qué debería quedarse en `app.py`

Muy poco.

`acp_managed/app.py` debería quedar como composición:

1. crear `HubRuntime`
2. llamar `create_app(runtime=...)`
3. construir dependencias managed
4. registrar routers privados

O sea, `app.py` debería ser pegamento, no un archivo gigante de reglas + HTML + rutas.

## División recomendada dentro de `managed`

### `auth/`

Solo identidad humana:

- password hashing
- session cookies
- principal store
- whitelist bootstrap

### `services/workspace_access.py`

Solo reglas de autorización del workspace:

- `require_instance_admin`
- `require_workspace_access`
- `require_workspace_admin_access`
- resolución del viewer actual

### `services/invitations.py`

Solo invitaciones:

- emitir invitación
- validar token
- aceptar invitación
- expirar o revocar invitación

### `services/workspace_tokens.py`

Solo token único del workspace:

- crear token
- rotar token
- revocar token
- resolver token actual desde request

### `services/workspace_sessions.py`

Puente entre workspace y ACP core:

- crear sesión ACP desde workspace
- listar sesiones del workspace
- enlazar `workspace -> session`
- enriquecer detalle administrativo

### `routes/admin.py`

Solo panel del `instance_admin`:

- crear workspace
- invitar admin
- desactivar o actualizar workspace

### `routes/workspace.py`

Solo panel del `workspace_admin`:

- dashboard del workspace
- token rotate/revoke
- crear sesión
- ver sesiones
- ver detalle de sesión

### `routes/agent.py`

Solo superficies para ACP client con `workspace token`:

- crear sesión
- listar sesiones
- ver sesión

### `ui/`

Solo HTML y helpers visuales:

- layout base
- topbar
- dashboard pages
- workspace pages
- invitation pages

Nada de permisos o reglas de negocio fuertes aquí.

## Regla de dependencia

La dirección correcta es esta:

```text
acp core <- acp_managed services <- acp_managed routes <- acp_managed ui
```

Y nunca al revés.

Especialmente:

- `acp.hub` no debe importar `acp_managed`
- `ui/` no debe resolver permisos por su cuenta
- `routes/` no deben hablar directo con sqlite si ya existe un service adecuado

## Qué partes del proyecto ya respetan esto

- existe una separación física entre [acp](apps/hub/src/acp) y [acp_managed](apps/hub/src/acp_managed)
- el repo ya reconoce la frontera pública en [PUBLIC_REPO_BOUNDARY.md](PUBLIC_REPO_BOUNDARY.md)
- el overlay privado (repo `acp-cloud`) compone una capa cerrada sobre el core público

## Qué todavía no respeta del todo esta modularidad

- [acp_managed/app.py](apps/hub/src/acp_managed/app.py) mezcla:
  - composición
  - permisos
  - servicios
  - rutas
  - HTML
- algunas rutas legacy siguen existiendo por compatibilidad
- parte de la UX todavía deja ver superficies auxiliares que no son el contrato principal

## Contrato de trabajo para futuros cambios

Cuando aparezca una nueva feature, primero decidir:

1. ¿esto pertenece al core o al managed?
2. ¿esto es público o privado?
3. ¿esto es servicio, ruta o UI?

Si no se responde eso antes de programar, el proyecto vuelve a mezclarse.

## Regla corta para decidir

- si coordina agentes dentro de una sesión: `ACP core`
- si administra personas, workspaces o tokens hosted: `managed privado`
- si podría publicarse sin filtrar producto hosted: `open source`
- si depende de cuentas humanas, invitaciones o branding hosted: `privado`
