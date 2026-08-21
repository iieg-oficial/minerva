# Guía de despliegue: Dev, Producción y Mantenimiento

> Ver [`arquitectura.md`](arquitectura.md) para el panorama general y
> [`glosario.md`](glosario.md) para los términos OIDC usados aquí.

## 1. Desarrollo

Requiere Docker Compose y [`just`](https://just.systems/).

```bash
cp .env.example .env
just build
just up
```

Usa `just logs` para seguir todos los servicios, `just restart` para reiniciarlos y
`just down` para detenerlos conservando datos. `just down-v` elimina también los
volúmenes de PostgreSQL y Redis y, por tanto, sus datos locales.

Todas las recetas operan el Compose que indique la variable `file` del `Justfile`, por defecto
`docker-compose.yml`. Para el despliegue por imágenes publicadas, ver §2.6.

Servicios:

| Servicio | Puerto host (default) | Notas |
|---|---|---|
| Backend (FastAPI) | `9000` | `BACKEND_PORT`; docs OpenAPI en `/docs` |
| Frontend (panel admin) | `3100` | `FRONTEND_PORT` |
| PostgreSQL | `5433` | `POSTGRES_PORT` (mapeado a 5432 dentro del contenedor) |
| Redis | `6379` | `REDIS_PORT` |

Al arrancar, el entrypoint (`backend/scripts/backend-entrypoint.sh`) corre **una sola vez**,
antes de levantar el servidor:
1. Aplica migraciones Alembic (`alembic upgrade head`).
2. Importa los manifiestos de `MINERVA_MANIFESTS_PATH` si `MINERVA_AUTO_IMPORT_MANIFESTS=true`
   (`python -m app.cli import-manifests`). Si un manifiesto falla, **el arranque se aborta**:
   no queda en un warning silencioso.

Después, el `lifespan` (`backend/app/main.py`) corre en cada worker:

3. Valida la configuración (`validate_production_config()` — no falla en modo dev).
4. Siembra (`_seed_data`) el usuario administrador y la aplicación `minerva` si no existen.
5. Garantiza una clave de firma RS256 activa (`_seed_signing_key`, idempotente).

### ⚠️ Gotcha de puertos: 8000 vs 9000

El backend se sirve en **9000** (Dockerfile, docker-compose, entrypoint). Algunos
valores legacy en `.env`/`config.py` (comentarios viejos) todavía mencionan **8000**.
Si tocas configuración de red/proxy/redirects, verifica el puerto extremo a extremo
(`MINERVA_ISSUER`, `vite.config.js`) antes de asumir que un solo lado está mal.

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

**Qué cuenta como producción:** una sola propiedad, `Settings.is_production`, resuelve las dos
señales que existen (`APP_ENV` y `MINERVA_MODE`). Es desarrollo **solo si ambas lo dicen**
(`APP_ENV=development` y `MINERVA_MODE=dev`); cualquier otro valor —incluido un typo— se trata como
producción y activa las validaciones. La misma propiedad gobierna la cookie del panel, así que no
puede haber un despliegue con cookie de producción y validaciones de dev.

`Settings.validate_production_config()` (`backend/app/core/config.py`) se ejecuta en el
`lifespan` del backend y **aborta el arranque** si la configuración es de producción y detecta
cualquiera de estos problemas:

| Variable | Requisito en producción |
|---|---|
| `APP_ENV` | `production` (o cualquier valor distinto de `development`/`dev`) |
| `MINERVA_MODE` | distinto de `dev` (p. ej. `central`) |
| `APP_DEBUG` | debe ser `false` |
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
- **TLS lo termina un terminador externo** delante de nginx (este nginx sirve HTTP). nginx propaga el
  esquema real del cliente al backend con `X-Forwarded-Proto` (respeta el que envía el terminador;
  si no hay, usa `$scheme`), así el backend ve `https` aunque el salto interno sea HTTP.
- **Cabeceras defensivas:** `nginx.conf` emite CSP (con `frame-ancestors 'none'`),
  `X-Content-Type-Options: nosniff` y `Referrer-Policy`. La CSP permite `style-src 'unsafe-inline'`
  por Ant Design (cssinjs) e `img-src ... https:` para los logos de branding por app (`logo_url`).
  **HSTS no lo emite este nginx** (sirve solo `:80`; el navegador ignora un HSTS recibido por HTTP):
  configúralo en el **terminador TLS** que va delante, con
  `add_header Strict-Transport-Security "max-age=63072000; includeSubDomains" always;` — **sin
  `preload`** por defecto (es difícil de revertir y exige HTTPS en todos los subdominios). La cookie de
  sesión del panel usa el prefijo `__Host-` (exige HTTPS): en HTTP local se usa `minerva_sid` sin
  `Secure`, derivado de la misma señal de entorno (`APP_ENV` + `MINERVA_MODE`, ver §2.1).
- **Redis es control de seguridad, no solo caché.** Además del rate limit, guarda la blacklist de
  `jti`, los cortes de invalidación por usuario y el **contenedor de sesión del panel**. Por eso corre
  con persistencia AOF (`appendonly yes`) y `maxmemory-policy noeviction` (ver §3.4): sobrevive
  reinicios y no desaloja revocaciones por presión de memoria. Perder Redis cierra las sesiones del
  panel y re-habilita tokens revocados, por eso es durable.

### 2.3 Variables a revisar/ajustar

- `MINERVA_ISSUER` / `MINERVA_JWT_ISSUER`: URL pública real de Minerva = **el host de nginx, sin
  `:9000`** (p. ej. `http://minerva.jalisco.gob.mx`; `https://…` al tener certificado). Aparece como
  `iss` en cada token y en el discovery; debe coincidir con lo que ven los consumidores.
- `FRONTEND_URL`: **debe ser el mismo host público** que `MINERVA_ISSUER`/`MINERVA_JWT_ISSUER`. La
  cookie `__Host-` es host-only: dos dominios distintos rompen el BFF (401 silencioso).
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

- **TLS/HTTPS**: al tener certificado, terminar TLS en un **terminador/reverse proxy externo** delante
  del nginx del servicio `frontend`, emitir ahí **HSTS** (sin `preload` por defecto) y cambiar
  `MINERVA_ISSUER`/`FRONTEND_URL` a `https://`. Ese terminador debe enviar `X-Forwarded-Proto: https`
  (nginx ya lo propaga al backend). Por ahora HTTP. Alternativa: terminar TLS en el propio nginx
  añadiendo un `server` con `listen 443 ssl` y su `add_header Strict-Transport-Security`.
- **Secret manager**: `MINERVA_KEY_ENCRYPTION_KEY`, `ADMIN_PASSWORD`, credenciales de
  PostgreSQL/Redis deben vivir en un gestor de secretos real, no en un `.env` plano en
  el servidor.
- **Observabilidad**: métricas/alertas externas (los `AuditLog` internos cubren eventos
  de negocio — login, rate limit excedido — pero no sustituyen monitoreo de
  infraestructura).

### 2.6 Operar el compose de deploy con `just`

`docker-compose.deploy.yml` consume las imágenes de `ghcr.io` en vez de construirlas
(ver [`uso-imagen-docker.md`](uso-imagen-docker.md)). Las recetas del `Justfile` lo operan
sin escribir `-f` en cada comando; el archivo se elige con la variable `file`, que también
puede llegar del entorno o del `.env` como `MINERVA_COMPOSE`:

```bash
# En el host de producción, una vez (en el .env o exportado):
MINERVA_COMPOSE=docker-compose.deploy.yml

just up                 # docker compose -f docker-compose.deploy.yml up -d
just pull && just up    # actualizar a la MINERVA_VERSION configurada
just logs               # seguir los servicios

# Puntual, sin declarar nada:
just file=docker-compose.deploy.yml ps
```

Dos diferencias con el compose de desarrollo, deliberadas:

- Si `.env` no existe, la receta lo crea desde **`.env.production.example`** (no desde
  `.env.example`): las imágenes publicadas no deben arrancar con `APP_DEBUG`, login de dev y
  secretos de ejemplo. La plantilla trae placeholders `<...>` en todos los secretos:
  reemplázalos antes de levantar (§2.1).
- No hay nada que construir: `just build` avisa «No services to build» y no hace nada. La
  actualización es `pull` + `up`, y la versión la fija `MINERVA_VERSION`.

## 3. Mantenimiento

### 3.1 Rotación de claves de firma RS256

La rotación es de **dos fases** (*publish-before-use*): la clave nueva se publica en el
JWKS antes de empezar a firmar con ella, para que los verificadores la tengan cacheada
cuando llegue el primer token firmado. Firmar de inmediato con una clave recién creada
es lo que corta el servicio.

```bash
# Dentro del contenedor backend, o con el entorno conda `minerva` activo:
python -m app.cli rotate-key     # fase 1: publica la clave nueva como `pending`
# ...esperar la ventana de propagación (ver abajo)...
python -m app.cli promote-key    # fase 2: la clave nueva empieza a firmar
```

`promote-key --force` salta la espera; úsalo solo si sabes que ningún verificador tiene
todavía el JWKS anterior cacheado.

**Fase 1 — `rotate-key`.** Crea un par RSA 2048 con `status=pending`: ya aparece en
`/.well-known/jwks.json`, pero **no firma nada todavía**. Invalida el caché JWKS de Redis
para que el propio backend la vea de inmediato.

**Fase 2 — `promote-key`.** La pendiente pasa a `active` y la anterior a `retired`, en una
sola transacción (nunca hay dos claves activas ni ninguna). Después purga las retiradas
que ya no puedan estar firmando nada vigente. El comando **rechaza** la promoción si no
ha pasado la ventana de propagación; `--force` la salta a propósito.

Las dos ventanas que gobiernan el proceso:

| Ventana | Variable | Default | Qué significa |
|---|---|---|---|
| Propagación | `MINERVA_KEY_PROPAGATION_MINUTES` | 60 min | Cuánto puede tardar un verificador en ver la clave nueva en su JWKS cacheado. Cubre el default del SDK (`MINERVA_JWKS_CACHE_TTL=3600`). Es lo que hay que esperar entre fase 1 y fase 2. |
| Retención | derivada (`key_retirement_overlap_minutes`) | 485 min | Cuánto sigue publicada una clave ya retirada: la vida máxima de token firmado (la sesión del panel, 480 min) + `MINERVA_CLOCK_SKEW_MINUTES`. Purgar antes invalidaría sesiones vigentes. |

La retención es **derivada, no configurable**, para que no pueda quedar desfasada del TTL
de sesión. Los refresh tokens no cuentan: son opacos, nadie los firma.

A lo sumo puede existir **una** clave `active` y **una** `pending` a la vez: lo garantizan
índices únicos parciales en `signing_keys` (migración 009), no solo el código, así que ni
un INSERT manual ni una restauración a medias pueden dejar ambiguo con qué clave se firma.

#### Retirada de emergencia de una clave comprometida

Este procedimiento rompe deliberadamente todos los tokens firmados por el `kid`
comprometido. No sustituye la rotación normal ni debe usarse para mantenimiento periódico.

```bash
# 1. Lista las claves y sus estados; no muestra material privado.
docker compose exec backend python -m app.cli revoke-key

# 2. Simula el impacto. No modifica la base ni el cache.
docker compose exec backend python -m app.cli revoke-key KID_COMPROMETIDO

# 3. Ejecuta solo si --confirm repite exactamente el kid.
docker compose exec backend python -m app.cli revoke-key KID_COMPROMETIDO \
  --confirm KID_COMPROMETIDO
```

Si la comprometida era `active`, el comando crea una clave nueva —o promueve la
`pending` ya publicada— antes de eliminarla. Después invalida el JWKS cacheado en Redis.
El comando es idempotente: si falla al limpiar Redis, repite exactamente el paso 3.

Verifica el simulacro antes de cerrar el incidente:

1. `curl -fsS https://HOST/.well-known/jwks.json` ya no contiene el `kid` comprometido.
2. Obtén un token nuevo y confirma que su `kid` es la nueva `active` y que autentica.
3. Fuerza a cada consumidor a refrescar su JWKS; un token firmado por el `kid` retirado
   debe fallar. Los caches externos no pueden invalidarse desde Minerva.
4. Revisa logs, accesos y tokens emitidos durante la ventana de compromiso, rota las
   credenciales que pudieron exponer la clave y conserva la evidencia del incidente.

**Recomendación operativa:** colgar la rotación de un cron periódico (p. ej. mensual),
recordando que son **dos** ejecuciones separadas por la ventana de propagación.

### 3.2 Backups de PostgreSQL

Usa el formato custom de `pg_dump`: permite validar el archivo con `pg_restore --list`
y restaurar con fallo inmediato. En producción añade
`-f docker-compose.deploy.yml` a cada comando `docker compose` (o declara
`MINERVA_COMPOSE` una vez y usa las recetas de `just`, §2.6).

```bash
mkdir -p backups
stamp=$(date -u +%Y%m%dT%H%M%SZ)
docker compose exec -T postgres sh -c \
  'pg_dump -Fc -U "$POSTGRES_USER" -d "$POSTGRES_DB"' \
  > "backups/minerva-$stamp.dump"
docker compose exec -T postgres pg_restore --list \
  < "backups/minerva-$stamp.dump" > /dev/null
sha256sum "backups/minerva-$stamp.dump" > "backups/minerva-$stamp.dump.sha256"
```

`backend/scripts/backup-postgres.sh` es una alternativa para un host que tenga
`pg_dump` y las variables de PostgreSQL; no está montado dentro del contenedor
`postgres`.

**Por qué es crítico:** la tabla `signing_keys` guarda las claves privadas RSA
(cifradas) que firman todos los tokens vigentes. Perder esta tabla sin backup invalida
de golpe todos los tokens emitidos y obliga a una rotación forzada con impacto en todos
los consumidores. El dump no contiene `MINERVA_KEY_ENCRYPTION_KEY`: conserva esa clave
en el secret manager, porque sin ella las claves privadas restauradas no se pueden
descifrar. Cadencia sugerida: diaria.

#### Simulacro de restauración

Restaura siempre en una base vacía con otro nombre. Así el origen queda intacto y el
rollback consiste en volver a apuntar al origen; no uses `--clean` sobre la base activa.

```bash
restore_db=minerva_restore_$(date -u +%Y%m%d%H%M%S)
dump=backups/minerva-AAAAMMDDTHHMMSSZ.dump

docker compose exec -T postgres sh -c \
  'createdb -T template0 -U "$POSTGRES_USER" "$1"' sh "$restore_db"
docker compose exec -T postgres sh -c \
  'pg_restore --exit-on-error --no-owner --no-privileges \
    -U "$POSTGRES_USER" -d "$1"' sh "$restore_db" < "$dump"
```

Antes de arrancar Minerva contra la copia, compara en origen y destino los conteos de
`users`, `applications`, `roles`, `permissions`, `groups`, `signing_keys`, `audit_logs`
y `refresh_tokens`. En la copia comprueba además:

```sql
SELECT version_num FROM alembic_version;
SELECT count(*) FROM signing_keys WHERE status = 'active'; -- debe ser 1
```

Después levanta una instancia no pública con `MINERVA_DB_URL` apuntando a
`$restore_db` y la misma `MINERVA_KEY_ENCRYPTION_KEY`. Debe responder `200` en
`/ready`; inicia sesión con una cuenta restaurada y completa Authorization Code + PKCE
hasta obtener `access_token` e `id_token`. No promuevas la copia si cualquier conteo,
la migración, la clave activa, readiness o el login difieren.

Para el corte, detén escrituras, toma un dump final y cambia `MINERVA_DB_URL` a la base
validada. Conserva la base anterior sin escrituras durante la ventana de rollback. Si
el smoke posterior falla, restaura el valor anterior de `MINERVA_DB_URL` y reinicia el
backend; no intentes fusionar escrituras entre ambas bases.

Registra `SHOW server_version`, `pg_dump --version` y `pg_restore --version` en cada
simulacro. Para restauraciones rutinarias usa la misma versión mayor de PostgreSQL. Si
el destino cambia de versión mayor, usa las herramientas de la versión destino, nunca
restaures hacia una versión anterior y ensaya la migración antes del corte.

#### Evidencia del simulacro 2026-08-19

Simulacro local no productivo sobre `fb2ee7f`, con PostgreSQL/`pg_dump`/`pg_restore`
16.14:

- dump custom de 56 KiB en 142 ms; restauración en base limpia en 208 ms;
- conteos origen/restauración: 2 usuarios, 3 aplicaciones, 8 roles, 35 permisos,
  0 grupos, 2 signing keys, 147 eventos de auditoría y 33 refresh tokens;
- migración `011_app_scoped_uniqueness` y exactamente una clave activa;
- `/ready` 200, login restaurado 200 y Authorization Code + PKCE completado con
  `access_token` e `id_token`;
- la base y el dump temporales se eliminaron al terminar.

Estos tiempos solo describen ese dataset pequeño; no son un SLO de producción.

### 3.3 Migraciones de base de datos

Se aplican automáticamente al arrancar el contenedor (`alembic upgrade head` en el
entrypoint). Para generar una migración nueva tras cambiar modelos:

```bash
cd backend
alembic revision --autogenerate -m "descripcion breve"
# Revisar el archivo generado en alembic/versions/ antes de aceptarlo
alembic upgrade head
```

### 3.4 Redis: control de seguridad durable

Redis es un **control de seguridad**, no solo caché. Guarda:
- Blacklist de `jti` de tokens revocados (logout-all, quitar cuenta, rotación de refresh).
- Cortes de invalidación por usuario (`minerva:uinval:*`, al cambiar contraseña/correo/status).
- Contenedor de sesión del panel (patrón BFF): cuentas iniciadas y token `typ=session` de cada una.
- Rate limiting (`/auth/login`, `/auth/authorize`) y sesiones efímeras del flujo `/authorize`.

Por eso corre con **persistencia AOF y sin evicción**:
`redis-server --appendonly yes --maxmemory 256mb --maxmemory-policy noeviction`, con un
volumen nombrado `minerva_redis_data:/data`. Consecuencias:
- **Sobrevive reinicios:** un token revocado sigue rechazado tras reiniciar el contenedor
  `minerva_redis` (antes, sin persistencia, un restart lo resucitaba hasta su `exp` — hasta 8 h
  para la sesión del panel).
- **`noeviction`:** las claves de seguridad no se desalojan por presión de memoria. Todas tienen
  TTL acotado (blacklist ≤ vida del token, panel 8 h, rate-limit 15 min), así que 256 mb sobra; si
  la memoria llegara a llenarse, fallan las escrituras (fail-closed) en vez de borrar revocaciones.
- **Backup:** incluye el volumen `minerva_redis_data` en la estrategia de respaldo junto con el de
  PostgreSQL (el AOF vive ahí).

**Política de fail-safe (fail-closed):** si Redis no está disponible, las operaciones de seguridad
(validar revocación, rate limit) fallan y la request se rechaza — Minerva **no** degrada a fail-open
(nunca honra un token que no pudo verificar contra la blacklist). Verificarlo tras un cambio de infra:
`docker compose restart minerva_redis` y reintentar un token revocado (sigue devolviendo 401);
`docker exec minerva_redis redis-cli config get appendonly maxmemory-policy` → `yes` / `noeviction`.

### 3.5 Checklist rápido antes de exponer Minerva a producción

1. `APP_ENV=production`, `MINERVA_MODE` ≠ `dev`, `APP_DEBUG=false` y `MINERVA_ENABLE_DEV_LOGIN=false`.
2. `ADMIN_PASSWORD`, `SECRET_KEY`, `JWT_SECRET_KEY` cambiados de su valor default.
3. `MINERVA_KEY_ENCRYPTION_KEY` generada y guardada en un secret manager.
4. `MINERVA_ISSUER` apunta a la URL pública real (HTTPS).
5. TLS terminado en el reverse proxy delante de backend y frontend.
6. Backup de PostgreSQL programado (cron diario mínimo); incluir el volumen `minerva_redis_data`
   (AOF con la blacklist/invalidaciones/sesiones del panel).
7. `rotate-key` programado en cron.
8. Confirmar que el backend arranca y `validate_production_config()` no lanza error
   (revisar logs del primer arranque).
