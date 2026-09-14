# CLAUDE.md — Minerva (raíz)

Guía para trabajar en este repositorio con Claude Code. Instrucciones en español, términos
técnicos en inglés (bilingüe, igual que el código del proyecto).

## Qué es Minerva

Minerva es el **sistema institucional de identidad, autenticación y autorización del IIEG**
(Instituto de Información Estadística y Geográfica de Jalisco). Funciona como un inicio de sesión
único (SSO) institucional interno: las plataformas del instituto redirigen el login hacia Minerva,
que autentica al usuario, valida sus permisos y devuelve un **JWT**.

**Principio rector (no negociable):**

> Los sistemas definen *qué* acciones existen. Minerva define *quién* puede hacerlas.
> Los sistemas validan **permisos**, nunca roles.

- Un sistema declara permisos como `portal_demo.documents.create` en su `manifest.minerva.yml`.
- Minerva administra qué usuarios tienen esos permisos (vía roles).
- El sistema consumidor valida con `require_permission("portal_demo.documents.create")`,
  **NUNCA** con `if user.role == "Admin"`.
- Convención de permisos: `{application_code}.{resource}.{action}`
  (acciones: `view, create, update, delete, assign, approve, authorize, export, import, manage`).

Fuentes de verdad del producto: `docs/arquitectura.md` (visión/arquitectura, con
diagramas), `docs/glosario.md` (terminología OIDC/OAuth), `docs/despliegue.md` (Dev/Prod
+ mantenimiento), `docs/integracion.md` (integración de sistemas consumidores) y
`docs/uso-imagen-docker.md` (despliegue por imágenes de ghcr, sin clonar el repo). Al tocar
topología de red/puertos/issuer, actualiza los cuatro — es fácil dejar uno desactualizado.
Los markdown de pasos futuros/roadmap son internos y **no** se trackean en el repo.

## Mapa del monorepo

| Carpeta | Qué es | Detalle |
|---|---|---|
| `backend/` | API FastAPI + SQLModel + Alembic + PostgreSQL | Ver `backend/CLAUDE.md` |
| `frontend/` | Panel admin React 19 + Ant Design 6 + Vite | Ver `frontend/CLAUDE.md` |
| `sdk/` | `minerva_sdk`: helpers para que sistemas consumidores validen permisos | `require_permission`, `get_current_user` |
| `manifests/` | YAML que declaran apps/permisos/roles | Convención `{app}.{recurso}.{accion}` |
| `examples/` | `minerva-consumer`: ejemplo de integración con el SDK | Referencia de cómo se consume Minerva |
| `docs/` | Arquitectura general, docs de módulos y guías de integración | Fuentes de verdad |

## Reglas globales de trabajo

1. **Entornos virtuales SIEMPRE para Python.** La regla del proyecto es usar el entorno **conda
   `minerva` con Python 3.12**. Nunca instalar paquetes de forma global ni sobre `base`.
   Para desarrollo integral, preferir levantar el stack con **Docker Compose**.

   ```bash
   conda create -n minerva python=3.12   # solo la primera vez
   conda activate minerva
   ```
2. **Modularidad y separación de responsabilidades.** Un archivo = una responsabilidad.
   Respeta las capas existentes (ver los CLAUDE.md scoped). No mezcles acceso a datos,
   lógica de negocio y HTTP en el mismo archivo.
3. **Código legible.** Nombres de identificadores en inglés (`snake_case` en Python,
   `camelCase` en JS); comentarios, mensajes de error y textos de UI en **español**.
   Prefiere funciones cortas y nombres descriptivos sobre comentarios que expliquen código confuso.
4. **Git.** No hagas `commit` ni `push` salvo que se pida explícitamente. No trabajes directo
   sobre `develop`: crea una rama. Los mensajes de commit en español.
5. **Secretos.** Nunca edites ni subas `.env` (está en `.gitignore`). Si agregas una variable
   nueva, actualiza `.env.example` (sin valores reales).
6. **Antes de terminar una tarea**, corre el linter/formateador y los tests del área tocada
   (ver CLAUDE.md de `backend/` y `frontend/`).

## Cómo levantar el stack

```bash
cp .env.example .env        # ajusta valores si es necesario
docker compose up --build
```

- Backend (FastAPI): http://localhost:9000  · docs OpenAPI en `/docs`
- Frontend (panel admin): http://localhost:3000
- PostgreSQL: puerto 5432

Las migraciones de Alembic se aplican automáticamente al arrancar el contenedor del backend
(`backend/scripts/backend-entrypoint.sh`).

### ⚠️ Gotcha conocido: puertos 8000 vs 9000

El backend se sirve en **9000** (docker-compose y Dockerfile), pero `frontend/vite.config.js`
y partes del `.env` apuntan a **8000**. Si tocas la configuración de red/proxy, verifica que el
puerto sea consistente extremo a extremo antes de asumir un bug. No "corrijas" uno sin revisar el otro.

## Sesiones, autenticación y selector de cuentas

Minerva firma **todo con RS256/JWKS** (no HS256). Dos modelos de sesión, deliberadamente distintos:

- **Consumidores OAuth/OIDC → stateless, Bearer en header.** No hay estado de sesión en servidor:
  el token se valida por firma/`jti`/corte. Sin cambios.
- **Panel admin → stateful (patrón BFF), cookie opaca HttpOnly.** El navegador NO guarda el JWT:
  solo una cookie opaca `__Host-minerva_sid` (dev: `minerva_sid`). El estado multi-cuenta vive en
  Redis (`backend/app/core/panel_session.py`). Es la **única** excepción al principio stateless.

- **Emisión/validación de tokens:** `backend/app/core/security.py` (create/decode RS256, `jti`,
  `hash_token`) y `backend/app/core/dependencies/auth.py`: `_resolve_token` valida contra JWKS,
  rechaza `jti` revocado y tokens con `iat` anterior al corte de invalidación. Dependencias por
  clase: `get_current_panel_user`/`get_optional_panel_user` (cookie → contenedor Redis → JWT
  `typ=session` de la cuenta activa → `_resolve_token`); `get_current_access_user` y
  `get_current_devkit_user` (Bearer, consumidores).
- **Contenedor de sesión del panel:** `backend/app/core/panel_session.py`. Clave Redis
  `minerva:psid:{sha256(sid)}`; guarda por cuenta el JWT `typ=session`, `exp`, `jti` y el descriptor
  no sensible, más la cuenta activa y el token CSRF. TTL = TTL de sesión del panel. El `sid` (256
  bits) se genera en el backend, se guarda hasheado y se **rota** en cada login/registro/refresh
  (fijación de sesión). La pérdida/limpieza de Redis invalida las sesiones del panel.
- **CSRF + Origin:** `backend/app/core/csrf.py` — middleware que exige `X-CSRF-Token` (synchronizer,
  comparación constante) y `Origin` válido en las mutaciones que traen la cookie de panel. Exentos:
  `/auth/login`, `/auth/register` (crean sesión), los endpoints OAuth de consumidor y, por ruta
  exacta, `/auth/credential` y `/auth/credential/inspect` (se autentican con el token del enlace).
- **OIDC para consumidores:** módulo `backend/app/modules/auth/` (`/authorize`, `/token`,
  `/revoke`, PKCE, refresh con rotación) + `backend/app/modules/oidc/` (discovery, JWKS,
  `/userinfo`, claves de firma). Guía consumidor: `docs/integracion.md` y skill
  `.claude/skills/minerva-integration/`.
- **Logout del panel:** `POST /auth/logout` es **suave** (cierra la cuenta activa del contenedor sin
  revocar; las demás quedan para reingresar). La revocación real (blacklist del `jti` en Redis,
  `backend/app/core/token_blacklist.py`) está en `DELETE /auth/session/accounts/{sub}` (quitar cuenta)
  y `POST /auth/logout-all` (cerrar todo + destruir el contenedor + borrar cookie).
- **Invalidación por usuario (cambio de credenciales/status):** cambiar contraseña, correo o poner
  status ≠ `active` mata las sesiones vigentes. `invalidate_user_tokens` marca un corte por `iat` en
  Redis (`minerva:uinval:{sub}`, chequeado en `_resolve_token`) y `UserService.revoke_refresh_tokens`
  revoca los refresh tokens OIDC (blacklisteando sus access `jti`). Vive en
  `backend/app/modules/users/invalidation.py` (`apply_with_invalidation`, fail-closed Redis → PG) y lo
  disparan el router de usuarios (`update_user`/`update_user_status`), `POST /auth/credential` y
  `POST /auth/password`. Login/authorize/refresh ya rechazan usuarios no-`active`.
- **Ciclo de vida de la credencial:** módulo `backend/app/modules/credentials/` (enlaces de un solo
  uso: invitación, restablecimiento, cambio obligatorio; solo el hash en `credential_tokens`). Alta sin
  contraseña → usuario `pending`; `password_change_required` hace que el login responda `403
  password_change_required` sin abrir sesión. SPA: `/activar` (token en el fragmento) y
  `/cuenta/contrasena` (cambio propio, `ProtectedRoute requireAdmin={false}`). Detalle:
  `docs/arquitectura.md` § Ciclo de vida de la credencial.
- **Red en producción (nginx consolidado):** un solo punto público (nginx del servicio `frontend`)
  sirve la SPA y proxea al backend `/.well-known`, `/auth`, `/userinfo`, `/api` (strip) y `/api/v1`
  (preserva). El backend **no publica puerto** en el deploy; el issuer va sin `:9000`. `FORWARDED_ALLOW_IPS`
  hace que el rate limit cuente por IP real. `nginx.conf` emite además cabeceras defensivas (CSP con
  `frame-ancestors 'none'` y `img-src ... https:` para logos de branding, `nosniff`, `Referrer-Policy`).
  **HSTS no se emite aquí** (nginx sirve HTTP): va en el terminador TLS externo, sin `preload`. Detalle:
  `frontend/nginx.conf` y `docs/despliegue.md` §2.2.

### Selector de cuentas / multi-sesión (v0.3.0)

Patrón "cambiar de cuenta" multi-sesión. La **fuente de verdad del multi-cuenta es el backend**
(contenedor en Redis); la SPA solo cachea descriptores no sensibles para pintar el selector.

- **Fuente de verdad:** el contenedor de sesión en Redis (`backend/app/core/panel_session.py`).
  `GET /auth/session` devuelve los descriptores (`sub`, email, nombre, `is_admin`, `exp`, `expired`),
  la cuenta activa y el CSRF — **nunca** el JWT. `POST /auth/session/active` cambia la activa;
  `DELETE /auth/session/accounts/{sub}` quita+revoca; `POST /auth/logout` es logout suave;
  `POST /auth/logout-all` cierra todo.
- **Cliente:** `frontend/src/api/session.js` es un cliente + caché en memoria de ese estado (sin
  tokens en `localStorage`). `frontend/src/features/auth/SessionContext.jsx` (`SessionProvider`) hace
  un fetch al montar y expone `{loading, active, accounts, isAdmin, refresh}`; lo consumen
  `ProtectedRoute`, `AccountSelector`, `AdminLayout`, `LoginPage` y `AuthorizePage`. `client.js`
  adjunta `X-CSRF-Token` en mutaciones y va con `withCredentials`.
- **Shell visual compartido:** `frontend/src/features/auth/components/AuthShell.jsx` — fondo
  morado + card de dos columnas (contenido izquierdo vía `children`, branding a la derecha) +
  footer Jalisco. Lo usan tanto `LoginPage.jsx` (formulario) como el selector, para que se vean
  idénticos. Referencias de diseño en `login-ui/` (no trackeadas).
- **UI del selector:** `frontend/src/features/auth/components/AccountSelector.jsx` — 4 estados en
  una columna (sin card propia): cuenta activa + Continuar (login_again), dropdown para cambiar de
  cuenta (login_select_account, con scroll/alto máximo) y gestor para quitar cuentas del dispositivo
  (login_account_manager). Integrado en `LoginPage.jsx` y en `AuthorizePage.jsx`
  (`prompt=select_account`). Dropdown de cuentas también en `AdminLayout.jsx`.
- **`/login` ya no auto-salta al panel:** con cuentas guardadas muestra el selector (login_again);
  sin cuentas, el formulario (login_first). `?add=1` fuerza el formulario (agregar/reingresar) y
  `?email=` prellena.
- **Disparo consumidor (estándar OIDC estricto):** en `/authorize` el selector solo aparece con
  `prompt=select_account` (o `prompt=login` para credenciales frescas). Sin `prompt`, SSO silencioso.
- **Backend:** `select_account` cae al camino normal de `/authorize` (la selección la resuelve la
  SPA); ver `backend/app/modules/auth/service.py` (`authorize`, `_requires_reauth`). Tests:
  `backend/tests/test_prompt_max_age.py`, `backend/tests/test_auth.py` (revocación de logout).

## Agentes y skills disponibles (`.claude/`)

- **Agente `revisor-arquitectura`** — revisa el diff actual contra las reglas de capas, modularidad
  y convenciones del proyecto. Solo lectura, no edita.
- **Agente `validador-manifiestos`** — valida un `manifest.minerva.yml` antes de importarlo.
- **Skill `scaffold-modulo-backend`** — genera un módulo backend nuevo siguiendo el patrón en capas.
- **Skill `scaffold-feature-frontend`** — genera una feature React (api + page) feature-sliced.
