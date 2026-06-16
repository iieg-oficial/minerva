# minerva-sdk

SDK mínimo para que un sistema consumidor (FastAPI) valide identidad y permisos
emitidos por Minerva.

> Principio: **los sistemas validan permisos, no roles.** Minerva define quién
> puede hacer qué; tu sistema solo comprueba permisos explícitos.

## Instalación

```bash
pip install -e ./sdk          # desde la raíz del repo Minerva
# o copia la carpeta minerva_sdk a tu proyecto
```

## Configuración (variables de entorno)

| Variable | Descripción | Default |
|---|---|---|
| `MINERVA_ISSUER_URL` | URL base de Minerva | `http://localhost:9000` |
| `MINERVA_APPLICATION_CODE` | Código de tu aplicación (slug) | `` |
| `MINERVA_JWT_SECRET` | Secreto compartido para validar la firma (modo dev HS256) | `dev-secret` |
| `MINERVA_JWT_ALGORITHM` | Algoritmo de firma | `HS256` |
| `MINERVA_EXPECTED_ISSUER` | Si se define, valida el claim `iss` | `` |
| `MINERVA_PERMISSIONS_CACHE_TTL` | TTL de caché de permisos (segundos) | `300` |
| `MINERVA_VERIFY_SIGNATURE` | Validar firma del JWT | `true` |

## Uso

```python
from fastapi import FastAPI, Depends
from minerva_sdk.fastapi import require_permission, get_current_user

app = FastAPI()

@app.get("/whoami")
def whoami(user=Depends(get_current_user)):
    return {"email": user["email"], "sub": user["sub"]}

@app.post("/oficios")
def crear_oficio(user=Depends(require_permission("godin.oficios.create"))):
    return {"message": "Oficio creado", "user": user["email"]}
```

`require_permission` valida la firma del token y consulta en tiempo real
`GET /api/v1/me/permissions?application=<code>` de Minerva (con caché en
memoria). Si el usuario no tiene el permiso, responde `403`.

## Migración a Minerva Central

Solo cambian las variables de entorno:

```env
MINERVA_ISSUER_URL=https://minerva.iieg.gob.mx
MINERVA_APPLICATION_CODE=godin
# y, en producción, el mecanismo de validación de firma (clave pública / JWKS)
```
