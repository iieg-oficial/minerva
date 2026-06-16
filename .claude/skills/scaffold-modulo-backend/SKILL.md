---
name: scaffold-modulo-backend
description: Genera un módulo nuevo del backend de Minerva (backend/app/modules/<nombre>/) siguiendo el patrón en capas models/schemas/repository/service/router del módulo users. Úsalo cuando se pida crear un nuevo dominio/recurso/endpoint en el backend FastAPI.
---

# Scaffold de módulo backend

Crea un módulo de dominio nuevo respetando la arquitectura en capas de Minerva. La referencia
canónica es `backend/app/modules/users/`. Lee `backend/CLAUDE.md` antes de empezar.

## Paso 0 — Datos

Confirma con el usuario (o infiere del contexto):
- `nombre` del módulo en plural y `snake_case` (ej. `oficios`).
- Nombre de la entidad en `PascalCase` singular (ej. `Oficio`).
- Campos del modelo (nombre, tipo, opcionalidad).

## Paso 1 — Inspecciona el patrón

Lee los 5 archivos de `backend/app/modules/users/` (`models.py`, `schemas.py`, `repository.py`,
`service.py`, `router.py`) para copiar estilo, imports y firmas exactas. **No inventes utilidades**:
reúsa las existentes.

## Paso 2 — Genera `backend/app/modules/<nombre>/`

- **`models.py`** — tabla SQLModel. PK `id: str` (default `str(uuid.uuid4())`), timestamps UTC
  (`created_at`, `updated_at` con `datetime.now(timezone.utc)`).
- **`schemas.py`** — DTOs Pydantic `<Entidad>Create`, `<Entidad>Update`, `<Entidad>Read`. Sin lógica.
- **`repository.py`** — clase `<Entidad>Repository(session)` con `get_by_id`, `list_all(offset, limit)`
  (devuelve `tuple[list, int]`), `create`, `update`. **Único lugar con `select(...)`.**
- **`service.py`** — clase `<Entidad>Service(session)` que instancia el repository, valida y lanza
  `AppException` (`NotFoundError`, etc. de `app/core/exceptions.py`). Sin imports HTTP.
- **`router.py`** — `APIRouter(prefix="/<nombre>", tags=["<Nombre>"])`, helper
  `get_<x>_service(session=Depends(get_db))`, endpoints finos protegidos con
  `Depends(get_current_user)`. Usa `PaginatedResponse[<Entidad>Read]` para el listado.

## Paso 3 — Integra

- Registra el router en `backend/app/main.py`: importa `<nombre>_router` y añade
  `app.include_router(<nombre>_router)` junto a los demás.
- Asegura que el modelo se descubra (sigue cómo se importan los modelos existentes en
  `app/core/models.py` / seeding).
- Genera la migración: `alembic revision --autogenerate -m "add <nombre>"` y revísala.

## Paso 4 — Tests

Crea `backend/tests/test_<nombre>.py` usando las fixtures de `tests/conftest.py`
(`client`, `admin_token`): cubre crear, listar, obtener y un caso de error (404).

## Paso 5 — Verifica

Con el entorno conda `minerva` activado (`conda activate minerva`):
```bash
ruff check . && ruff format . && pytest tests/test_<nombre>.py -v
```

Reporta los archivos creados/modificados y recuerda al usuario revisar la migración antes de aplicarla.
