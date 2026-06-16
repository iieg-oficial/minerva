# Minerva Dev Kit — Visión general y requerimientos iniciales

## 1. Contexto

Minerva es el sistema institucional para gestionar autenticación, usuarios, accesos, roles y permisos de múltiples plataformas internas.

La visión final es que exista una instancia central de Minerva, administrada institucionalmente, que funcione como proveedor de identidad y autorización para sistemas como Godín, Maríachi, Huachicol, SIEEJ y otras plataformas internas.

Sin embargo, antes de llegar a una Minerva central completa, se necesita una versión empaquetada para desarrollo que permita a los equipos integrar sus sistemas desde el inicio siguiendo las mismas políticas de autenticación y permisos.

Esta versión se llamará provisionalmente:

```text
Minerva Dev Kit
```

La idea no es crear una Minerva aislada por cada sistema en producción, sino una instancia local/de desarrollo compatible con la futura Minerva central.

---

## 2. Objetivo del Minerva Dev Kit

El objetivo es permitir que cualquier equipo de desarrollo pueda levantar una instancia local de Minerva junto con su sistema, registrar su plataforma, declarar permisos mediante manifiestos y probar roles, usuarios y accesos desde un panel administrativo.

Esto permitirá que los sistemas se desarrollen desde el principio bajo el contrato correcto:

* No implementar login propio.
* No guardar contraseñas dentro de cada sistema.
* No manejar roles quemados en código.
* No duplicar lógica de permisos.
* Validar acciones mediante permisos explícitos.
* Poder cambiar después de Minerva Dev a Minerva Central usando variables de entorno.

---

## 3. Idea general

Cada sistema consumidor debe poder incluir Minerva en su entorno de desarrollo de forma sencilla.

Ejemplo:

```bash
docker compose up -d
```

Esto debería levantar:

```text
sistema-en-desarrollo
minerva
minerva-db
```

El sistema en desarrollo se conecta a Minerva mediante variables de entorno:

```env
MINERVA_ISSUER_URL=http://minerva:9000
MINERVA_APPLICATION_CODE=godin
MINERVA_CLIENT_ID=godin-dev
MINERVA_CLIENT_SECRET=dev-secret
MINERVA_REDIRECT_URI=http://localhost:8000/auth/callback
```

Cuando exista la Minerva central, el sistema debería poder migrar cambiando solamente configuración:

```env
MINERVA_ISSUER_URL=https://minerva.iieg.gob.mx
MINERVA_CLIENT_ID=godin-prod
MINERVA_CLIENT_SECRET=secret-real
```

---

## 4. Principio arquitectónico

La regla principal es:

```text
Los sistemas definen qué acciones existen.
Minerva define quién puede hacerlas.
Los sistemas validan permisos, no roles.
```

Ejemplo:

Godín declara:

```text
godin.oficios.create
godin.oficios.authorize
godin.solicitudes.assign
```

Minerva administra:

```text
Usuario Alex -> Godín -> Rol Administrador -> permisos correspondientes
```

Godín solamente valida:

```python
@require_permission("godin.oficios.create")
def crear_oficio():
    ...
```

---

## 5. Alcance del MVP

El MVP del Minerva Dev Kit debe incluir:

* Empaquetado Docker para levantar Minerva en desarrollo.
* Panel administrativo ya existente integrado al backend.
* Backend/API de Minerva.
* Base de datos PostgreSQL.
* Manejo de plataformas/aplicaciones.
* Manejo de usuarios de desarrollo.
* Manejo de permisos por plataforma.
* Manejo de roles por plataforma.
* Asignación de roles a usuarios por plataforma.
* Carga de permisos y roles mediante manifiestos YAML.
* Autenticación local/dev.
* Generación de JWT para desarrollo.
* Endpoint para consultar usuario actual.
* Endpoint para consultar permisos del usuario actual.
* Middleware o SDK mínimo para FastAPI.
* Archivo `.env.example`.
* Archivo `docker-compose.yml` o `docker-compose.minerva.yml`.
* Documentación mínima de integración.

---

## 6. Fuera de alcance para el primer MVP

No es necesario implementar todavía:

* Google Workspace login completo.
* OIDC certificado completo.
* MFA.
* SCIM.
* Sincronización con Google Directory.
* Auditoría avanzada.
* Políticas ABAC complejas.
* Jerarquías institucionales complejas.
* Recuperación de contraseñas.
* Administración productiva de secretos.
* Alta formal de usuarios externos.
* Flujos de aprobación de accesos.

El MVP debe priorizar compatibilidad futura, facilidad de integración y estandarización del desarrollo.

---

## 7. Componentes principales

### 7.1 Minerva Admin

Panel administrativo para gestionar:

* Plataformas.
* Usuarios.
* Permisos.
* Roles.
* Asignaciones.
* Manifiestos importados.

La versión actual del proyecto ya cuenta con frontend/panel administrativo empaquetado. Esta parte debe conservarse y conectarse al backend/API necesario.

---

### 7.2 Minerva Core API

Backend principal de Minerva.

Responsabilidades:

* Exponer API REST.
* Administrar usuarios.
* Administrar plataformas.
* Administrar permisos.
* Administrar roles.
* Administrar asignaciones.
* Importar manifiestos.
* Generar tokens JWT para modo desarrollo.
* Exponer endpoints estándar para sistemas consumidores.

---

### 7.3 Minerva DB

Base de datos PostgreSQL con las tablas necesarias para el MVP.

Tablas conceptuales:

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

---

### 7.4 Manifest Loader

Componente encargado de leer archivos `manifest.minerva.yml` y registrar o actualizar en Minerva:

* Plataforma.
* Redirect URIs.
* Permisos.
* Roles.
* Relación rol-permisos.
* Usuarios o asignaciones de desarrollo, si se decide soportar esto.

---

### 7.5 SDK / Middleware

Debe existir al menos un SDK mínimo para FastAPI que permita validar permisos fácilmente.

Ejemplo esperado:

```python
from minerva_sdk.fastapi import require_permission

@router.post("/oficios")
def crear_oficio(
    user=Depends(require_permission("godin.oficios.create"))
):
    return {"message": "Oficio creado"}
```

---

## 8. Manifiesto de plataforma

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

  - key: godin.solicitudes.view
    name: Ver solicitudes
    description: Permite consultar solicitudes de información

  - key: godin.solicitudes.assign
    name: Asignar solicitudes
    description: Permite asignar solicitudes a usuarios

roles:
  - name: Consulta
    description: Usuario de solo lectura
    permissions:
      - godin.oficios.view
      - godin.solicitudes.view

  - name: Capturista
    description: Usuario que puede capturar información
    permissions:
      - godin.oficios.view
      - godin.oficios.create
      - godin.solicitudes.view

  - name: Administrador
    description: Control total del sistema
    permissions:
      - godin.oficios.view
      - godin.oficios.create
      - godin.oficios.authorize
      - godin.solicitudes.view
      - godin.solicitudes.assign
```

---

## 9. Convención de permisos

Todos los permisos deben seguir esta estructura:

```text
{application_code}.{resource}.{action}
```

Ejemplos:

```text
godin.oficios.view
godin.oficios.create
godin.oficios.update
godin.oficios.authorize

mariachi.database.view
mariachi.database.create
mariachi.table.update

huachicol.monitor.view
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
* `update`: edición.
* `delete`: eliminación.
* `assign`: asignación de responsables.
* `approve`: aprobación.
* `authorize`: autorización formal.
* `export`: exportación de datos.
* `import`: importación de datos.
* `manage`: administración general.

---

## 10. Endpoints mínimos esperados

### Salud

```http
GET /health
```

---

### Usuario actual

```http
GET /api/v1/me
```

Respuesta esperada:

```json
{
  "id": "usr_123",
  "email": "alex@iieg.gob.mx",
  "full_name": "Alex",
  "status": "active"
}
```

---

### Permisos del usuario actual

```http
GET /api/v1/me/permissions?application=godin
```

Respuesta esperada:

```json
{
  "application": "godin",
  "roles": ["Administrador"],
  "permissions": [
    "godin.oficios.view",
    "godin.oficios.create",
    "godin.oficios.authorize"
  ]
}
```

---

### Importar manifiesto

```http
POST /api/v1/manifests/import
```

---

### CRUD administrativo

```http
GET    /api/v1/applications
POST   /api/v1/applications
GET    /api/v1/applications/{id}
PATCH  /api/v1/applications/{id}

GET    /api/v1/users
POST   /api/v1/users
GET    /api/v1/users/{id}
PATCH  /api/v1/users/{id}

GET    /api/v1/roles
POST   /api/v1/roles
GET    /api/v1/roles/{id}
PATCH  /api/v1/roles/{id}

GET    /api/v1/permissions
POST   /api/v1/permissions

GET    /api/v1/access-assignments
POST   /api/v1/access-assignments
DELETE /api/v1/access-assignments/{id}
```

---

## 11. Tokens en modo desarrollo

Para el MVP, Minerva Dev debe poder emitir tokens JWT locales para simular sesiones reales.

Claims sugeridos:

```json
{
  "iss": "http://localhost:9000",
  "sub": "usr_123",
  "email": "alex@iieg.gob.mx",
  "name": "Alex",
  "applications": ["godin"],
  "roles": {
    "godin": ["Administrador"]
  }
}
```

Los permisos finos deben consultarse mediante el endpoint:

```http
GET /api/v1/me/permissions?application=godin
```

Esto permite que los permisos sean más dinámicos y evita depender completamente del contenido del token.

---

## 12. Docker Compose esperado

El proyecto debe permitir levantar Minerva Dev con algo similar a:

```yaml
services:
  minerva:
    build: .
    ports:
      - "9000:9000"
    environment:
      MINERVA_MODE: dev
      MINERVA_DB_URL: postgresql://minerva:minerva@minerva-db:5432/minerva
      MINERVA_ENABLE_DEV_LOGIN: "true"
      MINERVA_AUTO_IMPORT_MANIFESTS: "true"
      MINERVA_JWT_ISSUER: http://localhost:9000
      MINERVA_JWT_SECRET: dev-secret
    volumes:
      - ./manifest.minerva.yml:/app/manifests/manifest.minerva.yml
    depends_on:
      - minerva-db

  minerva-db:
    image: postgres:17
    environment:
      POSTGRES_USER: minerva
      POSTGRES_PASSWORD: minerva
      POSTGRES_DB: minerva
    volumes:
      - minerva_data:/var/lib/postgresql/data

volumes:
  minerva_data:
```

---

## 13. Integración esperada en sistemas consumidores

Cada sistema debe configurar Minerva mediante variables de entorno:

```env
MINERVA_ISSUER_URL=http://localhost:9000
MINERVA_APPLICATION_CODE=godin
MINERVA_CLIENT_ID=godin-dev
MINERVA_CLIENT_SECRET=dev-secret
MINERVA_REDIRECT_URI=http://localhost:8000/auth/callback
MINERVA_PERMISSIONS_CACHE_TTL=300
```

Y debe validar permisos con middleware o SDK.

Ejemplo:

```python
@router.post("/oficios")
def crear_oficio(
    user=Depends(require_permission("godin.oficios.create"))
):
    ...
```

---

## 14. Reglas para los equipos de desarrollo

Los sistemas que se integren con Minerva deben cumplir:

1. No implementar login propio.
2. No guardar contraseñas propias.
3. No manejar roles quemados en código.
4. No validar con `if user.role == "Administrador"`.
5. Validar siempre permisos explícitos.
6. Declarar todos los permisos en `manifest.minerva.yml`.
7. Guardar solo `minerva_user_id` cuando se necesite trazabilidad.
8. Poder cambiar de Minerva Dev a Minerva Central usando variables de entorno.
9. No conectarse directamente a la base de datos de Minerva.
10. Usar únicamente API, JWT, SDK o middleware.

---

## 15. Resultado esperado

El resultado esperado de esta primera etapa es un empaquetado funcional de Minerva que sirva para desarrollo local y pruebas de integración.

Debe permitir que los equipos puedan:

* Levantar Minerva localmente.
* Entrar al panel administrativo.
* Registrar su plataforma mediante manifiesto.
* Crear usuarios de prueba.
* Asignar roles.
* Probar permisos.
* Proteger endpoints.
* Prepararse para migrar a una Minerva central.

La meta no es resolver toda la arquitectura IAM institucional desde el primer sprint, sino crear una base sólida y estandarizada para que todos los sistemas nuevos nazcan compatibles con Minerva.
