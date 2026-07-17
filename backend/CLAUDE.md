# CLAUDE.md — Backend de Minerva

API de identidad/autorización en **FastAPI**. Lee primero el `CLAUDE.md` de la raíz para la visión
y las reglas globales. Este archivo cubre las reglas específicas del backend.

## Stack

- Python **3.12+** (`>=3.12,<3.14`)
- FastAPI · Uvicorn · **SQLModel** (ORM + schemas) · **Alembic** (migraciones)
- PostgreSQL vía **psycopg v3** · pydantic-settings · python-jose (**JWT RS256/JWKS**) · bcrypt · authlib
  · Redis async (rate limiting, blacklist de `jti`, caché JWKS)
- Build con **hatchling**. Lint/format con **Ruff**. Tests con **pytest** (`asyncio_mode=auto`).

## Entorno virtual (obligatorio): conda `minerva`

Regla del proyecto: trabajar **siempre** dentro del entorno **conda `minerva` con Python 3.12**.
Nunca instales paquetes globalmente ni sobre `base`.

```bash
conda create -n minerva python=3.12   # solo la primera vez
conda activate minerva
cd backend
pip install -e ".[dev]"               # instala el backend + dependencias de desarrollo
```

Para correr sin Docker necesitas un PostgreSQL accesible y `DATABASE_URL` configurado.
La opción recomendada para desarrollo integral sigue siendo `docker compose up` desde la raíz.

## Arquitectura modular en capas

Cada dominio vive en `app/modules/<nombre>/` y respeta **estrictamente** esta separación de
responsabilidades. Usa `app/modules/users/` como referencia canónica.

```
app/modules/<nombre>/
├── models.py       # Tablas SQLModel (estado en BD). Sin lógica de negocio.
├── schemas.py      # DTOs Pydantic: <X>Create / <X>Update / <X>Read. Contrato HTTP.
├── repository.py   # Acceso a datos. Clase <X>Repository(session) con get_by_id/list_all/create/update.
├── service.py      # Lógica de negocio y validaciones. Orquesta el repository. Lanza AppException.
└── router.py       # APIRouter(prefix, tags). Endpoints finos: parsean, llaman al service, responden.
```

**Flujo de una request:** `router → service → repository → models/schemas`.

Reglas:
- **Routers finos:** sin lógica de negocio ni queries; solo `Depends`, validación de entrada y
  delegación al service. Inyecta el service con un helper `get_<x>_service(session=Depends(get_db))`.
- **La lógica vive en el service.** El service no debe importar `Request`/objetos HTTP.
- **Acceso a datos SOLO en el repository.** Ningún `select(...)` fuera de `repository.py`.
- **Registra el router nuevo** en `app/main.py` con `app.include_router(<x>_router)`.
- Si el módulo añade tablas, créalas como modelos SQLModel e impórtalas donde corresponda
  (`app/core/models.py` / seeding), y genera una migración Alembic.

### Utilidades compartidas (reúsalas, no las dupliques)

- Paginación: `app/shared/pagination.py` → `PaginatedResponse[T].create(items, total)`.
- Dependencia de sesión DB: `app.core.dependencies.db.get_db`.
- Usuario autenticado: `app.core.dependencies.auth.get_current_user` (y `get_optional_user`).
- Errores: subclases de `AppException` en `app/core/exceptions.py`
  (`NotFoundError`, `UnauthorizedError`, `ForbiddenError`, `BadRequestError`, `ConflictError`),
  con mensajes en español. No lances `HTTPException` cruda desde el service.
- Seguridad/JWT y hashing: `app/core/security.py`.

## Convenciones

- **PK**: UUID como `str` (`str(uuid.uuid4())`).
- **Timestamps**: siempre UTC → `datetime.now(timezone.utc)`.
- Nombres de identificadores en inglés; mensajes de error de cara al usuario en español.
- Permisos siguen `{application_code}.{resource}.{action}` (ver CLAUDE.md raíz).

## Calidad (corre esto antes de terminar)

```bash
ruff check .          # lint (E, F, I, W); line-length 120
ruff format .         # formateo
pytest tests/ -v      # tests (SQLite in-memory, ver tests/conftest.py)
mypy app              # tipado (config permisiva; opcional pero recomendado)
```

Los tests usan fixtures en `tests/conftest.py` (DB en memoria, `client`, `admin_token`).
Al crear un módulo, agrega `tests/test_<nombre>.py` cubriendo el camino feliz y los errores clave.

## Migraciones (Alembic)

```bash
alembic revision --autogenerate -m "descripcion breve"   # genera migración desde los modelos
alembic upgrade head                                       # aplica
```

Revisa siempre la migración autogenerada antes de aceptarla. Las migraciones viven en
`alembic/versions/` y se versionan en git.
