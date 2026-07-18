# Changelog

Todos los cambios notables de Minerva se documentan aquí.

El formato sigue [Keep a Changelog](https://keepachangelog.com/es-ES/1.1.0/)
y el proyecto usa [Versionado Semántico](https://semver.org/lang/es/).

## [Unreleased]

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
