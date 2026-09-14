# Changelog

Todos los cambios notables de Minerva se documentan aquí.

El formato sigue [Keep a Changelog](https://keepachangelog.com/es-ES/1.1.0/)
y el proyecto usa [Versionado Semántico](https://semver.org/lang/es/).

## [Unreleased]

### Security

- **El rol `minerva.admin` solo da administración global si pertenece a la app `minerva`.**
  `is_minerva_admin` comparaba únicamente el slug del rol, así que un rol con ese nombre en
  cualquier otra aplicación habría pasado por administrador global. Además, crear roles con el
  prefijo `minerva.` fuera de la app `minerva` ahora responde 400. Hoy solo un administrador global
  crea roles, pero el cierre es previo a delegar administración por aplicación.

## [1.0.0] - 2026-08-21

> **Primer release estable.** Minerva publica el perfil OIDC Authorization Code + PKCE,
> administración centralizada de identidades y permisos, SDK para FastAPI, despliegue reproducible
> y controles de seguridad, integridad y operación validados por el CI del proyecto.

### Added

- **El `Justfile` cubre `docker-compose.deploy.yml`.** Las 15 recetas operaban un archivo fijo, así
  que desplegar con las imágenes publicadas en ghcr obligaba a escribir `docker compose -f
  docker-compose.deploy.yml` a mano, fuera de la interfaz que documenta el repo. Ahora el archivo
  lo elige la variable `file` (`just file=docker-compose.deploy.yml up`), que también se puede
  declarar una vez por host con `MINERVA_COMPOSE` en el `.env`; con el compose de deploy el `.env`
  se siembra desde `.env.production.example` en vez de `.env.example`.
- **Matriz de compatibilidad del SDK en el CI.** El job `sdk` pasa a dos entornos: Python 3.10 con
  `fastapi` y `httpx` clavados en su piso declarado, y Python 3.13 con resolución libre. Antes el
  SDK solo se probaba en 3.12, así que `requires-python = ">=3.10"`, `fastapi>=0.110` y
  `httpx>=0.27` eran soportes nominales que nadie ejercitaba.
- **Changelog propio del SDK** en `sdk/CHANGELOG.md`, con sus versiones 0.1.0, 0.2.0 y 0.3.0 y en
  qué release de Minerva viaja cada una. Los cambios del SDK ya no quedan enterrados dentro de un
  release del servidor.
- **`sdk/tests/test_version.py`**: falla si `minerva_sdk.__version__`, `sdk/pyproject.toml` y
  `sdk/CHANGELOG.md` se desincronizan.
- **Smoke E2E de autenticación web** (`frontend/src/test/auth-smoke.test.jsx`): monta la SPA
  completa contra una Minerva simulada en el adaptador de axios y recorre la jornada crítica
  —login con cookie y CSRF, `/authorize` transportando `state` y `max_age`, cambio de cuenta y
  logout—. Los tests de `features/auth` mockean `@/api/*`, así que nadie probaba el cableado que
  las une; ahora una regresión de cookie, CSRF, parámetros o navegación rompe el CI.

### Fixed

- El panel importaba el router desde `react-router` (una transitiva) en `LoginPage` y
  `AdminLayout`, y desde `react-router-dom` (la dependencia declarada) en el resto. Fuera del
  bundler los dos especificadores resuelven a instancias distintas y el contexto del router deja
  de compartirse; ahora todo el panel importa `react-router-dom`.

### Docs

- **Valores esperados de `MINERVA_ORG` y `MINERVA_VERSION`** en `docs/uso-imagen-docker.md` y
  `.env.production.example`: la org dueña de los paquetes en ghcr y el tag de la imagen, que es el
  del release **sin la `v`** (`v0.7.0` → `0.7.0`) o `latest`.
- **`sdk/README.md` declara qué soporta**: Python 3.10–3.13, FastAPI, httpx y python-jose, con la
  política de versionado pre-1.0 explícita (en `0.x` un cambio incompatible sube el MINOR y se
  marca `BREAKING` en el changelog) y la tabla de qué SDK viaja en qué Minerva.

## [0.7.0] - 2026-08-18

### Added

- **SDK 0.3.0 y consumidor de referencia.** `MinervaOIDC` construye el flujo Authorization
  Code + PKCE, canje, refresh y revocación desde una sola `MINERVA_ISSUER_URL`; los helpers
  públicos permiten validar sesiones server-side sin copiar funciones internas. El ejemplo
  `minerva-consumer` demuestra login, acceso denegado, roles informativos, permisos, 401/403,
  refresh y logout con tokens fuera del navegador. FastAPI compone módulos independientes de
  autenticación, API y sesiones, y sirve un frontend HTML/CSS/JS separado. Incluye Docker/Compose
  propio; Minerva y el mock ofrecen recetas `just` equivalentes para su ciclo operativo.

### Changed

- **Contrato de integración simplificado.** La guía separa las cinco variables del recorrido
  normal de los ajustes avanzados, recomienda importar el manifiesto desde el panel y elimina
  rutas, Bearers administrativos y URLs de frontend obsoletos de la documentación activa.

## [0.6.0] - 2026-08-12

> **Estado del release.** 0.6.0 es un release de **desbloqueo para los consumidores OIDC**: publica
> a `main` el contrato OAuth endurecido que hasta ahora solo existía en `develop`, para que los
> sistemas que se están integrando trabajen contra una versión publicada. **No es el 1.0.0**; la
> decisión de declarar 1.0 queda sujeta a la auditoría, que es posterior a este release.

> ⚠️ **Antes de actualizar.** Este release incluye un **BREAKING de despliegue** (#69): un
> despliegue con dos dominios públicos debe consolidarse en el origen único de nginx, o
> `validate_production_config()` aborta el arranque. Ver la entrada al final de *Fixed*.

### Added

- **El Authorization Endpoint acepta `POST` con `application/x-www-form-urlencoded`.** OIDC Core
  §3.1.2.1 obliga a soportar `GET` **y** `POST`, y `/auth/authorize` solo tenía `GET`: un RP que
  siguiera la spec al pie de la letra —o una librería OIDC certificada— recibía un `405`. Ahora los
  tres handlers (`GET`, `POST` form y la variante JSON que consume el panel) comparten un único
  flujo y el mismo modelo de parámetros, así que éxito y error son equivalentes entre métodos,
  incluido el `422` por parámetro faltante. El `POST` responde **303** para que el navegador siga
  el destino con `GET`. `/auth/authorize` queda exento del CSRF del panel: la cookie es
  `SameSite=Lax` y por tanto un `POST` cross-site nunca la lleva, la comprobación de `Origin` sigue
  aplicándose, y la defensa del RP contra login-CSRF es su `state`. (#80)
- **UserInfo acepta `POST`.** Mismo hueco de conformidad, esta vez OIDC Core §5.3: `/userinfo`
  atiende ahora `GET` y `POST` sobre la misma función y la misma dependencia, sin cambios de claims
  ni de scopes. Su política CORS pasa a `allow_methods: ["GET", "POST"]` — sin eso el preflight
  rechazaba el `POST` desde navegador y el endpoint solo habría sido equivalente server-to-server.
  El token sigue viajando como Bearer en el header. (#81)
- **El repositorio se publica con licencia libre.** `LICENSE` en la raíz con la **GNU AGPL-3.0**
  (`AGPL-3.0-only`) para el servidor —backend, frontend y documentación—, y `sdk/LICENSE` con
  **Apache-2.0** más su `NOTICE` para `minerva_sdk`: el SDK es una librería que el sistema
  consumidor importa en su propio proceso, y bajo AGPL arrastraría a cada plataforma del instituto
  a publicar su código. La metadata SPDX de los tres paquetes queda alineada. (#93)
- **`SECURITY.md`**: canal privado de reporte (GitHub Private Vulnerability Reporting), qué incluir
  en un reporte, qué esperar, versiones soportadas y alcance —explícitamente sin SLA ni
  recompensas. (#95)
- **`CONTRIBUTING.md`**: entorno, flujo issue → rama → PR, modelo de ramas, convención de commits,
  los comandos de validación idénticos a los del CI y la regla de revisar el diff completo contra
  su merge-base tras aplicar correcciones. (#97)

### Changed

- **La imagen del frontend fija nginx en `1.30.4-alpine`.** La etiqueta flotante `nginx:alpine`
  permitía que un `docker build` con capa cacheada siguiera levantando 1.29.8, vulnerable a
  CVE-2026-42533 (CVSS 9.2), CVE-2026-60005 y CVE-2026-56434. Pesa más aquí que en otros
  servicios: ese nginx es el **único punto público** del despliegue. `nginx.conf` no necesitó
  cambios. (#138)
- **El frontend sube a Vite 8, Vitest 4 y React 19.2.8.** Vite 8 cambia el bundler a Rolldown y el
  minificador de CSS a Lightning CSS; el bundle no crece (1,263 kB frente a 1,303 kB) y el build
  baja de 3.7 s a 0.4 s. El job `frontend` del CI pasa a Node 22 —la misma del `Dockerfile`— y
  ejecuta `npm test`, que hasta ahora no corría en ningún lado. **Para quien despliegue:**
  `build.target` sube a Chrome 111 / Edge 111 / Firefox 114 / Safari 16.4 / iOS 16.4, y cambian
  todos los hashes de los assets, así que las pestañas del panel abiertas durante el despliegue
  pueden quedarse en blanco hasta recargar. (#139)
- **Una sola versión para todo el proyecto.** Circulaban cinco: `pyproject` 0.5.0, el literal de
  `GET /`, el 0.1.0 por defecto de FastAPI en `/openapi.json`, `frontend/package.json` en 0.3.4 y
  dos versiones citadas en la documentación que nunca existieron. La fuente única es ahora
  `backend/pyproject.toml` —la misma del tag—, el backend la lee de la metadata del paquete
  instalado y `tests/test_version_alignment.py` falla si alguna superficie se queda atrás. (#89)
- **La resolución de dependencias del backend queda congelada** en `backend/constraints.txt` (76
  paquetes), que consumen tanto el CI como el `Dockerfile`. Antes dos builds en fechas distintas
  instalaban árboles distintos y un cambio de transitiva entraba sin aparecer en ningún diff.
  Sigue siendo pip: no se introduce Poetry ni uv. (#85)
- **La imagen del frontend se construye con `npm ci`** y el `package-lock.json` versionado, en vez
  de `npm install` ignorando el lock: la imagen podía resolver un árbol distinto al que valida el
  CI. (#86)
- **Un tag ya no puede publicar imágenes con el CI en rojo.** `docker-publish.yml` disparaba con
  `push: tags: v*` y sin ningún `needs`, así que subía a ghcr aunque el CI de ese commit hubiera
  fallado —o nunca hubiera corrido—. Ahora invoca `ci.yml` como workflow reutilizable y la
  publicación depende de que pase **sobre el mismo commit etiquetado**. (#87)
- **El CI corre las pruebas que PostgreSQL sí reproduce.** Los tests del advisory lock del seed,
  el trigger PL/pgSQL, los índices únicos parciales y el lock de fila del refresh estaban marcados
  `skipif` sobre una variable que el CI nunca definía: se saltaban siempre y el verde no decía nada
  de ellos. Job `backend-postgres` nuevo, con `postgres:16-alpine` y un paso que falla si la
  variable desaparece. (#84)
- **El CI escanea vulnerabilidades con `pip-audit`** sobre la resolución congelada, en su propio
  job. Lleva una única excepción acotada y documentada (`PYSEC-2026-1325`, `ecdsa`: upstream
  declara los side channels fuera de alcance y no hay versión corregida; no es alcanzable porque
  Minerva firma y valida solo RS256), con fecha de revisión. Cualquier alerta distinta rompe el
  job. (#88)

### Fixed

- **`GET /auth/authorize` propaga `max_age` desde el panel.** `AuthorizePage` no leía ni reenviaba
  el parámetro, así que el backend nunca lo recibía y una sesión activa completaba SSO silencioso
  ignorando la reautenticación que el RP había pedido. (#66)
- **Los endpoints Bearer emiten `WWW-Authenticate` conforme a RFC 6750 §3.** `/userinfo`,
  `/api/v1/me` y `/api/v1/me/permissions` respondían 401/403 sin el challenge, así que un cliente
  no podía distinguir «falta credencial» de «token inválido» ni saber qué scope le faltaba. Ahora
  el challenge se emite desde un único punto (`BearerUnauthorizedError` / `InsufficientScopeError`)
  y sus descripciones son fijas: no filtran si el token estaba expirado, revocado o mal firmado. La
  sesión por cookie del panel queda fuera, sin cambios. (#82)
- **Producción se deriva de una sola señal.** Había dos interruptores de entorno y solo uno hacía
  algo: `MINERVA_MODE` decidía todo y **`APP_ENV` no lo leía nadie**, así que
  `APP_ENV=production` + `MINERVA_MODE=dev` pasaba `validate_production_config()` sin una queja,
  con dev-login y contraseña por defecto activos. Ahora es desarrollo **solo si ambas** señales lo
  dicen: cualquier marca de producción, o un typo como `prod`, cae del lado seguro. El fail-fast
  además rechaza `APP_DEBUG=true`. (#68)
- **Las migraciones ya no se aplican a otra base que la que sirve la aplicación.** El runtime abre
  el engine con `settings.effective_db_url`, que da prioridad a `MINERVA_DB_URL`, mientras que
  `alembic/env.py` leía `DATABASE_URL` directo: con ambas definidas y distintas, Alembic migraba
  una base y Minerva servía otra. En `.env.production.example` coincidían por casualidad, lo que
  enmascaraba el problema. (#72)
- **`import_models()` estaba vacío**, así que Alembic recibía una metadata **sin ninguna tabla**:
  un `alembic revision --autogenerate` habría propuesto borrar el esquema completo y
  `alembic check` no vigilaba nada. Ahora importa explícitamente los 9 módulos con `table=True`
  (15 tablas), `env.py` aborta si la metadata queda vacía, y un test detecta al que agregue un
  modelo nuevo sin declararlo. (#73)
- **El autoimport de manifiestos deja de correr dentro del `lifespan`.** Con `gunicorn -w 4` eran
  cuatro importaciones en paralelo del mismo manifiesto sobre la misma base, y cada fallo se
  degradaba a un `warning`, así que un manifiesto roto pasaba inadvertido. Ahora es un paso único
  del entrypoint, después de `alembic upgrade head` y antes de arrancar el servidor: reporta todos
  los fallos y aborta el arranque si alguno falló. (#77)
- **BREAKING · El despliegue de producción exige un único origen público.** La plantilla
  `.env.production.example` proponía dos dominios (`<dominio-panel>` y `<dominio-api>`), pero la
  cookie de sesión del panel usa el prefijo `__Host-`, que es *host-only*: con hosts distintos la
  cookie nunca viaja al API y el login falla con un **401 mudo**, sin rastro en los logs. La
  plantilla ahora usa un solo `<dominio-publico>` para `FRONTEND_URL`, `MINERVA_ISSUER` y
  `MINERVA_JWT_ISSUER`, y `docs/despliegue.md` explica el porqué. Además, `validate_production_config()`
  **falla al arrancar** si esos hosts no coinciden, en vez de dejar que Minerva levante rota; la
  comparación ignora el esquema (el TLS puede terminar fuera del contenedor) pero sí distingue el
  puerto. La plantilla ya no sugiere `BACKEND_PORT` en el deploy: el backend no se publica, nginx
  lo proxea por la red interna. **Migración:** un despliegue pre-1.0 con dos hosts debe consolidarse
  en el origen único de nginx antes de actualizar. (#69)
- **La documentación decía cosas que el runtime no hacía.** `docs/integracion.md` afirmaba que
  `POST /auth/logout` con el `access_token` en el header revoca el token: el logout del panel es
  **suave**, se autentica con la cookie de sesión y no revoca nada —la revocación real está en
  `DELETE /auth/session/accounts/{sub}` y `POST /auth/logout-all`—. También proponía `prompt=none`
  para *silent renew* en un iframe, imposible porque nginx emite `frame-ancestors 'none'`. Se
  separó además la sección que mezclaba el logout del panel con `/auth/revoke` (RFC 7009, sobre el
  refresh token). En `sdk/README.md`, el SDK **no** descubre endpoints: concatena
  `{issuer}/.well-known/jwks.json` y `{issuer}/api/v1/me/permissions`, y ahora se documenta qué
  implica. (#90)
- **`docs/arquitectura.md` describía dependencias y rotación que no existen.** La tabla nombraba
  `get_current_user` / `get_optional_user`, símbolos ya inexistentes, en vez de las cinco
  dependencias reales y su validador común `_resolve_token`. El diagrama de rotación de claves
  describía un solo paso, cuando el runtime es de **dos fases** (`rotate-key` publica la clave como
  `pending` sin firmar nada; `promote-key` la asciende pasado `MINERVA_KEY_PROPAGATION_MINUTES` y
  ahí purga las retiradas). Se documenta también que el contrato de manifiestos es **aditivo**:
  quitar un permiso del YAML y reimportar no lo borra de la base. (#91)

## [0.5.0] - 2026-07-31

> **Estado del release.** 0.5.0 publica el trabajo ya integrado desde 0.4.0 como un checkpoint
> previo a 1.0.0. Incluye correcciones de seguridad, atomicidad, concurrencia y conformidad
> OAuth/OIDC; no implica que los pendientes del milestone 1.0.0 estén cerrados.

### Fixed

- **`/auth/token` no devolvía un error OAuth programable.** Sus errores (grant desconocido, código
  ya usado, `client_secret` inválido, parámetros faltantes) solo traían un `detail` genérico, así
  que un cliente no podía distinguir casos sin parsear texto en español. Ahora responde `error`
  (`invalid_request`, `invalid_client`, `invalid_grant`, `unsupported_grant_type`) y
  `error_description` con status 400, conforme a [RFC 6749 §5.2](https://www.rfc-editor.org/rfc/rfc6749.html#section-5.2).
  `detail` se conserva con el mismo texto por compatibilidad con quien ya lo leía.
- **Las respuestas exitosas de `/auth/token` no impedían su caché.** Ni el canje de código ni el
  refresh traían `Cache-Control`/`Pragma`, así que un proxy o el navegador podían guardar una
  respuesta con `access_token`/`refresh_token` (RFC 6749 §5.1). Ahora ambos grants responden con
  `Cache-Control: no-store` y `Pragma: no-cache`; el resto de los endpoints no se ve afectado.

- **BREAKING · `GET {panel}/logout?redirect_uri=...` solo acepta rutas internas del panel.**
  La página aceptaba cualquier URL absoluta `http(s)`, así que un consumidor —o un enlace
  fabricado— podía usar el logout de Minerva como *open redirect* hacia un dominio ajeno, con la
  credibilidad del dominio institucional detrás. Ahora el destino se resuelve contra el origen
  actual y se descarta si no coincide: cualquier URL externa cae en `/login`. Un destino externo
  legítimo requiere registro previo de `post_logout_redirect_uris`
  ([OIDC RP-Initiated Logout §2](https://openid.net/specs/openid-connect-rpinitiated-1_0.html#RPLogout)),
  que Minerva todavía no implementa. **Migración:** un consumidor que hoy pase su propia URL debe
  invertir el orden — cerrar primero su sesión y redirigir al final a `{panel}/logout`, o dejar que
  el usuario termine en el login de Minerva.
- **El logout ya no aparenta éxito cuando falla.** La navegación colgaba de `.finally()`, así que un
  `POST /auth/logout` fallido redirigía igual y el usuario se iba creyendo que había cerrado sesión
  mientras la cookie seguía viva. Ahora solo se navega en la resolución exitosa; ante un fallo la
  página se conserva y ofrece reintentar.
- **Un token emitido en el mismo segundo del corte de invalidación seguía siendo válido.** Al
  cambiar contraseña/correo/status, el rechazo comparaba `iat < corte`, así que un token con
  `iat` igual al corte (mismo segundo epoch) sobrevivía a una invalidación que prometía cerrarlo.
  La comparación ahora es inclusiva (`iat <= corte`).
- **Contraseñas mayores a 72 bytes UTF-8 causaban un 500 en vez de un rechazo.** bcrypt 5 lanza
  `ValueError` en vez de truncar más allá de ese límite, y ni el registro, el login, el alta de
  usuario ni el `PATCH` lo validaban antes de llamar a bcrypt. Ahora las cuatro rutas comparten un
  único validador que rechaza con 422 antes de llegar al hash/check.
- **Un `code_verifier` PKCE no-ASCII causaba un 500 en vez de un rechazo.** `verify_pkce` codificaba
  el verifier directamente como ASCII, así que un valor con caracteres fuera de ese rango lanzaba
  `UnicodeEncodeError` sin capturar. Ahora se valida primero contra el alfabeto y la longitud de
  [RFC 7636 §4.1](https://www.rfc-editor.org/rfc/rfc7636.html#section-4.1) (43–128 caracteres
  "unreserved"): fuera de ese formato, el canje responde 400 igual que un verifier incorrecto.
- **Un fallo al borrar un rol podía dejarlo a medias.** `RoleService.delete_role` confirmaba por
  separado cada limpieza de relaciones (permisos, usuarios, grupos) y el borrado del rol; si algo
  fallaba entre medio, las relaciones ya borradas no se recuperaban aunque el rol siguiera vivo (o
  viceversa). Ahora las cuatro operaciones comparten una sola transacción: si algo falla, el
  rollback automático revierte todo y no queda ningún estado intermedio.
- **Un fallo al emitir tokens dejaba el authorization code quemado sin entregar nada.** El canje
  confirmaba el reclamo del código (`used=True`) en un commit separado de la emisión y persistencia
  del refresh token; si algo fallaba entre medio, el código quedaba consumido para siempre sin que
  el cliente recibiera tokens. Ahora ambas operaciones comparten una sola transacción: si falla la
  emisión, el reclamo también se revierte y el código sigue disponible.
- **Un `full_name` más largo que la columna de BD no se rechazaba en el borde.** Los modelos
  SQLModel `table=True` no validan `max_length` en runtime (solo lo usan para el DDL), así que un
  `full_name` mayor a 255 caracteres pasaba sin error en el registro, el alta admin o el `PATCH`
  de usuarios. Ahora los tres esquemas de entrada rechazan con 422 lo que exceda los 255
  caracteres de `User.full_name`, y también exigen un mínimo de 6 caracteres.
- **BREAKING · `GET /api/v1/me/permissions` ya no filtra los permisos de otra aplicación.**
  El parámetro `application` de la query nunca se comparaba contra la audiencia del token, así que
  un access token emitido para la aplicación A podía pedir `application=B` y recibir los
  permisos/roles reales del usuario en B —una aplicación para la que ese token nunca fue
  autorizado— si el usuario los tenía asignados aparte
  ([RFC 9700 §2.3](https://www.rfc-editor.org/rfc/rfc9700.html#section-2.3)). Ahora se rechaza con
  403: un access token solo puede consultar la app de su `aud`, y un token dev solo las de su
  claim `applications`. **Migración:** un consumidor que hoy consulte una aplicación distinta a la
  suya recibirá 403 en vez de los permisos ajenos.
- **`/.well-known/openid-configuration` no coincidía con el runtime.** No anunciaba
  `revocation_endpoint` aunque `/auth/revoke` ya existe, y `claims_supported` listaba `roles`/
  `permissions` (que solo viven en el access token, nunca en el id_token ni en `/userinfo`) y
  omitía `preferred_username`, `email_verified`, `auth_time` y `nonce` (que sí se emiten). Ahora
  el documento de descubrimiento describe exactamente lo que el servidor soporta.
- **Dos altas concurrentes podían dejar un rol, permiso o redirect URI duplicado dentro de
  la misma aplicación.** Las altas por API y la importación de manifiestos comprobaban con un
  `SELECT` antes de insertar, sin que la base garantizara la unicidad: dos requests (o dos
  importaciones del mismo manifiesto) podían pasar ambas la comprobación antes de que ninguna
  confirmara. Ahora `roles`, `permissions` y `redirect_uris` tienen un constraint único por
  `(aplicación, slug/uri)`; una migración concilia primero los duplicados que ya existieran
  (conserva la fila más antigua y repunta sus asignaciones), y las cuatro rutas de escritura
  traducen la carrera restante a 409 en vez de un 500 sin manejar.

## [0.4.0] - 2026-07-22

> **Estado del release.** 0.4.0 es un checkpoint de integración, **no** la versión 1.0.0
> publicable. Cierra riesgos graves que seguían vivos en `main` (escalada administrativa vía
> `/api/v1`, revocación volátil en Redis, JWT del panel en `localStorage`, confusión de clases
> de token). Quedan pendientes conocidos de endurecimiento —entre ellos el `redirect_uri` de
> logout sin validar, el cruce de audiencia en `/api/v1/me/permissions`, `max_age` no
> transportado por la SPA, la invalidación por usuario emitida en el mismo segundo y la
> unificación de la URL de base de datos entre runtime y Alembic—, por lo que este tag no debe
> leerse como cierre del contrato 1.0.

### Changed

- **BREAKING · SDK 0.2.0: la caché de permisos queda desactivada por defecto.**
  `MINERVA_PERMISSIONS_CACHE_TTL` pasa de `300` a `0`. Con caché, una decisión positiva se
  servía de memoria sin consultar a Minerva, así que un token revocado seguía autorizando
  hasta 5 minutos: la revocación no era inmediata. Ahora cada chequeo pregunta a Minerva,
  que es quien la aplica. Activar la caché es una decisión explícita del consumidor, que
  acepta esa ventana a cambio de menos tráfico.
- **BREAKING · SDK 0.2.0: el bearer sale del objeto de usuario.** `get_current_user` ya no agrega
  `user["_token"]` con la credencial cruda; el dict son **solo** los claims del token, así que es
  seguro serializarlo en una respuesta o registrarlo en un log. `require_permission` obtiene el
  bearer de su propia dependencia `HTTPBearer`. Guía de migración en `sdk/README.md`; el resto del
  contrato del SDK no cambia.
- **BREAKING · La rotación de claves de firma pasa a dos fases (publish-before-use).**
  `python -m app.cli rotate-key` ya no activa la clave nueva: la publica en el JWKS como `pending`
  (aún no firma). El segundo paso, `python -m app.cli promote-key`, la activa y retira la anterior
  en una sola transacción, y rechaza hacerlo antes de `MINERVA_KEY_PROPAGATION_MINUTES` (60 min por
  defecto), que es el tiempo que un verificador puede tardar en ver la clave nueva en su JWKS
  cacheado. `promote-key --force` salta esa espera a propósito. La atención de una **clave
  comprometida** (retirarla del JWKS antes de que expiren los tokens firmados con ella) sigue
  siendo un procedimiento manual, no automatizado. Detalle operativo en `docs/despliegue.md` §3.1.

- **BREAKING · Sesión del panel migrada a cookie opaca HttpOnly (patrón BFF).** El panel admin ya
  no guarda JWT ni credenciales en `localStorage`: el navegador solo conserva una cookie opaca
  `__Host-minerva_sid` (`HttpOnly`, `Secure`, `SameSite=Lax`; en dev HTTP `minerva_sid` sin
  `Secure`). El estado multi-cuenta (cuentas iniciadas, cuál está activa, el token `typ=session`
  de cada una y el token CSRF) vive en Redis, con TTL igual al de la sesión del panel; es la
  **única** excepción al principio stateless de Minerva y aplica solo al panel. OAuth/OIDC de
  consumidores (Authorization Code+PKCE, `/token`, `/userinfo`, `/revoke`, discovery, JWKS,
  access/refresh/dev tokens, SDK) sigue **stateless y sin cambios**. `POST /auth/login` y
  `POST /auth/register` dejan de devolver `access_token`: responden `{ active, csrf }` y fijan la
  cookie. `POST /auth/logout` pasa a ser logout **suave** (cierra la cuenta activa sin revocar);
  la revocación real está en `DELETE /auth/session/accounts/{sub}` y `POST /auth/logout-all`.
  Nuevos endpoints: `GET /auth/session`, `POST /auth/session/active`.

### Security

- **Una revocación deja de autorizar de inmediato en el SDK.** La caché de permisos servía
  decisiones positivas sin consultar a Minerva, así que un token revocado seguía pasando hasta
  5 minutos; además se indexaba por `(usuario, aplicación)`, de modo que dos tokens distintos del
  mismo usuario compartían la decisión. La caché queda **apagada por defecto**; si se activa, se
  indexa por el `jti` del token, nunca sobrevive a su `exp`, un token sin `jti` no se cachea, un
  `401` de Minerva purga la entrada, y el número de entradas está acotado (se descartan las
  vencidas y, si aún sobra, las más próximas a vencer). Se añaden `invalidate_token(jti)` y
  `clear_caches()` para engancharlas al logout del consumidor.

- **La base garantiza una sola clave de firma `active` y una sola `pending`.** El invariante lo
  sostenía solo el código, así que un INSERT directo o una restauración a medias podían dejar dos
  activas y volver no determinista con qué clave se firma. La migración 009 repara los duplicados
  que existan (conserva la más reciente; retira las otras activas y borra las pendientes sobrantes,
  que nunca firmaron nada) y añade índices únicos parciales que lo impiden a futuro.

- **Rotar una clave ya no invalida sesiones vigentes.** La purga de claves retiradas usaba
  `MINERVA_ACCESS_TOKEN_TTL_MINUTES` (15 min) como ventana de solapamiento, pero los tokens
  `typ=session` y `typ=dev` viven 480 min: rotar borraba del JWKS una clave que todavía firmaba
  sesiones de panel activas. La ventana ahora se **deriva** de la vida máxima de token firmado más
  `MINERVA_CLOCK_SKEW_MINUTES`, para que no pueda quedar desfasada del TTL de sesión.

- **Sesión del panel fuera del alcance de JavaScript.** Un XSS ya no puede exfiltrar los tokens del
  panel (antes vivían legibles en `localStorage`). Se añade protección **CSRF** (synchronizer token
  en `X-CSRF-Token`, validado en tiempo constante) más validación de `Origin` para las mutaciones
  del panel, y el `sid` se guarda hasheado en Redis y se **rota** en cada autenticación.
- **Revocación durable en Redis.** Redis pasa a correr con persistencia AOF (`appendonly yes`) y
  `maxmemory-policy noeviction` sobre un volumen (`minerva_redis_data`), en vez de sin persistencia y
  `allkeys-lru`. Antes, un reinicio del contenedor o una evicción por presión de memoria borraba la
  blacklist de `jti`, los cortes de invalidación por usuario y las sesiones del panel, **resucitando
  tokens revocados** hasta su `exp` (hasta 8 h). Ahora un token revocado sigue rechazado tras
  reiniciar Redis; la política ante Redis caído es fail-closed (la request se rechaza, nunca fail-open).
  Además, todos los flujos que revocan/rotan tokens —invalidación al cambiar credenciales/status,
  revocación OAuth (`/revoke`), rotación de refresh (`grant_type=refresh_token`) y la revocación de
  familia por detección de reúso— ahora escriben las invalidaciones en Redis **antes** de confirmar
  PostgreSQL: si Redis falla, se hace rollback y el cambio no queda durable sin su invalidación
  (antes podía confirmarse el cambio en PG y perderse el corte/blacklist en Redis, o rotarse un
  refresh a medias).
- **Cabeceras HTTP defensivas en `nginx.conf`.** CSP (con `frame-ancestors 'none'`;
  `style-src 'unsafe-inline'` por Ant Design/cssinjs; `img-src` incluye `https:` para los logos de
  branding por app), `X-Content-Type-Options: nosniff` y `Referrer-Policy`. **HSTS no lo emite este
  nginx** (sirve HTTP; el deploy va tras un terminador TLS externo): debe configurarse en ese
  terminador, sin `preload` por defecto.

### Fixed

- **La URL de vuelta al consumidor se armaba concatenando strings.** Una `redirect_uri` registrada
  con query propia (`https://app/callback?tenant=jal`) quedaba malformada con dos `?`, y un `state`
  con caracteres reservados (espacio, `&`, `=`, `#`) llegaba alterado —justo el valor que el cliente
  compara para detectar CSRF. Ahora se construye con `urlencode`, preservando la query existente y
  devolviendo el `state` byte-for-byte (RFC 6749 §4.1.2). Aplica también a los callbacks de error
  (`access_denied`, `login_required`) y a la variante JSON `/auth/authorize/url`. Si la
  `redirect_uri` registrada trae un `code`/`state`/`error` propio, se reemplaza en vez de duplicar
  la clave: de cuál se quedaba el consumidor dependía de su parser, y un callback de error podía
  llegar con un `code`.
- **`response_type` se recibía y se ignoraba.** Un cliente que pedía `token` o `id_token` recibía un
  `code`, contradiciendo el propio discovery (`response_types_supported: ["code"]`). Ahora se rechaza
  con `error=unsupported_response_type` de vuelta al cliente, antes de emitir código alguno y sin
  hacer autenticar al usuario primero.
- **`auth_time` del `id_token` informaba una frescura falsa.** Se fijaba al instante de creación del
  código, así que un SSO silencioso 6 h después declaraba una autenticación reciente. Ahora es un
  claim inmutable del token `typ=session`, fijado al autenticarse y conservado al refrescarlo, y es
  la misma referencia contra la que se evalúa `max_age` (antes se enforceaba contra un valor y se
  reportaba otro). Es **por sesión de navegador**, no por usuario: iniciar sesión en otro equipo ya
  no rejuvenece las sesiones abiertas ni les deja pasar un `max_age` que no cumplen.
  `User.last_login_at` queda como dato informativo y deja de gobernar decisiones de autenticación.
  **Al desplegar, las sesiones abiertas exigen un re-login único**: no traen el claim, y `iat` no
  sirve como sustituto porque `/auth/refresh` lo regeneraba sin re-autenticar a nadie (una sesión
  vieja recién refrescada luciría fresca). Esas sesiones siguen sirviendo para SSO sin `max_age`,
  pero no pueden refrescarse ni acreditar frescura; se extinguen solas dentro del TTL de sesión.
- **Tras rotar, el backend rechazaba durante 5 min los tokens que él mismo acababa de firmar.** El
  caché del JWKS en Redis (`minerva:jwks:current`, 300 s) no se invalidaba nunca. Ahora el CLI lo
  borra al publicar o promover una clave, y además `_resolve_token` reconstruye el JWKS desde la BD
  al toparse con un `kid` que no conoce (una vez cada 10 s, para que un `kid` inventado no dispare
  una consulta por request). Con esa red de seguridad, un caché viejo ya no puede producir un 401
  espurio aunque Redis no se haya podido limpiar.

- **El SDK rechazaba tokens válidos hasta una hora tras una rotación de clave.** Solo refrescaba el
  JWKS al expirar su caché (`MINERVA_JWKS_CACHE_TTL`, 3600 s). Ahora lo refresca al ver un `kid`
  desconocido, limitado a uno cada `MINERVA_JWKS_REFRESH_COOLDOWN` (30 s por defecto).

- **La promoción de la clave nueva ya no deja el sistema sin clave activa.** El flujo anterior
  confirmaba el retiro de la clave activa antes de crear la siguiente, dejando una ventana en la
  que firmar respondía «No hay clave de firma activa». Retiro y activación ahora ocurren en la
  misma transacción, con `UPDATE` condicional: dos promociones concurrentes dejan exactamente una
  clave activa.

- **Borrar una aplicación ya usada dejaba huérfanos o violaba la FK.** `ApplicationRepository.delete`
  cascadeaba roles, permisos, redirect URIs, vínculos e importaciones de manifiesto, pero omitía los
  `auth_codes` y `refresh_tokens` emitidos por la app (ambos con FK a `applications.client_id`) ni los
  `audit_logs` (FK a `applications.id`). Ahora, en la misma transacción y antes de eliminar la app, se
  borran sus tokens OIDC (cascade duro, coherente con el resto) y se **conservan** los registros de
  auditoría desligándolos (`application_id = None`).

### Removed

- **BREAKING · CRUD administrativo retirado de `/api/v1`.** El Minerva Dev Kit ya no expone
  gestión de aplicaciones, usuarios, roles, permisos, asignaciones ni import de manifiestos.
  `/api/v1` queda solo con self-service: `POST /api/v1/auth/dev-login`, `GET /api/v1/me` y
  `GET /api/v1/me/permissions`. La administración vive únicamente en los routers canónicos del
  panel (`/applications`, `/users`, `/roles`, `/permissions`, `/groups`), protegidos con
  `require_minerva_admin`. El import de manifiestos por API pasa a `POST /applications/import-manifest`.

### Security

- **Escalada de privilegios por dev-login cerrada.** Antes, cualquier token de dev-login podía
  autoasignarse el rol Administrador porque el CRUD de `/api/v1` solo exigía estar autenticado.
- **Registro público cerrado por defecto.** `/auth/register` queda deshabilitado salvo que se
  active `MINERVA_ENABLE_PUBLIC_REGISTER=true`; además valida el correo (`EmailStr`) y exige una
  contraseña de al menos 8 caracteres.
- **Clases de token (`typ`) separadas por endpoint.** Cada JWT lleva un claim `typ`
  (`session`/`access`/`dev`/`id`) y cada endpoint acepta solo su clase mediante dependencias
  explícitas: el panel/admin, `/auth/refresh` y `/auth/authorize` exigen `typ=session`
  (`aud=minerva`); `/userinfo` solo `typ=access`; el self-service del Dev Kit (`/api/v1/me*`)
  `access`/`dev`; y el SDK de un consumidor solo `typ=access`. Tanto el backend como el SDK
  verifican **siempre** el `iss` (y el SDK el `aud` = `application_code`), sin interruptor para
  desactivarlo. Antes, un access de consumidor de 15 min cuyo sujeto fuera admin cruzaba al panel o
  refrescaba una sesión de 480 min, y `/userinfo` aceptaba cualquier token firmado.

### Fixed

- **Correo case-insensitive.** El correo se normaliza a minúsculas en el repositorio de usuarios,
  así distinto casing (`Alice@` vs `alice@`) no crea cuentas duplicadas y el login funciona sin
  importar mayúsculas.

## [0.3.4] - 2026-07-18

### Fixed

- **Login sin feedback al topar el rate limit.** `LoginPage` solo manejaba explícitamente `401`/
  `400`; un `429` (u otro error inesperado) fallaba en silencio — el botón "se apagaba" sin ningún
  mensaje, dando la impresión de que había dejado de responder. Ahora muestra un mensaje de error
  para `429` y para cualquier otro status no manejado.

### Docs

- **README rediseñado como portada del proyecto.** Banner institucional, enfoque en propósito y
  visión de Minerva en vez de manual técnico; el detalle de arquitectura/integración/despliegue
  se enlaza a `docs/` en vez de duplicarse.

## [0.3.3] - 2026-07-18

### Fixed

- **`/logout` colgado para consumidores.** `logout()` pasó a ser síncrono con el logout suave
  (v0.3.0), pero `LogoutPage` seguía llamando `.finally()` sobre su resultado (`undefined`) —
  `TypeError` que dejaba la página en "Cerrando sesión…" sin redirigir. Afectaba a todo consumidor
  que hiciera single logout contra el panel.
- **Doble clic con `prompt=select_account`.** Con una sola cuenta activa recién autenticada,
  `AuthorizePage` mostraba igual el selector de cuentas pidiendo "Continuar" — un clic redundante
  justo después de teclear credenciales. Ahora procede directo si la única cuenta guardada es la
  activa y no está vencida; el selector sigue apareciendo con ≥2 cuentas o una activa vencida.
- **Loop con `prompt=login`.** La re-autenticación forzada no limpiaba `prompt=login` del
  querystring de retorno, así que tras el login `AuthorizePage` volvía a forzar el formulario
  indefinidamente. Se quita `prompt` del resume antes de navegar a `/login`.

### Docs

- Documentado el single logout redirigido (`GET {panel}/logout?redirect_uri=...`) en
  `docs/integracion.md` y el skill `minerva-integration`: no estaba en el contrato para
  consumidores pese a ser el flujo que ya usaban, y no queda claro que es un logout suave (no
  revoca el token) a diferencia de `POST /auth/logout`.

## [0.3.2] - 2026-07-17

### Docs

- **Guías de integración/despliegue al día tras el nginx consolidado.** `docs/uso-imagen-docker.md`
  ya no dice que el backend publica `BACKEND_PORT`/`:9000` en el deploy de ghcr (ese compose no
  publica el backend desde v0.3.1); documenta `POSTGRES_DB`/`POSTGRES_USER`/`POSTGRES_PASSWORD` y
  el issuer sin puerto en producción. `docs/integracion.md` y el skill `minerva-integration`
  documentan la revocación server-side de refresh tokens al cambiar contraseña/correo o desactivar
  un usuario (código de error, y la diferencia de latencia entre `get_current_user` y
  `require_permission`).

## [0.3.1] - 2026-07-17

### Added

- **nginx consolidado para producción (un solo punto público).** nginx (servicio `frontend`) ahora
  sirve la SPA y proxea al backend `/.well-known`, `/auth`, `/userinfo`, `/api` (panel) y `/api/v1`
  (SDK/Dev Kit). El issuer OIDC pasa a `http://<host>` **sin `:9000`**; en el deploy el backend ya
  **no publica puerto** (solo nginx lo alcanza por la red interna). Deja listo el paso a HTTPS
  (terminación TLS en un solo lugar). Por ahora HTTP; al tener certificado, cambiar a `https://`.
- **Selector de cuentas con el mismo frontend del login.** El selector multi-sesión ahora usa
  el shell visual del formulario de login (fondo, card de dos columnas con branding y footer),
  con cuatro estados: formulario (sin cuentas guardadas), "Iniciar sesión con:" (cuenta activa +
  Continuar), dropdown para cambiar entre cuentas y gestor de cuentas para quitarlas del
  dispositivo. `/login` ya no salta directo al panel: si hay cuentas guardadas muestra el selector.
  Nuevo componente `AuthShell` (shell compartido) y reescritura de `AccountSelector`.

### Changed

- **Rate limit de login por cliente real.** Con `FORWARDED_ALLOW_IPS` en el backend y
  `X-Forwarded-For` de nginx, `request.client.host` es la IP real del cliente y no la de nginx, así
  el límite `5/15min` deja de ser global (un cliente ruidoso ya no bloquea a todos).
- **Logout suave.** "Cerrar sesión" en el panel ya no invalida el token ni marca
  la cuenta como vencida: solo sale localmente y la cuenta queda listada como activa mientras su
  token dure, para volver a entrar sin re-teclear credenciales. Para invalidar de verdad el token
  está "Cerrar todas las sesiones" (blacklist server-side); para olvidar la cuenta del dispositivo,
  "Gestionar cuentas" → quitar.

### Security

- **Invalidación de sesiones al cambiar credenciales o desactivar un usuario.** Cambiar contraseña,
  correo o poner el status en no-`active` invalida de inmediato los tokens vigentes: marca un corte
  por `iat` en Redis (rechazado en `get_current_user` para la sesión del panel) y revoca los refresh
  tokens OIDC del usuario (blacklisteando sus access `jti`). Los access tokens de consumidor son
  cortos (15 min) y no se renuevan tras la revocación.

### Fixed

- **Loop infinito `/admin`↔`/login`** cuando el `localStorage` tenía una sesión con un token
  rechazado por el backend (401), típicamente tras rotar las llaves RS256 (BD reseteada) o con
  una sesión previa a v0.3.0. `expireActive()` ahora limpia **siempre** el espejo legacy
  (`access_token`/`user`/`is_admin`), aunque no exista `minerva_active_sub`, y el interceptor de
  401 dispara un solo redirect a `/login` en vez de uno por cada request concurrente.

## [0.3.0] - 2026-07-17

### Added

- **Selector de cuentas / multi-sesión.** Minerva ahora puede mantener
  varias cuentas iniciadas en un mismo navegador y mostrar un selector al autorizar.
  - Un consumidor puede mandar `prompt=select_account` en `/auth/authorize` para que, en lugar de
    hacer SSO silencioso con la última cuenta activa, aparezca un selector con las cuentas ya
    iniciadas, las expiradas (para reingresar) y la opción de **agregar otra cuenta**.
  - `prompt=login` fuerza re-autenticación con credenciales aunque exista sesión.
  - Nuevo store multi-sesión en el panel (`frontend/src/api/session.js`) y componente
    `AccountSelector`. Dropdown de cambio de cuenta en el header del panel admin.
- **Logout server-side real.** `POST /auth/logout` ahora revoca el token en el servidor
  (blacklist por `jti` en Redis); un `/authorize` posterior ya no re-autentica en silencio con
  esa sesión.

### Fixed

- El interceptor de 401 del frontend ya no deja `is_admin` huérfano en `localStorage`.

### Docs

- `docs/integracion.md` y el skill `minerva-integration` documentan `prompt=select_account`,
  `prompt=login` y el logout server-side para los sistemas consumidores.

## [0.2.0]

- Línea base del contrato OIDC consumidor: Authorization Code + PKCE, access token RS256 corto,
  refresh tokens con rotación/reúso/revocación, id_token, discovery/JWKS, `/userinfo` y SDK
  (`minerva_sdk`) con validación RS256 vía JWKS. (Ver historial de git para el detalle por fase.)
