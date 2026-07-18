# Changelog

Todos los cambios notables de Minerva se documentan aquí.

El formato sigue [Keep a Changelog](https://keepachangelog.com/es-ES/1.1.0/)
y el proyecto usa [Versionado Semántico](https://semver.org/lang/es/).

## [Unreleased]

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
