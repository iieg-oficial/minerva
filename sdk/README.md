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
| `MINERVA_EXPECTED_ISSUER` | Si se define, valida el claim `iss` | `` |
| `MINERVA_VERIFY_AUD` | Verifica que el `aud` sea tu aplicación | `true` |
| `MINERVA_PERMISSIONS_CACHE_TTL` | TTL de caché de permisos (segundos) | `300` |
| `MINERVA_JWKS_CACHE_TTL` | TTL de caché del JWKS (segundos) | `3600` |
| `MINERVA_JWT_SECRET` | Secreto HS256 legacy (solo transición; vacío = solo RS256) | `` |
| `MINERVA_REQUEST_TIMEOUT` | Timeout de las llamadas a Minerva (segundos) | `10` |

La firma se valida con **RS256 contra el JWKS público** de Minerva: no necesitas
ningún secreto compartido, solo `MINERVA_ISSUER_URL`.

## Uso

```python
from fastapi import FastAPI, Depends
from minerva_sdk.fastapi import require_permission, get_current_user

app = FastAPI()

@app.get("/whoami")
async def whoami(user=Depends(get_current_user)):
    return {"email": user["email"], "sub": user["sub"]}

@app.post("/oficios")
async def crear_oficio(user=Depends(require_permission("godin.oficios.create"))):
    return {"message": "Oficio creado", "user": user["email"]}
```

`get_current_user` y `require_permission` son **async**. `require_permission`
verifica la firma del token (RS256/JWKS) y consulta en tiempo real
`GET /api/v1/me/permissions?application=<code>` de Minerva (con caché en
memoria). Si el usuario no tiene el permiso, responde `403`. Si el token fue
revocado, Minerva responde `401` y el SDK lo propaga.

## Migración a Minerva Central

Solo cambia la URL; el JWKS y los endpoints se descubren solos:

```env
MINERVA_ISSUER_URL=https://minerva.iieg.gob.mx
MINERVA_APPLICATION_CODE=godin
```
