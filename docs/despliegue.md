# Guía de despliegue: Dev, Producción y Mantenimiento

> Ver [`arquitectura.md`](arquitectura.md) para el panorama general y
> [`glosario.md`](glosario.md) para los términos OIDC usados aquí.

## 1. Desarrollo

```bash
cp .env.example .env
docker compose up --build
```

Servicios:

| Servicio | Puerto host (default) | Notas |
|---|---|---|
| Backend (FastAPI) | `9000` | `BACKEND_PORT`; docs OpenAPI en `/docs` |
| Frontend (panel admin) | `3100` | `FRONTEND_PORT` |
| PostgreSQL | `5433` | `POSTGRES_PORT` (mapeado a 5432 dentro del contenedor) |
| Redis | `6379` | `REDIS_PORT` |

Al arrancar (`lifespan` en `backend/app/main.py`), el backend:
1. Valida la configuración (`validate_production_config()` — no falla en modo dev).
2. Aplica migraciones Alembic (`alembic upgrade head`, en el entrypoint).
3. Siembra (`_seed_data`) el usuario administrador y la aplicación `minerva` si no existen.
4. Garantiza una clave de firma RS256 activa (`_seed_signing_key`, idempotente).
5. Auto-importa manifiestos desde `MINERVA_MANIFESTS_PATH` si `MINERVA_AUTO_IMPORT_MANIFESTS=true`.

### ⚠️ Gotcha de puertos: 8000 vs 9000

El backend se sirve en **9000** (Dockerfile, docker-compose, entrypoint). Algunos
valores legacy en `.env`/`config.py` (`GOOGLE_REDIRECT_URI`, comentarios viejos)
todavía mencionan **8000**. Si tocas configuración de red/proxy/redirects, verifica el
puerto extremo a extremo (`MINERVA_ISSUER`, `GOOGLE_REDIRECT_URI`, `vite.config.js`)
antes de asumir que un solo lado está mal.

### Correr el backend sin Docker (conda)

```bash
conda create -n minerva python=3.12   # una sola vez
conda activate minerva
cd backend
pip install -e ".[dev]"
# Requiere PostgreSQL y Redis accesibles; ajusta DATABASE_URL/REDIS_URL en .env
alembic upgrade head
uvicorn app.main:app --reload --port 9000
```

### Usuario administrador por defecto

Se crea automáticamente al primer arranque si no existe:
- Email: `ADMIN_EMAIL` (default `admin@iieg.gob.mx`)
- Password: `ADMIN_PASSWORD` (default `changeme123` — **cambiar antes de producción**)

## 2. Producción

### 2.1 Variables obligatorias

`Settings.validate_production_config()` (`backend/app/core/config.py`) se ejecuta en el
`lifespan` del backend y **aborta el arranque** si `MINERVA_MODE != dev` y detecta
cualquiera de estos problemas:

| Variable | Requisito en producción |
|---|---|
| `MINERVA_MODE` | distinto de `dev` (p. ej. `production`) |
| `MINERVA_ENABLE_DEV_LOGIN` | debe ser `false` |
| `ADMIN_PASSWORD` | distinto del default `changeme123` |
| `SECRET_KEY` | sin la cadena `change-me-in-production` |
| `JWT_SECRET_KEY` | sin la cadena `change-me-in-production` |
| `MINERVA_KEY_ENCRYPTION_KEY` | no vacía — clave Fernet para cifrar la clave privada RSA en reposo |

Genera `MINERVA_KEY_ENCRYPTION_KEY` con:

```bash
python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
```

Reporta **todos** los problemas encontrados de una vez (no se detiene en el primero),
para no tener que iterar arranque por arranque.

### 2.2 Topología: nginx como único punto público (consolidado)

El deploy (`docker-compose.deploy.yml`) expone **un solo servicio público: nginx** (servicio
`frontend`). nginx sirve la SPA y proxea al backend por la red interna:

| Ruta pública | Destino | Uso |
|---|---|---|
| `/` (y rutas SPA `/login`, `/admin`, `/authorize`) | estático | Panel/login |
| `/.well-known/`, `/auth/`, `/userinfo` | backend (raíz) | Discovery/JWKS, authorize/token/revoke, userinfo (consumidores OIDC) |
| `/api/v1/` | backend (preserva path) | SDK / Minerva Dev Kit |
| `/api/` | backend (elimina el prefijo `/api`) | Llamadas del panel admin |

Implicaciones:

- El **backend NO publica puerto** en el deploy (solo nginx lo alcanza). El issuer queda en
  `http://<host>` **sin `:9000`**.
- El backend recibe `FORWARDED_ALLOW_IPS=*` (seguro: nadie más que nginx lo alcanza), así honra
  `X-Forwarded-For` y el **rate limit de login se cuenta por IP real del cliente**, no por la de nginx.
- SSL futuro = terminar TLS en este nginx (un solo lugar); `nginx.conf` ya envía `X-Forwarded-Proto`.
- **Cabeceras defensivas:** `nginx.conf` emite CSP (con `frame-ancestors 'none'`),
  `X-Content-Type-Options: nosniff` y `Referrer-Policy`. La CSP permite `style-src 'unsafe-inline'`
  por Ant Design (cssinjs) e `img-src ... https:` para los logos de branding por app (`logo_url`).
  **HSTS no lo emite este nginx** (sirve solo `:80`; el navegador ignora un HSTS recibido por HTTP):
  configúralo en el **terminador TLS** que va delante, con
  `add_header Strict-Transport-Security "max-age=63072000; includeSubDomains" always;` — **sin
  `preload`** por defecto (es difícil de revertir y exige HTTPS en todos los subdominios). La cookie de
  sesión del panel usa el prefijo `__Host-` (exige HTTPS): en HTTP local se usa `minerva_sid` sin
  `Secure`, derivado de `MINERVA_MODE`.
- **Redis es control de seguridad, no solo caché.** Además del rate limit, guarda la blacklist de
  `jti`, los cortes de invalidación por usuario y el **contenedor de sesión del panel**. Perder Redis
  cierra las sesiones del panel y re-habilita tokens revocados: en producción, persistencia
  (`appendonly`) y `maxmemory-policy noeviction` para su keyspace de seguridad.

### 2.3 Variables a revisar/ajustar

- `MINERVA_ISSUER` / `MINERVA_JWT_ISSUER`: URL pública real de Minerva = **el host de nginx, sin
  `:9000`** (p. ej. `http://minerva.jalisco.gob.mx`; `https://…` al tener certificado). Aparece como
  `iss` en cada token y en el discovery; debe coincidir con lo que ven los consumidores.
- `FRONTEND_URL`: mismo host público del panel (entra en la whitelist de CORS).
- `MINERVA_ACCESS_TOKEN_TTL_MINUTES` / `MINERVA_REFRESH_TOKEN_TTL_DAYS`: ciclo de vida
  de los tokens OIDC emitidos a consumidores.
- `RATE_LIMIT_LOGIN_MAX` / `RATE_LIMIT_LOGIN_WINDOW` / `RATE_LIMIT_AUTHORIZE_MAX` /
  `RATE_LIMIT_AUTHORIZE_WINDOW`: ajustar según tráfico esperado.
- `DATABASE_URL`: apuntar a la instancia real de PostgreSQL (con TLS si la red no es de
  confianza).

### 2.4 Cómo correr el contenedor en modo producción

El entrypoint (`backend/scripts/backend-entrypoint.sh`) decide el servidor según
`MINERVA_MODE`:

- `MINERVA_MODE=dev` → `uvicorn --reload` (un proceso, recarga automática).
- Cualquier otro valor → `gunicorn` con 4 workers `UvicornWorker`, `--timeout 30`,
  `--keep-alive 5`, logs de acceso a stdout.

No hay que cambiar el comando del contenedor: basta con fijar `MINERVA_MODE` (y el
resto de variables de la sección 2.1) en el `.env` de producción.

### 2.5 Infraestructura fuera del alcance del código

Lo siguiente es **decisión de infraestructura del IIEG al desplegar a un servidor
real**, no algo que el backend resuelva por sí mismo:

- **TLS/HTTPS**: al tener certificado, terminar TLS en el nginx del servicio `frontend` (el único
  punto público; ver 2.2) y cambiar `MINERVA_ISSUER`/`FRONTEND_URL` a `https://`. Por ahora HTTP.
- **Secret manager**: `MINERVA_KEY_ENCRYPTION_KEY`, `ADMIN_PASSWORD`, credenciales de
  PostgreSQL/Redis deben vivir en un gestor de secretos real, no en un `.env` plano en
  el servidor.
- **Observabilidad**: métricas/alertas externas (los `AuditLog` internos cubren eventos
  de negocio — login, rate limit excedido — pero no sustituyen monitoreo de
  infraestructura).

## 3. Mantenimiento

### 3.1 Rotación de claves de firma RS256

```bash
# Dentro del contenedor backend, o con el entorno conda `minerva` activo:
python -m app.cli rotate-key
```

Qué hace (`OIDCService.rotate_key`, `backend/app/modules/oidc/service.py`):
1. Retira la clave activa actual (`status=retired`).
2. Genera un nuevo par RSA 2048 y lo marca como activa.
3. Purga claves retiradas más viejas que `MINERVA_ACCESS_TOKEN_TTL_MINUTES` — pasada esa
   ventana, ningún token vigente puede seguir firmado con ellas.

El JWKS público (`/.well-known/jwks.json`) sirve simultáneamente la clave activa y las
retiradas todavía dentro de la ventana, así que un token emitido segundos antes de la
rotación sigue verificando.

**Recomendación operativa:** colgar `rotate-key` de un cron periódico (p. ej. diario o
semanal) en el servidor o como Job programado del orquestador.

### 3.2 Backups de PostgreSQL

```bash
docker compose exec -T postgres bash -c \
  'PGPASSWORD="$POSTGRES_PASSWORD" pg_dump -U "$POSTGRES_USER" -d "$POSTGRES_DB"' \
  > backups/minerva-$(date +%Y%m%d-%H%M%S).sql
```

O usando el script `backend/scripts/backup-postgres.sh` dentro del contenedor
`postgres` (lee `POSTGRES_USER`/`POSTGRES_PASSWORD`/`POSTGRES_DB`/`BACKUP_DIR` del
entorno).

**Por qué es crítico:** la tabla `signing_keys` guarda las claves privadas RSA
(cifradas) que firman todos los tokens vigentes. Perder esta tabla sin backup invalida
de golpe todos los tokens emitidos y obliga a una rotación forzada con impacto en todos
los consumidores. Cadencia sugerida: diaria.

### 3.3 Migraciones de base de datos

Se aplican automáticamente al arrancar el contenedor (`alembic upgrade head` en el
entrypoint). Para generar una migración nueva tras cambiar modelos:

```bash
cd backend
alembic revision --autogenerate -m "descripcion breve"
# Revisar el archivo generado en alembic/versions/ antes de aceptarlo
alembic upgrade head
```

### 3.4 Redis: alcance y expectativas

Redis se levanta **sin persistencia** (`redis-server --maxmemory 256mb
--maxmemory-policy allkeys-lru`, sin RDB/AOF) — decisión explícita, no un descuido.
Solo guarda:
- Rate limiting (`/auth/login`, `/auth/authorize`).
- Blacklist de `jti` de tokens revocados.
- Sesiones efímeras del flujo `/authorize` (código + PKCE/nonce/state, de vida muy corta).

Perder este estado en un restart **no corrompe nada**: solo relaja temporalmente el
rate limiting y permite que tokens recién revocados sigan aceptándose hasta que
expiren por sí solos (ventana acotada por `MINERVA_ACCESS_TOKEN_TTL_MINUTES`). No
requiere backup.

### 3.5 Checklist rápido antes de exponer Minerva a producción

1. `MINERVA_MODE` ≠ `dev` y `MINERVA_ENABLE_DEV_LOGIN=false`.
2. `ADMIN_PASSWORD`, `SECRET_KEY`, `JWT_SECRET_KEY` cambiados de su valor default.
3. `MINERVA_KEY_ENCRYPTION_KEY` generada y guardada en un secret manager.
4. `MINERVA_ISSUER` apunta a la URL pública real (HTTPS).
5. TLS terminado en el reverse proxy delante de backend y frontend.
6. Backup de PostgreSQL programado (cron diario mínimo).
7. `rotate-key` programado en cron.
8. Confirmar que el backend arranca y `validate_production_config()` no lanza error
   (revisar logs del primer arranque).
