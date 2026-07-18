# CLAUDE.md — Minerva (raíz)

Guía para trabajar en este repositorio con Claude Code. Instrucciones en español, términos
técnicos en inglés (bilingüe, igual que el código del proyecto).

## Qué es Minerva

Minerva es el **sistema institucional de identidad, autenticación y autorización del IIEG**
(Instituto de Información Estadística y Geográfica de Jalisco). Funciona como un "Iniciar sesión
con Google" interno: las plataformas del instituto redirigen el login hacia Minerva, que autentica
al usuario, valida sus permisos y devuelve un **JWT**.

**Principio rector (no negociable):**

> Los sistemas definen *qué* acciones existen. Minerva define *quién* puede hacerlas.
> Los sistemas validan **permisos**, nunca roles.

- Un sistema declara permisos como `godin.oficios.create` en su `manifest.minerva.yml`.
- Minerva administra qué usuarios tienen esos permisos (vía roles).
- El sistema consumidor valida con `require_permission("godin.oficios.create")`,
  **NUNCA** con `if user.role == "Admin"`.
- Convención de permisos: `{application_code}.{resource}.{action}`
  (acciones: `view, create, update, delete, assign, approve, authorize, export, import, manage`).

Fuentes de verdad del producto: `docs/arquitectura.md` (visión/arquitectura, con
diagramas), `docs/glosario.md` (terminología OIDC/OAuth), `docs/despliegue.md` (Dev/Prod
+ mantenimiento) y `docs/integracion.md` (integración de sistemas consumidores).
Los markdown de pasos futuros/roadmap son internos y **no** se trackean en el repo.

## Mapa del monorepo

| Carpeta | Qué es | Detalle |
|---|---|---|
| `backend/` | API FastAPI + SQLModel + Alembic + PostgreSQL | Ver `backend/CLAUDE.md` |
| `frontend/` | Panel admin React 19 + Ant Design 6 + Vite | Ver `frontend/CLAUDE.md` |
| `sdk/` | `minerva_sdk`: helpers para que sistemas consumidores validen permisos | `require_permission`, `get_current_user` |
| `manifests/` | YAML que declaran apps/permisos/roles | Convención `{app}.{recurso}.{accion}` |
| `examples/` | `godin-consumer`: ejemplo de integración con el SDK | Referencia de cómo se consume Minerva |
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

Minerva firma **todo con RS256/JWKS** (no HS256). Autenticación por **Bearer en header**,
stateless: **no hay tabla `sessions` ni cookies de sesión**.

- **Emisión/validación de tokens:** `backend/app/core/security.py` (create/decode RS256, `jti`,
  `hash_token`) y `backend/app/core/dependencies/auth.py` (`get_current_user`/`get_optional_user`:
  valida contra JWKS, rechaza `jti` revocado y rechaza tokens con `iat` anterior al corte de
  invalidación del usuario).
- **Sesión del panel admin:** token RS256 (TTL 8h) emitido en login/register vía
  `OIDCService.issue_session_token`. En el frontend vive en `localStorage`.
- **OIDC para consumidores:** módulo `backend/app/modules/auth/` (`/authorize`, `/token`,
  `/revoke`, PKCE, refresh con rotación) + `backend/app/modules/oidc/` (discovery, JWKS,
  `/userinfo`, claves de firma). Guía consumidor: `docs/integracion.md` y skill
  `.claude/skills/minerva-integration/`.
- **Logout:** `POST /auth/logout` blacklistea el `jti` en Redis
  (`backend/app/core/token_blacklist.py`) — invalida el token de verdad. **Pero el panel lo usa
  solo en "Cerrar todas las sesiones"** (`logoutAll`). El "Cerrar sesión" normal es un **logout
  suave client-side** (`session.deactivate()`): sale de la cuenta sin invalidar el token, que sigue
  válido en el store para volver a entrar sin re-teclear (estilo Google). Ver la subsección del
  selector.
- **Invalidación por usuario (cambio de credenciales/status):** cambiar contraseña, correo o poner
  status ≠ `active` mata las sesiones vigentes. `invalidate_user_tokens` marca un corte por `iat` en
  Redis (`minerva:uinval:{sub}`, chequeado en `get_current_user`) y `UserService.revoke_refresh_tokens`
  revoca los refresh tokens OIDC (blacklisteando sus access `jti`). Disparado en el router de usuarios
  (`update_user`/`update_user_status`). Login/authorize/refresh ya rechazan usuarios no-`active`.
- **Red en producción (nginx consolidado):** un solo punto público (nginx del servicio `frontend`)
  sirve la SPA y proxea al backend `/.well-known`, `/auth`, `/userinfo`, `/api` (strip) y `/api/v1`
  (preserva). El backend **no publica puerto** en el deploy; el issuer va sin `:9000`. `FORWARDED_ALLOW_IPS`
  hace que el rate limit cuente por IP real. Detalle: `frontend/nginx.conf` y `docs/despliegue.md` §2.2.

### Selector de cuentas / multi-sesión (v0.3.0)

Patrón "cambiar de cuenta" de Google/GitHub. El estado multi-sesión vive en el **cliente** (no
hay tabla de sesiones): la SPA guarda varias cuentas iniciadas y muestra un selector.

- **Store (fuente de verdad):** `frontend/src/api/session.js` — arreglo `minerva_sessions` +
  `minerva_active_sub` en localStorage; mantiene el **espejo legacy** `access_token`/`user`/
  `is_admin` de la cuenta activa (por eso `client.js` y `ProtectedRoute` **no cambiaron**).
  Estados de una cuenta: `isExpired` (por `exp`) → activa/vencida; `deactivate()` = logout suave
  (limpia el espejo, conserva `exp`); `expireActive()` = degradar a vencida tras un 401. Self-check
  ejecutable: `frontend/src/api/session.selfcheck.mjs` (`node`).
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
