# Glosario OIDC / OAuth 2.0 / IdP

Términos usados en este repositorio y en la documentación de integración. Pensado para
quien integra un sistema con Minerva y no maneja a diario la jerga de estos protocolos.

## Conceptos generales

**IdP (Identity Provider / Proveedor de Identidad)**
El sistema que autentica usuarios y emite tokens sobre su identidad y permisos. En este
repositorio, **Minerva es el IdP**. Los sistemas que confían en él (Godín, etc.) son
**sistemas consumidores** o **Relying Parties (RP)**.

**OAuth 2.0**
Protocolo de **autorización**: define cómo una aplicación obtiene un token para actuar en
nombre de un usuario frente a un recurso, sin que la aplicación vea la contraseña del
usuario. Por sí solo OAuth 2.0 no estandariza "quién es el usuario" — eso lo añade OIDC.

**OIDC (OpenID Connect)**
Capa de **autenticación** construida sobre OAuth 2.0. Estandariza cómo obtener la
identidad del usuario (`id_token`, endpoint `/userinfo`) además de los tokens de
autorización. Minerva implementa el flujo OIDC **Authorization Code + PKCE**.

**Cliente (Client) / Aplicación consumidora**
El sistema que delega su login en Minerva (p. ej. Godín). En este repo, cada cliente es
un registro en la tabla `applications`, identificado por un `client_id`.

**Cliente confidencial vs. cliente público**
- **Confidencial**: tiene un `client_secret` que puede guardar de forma segura (un backend).
  Minerva lo genera al registrar la app con `is_public: false` (default).
- **Público**: no puede guardar un secreto de forma segura (una SPA, una app móvil). Se
  registra con `is_public: true`; en su lugar usa **PKCE** para ligar el código de
  autorización a quien lo originó.

## El flujo Authorization Code + PKCE

**Authorization Code (código de autorización)**
Flujo OAuth 2.0 en el que el cliente nunca recibe el token directamente del navegador:
recibe un **código de un solo uso** (`code`) que después canjea, servidor-a-servidor, por
los tokens reales. Es el flujo recomendado para apps con backend (y, con PKCE, también
para SPAs/móviles).

**`/authorize` (Authorization Endpoint)**
`GET /auth/authorize` en Minerva. El navegador del usuario llega aquí (vía redirect del
cliente); si hay sesión, Minerva genera el `code` y redirige de vuelta al cliente. Si no
hay sesión, redirige a la pantalla de login y retoma el flujo después (parámetro `next=`).

**`/token` (Token Endpoint)**
`POST /auth/token` en Minerva. El backend del cliente canjea el `code` (más `code_verifier`
si aplica) por `access_token` + `id_token` + `refresh_token`. Esta llamada es
servidor-a-servidor, no pasa por el navegador.

**`code` (código de autorización)**
Valor de un solo uso, de vida muy corta, que prueba que el usuario acaba de autenticarse
en Minerva con ese `client_id`/`redirect_uri`/`scope`. No es el token final — solo sirve
para canjearlo en `/token`.

**PKCE (Proof Key for Code Exchange, RFC 7636)**
Mecanismo que liga el `/authorize` inicial con el `/token` final, **sin necesitar
`client_secret`**. El cliente genera un secreto aleatorio (`code_verifier`), envía su hash
(`code_challenge`) en `/authorize`, y revela el `code_verifier` original al canjear en
`/token`. Si alguien intercepta el `code` pero no conoce el `code_verifier`, no puede
canjearlo. Minerva usa el método `S256` (SHA-256) y lo exige para clientes públicos.

**`code_challenge` / `code_verifier`**
- `code_verifier`: cadena aleatoria de alta entropía, generada por el cliente, nunca
  expuesta en la URL.
- `code_challenge`: `BASE64URL(SHA256(code_verifier))`, la versión que sí viaja en la URL
  de `/authorize`. Minerva la guarda; al canjear, recalcula el hash del `code_verifier`
  recibido y lo compara.

**`redirect_uri`**
URL exacta a la que Minerva redirige tras autenticar, con el `code` en el query string.
Debe coincidir con una de las URIs registradas para esa aplicación — evita que un atacante
redirija el `code` a un destino propio (*open redirect*).

**`state`**
Valor opaco generado por el cliente antes de redirigir a `/authorize`, que Minerva
devuelve sin tocar junto al `code`. Protege contra CSRF en el flujo: el cliente verifica
que el `state` que recibe es el mismo que generó.

**`nonce`**
Similar a `state`, pero específico de OIDC y verificado **dentro del `id_token`** (no en
la URL de retorno). Protege contra ataques de repetición del `id_token`.

**`scope`**
Lista de permisos de identidad que el cliente solicita (`openid`, `profile`, `email`).
Determina qué claims aparecen en el `id_token` y en `/userinfo`. No tiene relación con los
permisos finos de autorización (`godin.oficios.create`) — esos se consultan aparte.

## Tokens

**Access Token**
Token de vida corta (`MINERVA_ACCESS_TOKEN_TTL_MINUTES`, default 15 min) que el cliente
envía como `Authorization: Bearer <token>` para llamar APIs. En Minerva lleva `sub`,
`email`, `roles`, `permissions`, `scope`, `jti` y `typ=access`, firmado RS256.

**Clase de token (`typ`)**
Todos los JWT firmados por Minerva llevan un claim `typ` que marca su clase y es
mutuamente excluyente: `session` (sesión del panel, 480 min, `aud=minerva`), `access`
(consumidor OIDC, 15 min, `aud=<código de app>`), `dev` (Dev Kit) e `id` (ID Token). Cada
endpoint acepta solo su clase: p. ej. el panel/admin y `/auth/refresh` exigen `typ=session`,
y el SDK de un consumidor solo acepta `typ=access`. Así un token de un contexto no cruza a otro
aunque su firma sea válida.

**ID Token**
Token OIDC con la **identidad** del usuario (no permisos), pensado para el propio cliente,
no para llamar APIs. `aud` = `client_id`. Lleva `nonce` si se mandó uno en `/authorize`.

**Refresh Token**
Token de vida larga (`MINERVA_REFRESH_TOKEN_TTL_DAYS`, default 30 días) que el cliente
guarda para pedir un access token nuevo sin que el usuario vuelva a autenticarse.

**Rotación de refresh tokens**
Cada vez que se usa un refresh token para pedir un access token nuevo, Minerva invalida el
refresh token usado y emite uno nuevo (RFC 6749 §10.4). Si un refresh token ya rotado se
reutiliza (señal de robo), Minerva revoca **toda la familia** de tokens derivados de él.

**`jti` (JWT ID)**
Identificador único de un token, usado para poder revocarlo individualmente (blacklist en
Redis) antes de que expire por sí solo.

**Revocación (`/auth/revoke`, RFC 7009)**
Endpoint para invalidar un refresh token (y su familia) y blacklistear los access tokens
ya emitidos a partir de él, antes de que expiren naturalmente.

## Firma y verificación

**RS256**
Algoritmo de firma JWT asimétrico (RSA + SHA-256): Minerva firma con una **clave
privada** y publica la **clave pública** correspondiente para que cualquiera pueda
verificar la firma sin conocer el secreto. Es el único algoritmo que usa Minerva — no hay
HS256 (firma simétrica con secreto compartido) en el sistema.

**JWKS (JSON Web Key Set, RFC 7517)**
Documento JSON con las claves públicas de firma, publicado en
`/.well-known/jwks.json`. Los consumidores lo descargan (y cachean) para verificar la
firma de los tokens sin llamar a Minerva en cada request.

**`kid` (Key ID)**
Identificador de la clave de firma específica usada en un token (va en el header del
JWT). Permite que el JWKS publique varias claves a la vez (la activa y las recién
retiradas) y que el verificador sepa cuál usar.

**Rotación de claves de firma**
Reemplazar periódicamente la clave RSA activa por una nueva, sin invalidar de golpe los
tokens ya emitidos con la clave anterior (se publican ambas en el JWKS durante una
ventana de solapamiento). En Minerva: `python -m app.cli rotate-key`.

**Discovery (`/.well-known/openid-configuration`)**
Documento JSON estándar OIDC que describe la configuración del IdP: endpoints
(`authorization_endpoint`, `token_endpoint`, `jwks_uri`, `userinfo_endpoint`), algoritmos
soportados, scopes, etc. Permite que una librería cliente se autoconfigure.

**`/userinfo`**
Endpoint OIDC (Core 5.3) que devuelve los claims de identidad del usuario autenticado,
filtrados por el `scope` con el que se emitió el token presentado como Bearer.

## Autorización (específico de Minerva)

**Permiso**
Acción concreta que un sistema consumidor declara que existe, con la forma
`{application_code}.{resource}.{action}` (p. ej. `godin.oficios.create`). Las acciones
estándar son `view, create, update, delete, assign, approve, authorize, export, import,
manage`.

**Rol**
Conjunto de permisos, definido por aplicación. Los usuarios tienen roles asignados
(directamente o vía grupo); el rol nunca se valida directamente, solo sirve para
*agrupar* permisos en el panel de administración.

**Manifiesto (`manifest.minerva.yml`)**
Archivo YAML que un sistema consumidor declara con su `application`, `permissions` y
`roles`. Minerva lo auto-importa al arrancar y hace upsert (sin duplicar ni borrar datos
existentes). Ver [`integracion.md`](integracion.md).

**Grupo**
Conjunto de usuarios al que se le pueden asignar roles; los usuarios heredan los roles de
los grupos a los que pertenecen, combinados con sus roles directos.

**`require_permission` (SDK)**
Dependencia de FastAPI (`minerva_sdk.fastapi.require_permission`) que valida en tiempo
real, contra Minerva, si el usuario autenticado tiene un permiso específico — nunca
revisa el rol localmente.
