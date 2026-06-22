# Minerva

Sistema institucional de autenticación, autorización y gestión de accesos para las plataformas internas del IIEG.

Minerva funciona como el sistema central de identidad y acceso del instituto, similar al mecanismo de "Iniciar sesión con Google": las plataformas internas redirigen el login hacia Minerva, y Minerva se encarga de autenticar al usuario, validar su identidad, revisar sus permisos y devolver un token JWT.

> ## 🧰 Minerva Dev Kit
>
> Este repositorio se empaqueta también como **Minerva Dev Kit**: una instancia
> local/de desarrollo de Minerva, compatible con la futura Minerva Central, que
> permite a otros equipos levantar Minerva junto a su sistema, declarar permisos
> mediante manifiestos YAML, administrar roles/usuarios y desarrollar bajo el
> mismo contrato (`/api/v1`).
>
> - **Arquitectura (con diagramas):** [`docs/arquitectura.md`](docs/arquitectura.md)
> - **Glosario OIDC/OAuth:** [`docs/glosario.md`](docs/glosario.md)
> - **Despliegue Dev/Prod + mantenimiento:** [`docs/despliegue.md`](docs/despliegue.md)
> - **Integrar tu sistema (OIDC, login delegado, paso a paso):** [`docs/integracion.md`](docs/integracion.md)
> - **SDK para consumidores (FastAPI):** [`sdk/`](sdk)
>
> Inicio rápido: `cp .env.example .env && docker compose up --build` →
> API en http://localhost:9000 · panel en http://localhost:3000.

## Requisitos

- Python 3.12+
- Docker y Docker Compose
- Node.js 22+ (solo para desarrollo del frontend)

## Stack tecnológico

| Capa | Tecnología |
|---|---|
| Backend | Python 3.12, FastAPI, SQLModel, Alembic, PostgreSQL |
| Auth | OIDC (Authorization Code + PKCE), JWT RS256/JWKS, bcrypt |
| Frontend | React 19, Ant Design 6, Vite |
| Infra | Docker, Docker Compose, Nginx |
| Calidad | Ruff, Pytest |

## Inicio rápido

```bash
# Clonar y entrar al proyecto
cd Minerva

# Copiar variables de entorno
cp .env.example .env

# Editar .env con tus valores (especialmente GOOGLE_CLIENT_ID, GOOGLE_CLIENT_SECRET si usarás Google OAuth)

# Levantar el proyecto
docker compose up --build
```

Una vez levantado:
- **API**: http://localhost:9000
- **Documentación API**: http://localhost:9000/docs
- **Frontend (login / panel admin)**: http://localhost:3000

> El backend se expone en el puerto **9000** (contrato Minerva Dev Kit). El
> contrato de desarrollo vive bajo `/api/v1` (ver [`docs/integracion.md`](docs/integracion.md)).

### Usuario administrador por defecto

Al iniciar por primera vez, se crea automáticamente:
- **Email**: `admin@iieg.gob.mx`
- **Password**: `changeme123`

Modifica estos valores en el `.env` con `ADMIN_EMAIL` y `ADMIN_PASSWORD`.

## Variables de entorno (`.env`)

| Variable | Descripción | Por defecto |
|---|---|---|
| `APP_NAME` | Nombre de la aplicación | Minerva |
| `APP_ENV` | Entorno (development / production) | development |
| `APP_DEBUG` | Modo debug | true |
| `DATABASE_URL` | URL de conexión a PostgreSQL | postgresql+psycopg://minerva:minerva@postgres:5432/minerva |
| `JWT_SECRET_KEY` | Base para derivar la clave de cifrado en reposo en dev (la firma de tokens es RS256, no usa este secreto) | (cambiar en producción) |
| `ACCESS_TOKEN_EXPIRE_MINUTES` | Expiración del token de sesión interna del panel (minutos) | 480 |
| `MINERVA_ACCESS_TOKEN_TTL_MINUTES` | Expiración del access token emitido por el canje OIDC (minutos) | 15 |
| `MINERVA_KEY_ENCRYPTION_KEY` | Clave Fernet para cifrar la clave privada RSA en reposo (obligatoria en producción) | (vacío en dev) |
| `GOOGLE_CLIENT_ID` | Client ID de Google OAuth | (vacío) |
| `GOOGLE_CLIENT_SECRET` | Client Secret de Google OAuth | (vacío) |
| `GOOGLE_REDIRECT_URI` | URI de callback para Google OAuth | http://localhost:8000/auth/google/callback |
| `ALLOWED_GOOGLE_DOMAIN` | Dominio permitido para Google OAuth | iieg.gob.mx |
| `MINERVA_ISSUER` | Issuer de los tokens | http://localhost:8000 |

## Endpoints de la API (MVP)

> **Autorización del panel:** los endpoints de gestión (`/users`, `/applications`,
> `/roles`, `/permissions`, `/groups`, `/audit` y `/authorization/check`) exigen el
> rol global `minerva.admin` (dependencia `require_minerva_admin`), no basta con
> estar autenticado. Los endpoints self-service (`/auth/*`,
> `/authorization/me/permissions`) solo requieren un token válido.

### Auth

| Método | Ruta | Descripción |
|---|---|---|
| `POST` | `/auth/register` | Registro manual (email + contraseña) |
| `POST` | `/auth/login` | Login manual (email + contraseña) |
| `POST` | `/auth/logout` | Cerrar sesión |
| `GET` | `/auth/me` | Obtener usuario actual con roles y permisos |
| `GET` | `/auth/google/login` | Iniciar login con Google |
| `GET` | `/auth/google/callback` | Callback de Google OAuth |
| `GET` | `/auth/authorize` | Endpoint de autorización OIDC (redirect; soporta `prompt`/`max_age`) |
| `GET` | `/auth/authorize/url` | Variante JSON de `/auth/authorize` (devuelve la URL de redirección; la usa el frontend SPA) |
| `POST` | `/auth/token` | Intercambiar código por tokens (`authorization_code`/`refresh_token`; PKCE obligatorio para clientes públicos) |
| `POST` | `/auth/revoke` | Revocar un refresh token y su familia (RFC 7009) |
| `POST` | `/auth/refresh` | Refrescar el token de sesión interna del panel |
| `GET` | `/userinfo` | Claims de identidad filtrados por scope (OIDC Core 5.3, Bearer, CORS abierto) |
| `GET` | `/.well-known/openid-configuration` | Discovery OIDC |
| `GET` | `/.well-known/jwks.json` | Claves públicas RS256 (JWKS) |

### Users

| Método | Ruta | Descripción |
|---|---|---|
| `GET` | `/users` | Listar usuarios |
| `GET` | `/users/{user_id}` | Obtener usuario |
| `POST` | `/users` | Crear usuario |
| `PATCH` | `/users/{user_id}` | Actualizar usuario |
| `PATCH` | `/users/{user_id}/status` | Cambiar estado del usuario |

### Applications

| Método | Ruta | Descripción |
|---|---|---|
| `GET` | `/applications` | Listar aplicaciones |
| `POST` | `/applications` | Crear aplicación (genera client_id y client_secret; `is_public: true` registra un cliente público sin secret) |
| `GET` | `/applications/{app_id}` | Obtener aplicación |
| `PATCH` | `/applications/{app_id}` | Actualizar aplicación |
| `POST` | `/applications/{app_id}/redirect-uris` | Agregar redirect URI |
| `GET` | `/applications/{app_id}/redirect-uris` | Listar redirect URIs |

### Roles

| Método | Ruta | Descripción |
|---|---|---|
| `GET` | `/roles` | Listar roles (filtrar por `?application_id=`) |
| `POST` | `/roles` | Crear rol |
| `GET` | `/roles/{role_id}` | Obtener rol |
| `PATCH` | `/roles/{role_id}` | Actualizar rol |
| `DELETE` | `/roles/{role_id}` | Eliminar rol |
| `POST` | `/roles/{role_id}/permissions/{perm_id}` | Asignar permiso a rol |
| `DELETE` | `/roles/{role_id}/permissions/{perm_id}` | Quitar permiso de rol |
| `GET` | `/roles/{role_id}/permissions` | Listar permisos del rol |

### Permissions

| Método | Ruta | Descripción |
|---|---|---|
| `GET` | `/permissions` | Listar permisos (filtrar por `?application_id=`) |
| `POST` | `/permissions` | Crear permiso |
| `GET` | `/permissions/{perm_id}` | Obtener permiso |
| `PATCH` | `/permissions/{perm_id}` | Actualizar permiso |

### Groups

| Método | Ruta | Descripción |
|---|---|---|
| `GET` | `/groups` | Listar grupos |
| `POST` | `/groups` | Crear grupo |
| `GET` | `/groups/{group_id}` | Obtener grupo |
| `PATCH` | `/groups/{group_id}` | Actualizar grupo |
| `POST` | `/groups/{group_id}/users/{user_id}` | Agregar usuario a grupo |
| `DELETE` | `/groups/{group_id}/users/{user_id}` | Quitar usuario de grupo |
| `POST` | `/groups/{group_id}/roles/{role_id}` | Asignar rol a grupo |
| `DELETE` | `/groups/{group_id}/roles/{role_id}` | Quitar rol de grupo |
| `POST` | `/groups/users/{user_id}/roles/{role_id}` | Asignar rol directo a usuario |
| `DELETE` | `/groups/users/{user_id}/roles/{role_id}` | Quitar rol directo de usuario |

### Authorization

| Método | Ruta | Descripción |
|---|---|---|
| `POST` | `/authorization/check` | Validar si un usuario tiene un permiso |
| `GET` | `/authorization/me/permissions` | Permisos efectivos del usuario actual |

### Audit

| Método | Ruta | Descripción |
|---|---|---|
| `GET` | `/audit` | Listar logs de auditoría |

## Modos de autenticación

### Login manual (email + contraseña)

Para usuarios que no tienen cuenta de Google Workspace.

1. Registrar usuario: `POST /auth/register`
2. Iniciar sesión: `POST /auth/login`
3. Obtener perfil: `GET /auth/me`

```json
// POST /auth/register
{
  "email": "usuario@ejemplo.com",
  "full_name": "Nombre Completo",
  "password": "contraseña-segura"
}

// Respuesta
{
  "access_token": "eyJhbGci...",
  "token_type": "bearer",
  "expires_in": 28800
}
```

### Login con Google Workspace

Para usuarios del IIEG y gobierno con cuenta de Google Workspace.

1. Redirigir al usuario a `GET /auth/google/login`
2. Google autentica y redirige a `/auth/google/callback`
3. Minerva crea/actualiza el usuario interno (con `auth_provider: google`)
4. Minerva valida el dominio (`@iieg.gob.mx`)
5. Se genera token JWT

> **Nota:** El usuario puede existir en Google, pero Minerva decide si está activo y qué permisos tiene. No se asume acceso automático.

## Cómo integrar un nuevo sistema con Minerva

El login se delega por completo a Minerva: el usuario se autentica en Minerva y
vuelve a tu sistema con un JWT y sus permisos. El resumen es:

1. **Registra tu aplicación** en el panel (o `POST /applications`) y guarda el
   `client_id` y el `client_secret`; registra tu redirect URI.
2. **Declara permisos y roles** en un `manifest.minerva.yml` e impórtalo.
3. **Configura variables** en tu sistema: `MINERVA_ISSUER_URL` la usa tu backend
   (server-a-server), `MINERVA_LOGIN_URL` la usa el navegador, y tu
   `MINERVA_JWT_SECRET` debe coincidir con el secreto efectivo de Minerva.
4. En tu **backend** implementa `/auth/login` (redirige a Minerva),
   `/auth/callback` (canjea el `code` por el JWT) y `/auth/logout` (single
   logout), y valida el JWT + permisos.
5. En tu **frontend** quita el login propio (si lo tenía): un botón manda a
   `/api/auth/login` y una página de callback recibe el token.

📖 **Guía completa de integración OIDC**, paso a paso (registro, manifiesto, flujo
Authorization Code + PKCE, validación con el SDK RS256/JWKS, refresh y troubleshooting):
**[`docs/integracion.md`](docs/integracion.md)**.

## Estructura del proyecto

```
minerva/
  .env.example                  # Variables de entorno
  docker-compose.yml            # Orquestación de servicios
  README.md
  backend/
    Dockerfile
    pyproject.toml              # Dependencias Python
    alembic.ini                 # Configuración Alembic
    scripts/
      backend-entrypoint.sh     # Entrypoint (migraciones + uvicorn)
    alembic/
      env.py
      versions/001_initial.py   # Migración inicial (todas las tablas)
    tests/
      conftest.py
      test_auth.py
      test_users.py
      test_applications.py
      test_roles_permissions.py
      test_authorization.py
    app/
      main.py                   # FastAPI entry point, lifespan, CORS, routers
      core/
        config.py               # Pydantic Settings
        database.py             # Engine, get_session
        security.py             # JWT, bcrypt, hash_secret
        exceptions.py           # HTTP exceptions
        models.py               # Model registry (import_models)
        dependencies/
          auth.py               # get_current_user, get_optional_user
          db.py                 # get_db
      shared/
        pagination.py           # PaginatedResponse[T]
      modules/
        auth/                   # router, service, schemas, models, repository
        users/                  # router, service, schemas, models, repository
        applications/           # router, service, schemas, models, repository
        roles/                  # router, service, schemas, models, repository
        permissions/            # router, service, schemas, models, repository
        groups/                 # router, service, schemas, models, repository
        authorization/          # router, service, schemas
        audit/                  # router, service, models, repository
  frontend/
    Dockerfile
    nginx.conf
    package.json
    vite.config.js
    public/                     # Assets institucionales (fuentes, logos, fondos)
    src/
      main.jsx                  # Entry point, ConfigProvider
      App.jsx                   # Routes
      index.css                 # Estilos globales, Garet font
      api/
        client.js               # Axios con interceptors
        auth.js                 # Auth API calls
      features/auth/pages/
        LoginPage.jsx           # Login institucional
        AuthorizePage.jsx       # Punto de entrada OIDC para sistemas consumidores
  examples/
    godin-consumer/             # Ejemplo de integración con el SDK (cliente público, PKCE)
  sdk/
    minerva_sdk/                # SDK para sistemas consumidores (get_current_user, require_permission)
```

## Pruebas

```bash
cd backend
pip install -e ".[dev]"
pytest tests/ -v
```

## Decisiones técnicas y TODOs

### MVP vs producción

- **OIDC**: el flujo `/authorize` + `/token` es un proveedor OIDC conforme
  (Authorization Code + PKCE, discovery, JWKS, `/userinfo`, clientes públicos,
  `prompt`/`max_age`, refresh con rotación y revocación) — ver
  [`docs/arquitectura.md`](docs/arquitectura.md) e [`docs/integracion.md`](docs/integracion.md).
- **Google OAuth**: los endpoints `/auth/google/login` y `/auth/google/callback`
  están preparados pero requieren configuración de `GOOGLE_CLIENT_ID` y
  `GOOGLE_CLIENT_SECRET`. **TODO**: completar integración con Authlib para el
  intercambio de tokens (se rastrea en un issue aparte).
- **Sesiones**: la blacklist de access tokens revocados vive en Redis (`jti`),
  con alcance acotado (rate limiting, blacklist, no es fuente de verdad).
- **Roles por aplicación**: los roles y permisos están asociados a una aplicación específica.
- **Grupos**: los usuarios heredan roles de los grupos a los que pertenecen. Los roles directos + roles de grupo se combinan para calcular permisos efectivos.
- **Endurecimiento de producción** (TLS, secret manager, runbook de rotación de
  claves, observabilidad, backups): ver [`docs/despliegue.md`](docs/despliegue.md) sección 2.4.

## Licencia

Proyecto interno del IIEG. Uso institucional.
