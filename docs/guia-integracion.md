# Guía de integración de un sistema con Minerva

> **Nota (2026-06):** esta guía describe el flujo de transición con **firma HS256
> y secreto compartido** (`MINERVA_JWT_SECRET`). Sigue funcionando, pero para
> **sistemas nuevos** la vía recomendada es **OIDC con RS256/JWKS** (sin secreto
> compartido), documentada en **`docs/oidc-integracion.md`**. El registro de la app,
> el manifiesto y la asignación de roles (§2–§3) son comunes a ambos enfoques.

Esta guía explica, paso a paso, cómo conectar un sistema (un "consumidor") a
Minerva para que **todo el login se delegue a Minerva**: el usuario se autentica
en Minerva y vuelve a tu sistema con un JWT y sus permisos.

Cubre los dos escenarios:

- **Escenario A — tu sistema ya tiene login propio:** hay que **quitarlo** y
  redirigir a Minerva.
- **Escenario B — tu sistema aún no tiene login:** solo implementas la
  redirección a Minerva.

Ambos terminan en el mismo lugar: tu **backend** habla con Minerva, valida el
JWT y consulta permisos; tu **frontend** no tiene formulario de login.

> Implementación de referencia: **Godín** (`iieg/godin`). Si algo no queda claro,
> mira sus módulos `backend/app/modules/auth/` y `frontend/src/features/auth/`.

---

## 1. Cómo funciona el flujo (visión general)

Minerva funciona como "Iniciar sesión con Google", pero interno. El login vive
en el **frontend de Minerva**; el intercambio de tokens lo hace el **backend de
tu sistema** (que es quien guarda el `client_secret`).

```
Navegador        Tu backend            Frontend Minerva       API Minerva
   │  click "Iniciar sesión"
   ├──────────────► GET /auth/login
   │                  │ arma URL + state(cookie)
   │ ◄────────────────┘ 302 → {MINERVA_LOGIN_URL}/authorize?client_id&redirect_uri&state
   ├───────────────────────────────────► /authorize
   │                                        │ ¿sesión? si no → /login → login
   │                                        ├──────────────────────► GET /auth/authorize/url  (Bearer)
   │                                        │ ◄──────────────────────┘ { redirect_url con ?code }
   │ ◄──────────────────────────────────────┘ 302 → {redirect_uri}?code&state
   ├──────────────► GET /auth/callback?code&state
   │                  │ valida state, POST {ISSUER}/auth/token (client_secret)
   │                  │ recibe access_token (JWT)
   │ ◄────────────────┘ 302 → {FRONTEND_URL}/auth/callback#access_token=...
   │  (frontend guarda el token y llama GET /auth/me con Bearer)
```

Puntos clave:

- El **navegador** se redirige al **frontend** de Minerva (`MINERVA_LOGIN_URL`),
  no al API.
- El **backend** de tu sistema intercambia el `code` por el JWT contra el **API**
  de Minerva (`MINERVA_ISSUER_URL`) usando el `client_secret`. El secret nunca
  toca el navegador.
- Tu sistema valida el JWT (firma + audience) y consulta permisos en
  `GET {ISSUER}/api/v1/me/permissions?application=<code>`.

---

## 2. Paso 1 — Registrar tu aplicación en Minerva

Necesitas un `client_id` y un `client_secret`. Dos formas:

### Opción A — Panel de administración (recomendada)

1. Entra al panel (`http://localhost:3100/admin/applications` en dev).
2. **Nueva aplicación** → nombre y `slug` (el slug es el `application.code`, p. ej.
   `godin`).
3. Copia el **Client ID** y el **Client Secret** que aparecen en el modal.

> ⚠️ El `client_secret` **solo se muestra una vez**. Si lo pierdes, usa el botón
> **🔑 Regenerar client secret** del mismo renglón (no cambia el `client_id`).

4. En el renglón de tu app, botón **🔗** → agrega la **redirect URI**:
   `http://localhost:3000/api/auth/callback` (ajústala a tu host/puerto).

### Opción B — API

```bash
# Token de un admin (panel) o dev-login
POST /applications
{ "name": "Godín", "slug": "godin", "homepage_url": "http://localhost:3000" }
# → devuelve client_id y client_secret (el secret, una sola vez)

POST /applications/{app_id}/redirect-uris
{ "uri": "http://localhost:3000/api/auth/callback", "environment": "development" }
```

> ⚠️ **Gotcha del manifiesto:** si Minerva **auto-importa** tu manifiesto al
> arrancar (`MINERVA_AUTO_IMPORT_MANIFESTS=true`), la app `godin` se crea con un
> secret aleatorio que **no se muestra**. En ese caso, entra al panel y usa
> **Regenerar client secret** para obtener uno usable. Crear la app por segunda
> vez con el mismo slug falla con "Ya existe una aplicación con ese slug".

---

## 3. Paso 2 — Crear e importar el manifiesto

El manifiesto declara la aplicación, sus **permisos** y sus **roles**. Colócalo
como `manifest.minerva.yml` en la raíz de tu sistema.

```yaml
application:
  code: godin                 # slug único, == MINERVA_APPLICATION_CODE
  name: Godín
  description: Gestión de oficios, memos y solicitudes
  base_url: http://localhost:3000
  redirect_uris:
    - http://localhost:3000/api/auth/callback

permissions:
  - key: godin.oficios.view     # {application_code}.{recurso}.{accion}
    name: Ver oficios
  - key: godin.oficios.create
    name: Crear oficios

roles:
  - name: Capturista
    permissions:
      - godin.oficios.view
      - godin.oficios.create
  - name: Administrador
    permissions:
      - godin.oficios.view
      - godin.oficios.create
```

Reglas del importador (validadas):

- `application.code` obligatorio (minúsculas/números/guion_bajo).
- Cada permiso usa **`key`** con la convención `{application_code}.{recurso}.{accion}`.
  Acciones válidas: `view create update delete assign approve authorize export import manage`.
- Los roles solo pueden referenciar permisos declarados en el mismo manifiesto.

### Importar

```bash
# Multipart (legacy)
POST /applications/import-manifest   -F "file=@manifest.minerva.yml"
# o el contrato Dev Kit
POST /api/v1/manifests/import        -F "file=@manifest.minerva.yml"
```

O automático al arrancar Minerva: deja el archivo en `MINERVA_MANIFESTS_PATH`
(`./manifests`) con `MINERVA_AUTO_IMPORT_MANIFESTS=true`. La importación es
**idempotente** (upsert) y **no regenera** el secret de una app existente.

> Importar el manifiesto **no asigna** roles a usuarios. Eso se hace en el panel
> o por API (`POST /api/v1/access-assignments`). Un usuario sin rol/permiso de tu
> app autentica pero tu sistema debe tratarlo como "sin acceso" (ver §6).

---

## 4. Paso 3 — Configurar variables de entorno en tu sistema

Estas variables van en el `.env` del **backend** de tu sistema. Distingue cuáles
usa el **navegador** y cuáles el **backend**, porque en Docker cambian:

| Variable | La usa | Valor (dev) |
|---|---|---|
| `MINERVA_ISSUER_URL` | **backend → API** (validar token, permisos, canjear code) | `http://localhost:9000` o, si tu backend corre en Docker, `http://host.docker.internal:9000` |
| `MINERVA_LOGIN_URL` | **navegador** (página `/authorize` y `/logout`) | `http://localhost:3100` |
| `MINERVA_APPLICATION_CODE` | backend | `godin` (== `application.code`) |
| `MINERVA_JWT_SECRET` | backend (valida firma del JWT) | **debe ser igual** al secreto efectivo de Minerva |
| `MINERVA_CLIENT_ID` | backend | el del registro |
| `MINERVA_CLIENT_SECRET` | backend (canje del code) | el del registro |
| `MINERVA_REDIRECT_URI` | backend (debe coincidir con la registrada) | `http://localhost:3000/api/auth/callback` |
| `FRONTEND_URL` | backend (a dónde regresa tras login/logout) | `http://localhost:3000` |

Dos gotchas que cuestan horas:

- **Red de Docker:** `MINERVA_ISSUER_URL` es server-a-server. Si tu backend corre
  en un contenedor, `localhost:9000` es el propio contenedor, no Minerva. Usa
  `http://host.docker.internal:9000` y agrega en tu `docker-compose.yml`:
  ```yaml
  extra_hosts:
    - "host.docker.internal:host-gateway"
  ```
- **Secreto JWT compartido:** Minerva firma con
  `effective_jwt_secret = MINERVA_JWT_SECRET or JWT_SECRET_KEY`. Si en el `.env`
  de Minerva está `MINERVA_JWT_SECRET`, **ese gana**. Tu `MINERVA_JWT_SECRET`
  debe ser **idéntico** a ese valor efectivo; si no, todo token será rechazado
  (401) y entrarás en un bucle de login.

---

## 5. Paso 4 — Implementar en tu backend

Tu backend expone tres rutas y un validador de JWT. (En Godín: `auth/route.py`,
`auth/service.py`, `core/dependencies/auth.py`.)

- **`GET /auth/login`** → arma
  `{MINERVA_LOGIN_URL}/authorize?client_id&redirect_uri&response_type=code&scope=openid profile email&state`
  y redirige el navegador. Guarda `state` en una cookie `httponly` para validarlo en el callback (anti-CSRF).
- **`GET /auth/callback?code&state`** → valida que `state` coincida con la cookie,
  hace `POST {MINERVA_ISSUER_URL}/auth/token` con
  `{ client_id, client_secret, code, redirect_uri }`, recibe `access_token` y
  redirige a `{FRONTEND_URL}/auth/callback#access_token=...`.
- **`GET /auth/logout`** → redirige a
  `{MINERVA_LOGIN_URL}/logout?redirect_uri={FRONTEND_URL}/` para **cerrar también
  la sesión en Minerva** (si no, Minerva re-autoriza en silencio y el usuario no
  puede salir).

### Validar el JWT

```python
from jose import jwt

# verify_aud=False: el token trae aud="<code>" (OAuth) o ninguno (dev-login).
payload = jwt.decode(token, MINERVA_JWT_SECRET, algorithms=["HS256"],
                     options={"verify_aud": False})
aud = payload.get("aud")
if aud is not None and aud != MINERVA_APPLICATION_CODE:
    raise Unauthorized("audience inválido")
```

> No valides con `audience=...` directo: `jose` lanza `Invalid audience` y rompe
> el login para **todos**. Valida `aud` manualmente.

### Consultar permisos

```
GET {MINERVA_ISSUER_URL}/api/v1/me/permissions?application=<code>
Authorization: Bearer <jwt>
→ { "application": "...", "roles": [...], "permissions": ["godin.oficios.view", ...] }
```

Valida **permisos**, nunca roles (`require_permission("godin.oficios.create")`).

---

## 6. Paso 5 — Frontend de tu sistema

- **Botón "Iniciar sesión"** → `window.location.href = "/api/auth/login"` (deja
  que el backend arme la URL de Minerva).
- **Página de callback** (p. ej. `/auth/callback`): lee el `access_token` del
  fragmento (`#access_token=...`), lo guarda y llama a `GET /auth/me`.
- **Sin acceso:** si `GET /auth/me` indica que el usuario no tiene permisos de tu
  app, muéstrale una página "No tienes acceso, contacta al administrador" en vez
  de dejarlo entrar (o de rebotarlo a Minerva).
- **Logout** → `window.location.href = "/api/auth/logout"` (single logout).

### Escenario A — tu sistema YA tenía login propio: qué quitar

1. La **página/formulario de login** (email + contraseña) y su CSS.
2. Cualquier `POST` directo del navegador a Minerva o a tu API para autenticar.
3. Manejo local de **contraseñas** y tablas/campos de password.
4. **Roles locales** y lógica `if user.role === 'admin'`: ahora el acceso se
   decide por **permisos** que vienen de Minerva.
5. Endpoints propios de `login`/`register`/`refresh` en tu backend.

Sustituye todo eso por: la landing con botón → `/api/auth/login`, la página de
callback, y la validación de JWT + permisos descrita arriba.

### Escenario B — tu sistema no tenía login

Solo implementas lo de §5 y §6 (botón, callback, sin-acceso, logout). No hay nada
que quitar.

---

## 7. Troubleshooting (errores que verás en orden)

| Síntoma | Causa probable | Arreglo |
|---|---|---|
| `No se pudo contactar a Minerva` al canjear el code | `MINERVA_ISSUER_URL` no alcanzable desde el contenedor | `host.docker.internal:9000` + `extra_hosts` |
| `redirect_uri no autorizada` | la URI no está registrada en la app | regístrala (panel 🔗 o API) idéntica a `MINERVA_REDIRECT_URI` |
| El login **se cicla** entre Minerva y tu sistema | JWT rechazado (401): secreto distinto, o `aud` mal validado | iguala `MINERVA_JWT_SECRET` al secreto efectivo de Minerva; valida `aud` con `verify_aud=False` |
| `Invalid audience` | validaste con `audience=` | usa `verify_aud=False` y compara `aud` a mano |
| Usuario entra pero todo da 403 | autenticado pero sin rol/permiso de tu app | asígnale un rol (panel o `POST /api/v1/access-assignments`); muéstrale "sin acceso" mientras tanto |
| No puede cerrar sesión (reentra solo) | no implementaste el single logout | `GET /auth/logout` → `{MINERVA_LOGIN_URL}/logout` |

---

## 8. Checklist de integración

- [ ] App registrada en Minerva (`client_id` + `client_secret` guardados).
- [ ] Redirect URI registrada == `MINERVA_REDIRECT_URI`.
- [ ] `manifest.minerva.yml` creado e importado (permisos + roles).
- [ ] Roles asignados a los usuarios que deben tener acceso.
- [ ] Variables de entorno configuradas (ojo `ISSUER_URL` vs `LOGIN_URL` y el secreto JWT).
- [ ] Backend con `/auth/login`, `/auth/callback`, `/auth/logout` y validación de JWT/permisos.
- [ ] Frontend sin login propio: botón → `/api/auth/login`, callback, sin-acceso, logout.
