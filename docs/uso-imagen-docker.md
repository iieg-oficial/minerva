# Uso de la imagen Docker de Minerva

Guía para **consumir Minerva sin clonar el repositorio**, usando las imágenes publicadas
en GitHub Container Registry (ghcr.io). Pensada para miembros de la organización que solo
necesitan levantar Minerva, no desarrollarlo.

Las imágenes son **privadas**: heredan la visibilidad del repositorio, así que solo miembros
de la org con acceso pueden descargarlas.

## 1. Autenticarse contra ghcr (una sola vez)

Necesitas un **Personal Access Token (classic)** de GitHub con el scope `read:packages`.

1. GitHub → Settings → Developer settings → Personal access tokens → Tokens (classic) → *Generate new token*.
2. Marca **solo** `read:packages`. Autoriza el token para la organización (botón *Configure SSO* si aplica).
3. Inicia sesión en el registry:

```bash
echo "TU_PAT" | docker login ghcr.io -u TU_USUARIO_GITHUB --password-stdin
```

## 2. Preparar los archivos

Solo necesitas **tres cosas** en una carpeta (no el repo completo):

```
mi-despliegue/
├── docker-compose.deploy.yml   # descárgalo del repo
├── .env                        # tu configuración (ver sección 4)
└── manifests/                  # tus *.minerva.yml (opcional, ver sección 5)
```

Descarga el compose de consumo:

```bash
curl -O https://raw.githubusercontent.com/iieg-oficial/minerva/main/docker-compose.deploy.yml
```

## 3. Levantar Minerva

```bash
# Elige versión y org (o usa los defaults del compose)
export MINERVA_ORG=iieg-oficial
export MINERVA_VERSION=latest     # o una versión fija: 0.2.1

docker compose -f docker-compose.deploy.yml up -d
```

- Panel/login: `http://localhost:${FRONTEND_PORT}` (default 3100)

El **backend no publica puerto** en este compose: nginx (servicio `frontend`) es el único punto
público y proxea `/.well-known`, `/auth`, `/userinfo`, `/api` y `/api/v1` al backend por la red
interna (`BACKEND_PORT` no aplica aquí, solo al compose de desarrollo). Detalle de rutas en
[`despliegue.md` §2.2](despliegue.md#22-topología-nginx-como-único-punto-público-consolidado).

Las migraciones de base de datos se aplican solas al arrancar el contenedor del backend.

Para actualizar a una versión nueva:

```bash
export MINERVA_VERSION=0.2.2
docker compose -f docker-compose.deploy.yml pull
docker compose -f docker-compose.deploy.yml up -d
```

## 4. Variables de entorno (`.env`)

Parte de `.env.example` del repo. Las variables `MINERVA_*` tienen prioridad sobre sus
equivalentes heredadas (`DATABASE_URL`, `JWT_SECRET_KEY`, etc.).

### Puertos y URLs públicas

| Variable | Default | Descripción |
|---|---|---|
| `BACKEND_PORT` | `9000` | **Solo aplica al compose de desarrollo** (`docker-compose.yml`). Este compose de deploy no publica el backend: nginx lo proxea por la red interna. |
| `FRONTEND_PORT` | `3100` | Puerto expuesto del panel (nginx). En producción real, `80` (o `443` con SSL) — nginx sirve todo. |
| `POSTGRES_PORT` | `5433` | Puerto expuesto de PostgreSQL. |
| `REDIS_PORT` | `6379` | Puerto expuesto de Redis. |
| `FRONTEND_URL` | `http://localhost:3100` | URL pública del panel. Fuera de localhost: `http://<dominio\|IP>` **sin puerto** si `FRONTEND_PORT=80` (nginx consolidado). |
| `MINERVA_JWT_ISSUER` | `http://localhost:9000` | **Issuer** de los tokens OIDC. Fuera de localhost: el mismo host de nginx, **sin `:9000`** (el backend no publica puerto en este deploy); `https://` al tener certificado. |
| `POSTGRES_DB` / `POSTGRES_USER` / `POSTGRES_PASSWORD` | `minerva` / `minerva` / `minerva` | Credenciales de PostgreSQL. **Cambia `POSTGRES_PASSWORD` en producción** (antes venían fijas en el compose; ahora se leen del `.env`). |

### Aplicación

| Variable | Default | Descripción |
|---|---|---|
| `APP_NAME` | `Minerva` | Nombre de la aplicación. |
| `APP_ENV` | `development` | Entorno lógico. En producción: `production`. Junto con `MINERVA_MODE` forma **una sola señal**: es desarrollo solo si ambas lo dicen. |
| `APP_DEBUG` | `true` | Modo debug. **Debe ser `false` en producción**: si no, el backend aborta el arranque. |
| `SECRET_KEY` | — | Cadena aleatoria larga. **Cámbiala en producción.** |

### Minerva Dev Kit / modo de operación

| Variable | Default | Descripción |
|---|---|---|
| `MINERVA_MODE` | `dev` | `dev` o `central`. En despliegues reales normalmente `central`. Cualquier valor distinto de `dev` (o un `APP_ENV` distinto de `development`) activa las validaciones de producción. |
| `MINERVA_DB_URL` | `postgresql://minerva:minerva@minerva-db:5432/minerva` | Conexión a PostgreSQL. Tiene prioridad sobre `DATABASE_URL`. |
| `MINERVA_ENABLE_DEV_LOGIN` | `true` | Habilita el login de desarrollo. **`false` en producción.** |
| `MINERVA_ENABLE_PUBLIC_REGISTER` | `false` | Habilita el registro público self-service en `/auth/register`. Cerrado por defecto: las cuentas las provisiona un admin. |
| `MINERVA_AUTO_IMPORT_MANIFESTS` | `true` | Importa los manifests de `MINERVA_MANIFESTS_PATH` al arrancar. |
| `MINERVA_MANIFESTS_PATH` | `/app/manifests` | Ruta interna donde se leen los manifests (montada como volumen). |
| `MINERVA_JWT_SECRET` | `dev-secret` | Legado; la firma real es RS256. Cámbialo igualmente. |
| `MINERVA_ACCESS_TOKEN_EXPIRE_MINUTES` | `480` | TTL de la sesión del panel (minutos). |

### JWT / OIDC (firma RS256)

| Variable | Default | Descripción |
|---|---|---|
| `MINERVA_KEY_ENCRYPTION_KEY` | vacío | Clave Fernet que cifra la clave RSA privada en reposo. **OBLIGATORIA en producción.** Genera con: `python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"`. En dev, vacía → se deriva del secreto JWT. |
| `MINERVA_ACCESS_TOKEN_TTL_MINUTES` | `15` | TTL del access token OIDC emitido en `/auth/token`. |
| `MINERVA_REFRESH_TOKEN_TTL_DAYS` | `30` | TTL del refresh token (rota en cada uso). |
| `MINERVA_ISSUER` | `http://localhost:9000` | Issuer heredado; respaldo de `MINERVA_JWT_ISSUER`. Misma regla: en producción, sin `:9000`. |
| `JWT_SECRET_KEY` | — | Ya no firma tokens; solo deriva la clave de cifrado en dev. Cámbiala en producción. |

### Administrador inicial

| Variable | Default | Descripción |
|---|---|---|
| `ADMIN_EMAIL` | `admin@iieg.gob.mx` | Correo del admin sembrado al arrancar. |
| `ADMIN_PASSWORD` | `changeme123` | Contraseña del admin. **Cámbiala en producción.** |

### Redis y rate limiting

| Variable | Default | Descripción |
|---|---|---|
| `REDIS_URL` | `redis://minerva_redis:6379/0` | Conexión a Redis (rate limiting, blacklist de tokens, sesiones de `/authorize`). |
| `RATE_LIMIT_LOGIN_MAX` | `5` | Intentos de login permitidos por ventana. |
| `RATE_LIMIT_LOGIN_WINDOW` | `900` | Ventana del rate limit de login (segundos). |
| `RATE_LIMIT_AUTHORIZE_MAX` | `20` | Peticiones a `/authorize` por ventana. |
| `RATE_LIMIT_AUTHORIZE_WINDOW` | `60` | Ventana del rate limit de `/authorize` (segundos). |

## 5. Manifests

Los manifests (`*.minerva.yml`) **no van dentro de la imagen**. Para que Minerva conozca tus
aplicaciones y permisos, coloca los archivos en la carpeta `./manifests` junto al compose:
se montan en `/app/manifests` y, con `MINERVA_AUTO_IMPORT_MANIFESTS=true`, se importan al
arrancar. Si la carpeta está vacía, Minerva arranca sin apps y puedes importarlas después
desde el panel o la API.

## 6. Checklist de producción

Para un despliegue de producción, parte de **`.env.production.example`** (en la raíz del repo):
ya viene con `APP_ENV=production`, `restart: unless-stopped` en los servicios y placeholders
`<...>` para todos los secretos. Cópialo a `.env` y reemplaza los valores.

- [ ] `APP_ENV=production` y `APP_DEBUG=false`.
- [ ] `MINERVA_MODE=central` y `MINERVA_ENABLE_DEV_LOGIN=false`.
- [ ] `SECRET_KEY`, `JWT_SECRET_KEY`, `MINERVA_JWT_SECRET` con valores aleatorios largos.
- [ ] `MINERVA_KEY_ENCRYPTION_KEY` generada y persistida de forma segura.
- [ ] `ADMIN_PASSWORD` cambiada tras el primer acceso.
- [ ] `MINERVA_JWT_ISSUER` / `FRONTEND_URL` con las URLs públicas reales
      (issuer **sin `:9000`**: nginx es el único punto público, ver sección 3).
- [ ] Credenciales de PostgreSQL distintas a las de ejemplo (`minerva:minerva`).
