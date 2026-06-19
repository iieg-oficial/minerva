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
> - **Visión y requerimientos:** [`docs/minerva-dev-kit-context.md`](docs/minerva-dev-kit-context.md)
> - **Guía de uso (levantar, login dev, manifiestos, permisos, SDK):** [`docs/minerva-dev-kit.md`](docs/minerva-dev-kit.md)
> - **SDK para consumidores (FastAPI):** [`sdk/`](sdk) · **Ejemplo:** [`examples/godin-consumer/`](examples/godin-consumer)
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
| Auth | JWT (HS256), Passlib + bcrypt, Authlib (Google OAuth) |
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
> contrato de desarrollo vive bajo `/api/v1` (ver [`docs/minerva-dev-kit.md`](docs/minerva-dev-kit.md)).

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
| `JWT_SECRET_KEY` | Clave secreta para firmar JWT | (cambiar en producción) |
| `JWT_ALGORITHM` | Algoritmo JWT | HS256 |
| `ACCESS_TOKEN_EXPIRE_MINUTES` | Expiración del token (minutos) | 480 |
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
| `GET` | `/auth/authorize` | Endpoint de autorización OAuth2 (redirect) |
| `GET` | `/auth/authorize/url` | Variante JSON de `/auth/authorize` (devuelve la URL de redirección; la usa el frontend SPA) |
| `POST` | `/auth/token` | Intercambiar código por token |
| `POST` | `/auth/refresh` | Refrescar token JWT |

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
| `POST` | `/applications` | Crear aplicación (genera client_id y client_secret) |
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

### Paso 1: Registrar la aplicación en Minerva

```http
POST /applications
Content-Type: application/json

{
  "name": "Godín",
  "slug": "godin",
  "description": "Sistema de gestión de oficios, memos y solicitudes",
  "homepage_url": "https://godin.iieg.gob.mx"
}
```

**Respuesta:**
```json
{
  "id": "uuid",
  "name": "Godín",
  "slug": "godin",
  "client_id": "uuid-del-cliente",
  "client_secret_hash": "secret-en-texto-plano-solo-en-creacion",
  "status": "active",
  ...
}
```

> Guarda el `client_id` y `client_secret_hash` (el secret real). El secret no se volverá a mostrar.

### Paso 2: Registrar redirect URIs

```http
POST /applications/{app_id}/redirect-uris
Content-Type: application/json

{
  "uri": "https://godin.iieg.gob.mx/auth/callback",
  "environment": "production"
}
```

### Paso 3: Definir roles y permisos

```http
POST /roles?application_id={app_id}
{
  "name": "Administrador",
  "slug": "godin.admin"
}

POST /permissions?application_id={app_id}
{
  "name": "Crear oficios",
  "slug": "godin.oficios.crear"
}
```

Asignar permisos a roles:
```http
POST /roles/{role_id}/permissions/{permission_id}
```

### Paso 4: Asignar roles a usuarios o grupos

```http
POST /groups/users/{user_id}/roles/{role_id}
```

### Paso 5: Redirigir login desde la aplicación cliente

Cuando un usuario no tenga sesión, redirige al navegador a la página de
autorización del **frontend** de Minerva (no al API). El frontend muestra el
login si hace falta y, una vez autenticado, llama al API y regresa al cliente:

```
GET https://minerva.iieg.gob.mx/authorize
  ?client_id=CLIENT_ID_DE_GODIN
  &redirect_uri=https://godin.iieg.gob.mx/auth/callback
  &response_type=code
  &scope=openid profile email
  &state=RANDOM_STATE
```

> En desarrollo lado-a-lado, el frontend de Minerva corre en
> `http://localhost:3100` (el API en `http://localhost:9000`). La página
> `/authorize` lee estos parámetros, autentica al usuario y, vía
> `GET /auth/authorize/url` (variante JSON de `/auth/authorize`), obtiene la
> URL de regreso con el `code` y redirige el navegador al cliente.

Minerva redirige de regreso a:

```
https://godin.iieg.gob.mx/auth/callback?code=AUTH_CODE&state=RANDOM_STATE
```

### Paso 6: Intercambiar código por token

```http
POST /auth/token
Content-Type: application/json

{
  "client_id": "CLIENT_ID",
  "client_secret": "CLIENT_SECRET",
  "code": "AUTH_CODE",
  "redirect_uri": "https://godin.iieg.gob.mx/auth/callback"
}
```

**Respuesta:**
```json
{
  "access_token": "eyJhbGci...",
  "token_type": "bearer",
  "expires_in": 28800
}
```

### Paso 7: Validar token en la aplicación externa

El token JWT contiene:

```json
{
  "sub": "user_id",
  "email": "usuario@iieg.gob.mx",
  "name": "Nombre Completo",
  "iss": "https://minerva.iieg.gob.mx",
  "aud": "godin",
  "roles": ["godin.admin"],
  "permissions": ["godin.oficios.ver", "godin.oficios.crear"],
  "iat": 1234567890,
  "exp": 1234571490
}
```

Cada sistema debe validar:
- Firma del JWT (con `JWT_SECRET_KEY` compartido o clave pública)
- Fecha de expiración (`exp`)
- Issuer (`iss`)
- Audience (`aud`)
- Permisos o roles incluidos

### Ejemplo de integración con FastAPI

```python
# En tu aplicación externa
import requests
from fastapi import FastAPI, Depends, HTTPException
from fastapi.security import HTTPBearer
from jose import jwt

JWT_SECRET = "misma-clave-que-minerva"
MINERVA_ISSUER = "https://minerva.iieg.gob.mx"
APP_SLUG = "godin"

bearer = HTTPBearer(auto_error=False)

def get_current_user(token=Depends(bearer)):
    try:
        payload = jwt.decode(token.credentials, JWT_SECRET, algorithms=["HS256"])
        if payload["iss"] != MINERVA_ISSUER:
            raise HTTPException(401, "Issuer inválido")
        return payload
    except Exception:
        raise HTTPException(401, "Token inválido")

def require_permission(permission: str):
    def dependency(user=Depends(get_current_user)):
        if permission not in user.get("permissions", []):
            raise HTTPException(403, f"Requiere permiso: {permission}")
        return user
    return dependency

app = FastAPI()

@app.post("/oficios")
def crear_oficio(user=Depends(require_permission("godin.oficios.crear"))):
    return {"message": "Oficio creado", "user": user["email"]}
```

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
```

## Pruebas

```bash
cd backend
pip install -e ".[dev]"
pytest tests/ -v
```

## Decisiones técnicas y TODOs

### MVP vs producción

- **Refresh tokens**: El endpoint `/auth/refresh` extiende la sesión con un nuevo JWT, pero no implementa refresh token separado. **TODO**: Implementar refresh tokens con rotación.
- **Google OAuth**: Los endpoints `/auth/google/login` y `/auth/google/callback` están preparados pero requieren configuración de `GOOGLE_CLIENT_ID` y `GOOGLE_CLIENT_SECRET`. **TODO**: Completar integración con Authlib para intercambio de tokens.
- **OAuth2/OpenID Connect**: El flujo `/authorize` y `/token` es una implementación simplificada. **TODO**: Evolucionar hacia un flujo completo compatible con OAuth2/OpenID Connect.
- **Sesiones**: Los JWT son stateless (no hay tabla de sesiones activas). Para blacklisting de tokens se necesitaría una tabla de tokens revocados.
- **Roles por aplicación**: Los roles y permisos están asociados a una aplicación específica.
- **Grupos**: Los usuarios heredan roles de los grupos a los que pertenecen. Los roles directos + roles de grupo se combinan para calcular permisos efectivos.

## Licencia

Proyecto interno del IIEG. Uso institucional.
