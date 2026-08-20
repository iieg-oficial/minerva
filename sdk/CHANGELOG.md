# Changelog de `minerva_sdk`

Los cambios del SDK se documentan aquí, **no** en el [`CHANGELOG.md`](../CHANGELOG.md) del
servidor: el SDK versiona en su propio ciclo (ver «Compatibilidad y versiones» en
[`README.md`](README.md)) y quien lo actualiza necesita leer un solo archivo con las versiones
del SDK, no las de Minerva.

El formato sigue [Keep a Changelog](https://keepachangelog.com/es-ES/1.1.0/)
y el paquete usa [Versionado Semántico](https://semver.org/lang/es/).

Cada versión indica en qué tags de Minerva viaja, porque el SDK se instala como requisito VCS
desde este repositorio: es lo que permite fijar la instalación a un tag concreto en vez de a
`main`.

> Las entradas 0.1.0–0.3.0 se reconstruyeron a partir del `CHANGELOG.md` del servidor y del
> historial de `sdk/`; el detalle fino de esas versiones está en git.

## [Unreleased]

## [0.3.0] - 2026-08-18

Viaja en Minerva `v0.7.0` y posteriores.

### Added

- **`MinervaOIDC`: el flujo OIDC completo sin copiar PKCE.** `authorization_request` (PKCE S256),
  `exchange_code`, `refresh` y `revoke` se construyen desde una sola `MINERVA_ISSUER_URL`, sin
  armar URLs de `/auth/authorize` ni `/auth/token` a mano. Errores OAuth como `MinervaOIDCError`.
- **Helpers públicos para sesiones server-side.** `validate_access_token`, `get_permissions`,
  `check_permission` e `invalidate_token` dejan de ser funciones internas: un consumidor que
  guarda la sesión en su propio backend ya no tiene que importar privados ni duplicarlos.
- **`settings.validate(login=...)`** enumera de una vez todos los valores faltantes o mal
  formados, en lugar de fallar en el primero.

### Changed

- **Contrato de integración simplificado.** El SDK trabaja con cinco variables en el recorrido
  normal (`MINERVA_ISSUER_URL`, `MINERVA_APPLICATION_CODE`, `MINERVA_CLIENT_ID`,
  `MINERVA_CLIENT_SECRET`, `MINERVA_REDIRECT_URI`); el resto son ajustes avanzados con default.

## [0.2.0] - 2026-07-20

Viaja en Minerva `v0.4.0` … `v0.6.0`.

### Changed

- **BREAKING · La caché de permisos queda desactivada por defecto.**
  `MINERVA_PERMISSIONS_CACHE_TTL` pasa de `300` a `0`. Con caché, una decisión positiva se servía
  de memoria sin consultar a Minerva, así que un token revocado seguía autorizando hasta 5
  minutos: la revocación no era inmediata. Ahora cada chequeo pregunta a Minerva, que es quien la
  aplica. Activar la caché es una decisión explícita del consumidor, que acepta esa ventana a
  cambio de menos tráfico.
  **Migración:** si dependías de la caché, pon `MINERVA_PERMISSIONS_CACHE_TTL=300` a propósito.
- **BREAKING · El bearer sale del objeto de usuario.** `get_current_user` ya no agrega
  `user["_token"]` con la credencial cruda; el dict son **solo** los claims del token, así que es
  seguro serializarlo en una respuesta o registrarlo en un log. `require_permission` obtiene el
  bearer de su propia dependencia `HTTPBearer`.
  **Migración:** donde leías `user["_token"]`, declara `HTTPBearer` como dependencia en tu
  endpoint. El resto del contrato del SDK no cambia.

### Fixed

- `clear_caches` también reinicia el cooldown de refresco del JWKS.
- La cota de la caché de permisos expulsa las entradas más próximas a vencer cuando barrer las
  vencidas no basta.

## [0.1.0] - 2026-06-16

Viaja en Minerva `v0.1.0` … `v0.3.4`.

### Added

- Primera versión del SDK: `get_current_user` y `require_permission` como dependencias de
  FastAPI, configuración por variables `MINERVA_*` y consulta de permisos efectivos a
  `GET /api/v1/me/permissions`.
- Validación de la firma **RS256 contra el JWKS público** de Minerva (sin secreto compartido),
  con el algoritmo fijado por rama para evitar confusión de algoritmo, verificación del `aud`
  contra `MINERVA_APPLICATION_CODE` y caché del JWKS (`MINERVA_JWKS_CACHE_TTL`).
