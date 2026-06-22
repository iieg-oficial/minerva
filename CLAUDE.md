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

Fuentes de verdad del producto: `docs/minerva-dev-kit-context.md` (visión/arquitectura),
`docs/minerva-dev-kit.md` (guía de uso) y `docs/oidc-integracion.md` (integración OIDC).
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

## Agentes y skills disponibles (`.claude/`)

- **Agente `revisor-arquitectura`** — revisa el diff actual contra las reglas de capas, modularidad
  y convenciones del proyecto. Solo lectura, no edita.
- **Agente `validador-manifiestos`** — valida un `manifest.minerva.yml` antes de importarlo.
- **Skill `scaffold-modulo-backend`** — genera un módulo backend nuevo siguiendo el patrón en capas.
- **Skill `scaffold-feature-frontend`** — genera una feature React (api + page) feature-sliced.
