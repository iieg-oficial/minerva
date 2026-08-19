# Arquitectura de Minerva

Minerva es el **proveedor de identidad (IdP) institucional del IIEG**. Centraliza
autenticación, gestión de usuarios/roles/permisos y emisión de tokens **OIDC/OAuth 2.0**
para que las plataformas internas deleguen su login y autorización en un solo lugar.

> Para la terminología OIDC/OAuth usada en este documento, ver [`glosario.md`](glosario.md).
> Para integrar un sistema consumidor, ver [`integracion.md`](integracion.md).
> Para desplegar y operar Minerva, ver [`despliegue.md`](despliegue.md).

## Principio rector

> Los sistemas definen *qué* acciones existen. Minerva define *quién* puede hacerlas.
> Los sistemas consumidores validan **permisos** (`{app}.{recurso}.{accion}`), nunca roles.

Un sistema declara sus permisos en un `manifest.minerva.yml`; Minerva administra qué
usuarios tienen esos permisos (vía roles); el sistema consumidor valida en tiempo de
ejecución con `require_permission("portal_demo.documents.create")`, nunca con `if user.role == "Admin"`.

## Mapa del monorepo

```
minerva/
├── backend/        FastAPI + SQLModel + Alembic + PostgreSQL — el IdP en sí
├── frontend/        React 19 + Ant Design 6 — panel admin + páginas de login/authorize
├── sdk/            minerva_sdk — helpers para que un consumidor valide tokens y permisos
├── manifests/      YAML que declaran apps/permisos/roles de los sistemas consumidores
├── examples/       minerva-consumer — integración de referencia (cliente público + PKCE)
└── docs/           esta documentación
```

## Componentes en tiempo de ejecución

```mermaid
flowchart LR
    subgraph Cliente["Sistema consumidor"]
        SPA[Frontend / SPA]
        API[Backend del consumidor<br/>+ minerva_sdk]
    end

    subgraph Minerva["Minerva (backend)"]
        AUTH[/auth/* · Login, authorize, token, revoke/]
        WK[/.well-known/* · Discovery, JWKS/]
        UI[/userinfo/]
        ADMIN[Panel admin API<br/>users · applications · roles · permissions · groups · audit]
        DEVKIT[/api/v1/* · Dev Kit/]
    end

    PG[(PostgreSQL)]
    REDIS[(Redis<br/>rate limit · blacklist · sesiones efímeras)]
    FRONTEND[Panel admin<br/>React]

    SPA -- "1. redirige a /auth/authorize" --> AUTH
    SPA -- login --> FRONTEND
    FRONTEND -- credenciales --> AUTH
    AUTH -- "2. code" --> SPA
    API -- "3. POST /auth/token (code + PKCE)" --> AUTH
    API -- "valida JWT" --> WK
    API -- "consulta permisos" --> DEVKIT
    API -- "claims de identidad" --> UI

    AUTH --> PG
    AUTH --> REDIS
    ADMIN --> PG
    DEVKIT --> PG
    WK --> PG
    FRONTEND -.administra.-> ADMIN
```

## Backend: arquitectura modular en capas

Cada dominio vive en `backend/app/modules/<nombre>/` con la misma separación estricta:

```
modules/<nombre>/
├── models.py       # Tablas SQLModel — estado en BD, sin lógica de negocio
├── schemas.py      # DTOs Pydantic (Create/Update/Read) — contrato HTTP
├── repository.py   # Único lugar con queries (`select(...)`)
├── service.py       # Lógica de negocio, validaciones, lanza AppException
└── router.py       # APIRouter — fino: parsea, llama al service, responde
```

`router → service → repository → models/schemas`. Ver `backend/CLAUDE.md` para las reglas
completas (no se repiten aquí).

### Módulos

| Módulo | Responsabilidad |
|---|---|
| `auth` | Login/registro, flujo OIDC `/authorize` + `/token` + `/revoke`, rate limiting |
| `oidc` | Claves de firma RS256, JWKS, discovery, `/userinfo` |
| `users` | CRUD de usuarios, hashing de contraseñas |
| `applications` | Registro de aplicaciones consumidoras (`client_id`/secret, redirect URIs, clientes públicos) |
| `roles` | Roles por aplicación |
| `permissions` | Permisos por aplicación y su relación con roles |
| `groups` | Grupos de usuarios; herencia de roles vía grupo |
| `authorization` | Chequeo de permisos efectivos (`/authorization/check`, `/authorization/me/permissions`) |
| `audit` | Bitácora de eventos (login, token exchange, rate limit excedido, etc.) |
| `devkit` | Contrato `/api/v1/*` **solo self-service**: dev-login, `me` y `me/permissions` (consumido por el SDK). La administración (CRUD, import de manifiestos) vive en los routers canónicos del panel |

### `core/`: utilidades compartidas

| Archivo | Responsabilidad |
|---|---|
| `config.py` | `Settings` (Pydantic), variables `MINERVA_*`, validación fail-fast en producción |
| `security.py` | Firma/verificación RS256, PKCE (S256), bcrypt, hashing de tokens |
| `crypto.py` | Cifrado Fernet de la clave privada RSA en reposo |
| `database.py` | Engine y sesión de SQLModel |
| `redis.py` | Cliente Redis async |
| `rate_limit.py` | Ventana deslizante para `/auth/login` y `/auth/authorize` |
| `token_blacklist.py` | Revocación de `jti` (access tokens) |
| `dependencies/auth.py` | Dependencias de autenticación **por clase de token** (ver tabla abajo); `_resolve_token` es el validador común (RS256 contra JWKS + `jti` blacklisteado + corte de invalidación por usuario) |
| `exceptions.py` | Jerarquía de `AppException` con mensajes en español |

#### Dependencias de autenticación por clase de token

No hay una dependencia genérica: cada endpoint declara qué `typ` de token acepta, para que
un JWT firmado por Minerva no sirva automáticamente en cualquier puerta.

| Dependencia | Credencial | Clases (`typ`) aceptadas | La usan |
|---|---|---|---|
| `get_current_panel_user` | Cookie opaca de panel → cuenta activa del contenedor | `session` | Panel/admin |
| `get_optional_panel_user` | Igual, pero sin sesión no falla | `session` | `/auth/authorize` (el consumidor puede llegar sin sesión) |
| `get_panel_session` | Cookie opaca, **sin** exigir cuenta activa válida | — | Selector de cuentas, logout |
| `get_current_access_user` | `Authorization: Bearer` | `access` | `/userinfo` y endpoints de consumidor |
| `get_current_devkit_user` | `Authorization: Bearer` | `access`, `dev` | Self-service del Dev Kit (`/api/v1/me*`) |

Las tres primeras resuelven **qué** token usar (el de la cuenta activa en Redis) y luego lo
validan con `_resolve_token`, igual que las de Bearer.

### Por qué `.well-known` y `/userinfo` son sub-apps aparte

`app/main.py` monta `wellknown_app` y `userinfo_app` (definidas en
`app/modules/oidc/router.py`) como **sub-aplicaciones FastAPI independientes**, no como
routers de la app principal:

- Deben responder con `Access-Control-Allow-Origin: *` (cualquier consumidor puede
  descubrir la configuración o validar su token) — incompatible con `allow_credentials=True`,
  que sí usa la app principal (cookies/sesión del panel).
- Aislarlas en su propia sub-app les da una política de CORS propia sin tocar la de la app principal.

## Flujo de autenticación delegada (OIDC Authorization Code + PKCE)

```mermaid
sequenceDiagram
    participant U as Usuario
    participant C as Sistema consumidor
    participant M as Minerva
    participant R as Redis/Postgres

    U->>C: Abre /login
    C->>U: Redirige a Minerva /auth/authorize?...&code_challenge=...
    U->>M: GET /auth/authorize (sin sesión)
    M->>U: Redirige a panel de login (?next=...)
    U->>M: Login (email/password o dev-login)
    M->>U: Redirige de vuelta a /auth/authorize (con sesión)
    M->>R: Genera `code`, guarda PKCE/nonce/state
    M->>C: Redirige a redirect_uri?code=...&state=...
    C->>M: POST /auth/token (code + code_verifier)
    M->>R: Valida code + PKCE, lo consume (un solo uso)
    M->>C: access_token + id_token + refresh_token (RS256)
    C->>M: GET /.well-known/jwks.json (cacheado)
    C->>C: Verifica firma del access_token localmente
    C->>M: GET /api/v1/me/permissions?application=<code>
    M->>C: Lista de permisos efectivos del usuario
```

Ver [`integracion.md`](integracion.md) para el detalle paso a paso y
[`glosario.md`](glosario.md) para cada término (`PKCE`, `code_challenge`, `nonce`, etc.).

## Firma de tokens y rotación de claves

Toda la firma es **RS256** (no hay HS256 en el sistema: un solo mecanismo de firma para
tokens de consumidores y de sesión interna del panel).

La rotación es de **dos fases (publish-before-use)** y son **dos comandos**, no uno: firmar
con una clave recién creada cortaría el servicio, porque los verificadores (el propio backend
vía Redis, el SDK con su caché de 1 h, cualquier consumidor OIDC) todavía no la tienen en su
JWKS cacheado.

```mermaid
flowchart TD
    A[Arranque del backend] --> B{¿Existe clave activa?}
    B -- no --> C[Genera par RSA 2048<br/>cifra clave privada con Fernet]
    B -- sí --> D[Usa la clave activa]
    C --> D
    D --> E[Firma tokens con kid de la clave activa]

    F["Fase 1 · python -m app.cli rotate-key"] --> G["Genera clave nueva → status=pending<br/>se publica en el JWKS pero NO firma nada"]
    G -.espera MINERVA_KEY_PROPAGATION_MINUTES.-> H["Fase 2 · python -m app.cli promote-key"]
    H --> I[pending → active<br/>la anterior pasa a retired]
    I --> J["Purga las retiradas más viejas que<br/>key_retirement_overlap_minutes"]

    E -.publica JWKS con activa + pendiente + retiradas.-> K["/.well-known/jwks.json"]
```

- **Fase 1 — `rotate-key`.** Publica la clave nueva como `pending`. Solo puede haber una
  pendiente a la vez (índice único parcial); intentar publicar otra da `409`.
- **Fase 2 — `promote-key`.** Rechaza la promoción si no han pasado
  `MINERVA_KEY_PROPAGATION_MINUTES` (default **60**) desde que se publicó la pendiente: en esa
  ventana todavía hay verificadores con el JWKS viejo. `--force` la salta a propósito, para el
  caso de clave comprometida (asumiendo el corte).
- **Retención.** Al promover, la clave anterior queda `retired` y **sigue publicada** en el
  JWKS `key_retirement_overlap_minutes` más. No es una variable de entorno: se **deriva** del
  token firmado más longevo (`max(MINERVA_ACCESS_TOKEN_TTL_MINUTES, sesión del panel)`) más el
  margen de reloj, precisamente para que no pueda quedar desincronizada del TTL de sesión.
- El `Cache-Control: max-age` del JWKS se emite con esa misma ventana de propagación, así que
  un verificador que respete la cabecera ya tiene la clave nueva cuando empieza a firmar.

No hay scheduler ni reconciliación automática: las dos fases se disparan desde el CLI (cron o
a mano) y es la operación quien decide cuándo.

La clave privada nunca se expone: se cifra con Fernet (`MINERVA_KEY_ENCRYPTION_KEY`) y
se guarda en la tabla `signing_keys`. El JWKS público solo expone la(s) clave(s) pública(s).

## Frontend

`frontend/src/` sigue un patrón **feature-sliced**: un cliente HTTP en `api/<dominio>.js`
(axios) por cada dominio, y páginas/componentes en `features/<feature>/`. Dos áreas:

- **`features/auth/`** — páginas públicas: login, `AuthorizePage` (punto de entrada del
  flujo OIDC para sistemas consumidores), dashboard, logout.
- **`features/admin/`** — panel administrativo (usuarios, aplicaciones, roles, permisos,
  grupos, autorización, auditoría), protegido por `ProtectedRoute`.

**Sesión del panel (patrón BFF).** El panel es **stateful**: el navegador guarda solo una cookie
opaca HttpOnly (`__Host-minerva_sid`), y el estado multi-cuenta (tokens `typ=session`, cuenta
activa, CSRF) vive en Redis (`backend/app/core/panel_session.py`). El frontend nunca ve el JWT: el
`SessionProvider` consulta `GET /auth/session` (descriptores no sensibles) y las mutaciones llevan
`X-CSRF-Token`. Es la única excepción al principio stateless; **OAuth/OIDC de consumidores sigue
stateless** (Bearer). La pérdida/limpieza de Redis invalida las sesiones del panel.

## SDK (`sdk/minerva_sdk`)

Helpers de FastAPI para que un sistema consumidor valide identidad y permisos sin
reimplementar la verificación JWT:

- `get_current_user`: decodifica el Bearer, exige `alg=RS256` (rechaza confusión de
  algoritmo), valida contra el JWKS de Minerva (cacheado), verifica `aud`/`iss` y que el
  token sea de clase `typ=access` (un consumidor no acepta sesiones de panel ni dev tokens).
- `require_permission(permission, application_code=None)`: dependencia que además
  consulta `GET /api/v1/me/permissions` en tiempo real (con caché corta) — un permiso
  revocado en Minerva deja de pasar en el siguiente request, sin esperar a que expire el token.

Ver `examples/minerva-consumer/` como integración de referencia completa.

## Manifiestos

Cada sistema consumidor declara su aplicación, permisos y roles en un
`manifest.minerva.yml` (formato y validaciones en [`integracion.md`](integracion.md)).
Minerva los auto-importa al arrancar (`MINERVA_AUTO_IMPORT_MANIFESTS`) de forma
**idempotente** (upsert: reimportar no borra datos ni regenera secrets).

**El contrato es aditivo: el manifiesto no es el estado deseado.** El importador
(`backend/app/modules/devkit/manifest.py`) solo crea o actualiza; **nunca borra**. En concreto:

- Quitar un permiso o un rol del YAML y reimportar **no** lo elimina de la base de datos, ni
  revoca las asignaciones que ya tenían los usuarios. El permiso sigue existiendo y sigue
  concediéndose.
- Quitar un permiso de la lista de un rol tampoco deshace esa relación.
- Renombrar equivale a **crear uno nuevo**, y el viejo se queda: la identidad de un permiso
  es su `key`, y la de un rol es el slug derivado de su `name`. Cambiar el `name` de un rol
  crea otro rol y deja el anterior con sus usuarios asignados.

Dar de baja un permiso, un rol o una asignación es una acción explícita desde el panel
administrativo. No hay reconciliación ni proceso que compare el YAML con la base y borre la
diferencia — y es deliberado: un manifiesto mal editado no debe poder tirar accesos vivos.

## Estado real de la implementación

Ver el checklist interno (`docs/minerva-roadmap-checklist.md`, no trackeado en git) para
el detalle componente por componente.
