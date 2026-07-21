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
| `MINERVA_APPLICATION_CODE` | Código de tu aplicación (slug). **Obligatorio**: es el `aud` que se exige siempre | `` |
| `MINERVA_EXPECTED_ISSUER` | Issuer esperado del `iss`; si se deja vacío se usa `MINERVA_ISSUER_URL`. La validación NO se puede desactivar | `` |
| `MINERVA_PERMISSIONS_CACHE_TTL` | TTL de caché de permisos (segundos). **`0` = sin caché** (default): cada chequeo consulta a Minerva y la revocación es inmediata. Un valor > 0 activa la caché y esa cifra pasa a ser lo que tarda una revocación en notarse | `0` |
| `MINERVA_JWKS_CACHE_TTL` | TTL de caché del JWKS (segundos) | `3600` |
| `MINERVA_JWKS_REFRESH_COOLDOWN` | Mínimo entre dos refrescos del JWKS disparados por un `kid` desconocido (segundos) | `30` |
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

### El objeto de usuario

El dict que devuelven `get_current_user` y `require_permission` son **solo los claims
del token** (`sub`, `email`, `name`, `jti`, `exp`, ...). Nunca contiene la credencial,
así que es seguro serializarlo en una respuesta o registrarlo en un log.

### Cachés y revocación

- **Permisos: sin caché por defecto.** Cada `require_permission` consulta a Minerva, que
  es quien aplica la revocación, así que revocar un token deja de autorizar en el acto.
  Servir una decisión positiva desde memoria significa, por definición, no enterarse de
  una revocación hasta que la entrada expire; por eso la caché es **opt-in**.
- **Si la activas** (`MINERVA_PERMISSIONS_CACHE_TTL > 0`), aceptas esa ventana: un token
  revocado sigue autorizando hasta ese TTL. La caché se indexa por el `jti` del token
  (dos tokens del mismo usuario no comparten decisión), nunca sobrevive al `exp` del
  token, un token sin `jti` no se cachea, y un `401` de Minerva purga la entrada. El
  número de entradas está acotado.
- **JWKS:** si llega un token con un `kid` que no está en la caché, el SDK la refresca
  aunque no haya expirado, así que una rotación de clave en Minerva **no** provoca 401.
- Para forzarlo desde tu propio logout: `invalidate_token(jti)` y `clear_caches()`.

## Migración desde 0.1.0

**Cambio incompatible:** `get_current_user` ya no agrega `_token` (el bearer crudo) al
dict de usuario. Si tu código lo leía, declara la dependencia del bearer en tu endpoint:

```python
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

bearer = HTTPBearer()

@app.get("/algo")
async def algo(user=Depends(get_current_user), creds: HTTPAuthorizationCredentials = Depends(bearer)):
    token = creds.credentials
```

Nada más cambia: `get_current_user` y `require_permission` conservan su firma.

## Migración a Minerva Central

Solo cambia la URL; el JWKS y los endpoints se descubren solos:

```env
MINERVA_ISSUER_URL=https://minerva.iieg.gob.mx
MINERVA_APPLICATION_CODE=godin
```
