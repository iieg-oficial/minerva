# Minerva Dev Kit — Guía de uso

Esta guía explica cómo levantar y probar **Minerva Dev Kit**, el empaquetado de
desarrollo de Minerva. La visión, arquitectura y reglas de diseño están en
[`minerva-dev-kit-context.md`](./minerva-dev-kit-context.md) (fuente de verdad).

> Minerva Dev Kit reutiliza el backend, el panel administrativo y la base de
> datos ya existentes, y añade encima el **contrato de desarrollo** (`/api/v1`):
> login dev, JWT, manifiestos, `me`, `me/permissions`, asignaciones de acceso y
> un SDK mínimo para FastAPI. **No reemplaza** el panel ni las rutas previas.

---

## 1. ¿Qué es?

Una instancia local de Minerva, compatible con la futura Minerva Central, que
permite a un equipo:

- levantar Minerva con Docker,
- registrar su plataforma mediante un manifiesto YAML,
- administrar usuarios, roles, permisos y asignaciones desde el panel o la API,
- emitir tokens JWT de desarrollo,
- proteger los endpoints de su sistema validando **permisos** (no roles),
- migrar después a Minerva Central cambiando sólo variables de entorno.

---

## 2. Cómo levantarlo

```bash
cp .env.example .env
docker compose up --build
```

Servicios y puertos:

| Servicio | URL | Notas |
|---|---|---|
| Minerva API (Dev Kit) | http://localhost:9000 | Alias de red interno: `minerva` |
| Documentación OpenAPI | http://localhost:9000/docs | Swagger UI |
| Panel administrativo | http://localhost:3000 | Frontend existente (sin cambios) |
| PostgreSQL | localhost:5432 | Alias de red interno: `minerva-db` |

Al arrancar:

1. Se aplican las migraciones (`alembic upgrade head`).
2. Se crea el usuario administrador (`ADMIN_EMAIL` / `ADMIN_PASSWORD`).
3. Si `MINERVA_AUTO_IMPORT_MANIFESTS=true`, se importan los manifiestos de
   `MINERVA_MANIFESTS_PATH` (`./manifests` montado en `/app/manifests`). El
   repo incluye `manifests/manifest.minerva.yml` (aplicación `godin`).

Comprobación de salud:

```bash
curl http://localhost:9000/health      # {"status":"ok"}
```

---

## 3. Entrar al panel administrativo

Abre http://localhost:3000 e inicia sesión con el administrador por defecto
(`admin@iieg.gob.mx` / `changeme123`, configurables en `.env`). El panel sigue
usando la API existente; el Dev Kit sólo añade el contrato `/api/v1`.

---

## 4. Login de desarrollo (JWT)

```bash
curl -s -X POST http://localhost:9000/api/v1/auth/dev-login \
  -H 'Content-Type: application/json' \
  -d '{"email":"admin@local.dev"}'
```

Respuesta:

```json
{ "access_token": "...", "token_type": "bearer", "expires_in": 28800 }
```

En modo dev, si el usuario no existe se crea automáticamente. El token incluye
los claims sugeridos por el documento de contexto (`applications`, `roles` por
aplicación). Los permisos finos se consultan aparte (ver §7).

> El login dev se puede deshabilitar con `MINERVA_ENABLE_DEV_LOGIN=false`.

Guarda el token para los siguientes pasos:

```bash
TOKEN=$(curl -s -X POST http://localhost:9000/api/v1/auth/dev-login \
  -H 'Content-Type: application/json' -d '{"email":"admin@local.dev"}' \
  | python3 -c 'import sys,json;print(json.load(sys.stdin)["access_token"])')
```

Usuario autenticado:

```bash
curl -s http://localhost:9000/api/v1/me -H "Authorization: Bearer $TOKEN"
```

---

## 5. Importar un manifiesto

Cada sistema declara su aplicación, permisos y roles en `manifest.minerva.yml`
(ver ejemplo en `manifests/manifest.minerva.yml`).

Por archivo (multipart):

```bash
curl -s -X POST http://localhost:9000/api/v1/manifests/import \
  -H "Authorization: Bearer $TOKEN" \
  -F "file=@manifests/manifest.minerva.yml"
```

O enviando el contenido como cuerpo de texto:

```bash
curl -s -X POST http://localhost:9000/api/v1/manifests/import \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/x-yaml" \
  --data-binary @manifests/manifest.minerva.yml
```

La importación hace **upsert** de aplicación, permisos, roles y relación
rol-permiso, y registra la importación (`manifest_imports`). Es **idempotente**.

Validaciones aplicadas:

- `application.code` es obligatorio.
- Cada permiso sigue `{application_code}.{resource}.{action}`.
- Los roles no referencian permisos inexistentes en el manifiesto.
- El manifiesto no incluye permisos de otra aplicación.

---

## 6. Administrar usuarios, roles y asignaciones (API)

```bash
# Crear un usuario de desarrollo
curl -s -X POST http://localhost:9000/api/v1/users \
  -H "Authorization: Bearer $TOKEN" -H 'Content-Type: application/json' \
  -d '{"email":"capturista@local.dev","full_name":"Capturista"}'

# Listar roles de la aplicación godin
curl -s "http://localhost:9000/api/v1/roles?application_code=godin" \
  -H "Authorization: Bearer $TOKEN"

# Asignar un rol a un usuario (access assignment)
curl -s -X POST http://localhost:9000/api/v1/access-assignments \
  -H "Authorization: Bearer $TOKEN" -H 'Content-Type: application/json' \
  -d '{"user_id":"<USER_ID>","role_id":"<ROLE_ID>"}'

# Quitar la asignación
curl -s -X DELETE http://localhost:9000/api/v1/access-assignments/<USER_ID>:<ROLE_ID> \
  -H "Authorization: Bearer $TOKEN"
```

> Todo esto también se administra desde el panel en http://localhost:3000.

---

## 7. Consultar permisos del usuario autenticado

```bash
curl -s "http://localhost:9000/api/v1/me/permissions?application=godin" \
  -H "Authorization: Bearer $TOKEN"
```

```json
{
  "application": "godin",
  "roles": ["Administrador"],
  "permissions": ["godin.oficios.create", "godin.oficios.view"]
}
```

---

## 8. Conectar un sistema consumidor (SDK FastAPI)

El SDK vive en [`../sdk`](../sdk). Para integrar el login completo (redirección,
canje del code, manifiesto y variables) sigue la
[guía de integración](./guia-integracion.md).

```python
from fastapi import Depends, FastAPI
from minerva_sdk.fastapi import require_permission

app = FastAPI()

@app.post("/oficios")
def crear_oficio(user=Depends(require_permission("godin.oficios.create"))):
    return {"message": "Oficio creado", "user": user["email"]}
```

Variables del consumidor (desarrollo):

```env
MINERVA_ISSUER_URL=http://localhost:9000
MINERVA_APPLICATION_CODE=godin
MINERVA_JWT_SECRET=dev-secret
MINERVA_PERMISSIONS_CACHE_TTL=300
```

`require_permission` valida la firma del JWT y consulta
`GET /api/v1/me/permissions` (con caché). Así se valida **permiso**, no rol.

---

## 9. Migrar a Minerva Central

No cambia el código del sistema consumidor; sólo su configuración:

```env
MINERVA_ISSUER_URL=https://minerva.iieg.gob.mx
MINERVA_APPLICATION_CODE=godin
# en producción: validación por clave pública / JWKS en lugar del secreto dev
```

Del lado de Minerva, las variables `MINERVA_*` (DB, issuer, secreto, expiración)
tienen prioridad sobre las heredadas, por lo que apuntar a otra base/issuer es
sólo configuración.

---

## 10. Variables de entorno (Dev Kit)

| Variable | Descripción | Default |
|---|---|---|
| `MINERVA_MODE` | Modo de operación | `dev` |
| `MINERVA_DB_URL` | URL de PostgreSQL (acepta `postgresql://` o `postgresql+psycopg://`) | (usa `DATABASE_URL`) |
| `MINERVA_ENABLE_DEV_LOGIN` | Habilita `POST /api/v1/auth/dev-login` | `true` |
| `MINERVA_AUTO_IMPORT_MANIFESTS` | Importa manifiestos al arrancar | `true` |
| `MINERVA_MANIFESTS_PATH` | Carpeta de manifiestos | `/app/manifests` |
| `MINERVA_JWT_ISSUER` | Issuer (`iss`) de los tokens | `http://localhost:9000` |
| `MINERVA_JWT_SECRET` | Secreto de firma (HS256) | `dev-secret` |
| `MINERVA_ACCESS_TOKEN_EXPIRE_MINUTES` | Expiración del token | `480` |

Cuando una variable `MINERVA_*` no está definida, se usa la equivalente
heredada (`DATABASE_URL`, `JWT_SECRET_KEY`, `ACCESS_TOKEN_EXPIRE_MINUTES`,
`MINERVA_ISSUER`).

---

## 11. Endpoints del contrato Dev Kit (`/api/v1`)

```http
GET    /health

POST   /api/v1/auth/dev-login
GET    /api/v1/me
GET    /api/v1/me/permissions?application={code}

GET    /api/v1/applications
POST   /api/v1/applications
GET    /api/v1/applications/{id}
PATCH  /api/v1/applications/{id}

GET    /api/v1/users
POST   /api/v1/users
GET    /api/v1/users/{id}
PATCH  /api/v1/users/{id}

GET    /api/v1/roles            (?application_code= | ?application_id=)
POST   /api/v1/roles            (?application_code= | ?application_id=)
GET    /api/v1/roles/{id}
PATCH  /api/v1/roles/{id}

GET    /api/v1/permissions      (?application_code= | ?application_id=)
POST   /api/v1/permissions      (?application_code= | ?application_id=)

GET    /api/v1/access-assignments  (?user_id= | ?application=)
POST   /api/v1/access-assignments
DELETE /api/v1/access-assignments/{user_id}:{role_id}

POST   /api/v1/manifests/import
```

> Las rutas previas (`/auth`, `/users`, `/applications`, `/roles`,
> `/permissions`, `/groups`, `/authorization`, `/audit`) siguen activas sin
> cambios; el panel administrativo las usa tal cual.

---

## 12. Pruebas

```bash
cd backend
pip install -e ".[dev]"
pytest tests/ -v          # incluye tests/test_devkit.py
```
