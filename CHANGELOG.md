# Changelog

Todos los cambios notables de Minerva se documentan aquí.

El formato sigue [Keep a Changelog](https://keepachangelog.com/es-ES/1.1.0/)
y el proyecto usa [Versionado Semántico](https://semver.org/lang/es/).

## [Unreleased]

### Changed

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
- **Logout suave estilo Google.** "Cerrar sesión" en el panel ya no invalida el token ni marca
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

- **Selector de cuentas / multi-sesión (estilo Google/GitHub).** Minerva ahora puede mantener
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
