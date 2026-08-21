# Guía de contribución

Gracias por querer aportar a Minerva. Esta guía cubre el flujo completo: preparar el entorno,
abrir un issue, trabajarlo en una rama, validar y mandar el pull request.

Antes de escribir código, lee [`CLAUDE.md`](CLAUDE.md) (reglas de arquitectura y convenciones del
repositorio) y [`docs/arquitectura.md`](docs/arquitectura.md). El principio rector del proyecto no
es negociable:

> Los sistemas definen *qué* acciones existen. Minerva define *quién* puede hacerlas.
> Los sistemas consumidores validan **permisos**, nunca roles.

## 1. Preparar el entorno

### Todo el stack con Docker (recomendado para desarrollo integral)

```bash
cp .env.example .env
docker compose up --build
```

Panel en `http://localhost:3100`, API en `http://localhost:9000` (OpenAPI en `/docs`). Las
migraciones de Alembic se aplican solas al arrancar el contenedor del backend.

### Backend suelto

Regla del proyecto: **siempre** el entorno conda `minerva` con Python 3.12. Nunca instales sobre
`base` ni globalmente.

```bash
conda create -n minerva python=3.12   # solo la primera vez
conda activate minerva
cd backend
pip install -e ".[dev]" -c constraints.txt   # misma resolución que la imagen Docker y el CI
```

Necesitas un PostgreSQL accesible vía `DATABASE_URL`. Los tests **no** lo requieren: corren con
SQLite en memoria y `fakeredis` (salvo los `tests/test_*_pg.py`, ver §4).

### Frontend

```bash
cd frontend
npm ci        # `ci`, no `install`: respeta package-lock.json igual que el build de Docker
npm run dev
```

### SDK

```bash
conda activate minerva
cd sdk
pip install -e ".[dev]"
```

## 2. Del issue a la rama

**Un issue = una rama = un pull request.** No mezcles invariantes distintos en el mismo PR aunque
toquen los mismos archivos: si el PR necesita un párrafo para justificar por qué hace dos cosas,
son dos PRs.

1. **Abre un issue** con la plantilla que corresponda ([`.github/ISSUE_TEMPLATE/`](.github/ISSUE_TEMPLATE)):
   `Bug`, `Feature`, `Refactor`, `Documentacion` o `Release`. Descríbelo con alcance exacto y
   criterios de aceptación; las plantillas ya te piden ambos.
2. **Crea la rama desde `develop`**, nunca desde `main` y nunca trabajes directo sobre `develop`:

   ```bash
   git checkout develop && git pull
   git checkout -b fix/nombre-corto-del-issue
   ```

   Nombre `tipo/descripcion-en-kebab-case`, con el mismo `tipo` que usarás en los commits
   (`feat`, `fix`, `docs`, `refactor`, `chore`, `test`).

### Modelo de ramas

| Rama | Qué es |
|---|---|
| `main` | Rama estable y default. Solo recibe releases desde `develop`, con su tag `vX.Y.Z`. |
| `develop` | Integración. Es la base y el destino de todo PR de trabajo. |
| `tipo/...` | Tu rama de trabajo, una por issue. |

## 3. Commits

Formato **Conventional Commits en español**, una sola línea:

```
tipo(alcance): descripción breve en minúsculas
```

- Ejemplo: `feat(users): se agrega el modulo de gestion de usuarios con su crud, schemas y routes`.
- **Sin cuerpo.** La línea completa describe el cambio entero. Si sientes que necesita un párrafo
  para justificarse, la señal es que hay que partirlo en commits más atómicos, no escribir más.
- **Commits atómicos:** un cambio lógico por commit, para que cada uno sea revertible y
  describible en una línea.
- El mensaje debe entenderse **solo con git**: no cites documentos, auditorías ni identificadores
  que no estén versionados en el repositorio.

## 4. Validar antes de abrir el PR

Corre lo del área que tocaste. Son **los mismos comandos que ejecuta el CI**
([`.github/workflows/ci.yml`](.github/workflows/ci.yml)): si pasan aquí, pasan allá.

```bash
# Backend (entorno conda `minerva`, desde backend/)
ruff check app alembic tests
ruff format --check app alembic tests
mypy app                      # gate de tipos: falla ante errores nuevos
pytest tests/ -v              # SQLite + fakeredis, sin servicios externos

# SDK (desde sdk/)
ruff check minerva_sdk tests
ruff format --check minerva_sdk tests
pytest tests/ -v

# Frontend (desde frontend/)
npm run lint
npm run build
npm test

# Compose (desde la raíz)
cp .env.example .env          # compose exige el .env, que está en .gitignore
docker compose config
docker compose build
```

**Tests que exigen PostgreSQL real** (constraints, triggers, concurrencia). El CI los corre en un
job aparte; en local son opcionales:

```bash
export MINERVA_TEST_POSTGRES_URL="postgresql+psycopg://usuario:pass@localhost:5432/minerva_test"
pytest tests/test_*_pg.py -v
```

Otras cosas que el CI comprueba y conviene no romper:

- **`pip-audit`** contra `backend/constraints.txt`. Si agregas o subes una dependencia, actualiza
  `constraints.txt` siguiendo el procedimiento de [`backend/CLAUDE.md`](backend/CLAUDE.md); no lo
  edites a ojo.
- **Alineación de versión**: la versión vive en `backend/pyproject.toml` y `frontend/package.json`
  la repite. `tests/test_version_alignment.py` falla si se desincronizan. El SDK tiene su propio
  guardián, `sdk/tests/test_version.py` (ver §6).
- **Smoke E2E de autenticación**: `frontend/src/test/auth-smoke.test.jsx` monta la SPA completa
  contra una Minerva simulada en el adaptador de axios (misma herramienta que el resto de tests,
  sin navegador ni backend). Cubre la jornada crítica: login con cookie y CSRF, `/authorize`
  transportando `state` y `max_age`, cambio de cuenta y logout. Si tocas `api/client.js`,
  `api/session.js` o el flujo de `features/auth`, córrelo.
- **Matriz del SDK**: el CI corre el SDK en dos entornos, Python 3.10 con `fastapi` y `httpx` en su
  piso declarado y Python 3.13 con resolución libre. En local basta con uno; si tocas los `>=` de
  `sdk/pyproject.toml`, prueba el piso.
- **Migraciones**: si cambias modelos, genera la migración (`alembic revision --autogenerate -m
  "descripcion breve"`), **revísala a mano** y versiónala.
- **Secretos**: nunca edites ni subas `.env`. Si agregas una variable, documéntala en
  `.env.example` sin valor real.

## 5. Abrir el pull request

- **Base `develop`.** Título con el mismo formato del commit.
- Llena [`.github/pull_request_template.md`](.github/pull_request_template.md) — incluida la
  sección de validación, marcando lo que de verdad corriste.
- **Enlaza el issue con `Closes #N`** en el cuerpo.
- Si el trabajo depende de otro PR sin mergear, apílalo declarando ese PR como base en vez de
  `develop`, y dilo en la descripción.

### Revisión

Quien revisa comprueba el **diff completo contra su merge-base**, no solo los commits nuevos, y
que el PR resuelva **solo** el invariante de su issue, sin abstracciones especulativas de más.

Cuando apliques correcciones de review, **hay que revisar de nuevo el diff completo**, no
únicamente los commits de arreglo: un cambio tardío puede romper algo que ya se había revisado.
Marca los comentarios como resueltos solo cuando el cambio esté empujado.

Si un PR toca la topología de red, los puertos o el issuer, actualiza a la vez
`docs/arquitectura.md`, `docs/despliegue.md`, `docs/integracion.md` y `docs/uso-imagen-docker.md`:
es fácil dejar uno desactualizado.

## 6. Release

Los releases van de `develop` a `main`, con su tag `vX.Y.Z` y su entrada en
[`CHANGELOG.md`](CHANGELOG.md). Usa la plantilla de issue `Release` como checklist.
`minerva_sdk` versiona por su cuenta ([`sdk/pyproject.toml`](sdk/pyproject.toml)): su número no
sigue al del servidor. Si tu PR toca `sdk/minerva_sdk/`, sube su versión en el mismo PR —
`sdk/pyproject.toml`, `minerva_sdk.__version__` y una entrada en
[`sdk/CHANGELOG.md`](sdk/CHANGELOG.md)—; `sdk/tests/test_version.py` falla si los tres no
coinciden. Un cambio incompatible se marca `BREAKING` y, mientras el SDK esté en `0.x`, sube el
MINOR (ver «Política de versionado» en [`sdk/README.md`](sdk/README.md)).

## 7. Licencia de tus contribuciones

Al contribuir aceptas que tu aportación se distribuya bajo la licencia del componente que tocas:
**AGPL-3.0-only** para el servidor (ver [`LICENSE`](LICENSE)) y **Apache-2.0** para el SDK (ver
[`sdk/LICENSE`](sdk/LICENSE)).

Para reportar una **vulnerabilidad**, no abras un issue: sigue [`SECURITY.md`](SECURITY.md).
