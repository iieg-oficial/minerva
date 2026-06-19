# Minerva — Manual de alcance, madurez y checklist de evolución

## 1. Propósito del documento

Este documento define qué debe tener Minerva para considerarse completo como sistema institucional de autenticación, autorización y gestión de accesos para múltiples plataformas internas.

También incluye una checklist de estado para identificar qué ya existe en la primera versión del **Minerva Dev Kit** y qué falta priorizar para llegar a una versión centralizada, segura y productiva.

---

## 2. Visión general de Minerva

Minerva será la plataforma institucional encargada de centralizar:

* Usuarios.
* Autenticación.
* Accesos a plataformas.
* Roles.
* Permisos.
* Manifiestos de permisos por sistema.
* Tokens de acceso.
* Administración de aplicaciones internas.
* Auditoría de cambios de acceso.

La meta es que los sistemas internos no implementen login ni permisos desde cero. En su lugar, cada sistema deberá integrarse con Minerva.

Ejemplos de sistemas consumidores:

* Godín.
* Maríachi.
* Huachicol.
* SIEEJ.
* Catálogo y Gobernanza.
* Otros sistemas internos futuros.

---

## 3. Principio rector

La regla principal del diseño de Minerva es:

```text
Los sistemas definen qué acciones existen.
Minerva define quién puede hacerlas.
Los sistemas validan permisos, no roles.
```

Ejemplo:

Godín declara que existen estos permisos:

```text
godin.oficios.view
godin.oficios.create
godin.oficios.authorize
godin.solicitudes.assign
```

Minerva administra qué usuarios tienen esos permisos mediante roles y asignaciones.

Godín únicamente valida:

```python
require_permission("godin.oficios.create")
```

El sistema consumidor no debería validar cosas como:

```python
if user.role == "Administrador":
    ...
```

Los roles pueden cambiar. Los permisos deben ser el contrato estable.

---

## 4. Niveles de completitud de Minerva

Minerva debe entenderse por etapas, no como una sola entrega.

---

### 4.1 Minerva Dev Kit completo

Minerva Dev Kit está completo cuando permite que cualquier equipo pueda levantar una instancia local para desarrollar su sistema siguiendo el contrato correcto.

Debe permitir:

* Levantar Minerva localmente con Docker.
* Usar el panel administrativo.
* Crear usuarios de desarrollo.
* Registrar plataformas.
* Importar manifiestos.
* Crear permisos.
* Crear roles.
* Asignar roles a usuarios.
* Emitir JWT de desarrollo.
* Consultar permisos por aplicación.
* Proteger endpoints desde una app consumidora.
* Migrar después a Minerva Central mediante variables de entorno.

Este es el primer objetivo.

---

### 4.2 Minerva Staging completo

Minerva Staging está completo cuando permite probar integraciones reales entre varios sistemas antes de producción.

Debe permitir:

* Conectar varios sistemas reales.
* Usar configuración parecida a producción.
* Probar login con Google Workspace.
* Probar usuarios reales o semi-reales.
* Validar manifiestos reales.
* Probar permisos entre sistemas.
* Validar migración desde Minerva Dev.
* Probar flujos administrativos.

---

### 4.3 Minerva Central completo

Minerva Central está completo cuando puede operar como el gestor institucional de accesos.

Debe permitir:

* Login institucional con Google Workspace.
* Login manual controlado para usuarios externos.
* Gestión centralizada de usuarios.
* Gestión centralizada de plataformas.
* Gestión centralizada de roles y permisos.
* Auditoría de cambios.
* Seguridad productiva.
* Backups.
* Logs.
* Operación estable.
* Documentación oficial para equipos de desarrollo.

---

## 5. Arquitectura general esperada

La arquitectura objetivo debe verse así:

```text
Usuario
  ↓
Sistema consumidor
  ↓
Minerva Auth / API
  ↓
Base de datos Minerva
```

Los sistemas consumidores deben conectarse a Minerva mediante:

* JWT.
* API HTTP.
* SDK.
* Middleware.
* Manifiestos YAML.

No deben conectarse directamente a la base de datos de Minerva.

---

## 6. Componentes principales de Minerva

---

### 6.1 Minerva Admin

Panel administrativo para gestionar:

* Usuarios.
* Plataformas.
* Permisos.
* Roles.
* Asignaciones.
* Manifiestos.
* Clientes.
* Auditoría.
* Configuración.

---

### 6.2 Minerva Core API

Backend principal encargado de:

* Autenticación.
* Emisión de tokens.
* Administración de usuarios.
* Administración de plataformas.
* Administración de permisos.
* Administración de roles.
* Administración de asignaciones.
* Importación de manifiestos.
* Consulta de permisos.
* Auditoría.

---

### 6.3 Minerva DB

Base de datos central de Minerva.

Tablas mínimas:

```text
users
applications
application_clients
permissions
roles
role_permissions
access_assignments
manifest_imports
```

Tablas necesarias para madurez productiva:

```text
audit_logs
groups
group_members
group_access_assignments
access_requests
refresh_tokens
login_events
api_clients
```

---

### 6.4 Minerva SDK

SDK para facilitar la integración con sistemas consumidores.

Primera prioridad:

```text
minerva-sdk-python
minerva-fastapi-auth
```

Después:

```text
minerva-sdk-js
minerva-react-auth
minerva-next-auth
```

---

### 6.5 Minerva CLI

Herramienta de línea de comandos para tareas comunes.

Comandos deseables:

```bash
minerva manifest validate manifest.minerva.yml
minerva manifest apply manifest.minerva.yml
minerva db upgrade
minerva seed dev
minerva users create
minerva apps list
```

---

## 7. Manifiestos de plataforma

Cada sistema debe declarar sus permisos y roles iniciales en un archivo:

```text
manifest.minerva.yml
```

Ejemplo:

```yaml
application:
  code: godin
  name: Godín
  description: Gestor de oficios, memos y solicitudes de información
  base_url: http://localhost:8000
  redirect_uris:
    - http://localhost:8000/auth/callback

permissions:
  - key: godin.oficios.view
    name: Ver oficios
    description: Permite consultar oficios

  - key: godin.oficios.create
    name: Crear oficios
    description: Permite crear nuevos oficios

  - key: godin.oficios.authorize
    name: Autorizar oficios
    description: Permite autorizar oficios

roles:
  - name: Consulta
    description: Usuario de solo lectura
    permissions:
      - godin.oficios.view

  - name: Capturista
    description: Usuario que puede capturar información
    permissions:
      - godin.oficios.view
      - godin.oficios.create

  - name: Administrador
    description: Control total del sistema
    permissions:
      - godin.oficios.view
      - godin.oficios.create
      - godin.oficios.authorize
```

---

## 8. Convención de permisos

Todos los permisos deben seguir esta estructura:

```text
{application_code}.{resource}.{action}
```

Ejemplos:

```text
godin.oficios.view
godin.oficios.create
godin.oficios.authorize
mariachi.database.view
mariachi.table.update
huachicol.alert.resolve
```

Acciones recomendadas:

```text
view
create
update
delete
assign
approve
authorize
export
import
manage
```

Reglas:

* `view`: lectura.
* `create`: creación.
* `update`: modificación.
* `delete`: eliminación.
* `assign`: asignación.
* `approve`: aprobación.
* `authorize`: autorización formal.
* `export`: exportación.
* `import`: importación.
* `manage`: administración general.

---

## 9. Contrato mínimo para sistemas consumidores

Todo sistema conectado a Minerva debe usar variables de entorno como:

```env
MINERVA_ISSUER_URL=http://localhost:9000
MINERVA_APPLICATION_CODE=godin
MINERVA_CLIENT_ID=godin-dev
MINERVA_CLIENT_SECRET=dev-secret
MINERVA_REDIRECT_URI=http://localhost:8000/auth/callback
MINERVA_PERMISSIONS_CACHE_TTL=300
```

Los endpoints mínimos de Minerva que un sistema consumidor puede necesitar son:

```http
GET /api/v1/me
GET /api/v1/me/permissions?application={application_code}
```

En producción también deben existir endpoints compatibles con flujos de autenticación formal:

```http
GET /.well-known/openid-configuration
GET /.well-known/jwks.json
GET /oauth/authorize
POST /oauth/token
GET /oauth/userinfo
```

Estos últimos pueden quedar para una etapa posterior.

---

## 10. Checklist general de estado

Esta checklist asume que ya se implementó satisfactoriamente la primera versión del **Minerva Dev Kit**.

Leyenda:

```text
[x] Ya debería existir en la primera versión
[ ] Pendiente
[P0] Crítico inmediato
[P1] Alta prioridad
[P2] Media prioridad
[P3] Deseable / futuro
```

---

# 11. Checklist — Minerva Dev Kit

## 11.1 Empaquetado y ejecución local

* [x] [P0] Docker Compose para levantar Minerva localmente.
* [x] [P0] Servicio de base de datos PostgreSQL.
* [x] [P0] Variables de entorno para modo dev.
* [x] [P0] `.env.example`.
* [x] [P0] Healthcheck básico.
* [x] [P0] Panel administrativo incluido en el empaquetado.
* [ ] [P1] Script único de arranque para desarrolladores.
* [ ] [P1] Script de reset de entorno dev.
* [ ] [P1] Documentación visual del flujo de arranque.
* [ ] [P2] Imagen Docker publicada en registry interno.
* [ ] [P2] Versionado semántico de la imagen.

---

## 11.2 Usuarios de desarrollo

* [x] [P0] Modelo de usuarios.
* [x] [P0] CRUD básico de usuarios.
* [x] [P0] Usuario seed `admin@local.dev`.
* [x] [P0] Login dev.
* [x] [P0] JWT emitido en modo dev.
* [ ] [P1] Estados completos de usuario: `active`, `inactive`, `blocked`, `pending`.
* [ ] [P1] Bloqueo de usuarios inactivos.
* [ ] [P2] Vista de último login.
* [ ] [P2] Eventos de login exitoso/fallido.
* [ ] [P3] Simulación de usuarios por grupos o áreas.

---

## 11.3 Plataformas / aplicaciones

* [x] [P0] Modelo de aplicaciones.
* [x] [P0] CRUD de aplicaciones.
* [x] [P0] Código único por aplicación.
* [x] [P0] Registro de `base_url`.
* [x] [P0] Registro de `redirect_uris`.
* [ ] [P1] Estados de aplicación: `active`, `inactive`, `deprecated`.
* [ ] [P1] Vista de usuarios con acceso por aplicación.
* [ ] [P1] Vista de roles por aplicación.
* [ ] [P2] Separación por ambiente: `dev`, `staging`, `production`.
* [ ] [P2] Responsable técnico por aplicación.
* [ ] [P2] Responsable funcional por aplicación.

---

## 11.4 Clientes y credenciales

* [x] [P0] Modelo conceptual de clientes por aplicación.
* [x] [P0] `client_id` por aplicación.
* [x] [P0] `client_secret` para modo dev.
* [ ] [P1] Hash seguro de `client_secret`.
* [ ] [P1] Regeneración de `client_secret` desde panel.
* [ ] [P1] Desactivación de clientes.
* [ ] [P1] Validación fuerte de `redirect_uris`.
* [ ] [P2] Múltiples clientes por aplicación.
* [ ] [P2] Separación entre clientes web, backend y machine-to-machine.
* [ ] [P3] Rotación programada de secretos.

---

## 11.5 Permisos

* [x] [P0] Modelo de permisos.
* [x] [P0] Permisos asociados a una aplicación.
* [x] [P0] Llave única de permiso.
* [x] [P0] Validación de convención `{application_code}.{resource}.{action}`.
* [x] [P0] CRUD básico de permisos.
* [ ] [P1] Vista agrupada por recurso.
* [ ] [P1] Detección de permisos no utilizados.
* [ ] [P2] Marcar permisos como deprecated.
* [ ] [P2] Historial de cambios de permisos.
* [ ] [P3] Catálogo institucional de acciones recomendadas.

---

## 11.6 Roles

* [x] [P0] Modelo de roles.
* [x] [P0] Roles asociados a una aplicación.
* [x] [P0] Relación rol-permisos.
* [x] [P0] CRUD básico de roles.
* [x] [P0] Asignación de permisos a roles.
* [ ] [P1] Vista de permisos contenidos por rol.
* [ ] [P1] Vista de usuarios asignados a un rol.
* [ ] [P1] Duplicar rol.
* [ ] [P2] Marcar rol como deprecated.
* [ ] [P2] Historial de cambios en roles.

---

## 11.7 Asignación de accesos

* [x] [P0] Modelo de asignaciones.
* [x] [P0] Asignación usuario -> aplicación -> rol.
* [x] [P0] Endpoint para crear asignaciones.
* [x] [P0] Endpoint para eliminar asignaciones.
* [ ] [P1] Estado de asignación: `active`, `inactive`, `expired`.
* [ ] [P1] Vigencia de asignaciones: `valid_from`, `valid_until`.
* [ ] [P1] Vista por usuario: plataformas a las que tiene acceso.
* [ ] [P1] Vista por plataforma: usuarios con acceso.
* [ ] [P2] Asignaciones temporales.
* [ ] [P2] Revocación con motivo.
* [ ] [P3] Solicitud y aprobación de accesos.

---

## 11.8 Manifiestos

* [x] [P0] Importación de `manifest.minerva.yml`.
* [x] [P0] Upsert de aplicación.
* [x] [P0] Upsert de permisos.
* [x] [P0] Upsert de roles.
* [x] [P0] Actualización de relación rol-permisos.
* [x] [P0] Registro de hash del manifiesto.
* [x] [P0] Validación de permisos por aplicación.
* [x] [P0] Validación de roles que referencian permisos inexistentes.
* [ ] [P1] Endpoint para validar manifiesto sin importarlo.
* [ ] [P1] Diff entre manifiesto nuevo y estado actual.
* [ ] [P1] Historial visual de imports.
* [ ] [P1] Reporte de cambios introducidos por manifiesto.
* [ ] [P2] Importación automática al arrancar.
* [ ] [P2] Importación desde CLI.
* [ ] [P2] Rechazo controlado de eliminación peligrosa de permisos.
* [ ] [P3] Versionado formal de manifiestos.

---

## 11.9 Autenticación dev y tokens

* [x] [P0] Endpoint `POST /api/v1/auth/dev-login`.
* [x] [P0] Emisión de JWT.
* [x] [P0] Validación de token en endpoints protegidos.
* [x] [P0] Claim `sub`.
* [x] [P0] Claim `email`.
* [x] [P0] Claim `iss`.
* [x] [P0] Expiración de token configurable.
* [ ] [P1] Llaves asimétricas para firma de JWT.
* [ ] [P1] Endpoint JWKS.
* [ ] [P1] Refresh tokens.
* [ ] [P1] Logout.
* [ ] [P2] Revocación de tokens.
* [ ] [P2] Sesiones activas por usuario.
* [ ] [P3] Soporte completo OIDC.

---

## 11.10 Endpoints de usuario actual

* [x] [P0] `GET /api/v1/me`.
* [x] [P0] `GET /api/v1/me/permissions?application=...`.
* [x] [P0] Respuesta con roles del usuario en la aplicación.
* [x] [P0] Respuesta con permisos efectivos del usuario.
* [ ] [P1] Respuesta de aplicaciones disponibles para el usuario.
* [ ] [P1] Manejo claro de usuario sin acceso a aplicación.
* [ ] [P1] Manejo claro de aplicación inexistente.
* [ ] [P2] Cache control en respuestas de permisos.
* [ ] [P2] Endpoint para verificar un permiso específico.

---

## 11.11 Panel administrativo

* [x] [P0] Panel administrativo empaquetado.
* [x] [P0] Conexión básica al backend.
* [x] [P0] Vista de usuarios.
* [x] [P0] Vista de aplicaciones.
* [x] [P0] Vista de permisos.
* [x] [P0] Vista de roles.
* [x] [P0] Vista de asignaciones.
* [ ] [P1] Vista de importaciones de manifiestos.
* [ ] [P1] Vista de detalle por aplicación.
* [ ] [P1] Vista de detalle por usuario.
* [ ] [P1] Mejoras de validación en formularios.
* [ ] [P1] Mensajes claros de error.
* [ ] [P2] Dashboard general.
* [ ] [P2] Búsqueda y filtros.
* [ ] [P2] Paginación.
* [ ] [P3] Tema visual institucional completo.

---

## 11.12 SDK e integración

* [x] [P0] Helper mínimo para FastAPI.
* [x] [P0] Validación de JWT desde sistema consumidor.
* [x] [P0] Consulta de permisos a Minerva.
* [x] [P0] Bloqueo 401 sin token.
* [x] [P0] Bloqueo 403 sin permiso.
* [ ] [P1] Paquete `minerva-sdk-python` formal.
* [ ] [P1] Publicación o instalación local del SDK.
* [ ] [P1] Cache de permisos configurable.
* [ ] [P1] Ejemplo completo con FastAPI.
* [ ] [P2] SDK para frontend.
* [ ] [P2] Ejemplo con React/Next.
* [ ] [P2] Middleware para servicios legacy.
* [ ] [P3] Minerva Guard / Auth Proxy.

---

## 11.13 Documentación

* [x] [P0] README inicial.
* [x] [P0] Documentación de Minerva Dev Kit.
* [x] [P0] Ejemplo de manifiesto.
* [x] [P0] Instrucciones para levantar Docker.
* [x] [P0] Instrucciones para login dev.
* [x] [P0] Instrucciones para consultar permisos.
* [ ] [P1] Manual oficial para equipos consumidores.
* [ ] [P1] Guía de convención de permisos.
* [ ] [P1] Guía para crear manifiestos.
* [ ] [P1] Guía de integración FastAPI.
* [ ] [P1] Guía de migración Dev -> Central.
* [ ] [P2] Diagramas de arquitectura.
* [ ] [P2] Ejemplo completo con Godín.
* [ ] [P3] Portal de documentación interno.

---

# 12. Checklist — Minerva Central

## 12.1 Login institucional

* [ ] [P0] Login con Google Workspace.
* [ ] [P0] Restricción opcional por dominio institucional.
* [ ] [P0] Mapeo de cuenta Google a usuario Minerva.
* [ ] [P1] Login manual para externos.
* [ ] [P1] Control de usuarios externos.
* [ ] [P1] Desactivación de usuarios.
* [ ] [P2] Recuperación de acceso para usuarios manuales.
* [ ] [P2] MFA opcional.
* [ ] [P3] Sincronización con Google Directory.

---

## 12.2 OIDC / OAuth2

* [ ] [P0] Definir si Minerva implementará OIDC directamente o usará Keycloak/AuthentiK como motor.
* [ ] [P1] Endpoint `/.well-known/openid-configuration`.
* [ ] [P1] Endpoint `/oauth/authorize`.
* [ ] [P1] Endpoint `/oauth/token`.
* [ ] [P1] Endpoint `/oauth/userinfo`.
* [ ] [P1] Endpoint `/.well-known/jwks.json`.
* [ ] [P1] Authorization Code Flow.
* [ ] [P2] PKCE.
* [ ] [P2] Refresh tokens.
* [ ] [P2] Client Credentials Flow.
* [ ] [P3] Device Code Flow.

---

## 12.3 Seguridad productiva

* [ ] [P0] HTTPS obligatorio.
* [ ] [P0] Secretos fuera del repo.
* [ ] [P0] Hash seguro de contraseñas y client secrets.
* [ ] [P0] Configuración segura de CORS.
* [ ] [P0] Validación estricta de redirect URIs.
* [ ] [P1] Rate limiting en login.
* [ ] [P1] Rotación de llaves JWT.
* [ ] [P1] Logs de seguridad.
* [ ] [P1] Protección contra usuarios inactivos.
* [ ] [P2] Revocación de sesiones.
* [ ] [P2] Revisión periódica de accesos.
* [ ] [P3] Integración con SIEM o monitoreo institucional.

---

## 12.4 Auditoría

* [ ] [P0] Tabla `audit_logs`.
* [ ] [P0] Registrar cambios de roles.
* [ ] [P0] Registrar cambios de permisos.
* [ ] [P0] Registrar asignaciones de acceso.
* [ ] [P0] Registrar revocaciones de acceso.
* [ ] [P1] Registrar imports de manifiestos.
* [ ] [P1] Registrar login exitoso/fallido.
* [ ] [P1] Mostrar auditoría en panel.
* [ ] [P2] Filtros por usuario, aplicación y fecha.
* [ ] [P2] Exportación de auditoría.
* [ ] [P3] Alertas por cambios sensibles.

---

## 12.5 Operación y despliegue

* [ ] [P0] Dockerfile productivo.
* [ ] [P0] Migraciones con Alembic.
* [ ] [P0] Configuración por variables de entorno.
* [ ] [P0] Healthcheck.
* [ ] [P0] Backups de PostgreSQL.
* [ ] [P1] Endpoint `/ready`.
* [ ] [P1] Logs estructurados.
* [ ] [P1] Documentación de despliegue.
* [ ] [P1] Ambiente staging.
* [ ] [P2] CI/CD.
* [ ] [P2] Monitoreo de disponibilidad.
* [ ] [P2] Métricas básicas.
* [ ] [P3] Alta disponibilidad.

---

## 12.6 Gobierno de accesos

* [ ] [P1] Solicitudes de acceso.
* [ ] [P1] Aprobación/rechazo de solicitudes.
* [ ] [P1] Responsables por plataforma.
* [ ] [P2] Grupos de usuarios.
* [ ] [P2] Áreas o unidades administrativas.
* [ ] [P2] Asignación de roles por grupo.
* [ ] [P2] Vigencia de accesos.
* [ ] [P3] Revisiones periódicas de accesos.
* [ ] [P3] Reportes de accesos por sistema.

---

# 13. Priorización recomendada después de la primera versión

Una vez que exista el primer Minerva Dev Kit funcional, la prioridad no debería ser meter más features al azar. El orden recomendado es este.

---

## Prioridad 1 — Validar con un sistema real

Antes de endurecer Minerva, hay que probarla con un sistema real.

Sistema recomendado:

```text
Godín
```

Objetivo:

* Crear `manifest.minerva.yml` real de Godín.
* Importarlo en Minerva.
* Crear usuarios dev.
* Asignar roles.
* Proteger endpoints reales.
* Validar que la integración sea cómoda.
* Detectar fricciones en el SDK.
* Detectar carencias del panel.

Resultado esperado:

```text
Godín puede usar Minerva Dev para login dev y permisos.
```

---

## Prioridad 2 — Fortalecer manifiestos

Los manifiestos serán el contrato más importante entre Minerva y los sistemas.

Dar prioridad a:

* Validación sin importar.
* Diff de cambios.
* Errores claros.
* Historial de imports.
* Documentación de convención.
* Protección contra cambios peligrosos.

Resultado esperado:

```text
Los equipos pueden declarar permisos de forma segura y repetible.
```

---

## Prioridad 3 — Formalizar SDK Python / FastAPI

Si cada equipo integra Minerva a su manera, se pierde el objetivo.

Dar prioridad a:

* Paquete `minerva-sdk-python`.
* Helper `require_permission`.
* Helper `get_current_user`.
* Cache de permisos.
* Ejemplo completo.
* Documentación clara.

Resultado esperado:

```text
Integrar Minerva en FastAPI toma minutos, no días.
```

---

## Prioridad 4 — Mejorar panel administrativo

El panel debe volverse cómodo para administrar permisos y accesos.

Dar prioridad a:

* Vista por aplicación.
* Vista por usuario.
* Vista de asignaciones.
* Vista de roles con permisos.
* Vista de manifiestos importados.
* Filtros y búsqueda.
* Mensajes claros de error.

Resultado esperado:

```text
Un administrador puede operar accesos sin tocar base de datos.
```

---

## Prioridad 5 — Auditoría básica

Antes de ir a staging o producción, Minerva debe registrar cambios.

Dar prioridad a:

* Cambios de roles.
* Cambios de permisos.
* Asignaciones de acceso.
* Revocaciones.
* Imports de manifiestos.
* Logins.

Resultado esperado:

```text
Se puede saber quién cambió qué y cuándo.
```

---

## Prioridad 6 — Login Google Workspace

Una vez validado el contrato de integración, se debe implementar login real.

Dar prioridad a:

* Login con Google Workspace.
* Restricción por dominio.
* Asociación con usuario Minerva.
* Creación controlada de usuarios.
* Manejo de usuarios externos.

Resultado esperado:

```text
Usuarios institucionales pueden autenticarse con su cuenta Google.
```

---

## Prioridad 7 — Seguridad productiva

Cuando ya exista integración real y login institucional, endurecer Minerva.

Dar prioridad a:

* HTTPS.
* CORS seguro.
* Hash de secretos.
* Rotación de secretos.
* JWT con llaves seguras.
* JWKS.
* Rate limiting.
* Backups.
* Logs estructurados.

Resultado esperado:

```text
Minerva puede operar en staging/productivo con menor riesgo.
```

---

# 14. Orden de trabajo recomendado

## Sprint 1 — Validación real con Godín

* [ ] Crear manifiesto real de Godín.
* [ ] Importar manifiesto en Minerva.
* [ ] Crear roles reales de Godín.
* [ ] Crear usuarios dev.
* [ ] Proteger endpoints de Godín.
* [ ] Documentar fricciones.

---

## Sprint 2 — SDK y contrato de integración

* [ ] Convertir helper en SDK formal.
* [ ] Agregar cache de permisos.
* [ ] Documentar variables estándar.
* [ ] Crear ejemplo FastAPI completo.
* [ ] Crear plantilla para nuevos sistemas.

---

## Sprint 3 — Manifiestos robustos

* [ ] Validar manifiesto sin importar.
* [ ] Mostrar diff.
* [ ] Mejorar errores.
* [ ] Registrar historial.
* [ ] Documentar convención oficial.

---

## Sprint 4 — Panel administrativo usable

* [ ] Mejorar vistas por aplicación.
* [ ] Mejorar vistas por usuario.
* [ ] Mejorar asignación de roles.
* [ ] Agregar vista de manifiestos.
* [ ] Agregar filtros y búsqueda.

---

## Sprint 5 — Auditoría básica

* [ ] Crear `audit_logs`.
* [ ] Auditar cambios de acceso.
* [ ] Auditar cambios de roles.
* [ ] Auditar cambios de permisos.
* [ ] Auditar importación de manifiestos.
* [ ] Mostrar auditoría en panel.

---

## Sprint 6 — Login institucional

* [ ] Implementar Google login.
* [ ] Asociar usuario Google con usuario Minerva.
* [ ] Validar dominio institucional.
* [ ] Mantener login manual para externos.
* [ ] Documentar configuración.

---

## Sprint 7 — Preparación para staging

* [ ] Configurar ambiente staging.
* [ ] Separar secrets.
* [ ] Revisar CORS.
* [ ] Revisar redirect URIs.
* [ ] Preparar backups.
* [ ] Preparar logs.
* [ ] Probar con 2 o más sistemas reales.

---

# 15. Criterio para decir que Minerva Dev Kit está listo

Minerva Dev Kit puede considerarse listo cuando se cumpla esto:

* [ ] Un desarrollador puede levantarlo con Docker.
* [ ] Un desarrollador puede importar un manifiesto.
* [ ] Un desarrollador puede crear usuarios dev.
* [ ] Un desarrollador puede asignar roles.
* [ ] Un sistema FastAPI puede validar permisos.
* [ ] La integración no requiere tocar la base de datos de Minerva.
* [ ] El cambio a Minerva Central puede hacerse por variables de entorno.
* [ ] Existe documentación suficiente para otro equipo.
* [ ] Existe al menos un sistema real integrado.
* [ ] Existe al menos un ejemplo funcional.

---

# 16. Criterio para decir que Minerva Central está lista

Minerva Central puede considerarse lista cuando se cumpla esto:

* [ ] Login Google Workspace funcionando.
* [ ] Login manual controlado funcionando.
* [ ] Usuarios centralizados.
* [ ] Plataformas reales registradas.
* [ ] Client credentials por plataforma.
* [ ] Manifiestos reales importados.
* [ ] Roles y permisos reales configurados.
* [ ] Sistemas reales conectados.
* [ ] Auditoría básica funcionando.
* [ ] Backups configurados.
* [ ] Logs configurados.
* [ ] HTTPS configurado.
* [ ] Documentación de operación.
* [ ] Documentación para desarrolladores.
* [ ] Plan de recuperación ante fallos.
* [ ] Al menos 2 sistemas internos usando Minerva sin login propio.

---

# 17. Riesgos principales

## Riesgo 1: Que cada sistema integre Minerva diferente

Mitigación:

* SDK oficial.
* Plantillas.
* Ejemplos.
* Revisión de manifiestos.
* Documentación obligatoria.

---

## Riesgo 2: Que se validen roles en lugar de permisos

Mitigación:

* Prohibir validación por rol en código.
* Documentar regla.
* Revisar PRs.
* Usar `require_permission`.

---

## Riesgo 3: Que Minerva Dev y Minerva Central no sean compatibles

Mitigación:

* Mantener contrato estable.
* Usar mismas variables de entorno.
* Mantener mismos endpoints clave.
* Evitar acoplamiento a base de datos.
* Probar migración con un sistema real.

---

## Riesgo 4: Que los manifiestos se vuelvan desordenados

Mitigación:

* Convención estricta.
* Validador.
* Diff.
* Historial de imports.
* Documentación de acciones permitidas.

---

## Riesgo 5: Que Minerva se vuelva demasiado compleja antes de usarse

Mitigación:

* Primero integrar un sistema real.
* Priorizar SDK y manifiestos.
* Evitar OIDC completo en el Dev Kit inicial.
* Endurecer seguridad después de validar el flujo.

---

# 18. Recomendación final de prioridad

Después de tener la primera versión generada, el orden correcto debería ser:

```text
1. Integrar Godín o un sistema real.
2. Mejorar el SDK FastAPI.
3. Robustecer manifiestos.
4. Mejorar panel administrativo.
5. Agregar auditoría básica.
6. Implementar Google Workspace login.
7. Preparar staging.
8. Endurecer seguridad productiva.
9. Conectar un segundo sistema.
10. Formalizar Minerva Central.
```

La prioridad inmediata no es agregar más pantallas ni más features. La prioridad es demostrar que un sistema real puede vivir con Minerva sin implementar login ni permisos propios.

Si eso funciona bien, el resto del proyecto se vuelve mucho más fácil de justificar, priorizar y escalar.
