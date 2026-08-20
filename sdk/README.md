# minerva-sdk

SDK oficial para integrar sistemas FastAPI con Minerva sin implementar JWT, PKCE,
URLs OAuth ni consultas de permisos a mano.

> El consumidor valida permisos, nunca roles. Minerva decide quién tiene cada permiso.

## Instalación

El SDK se instala **desde este repositorio**; no se publica en PyPI.

```bash
pip install "minerva-sdk @ git+https://github.com/iieg-oficial/minerva.git@main#subdirectory=sdk"
```

`main` es la rama de releases: es la referencia que debes usar. El repositorio es privado, así
que necesitas acceso; si tienes llave SSH configurada, la forma equivalente es:

```bash
pip install "minerva-sdk @ git+ssh://git@github.com/iieg-oficial/minerva.git@main#subdirectory=sdk"
```

Declara ese mismo requisito en tu `pyproject.toml` o `requirements.txt` para fijarlo, en lugar
de pedir `minerva-sdk` por nombre.

> ⚠️ **El paquete `minerva-sdk` de PyPI no es este proyecto.** Es de un tercero sin relación con
> el IIEG: `pip install minerva-sdk` a secas instala software ajeno.

### Instalación editable (si clonaste el repositorio)

Para desarrollar sobre el SDK o trabajar con un checkout local del monorepo:

```bash
pip install -e path/to/minerva/sdk
```

Es un canal local de desarrollo, no el canal de distribución de arriba.

## Configuración mínima

Para proteger una API solo necesitas:

```env
MINERVA_ISSUER_URL=http://localhost:3100
MINERVA_APPLICATION_CODE=portal_demo
```

Para iniciar sesión desde tu sistema agrega:

```env
MINERVA_CLIENT_ID=<client_id mostrado por Minerva>
MINERVA_REDIRECT_URI=http://localhost:8100/callback
MINERVA_CLIENT_SECRET=<solo para cliente confidencial>
```

Qué significa cada valor:

| Variable | Valor exacto |
|---|---|
| `MINERVA_ISSUER_URL` | Una sola URL pública de Minerva. Dev: `http://localhost:3100`. Producción: su origen HTTPS público |
| `MINERVA_APPLICATION_CODE` | `application.code` del manifiesto; también es el `aud` del access token |
| `MINERVA_CLIENT_ID` | Credencial pública mostrada al registrar/importar la aplicación |
| `MINERVA_CLIENT_SECRET` | Credencial privada mostrada una vez; se omite en clientes públicos |
| `MINERVA_REDIRECT_URI` | Callback del consumidor, idéntica carácter por carácter a la registrada en Minerva |

No configures `MINERVA_JWT_SECRET`: Minerva firma con RS256 y el SDK obtiene las claves
públicas del JWKS.

## Proteger endpoints FastAPI

```python
from fastapi import Depends, FastAPI
from minerva_sdk import get_current_user, require_permission

app = FastAPI()


@app.get("/whoami")
async def whoami(user: dict = Depends(get_current_user)):
    return {"sub": user["sub"], "email": user.get("email")}


@app.post("/oficios")
async def create_document(user: dict = Depends(require_permission("portal_demo.documents.create"))):
    return {"created_by": user["email"]}
```

- Sin token o token inválido: `401`.
- Token válido sin permiso: `403`.
- Minerva no disponible durante la consulta de permisos: `502`.

El objeto `user` contiene únicamente claims; nunca incluye el bearer.

## Login OIDC sin copiar PKCE

El SDK genera `state`, `code_verifier`, challenge y la URL completa:

```python
from minerva_sdk import MinervaOIDC

oidc = MinervaOIDC()
authorization = oidc.authorization_request()

# Guarda code_verifier asociado a state en tu sesión server-side.
save_pending(authorization.state, authorization.code_verifier)
return RedirectResponse(authorization.url)
```

Para mostrar el selector de cuentas:

```python
authorization = oidc.authorization_request(prompt="select_account")
```

En la callback, maneja primero `error=access_denied`; después recupera el verifier y
canjea el código:

```python
tokens = await oidc.exchange_code(code, code_verifier)
```

No expongas los tokens al navegador. Guárdalos en el mecanismo de sesión server-side
que ya use tu aplicación.

## Refresh y logout

```python
tokens = await oidc.refresh(current_refresh_token)
await oidc.revoke(tokens["refresh_token"])
```

El refresh token rota: reemplaza siempre el anterior. `revoke()` invalida la familia de
refresh tokens; el consumidor debe borrar además su propia sesión/cookie local.

## Sesiones server-side

Si el access token vive en una sesión del backend en vez de llegar como Bearer, usa los
mismos controles sin tocar funciones privadas:

```python
from minerva_sdk import check_permission, get_permissions, validate_access_token

user = await validate_access_token(access_token)
permissions = await get_permissions(access_token)
user = await check_permission(access_token, "portal_demo.documents.create")
```

## Variables avanzadas

No hacen falta en el camino normal:

| Variable | Default | Cuándo usarla |
|---|---:|---|
| `MINERVA_EXPECTED_ISSUER` | misma URL base | Solo si el host interno usado para JWKS difiere del `iss` público |
| `MINERVA_PERMISSIONS_CACHE_TTL` | `0` | Opt-in: reduce tráfico, pero retrasa revocaciones hasta ese TTL |
| `MINERVA_JWKS_CACHE_TTL` | `3600` | Ajustar caché de claves públicas |
| `MINERVA_JWKS_REFRESH_COOLDOWN` | `30` | Limitar refrescos por `kid` desconocido |
| `MINERVA_REQUEST_TIMEOUT` | `10` | Timeout de llamadas a Minerva |

Con caché de permisos desactivada, `require_permission` consulta a Minerva en cada
decisión y detecta revocaciones inmediatamente. La validación local de
`get_current_user` no consulta revocación y puede aceptar el access token hasta su `exp`.

## Errores de configuración

`settings.validate(login=True)` enumera juntos los valores faltantes o mal formados. El
cliente OIDC lo ejecuta automáticamente antes de iniciar login, exchange, refresh o
revoke.

## Compatibilidad y versiones

El SDK corre en **tu** entorno, no en el de Minerva, así que estos son los soportes que el CI
prueba de verdad en cada PR ([`.github/workflows/ci.yml`](../.github/workflows/ci.yml), job
`sdk`): una matriz de dos entornos, el mínimo declarado y el más reciente soportado.

| Requisito | Soportado | Cómo se prueba |
|---|---|---|
| Python | 3.10 – 3.13 | La matriz corre en 3.10 y en 3.13, los dos extremos |
| FastAPI | `>=0.110` | El entorno de 3.10 instala `fastapi==0.110.*`, el piso exacto |
| httpx | `>=0.27` | El entorno de 3.10 instala `httpx==0.27.*`, el piso exacto |
| python-jose | `>=3.3` (extra `[cryptography]`) | Resolución libre en ambos entornos |

`requires-python` se queda en `>=3.10` **sin techo** a propósito: una librería que se instala en
el entorno del consumidor no debe bloquear su Python. Pero el soporte llega hasta donde llega lo
probado — si corres 3.14, corres por delante de la matriz.

**Solo FastAPI.** Las dependencias del SDK son dependencias de FastAPI (`Depends`, `HTTPBearer`);
no se soportan Flask, Django ni otros frameworks, y no está previsto añadirlos.

### Qué versión del SDK va con qué Minerva

El SDK se instala como requisito VCS desde este repositorio, así que puedes fijarlo a un tag de
release en lugar de a `main` y tener instalaciones reproducibles:

```bash
pip install "minerva-sdk @ git+https://github.com/iieg-oficial/minerva.git@v0.7.0#subdirectory=sdk"
```

| SDK | Viaja en Minerva |
|---|---|
| 0.3.0 | `v0.7.0` y posteriores |
| 0.2.0 | `v0.4.0` … `v0.6.0` |
| 0.1.0 | `v0.1.0` … `v0.3.4` |

Contra el servidor, el SDK solo consume el contrato OIDC estable —
`/.well-known/jwks.json`, `/auth/authorize`, `/auth/token`, `/auth/revoke` y
`GET /api/v1/me/permissions`—, así que la tabla dice **con qué release viaja cada versión**, no
que las demás combinaciones estén rotas.

### Política de versionado

El SDK **versiona por su cuenta** ([`pyproject.toml`](pyproject.toml)): su número no sigue al del
servidor, porque lo actualizas a tu ritmo.

- Mientras el SDK esté en `0.x`, un cambio **incompatible sube el MINOR** (0.2.0 → 0.3.0), que es
  lo que permite SemVer antes de 1.0. A partir de `1.0.0` un cambio incompatible sube el **MAJOR**.
- Todo cambio incompatible se marca como `BREAKING` en [`CHANGELOG.md`](CHANGELOG.md), con su nota
  de migración. Un cambio incompatible sin entrada de changelog no se mergea: hay una prueba que
  falla si la versión del paquete no está documentada.
- Antes de actualizar, lee [`CHANGELOG.md`](CHANGELOG.md) — es el changelog del SDK, distinto del
  [changelog de Minerva](../CHANGELOG.md).

## Ejemplo ejecutable

[`examples/minerva-consumer`](../examples/minerva-consumer) contiene un sistema mock con
login, callback, sesión HttpOnly, roles informativos, permisos efectivos, errores 401/403,
refresh, logout y un manifiesto listo para subir al panel.
