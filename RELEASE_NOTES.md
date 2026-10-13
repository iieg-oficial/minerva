# Changelog

Todos los cambios notables de Minerva se documentan aquí.

El formato sigue [Keep a Changelog](https://keepachangelog.com/es-ES/1.1.0/)
y el proyecto usa [Versionado Semántico](https://semver.org/lang/es/).

## [Unreleased]

### Added

- **Política de contraseña y medidor de fuerza.** Toda contraseña nueva —activación por
  invitación y cambio propio— exige mínimo 8 caracteres y al menos 2 de tres familias
  (mayúscula y minúscula, número, carácter especial), validada en el backend y con un indicador
  de fuerza en la pantalla. Portado del medidor de mariachi.
- **El enlace de contraseña puede llevar a la aplicación de la persona.** Al generarlo, el panel
  ofrece las aplicaciones donde tiene roles y con `homepage_url`; al guardar la contraseña se le
  manda ahí en vez del login de Minerva, cuyo panel es solo para administradores. El destino vive
  en `credential_tokens.application_id` (migración `013`), no en el enlace, así que no se puede
  alterar. Nuevos `GET /users/{id}/credential-destinations` y el cuerpo opcional
  `{"application_id"}` en `POST /users/{id}/credential-link`.

### Changed

- **El alta y la edición de usuarios ya no fijan contraseña: siempre es por invitación.** El
  panel emite un enlace de un solo uso para que la persona defina la suya; se retiró el campo de
  contraseña y la marca de cambio obligatorio del alta/edición, y `UserCreate`/`UserUpdate` dejan
  de aceptar `password` (y `require_change`).

### Fixed

- **`/userinfo` sin barra respondía 307.** El discovery lo anuncia sin barra, pero el mount solo
  resolvía `/userinfo/`; detrás del proxy la redirección perdía el puerto interno y los
  consumidores server-to-server no completaban el login. Un middleware reescribe la ruta antes de
  llegar al router.

- **Quien no administra Minerva terminaba en un 403 después de iniciar sesión en él.** `/no-access`
  ahora ofrece ir a las aplicaciones que la persona usa (`/auth/me` devuelve `applications`) y solo
  muestra el aviso de acceso cuando no tiene ninguna.

- **El cambio de contraseña por enlace dejaba el panel ciclando en el login.** Al fijar la
  contraseña por enlace (sin sesión de panel) el backend revoca las sesiones pero no puede limpiar el
  contenedor del navegador, así que el selector seguía ofreciendo la cuenta ya revocada: elegirla daba
  401 y rebotaba (login → selector → login). `SetPasswordPage` ahora destruye el contenedor tras
  guardar, para llegar a un login en blanco.
- **El panel reventaba (React #31) al mostrar un error de validación 422.** Renderizaba el
  `detail` de FastAPI —un arreglo de objetos— como texto; ahora se normaliza a su mensaje legible.
- **El aviso de privacidad del login apuntaba a un PDF con fecha en la URL.** El enlace del pie
  llevaba a `iieg.gob.mx/ns/wp-content/uploads/2025/06/Aviso_de_Privacidad_Integral_IIEG_06_2025.pdf`,
  así que el día que el instituto publique una versión nueva el enlace queda apuntando a la vieja o
  responde 404, y arreglarlo obliga a tocar este repo y desplegar. Es el mismo problema que ya
  corrigieron los otros consumidores.

  Ahora apunta a `https://iieg.jalisco.gob.mx/acervo/iieg/avisos-de-privacidad.pdf`, servido desde
  el Acervo del instituto: la URL no lleva versión, así que publicar un aviso nuevo es reemplazar el
  objeto en el bucket, sin tocar este repo ni desplegar. Es el mismo destino que usan mariachi y
  sieej, así que el usuario ve el mismo aviso en las tres pantallas.

### Security

- **El límite de intentos del login se esquivaba cambiando `X-Forwarded-For` (#209).** nginx
  reenviaba el header del cliente con `$proxy_add_x_forwarded_for` y el backend confiaba en
  cualquier origen (`FORWARDED_ALLOW_IPS="*"`), así que bastaba rotar el header para no topar nunca.
  Ahora nginx solo crea el `X-Forwarded-For` del proxy de confianza (`MINERVA_TRUSTED_PROXY`, por
  defecto ninguno) y lo reemplaza por la IP resuelta, y el backend solo confía en la IP fija de
  nginx (`MINERVA_PROXY_IP` dentro de `MINERVA_SUBNET`). ⚠️ La red interna pasa a subred fija:
  recrearla una vez (`just down && just up`).
- **Límite de intentos por cuenta en el login (#209).** Tras `RATE_LIMIT_LOGIN_MAX` fallos de una
  cuenta en `RATE_LIMIT_LOGIN_WINDOW`, esa cuenta responde 429 con `Retry-After`, con la misma
  respuesta exista o no. Un login exitoso limpia el contador. El límite por IP se conserva como
  segundo nivel con `RATE_LIMIT_LOGIN_IP_MAX`/`RATE_LIMIT_LOGIN_IP_WINDOW` (200 en 15 min): detrás
  de un WAF que no agrega `X-Forwarded-For` todos comparten IP y un tope bajo bloquearía a todos.
  ⚠️ `RATE_LIMIT_LOGIN_MAX` pasa de contar intentos por IP a contar fallos por cuenta.
- **Tras cerrar sesión, la cuenta se reactivaba sin contraseña (#210).** «Cerrar sesión» era un
  logout suave: conservaba el token de 8 h y el selector volvía a activarlo con un clic, así que en
  un equipo compartido quien llegaba después entraba como la persona anterior. Ahora
  `POST /auth/logout` revoca el token de la cuenta activa y la deja en el selector como cerrada
  (`signed_out`), pidiendo contraseña para volver. `POST /auth/session/active` solo activa cuentas
  con sesión viva y responde 409 si no; cambiar entre cuentas abiertas sigue sin pedir contraseña.
- **`python-jose` sube su mínimo a 3.4** en el backend y en el SDK. Con `>=3.3` una instalación podía
  quedarse en 3.3.0, afectada por CVE-2024-33663 (confusión de algoritmos) y CVE-2024-33664 (DoS con
  JWE comprimido).
- **`axios` sube a 1.20.0** en el panel (mínimo `^1.20.0`), que cierra nueve avisos de Dependabot
  sobre 1.18.0. Ninguno era alcanzable: casi todos viven en los adaptadores `http`/`http2` de Node o
  en su manejo de proxies, y el panel corre en el navegador con el adaptador `xhr`.

## [1.1.0] - 2026-10-13

> **Release de mejoras de credenciales y seguridad.** Esta versión añade seguridad alrededor de
> contraseñas y enlaces de acceso, simplifica el alta/edición de usuarios y corrige varios
> problemas de flujo, navegación y protección en el panel y el login.

### Added

- **Política de contraseña y medidor de fuerza.** Toda contraseña nueva —activación por
  invitación y cambio propio— exige mínimo 8 caracteres y al menos 2 de tres familias
  (mayúscula y minúscula, número, carácter especial), validada en el backend y con un indicador
  de fuerza en la pantalla. Portado del medidor de mariachi.
- **El enlace de contraseña puede llevar a la aplicación de la persona.** Al generarlo, el panel
  ofrece las aplicaciones donde tiene roles y con `homepage_url`; al guardar la contraseña se le
  manda ahí en vez del login de Minerva, cuyo panel es solo para administradores. El destino vive
  en `credential_tokens.application_id` (migración `013`), no en el enlace, así que no se puede
  alterar. Nuevos `GET /users/{id}/credential-destinations` y el cuerpo opcional
  `{"application_id"}` en `POST /users/{id}/credential-link`.

### Changed

- **El alta y la edición de usuarios ya no fijan contraseña: siempre es por invitación.** El
  panel emite un enlace de un solo uso para que la persona defina la suya; se retiró el campo de
  contraseña y la marca de cambio obligatorio del alta/edición, y `UserCreate`/`UserUpdate` dejan
  de aceptar `password` (y `require_change`).

### Fixed

- **`/userinfo` sin barra respondía 307.** El discovery lo anuncia sin barra, pero el mount solo
  resolvía `/userinfo/`; detrás del proxy la redirección perdía el puerto interno y los
  consumidores server-to-server no completaban el login. Un middleware reescribe la ruta antes de
  llegar al router.
- **Quien no administra Minerva terminaba en un 403 después de iniciar sesión en él.** `/no-access`
  ahora ofrece ir a las aplicaciones que la persona usa (`/auth/me` devuelve `applications`) y solo
  muestra el aviso de acceso cuando no tiene ninguna.
- **El cambio de contraseña por enlace dejaba el panel ciclando en el login.** Al fijar la
  contraseña por enlace (sin sesión de panel) el backend revoca las sesiones pero no puede limpiar el
  contenedor del navegador, así que el selector seguía ofreciendo la cuenta ya revocada: elegirla daba
  401 y rebotaba (login → selector → login). `SetPasswordPage` ahora destruye el contenedor tras
  guardar, para llegar a un login en blanco.
- **El panel reventaba (React #31) al mostrar un error de validación 422.** Renderizaba el
  `detail` de FastAPI —un arreglo de objetos— como texto; ahora se normaliza a su mensaje legible.
- **El aviso de privacidad del login apuntaba a un PDF con fecha en la URL.** El enlace del pie
  llevaba a `iieg.gob.mx/ns/wp-content/uploads/2025/06/Aviso_de_Privacidad_Integral_IIEG_06_2025.pdf`,
  así que el día que el instituto publique una versión nueva el enlace queda apuntando a la vieja o
  responde 404, y arreglarlo obliga a tocar este repo y desplegar. Es el mismo problema que ya
  corrigieron los otros consumidores.

  Ahora apunta a `https://iieg.jalisco.gob.mx/acervo/iieg/avisos-de-privacidad.pdf`, servido desde
  el Acervo del instituto: la URL no lleva versión, así que publicar un aviso nuevo es reemplazar el
  objeto en el bucket, sin tocar este repo ni desplegar. Es el mismo destino que usan mariachi y
  sieej, así que el usuario ve el mismo aviso en las tres pantallas.

### Security

- **El límite de intentos del login se esquivaba cambiando `X-Forwarded-For` (#209).** nginx
  reenviaba el header del cliente con `$proxy_add_x_forwarded_for` y el backend confiaba en
  cualquier origen (`FORWARDED_ALLOW_IPS="*"`), así que bastaba rotar el header para no topar nunca.
  Ahora nginx solo crea el `X-Forwarded-For` del proxy de confianza (`MINERVA_TRUSTED_PROXY`, por
  defecto ninguno) y lo reemplaza por la IP resuelta, y el backend solo confía en la IP fija de
  nginx (`MINERVA_PROXY_IP` dentro de `MINERVA_SUBNET`). ⚠️ La red interna pasa a subred fija:
  recrearla una vez (`just down && just up`).
- **Límite de intentos por cuenta en el login (#209).** Tras `RATE_LIMIT_LOGIN_MAX` fallos de una
  cuenta en `RATE_LIMIT_LOGIN_WINDOW`, esa cuenta responde 429 con `Retry-After`, con la misma
  respuesta exista o no. Un login exitoso limpia el contador. El límite por IP se conserva como
  segundo nivel con `RATE_LIMIT_LOGIN_IP_MAX`/`RATE_LIMIT_LOGIN_IP_WINDOW` (200 en 15 min): detrás
  de un WAF que no agrega `X-Forwarded-For` todos comparten IP y un tope bajo bloquearía a todos.
  ⚠️ `RATE_LIMIT_LOGIN_MAX` pasa de contar intentos por IP a contar fallos por cuenta.
- **Tras cerrar sesión, la cuenta se reactivaba sin contraseña (#210).** «Cerrar sesión» era un
  logout suave: conservaba el token de 8 h y el selector volvía a activarlo con un clic, así que en
  un equipo compartido quien llegaba después entraba como la persona anterior. Ahora
  `POST /auth/logout` revoca el token de la cuenta activa y la deja en el selector como cerrada
  (`signed_out`), pidiendo contraseña para volver. `POST /auth/session/active` solo activa cuentas
  con sesión viva y responde 409 si no; cambiar entre cuentas abiertas sigue sin pedir contraseña.
- **`python-jose` sube su mínimo a 3.4** en el backend y en el SDK. Con `>=3.3` una instalación podía
  quedarse en 3.3.0, afectada por CVE-2024-33663 (confusión de algoritmos) y CVE-2024-33664 (DoS con
  JWE comprimido).
- **`axios` sube a 1.20.0** en el panel (mínimo `^1.20.0`), que cierra nueve avisos de Dependabot
  sobre 1.18.0. Ninguno era alcanzable: casi todos viven en los adaptadores `http`/`http2` de Node o
  en su manejo de proxies, y el panel corre en el navegador con el adaptador `xhr`.

## [1.0.1] - 2026-09-14

> **Release intermedio.** Las personas fijan y cambian su propia contraseña (invitación,
> restablecimiento, cambio obligatorio y cambio propio), y el rol `minerva.admin` deja de conceder
> administración global fuera de la app `minerva`. Incluye la migración `012_credential_lifecycle`.
> ⚠️ **Cambio de contrato:** `PATCH /users/{id}` con `password` ahora exige cambiarla en el próximo
> ingreso, salvo que se envíe `"require_change": false` (ver *Changed*).

### Added

- **Ciclo de vida de la credencial.** Hasta ahora la contraseña solo la creaba o cambiaba un
  administrador global, era obligatoria al dar de alta y nada forzaba a cambiar una temporal.
  - **Alta por invitación:** `POST /users` sin `password` crea al usuario en estado `pending` y
    devuelve un enlace de un solo uso (`credential_link`) que el administrador entrega; con él la
    persona fija su contraseña en `/activar` y la cuenta pasa a `active`. Sin SMTP.
  - **Restablecimiento:** `POST /users/{id}/credential-link` genera un enlace nuevo (invitación si
    sigue pendiente, restablecimiento si no) e invalida los anteriores. Es también la vía de
    recuperación por olvido mientras Minerva no envíe correo.
  - **Cambio obligatorio:** si un administrador fija la contraseña (`PATCH /users/{id}`), la
    persona debe cambiarla en su próximo ingreso (`require_change`, activo por defecto). El login
    responde `403 password_change_required` con un token de un solo uso y **no** abre sesión.
  - **Cambio propio:** `POST /auth/password` (sesión + CSRF, exige la contraseña actual) y la
    pantalla `/cuenta/contrasena`, accesible también para quien no es administrador.
  - Los enlaces guardan solo el hash del token, llevan el token en el fragmento (`#token=`) para
    que no llegue a logs ni al `Referer`, vencen (`CREDENTIAL_INVITE_TTL_HOURS=72`,
    `CREDENTIAL_RESET_TTL_HOURS=24`) y tienen rate limit por IP (`RATE_LIMIT_CREDENTIAL_*`). Fijar
    o cambiar la contraseña invalida todas las sesiones y refresh tokens previos del usuario.
  - Migración `012_credential_lifecycle`: tabla `credential_tokens` y columna
    `users.password_change_required`.

### Changed

- **`PATCH /users/{id}` con `password` ahora obliga a cambiarla en el próximo ingreso.** Es un
  cambio de contrato para quien ya fijaba contraseñas por API: el login responde `403
  password_change_required` hasta que la persona defina una propia. Para conservar el
  comportamiento anterior, envía `"require_change": false`.
- **El estado `pending` solo lo asigna el alta sin contraseña.** Ponerlo a mano responde 400, y
  fijar una contraseña a un usuario pendiente lo activa y anula su invitación.

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

### Fixed

- El panel importaba el router desde `react-router` (una transitiva) en `LoginPage` y
  `AdminLayout`, y desde `react-router-dom` (la dependencia declarada) en el resto. Fuera del
  bundler los dos especificadores resuelven a instancias distintas y el contexto del router deja
  de compartirse; ahora todo el panel importa `react-router-dom`.

### Docs

- **Valores esperados de `MINERVA_ORG` y `MINERVA_VERSION`** en `docs/uso-imagen-docker.md` y
  `.env.production.example`: la org dueña de los paquetes en ghcr y el tag de la imagen, que es el
  del release **sin la `v`** (`v0.7.0` → `0.7.0`) o `latest`.

## [0.7.0] - 2026-08-18

### Added

- **SDK 0.3.0 y consumidor de referencia.** `MinervaOIDC` construye el flujo Authorization
  Code + PKCE, canje, refresh y revocación desde una sola `MINERVA_ISSUER_URL`; los helpers
  públicos permiten validar sesiones server-side sin copiar funciones internas. El ejemplo
  `minerva-consumer` demuestra login, acceso denegado, roles informativos, permisos, 401/403,
  refresh y logout con tokens fuera del navegador.

## [0.6.0] - 2026-08-12

> **Estado del release.** 0.6.0 es un release de **desbloqueo para los consumidores OIDC**: publica
> a `main` el contrato OAuth endurecido que hasta ahora solo existía en `develop`, para que los
> sistemas que se están integrando trabajen contra una versión publicada. **No es el 1.0.0**; la
> decisión de declarar 1.0 queda sujeta a la auditoría, que es posterior a este release.

### Added

- **El Authorization Endpoint acepta `POST` con `application/x-www-form-urlencoded`.** OIDC Core
  §3.1.2.1 obliga a soportar `GET` **y** `POST`, y `/auth/authorize` solo tenía `GET`: un RP que
  siguiera la spec al pie de la letra —o una librería OIDC certificada— recibía un `405`.

### Fixed

- **`GET /auth/authorize` propaga `max_age` desde el panel.** `AuthorizePage` no leía ni reenviaba
  el parámetro, así que el backend nunca lo recibía y una sesión activa completaba SSO silencioso
  ignorando la reautenticación que el RP había pedido.

## [0.5.0] - 2026-07-31

> **Estado del release.** 0.5.0 publica el trabajo ya integrado desde 0.4.0 como un checkpoint
> previo a 1.0.0. Incluye correcciones de seguridad, atomicidad, concurrencia y conformidad
> OAuth/OIDC; no implica que los pendientes del milestone 1.0.0 estén cerrados.

### Fixed

- **`/auth/token` no devolvía un error OAuth programable.** Sus errores (grant desconocido, código
  ya usado, `client_secret` inválido, parámetros faltantes) solo traían un `detail` genérico, así
  que un cliente no podía distinguir casos sin parsear texto en español.

## [0.4.0] - 2026-07-22

> **Estado del release.** 0.4.0 es un checkpoint de integración, **no** la versión 1.0.0
> publicable. Cierra riesgos graves que seguían vivos en `main`.

## [0.3.4] - 2026-07-18

### Fixed

- **Login sin feedback al topar el rate limit.** `LoginPage` solo manejaba explícitamente `401`/
  `400`; un `429` (u otro error inesperado) fallaba en silencio.

## [0.3.3] - 2026-07-18

### Fixed

- **`/logout` colgado para consumidores.** `logout()` pasó a ser síncrono con el logout suave
  (v0.3.0), pero `LogoutPage` seguía llamando `.finally()` sobre su resultado (`undefined`) —
  `TypeError` que dejaba la página en "Cerrando sesión…" sin redirigir.

## [0.3.2] - 2026-07-17

### Docs

- **Guías de integración/despliegue al día tras el nginx consolidado.**

## [0.3.1] - 2026-07-17

### Added

- **nginx consolidado para producción (un solo punto público).**

## [0.3.0] - 2026-07-17

### Added

- **Selector de cuentas / multi-sesión.**

## [0.2.0]

- Línea base del contrato OIDC consumidor: Authorization Code + PKCE, access token RS256 corto,
  refresh tokens con rotación/reúso/revocación, id_token, discovery/JWKS, `/userinfo` y SDK
  (`minerva_sdk`) con validación RS256 vía JWKS.

## [0.1.0] - 2026-07-01

- Primer release versionado de Minerva para que integradores y despliegues puedan fijar una
  versión estable del repositorio.

### Added

- Migración de Authentik a Minerva Dev Kit.
- Provider OIDC estándar con Authorization Code + PKCE, JWKS, id_token y refresh tokens.

### Fixed

- Ajustes de despliegue y validaciones de CI.

### Docs

- Documentación de arquitectura, despliegue e integración.
