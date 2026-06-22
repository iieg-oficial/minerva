# Integración OIDC con Minerva (vía recomendada)

Minerva es un **proveedor OIDC (OpenID Connect)**. Un sistema nuevo del IIEG se
integra con el **Authorization Code Flow + PKCE**, valida los tokens con **RS256
contra el JWKS público** de Minerva y consulta permisos en tiempo real. **Ya no
se comparte ningún secreto de firma**: basta la URL de Minerva.

> Minerva firma **todo con RS256** y valida contra el JWKS público: no hay HS256 ni
> secreto compartido en ningún lado. Esta es la guía de integración vigente.

---

## 1. Qué expone Minerva (contrato OIDC)

Todo se descubre desde el **discovery**; un sistema no debería hardcodear rutas
salvo `MINERVA_ISSUER_URL`.

| Endpoint | Método | Para qué |
|---|---|---|
| `/.well-known/openid-configuration` | GET (público, CORS abierto) | Descubrimiento: issuer, endpoints, algoritmos, scopes |
| `/.well-known/jwks.json` | GET (público, CORS abierto) | Claves públicas RS256 para verificar la firma |
| `/auth/authorize` | GET | Inicia el flujo; devuelve un `code` |
| `/auth/token` | POST (form-urlencoded o JSON) | Canjea `code` → tokens; y `grant_type=refresh_token` |
| `/auth/revoke` | POST | Revoca un refresh token y su familia (RFC 7009) |
| `/api/v1/me/permissions?application=<code>` | GET (Bearer) | Permisos del usuario para tu app (lo usa el SDK) |

El discovery anuncia: `response_types=["code"]`,
`grant_types=["authorization_code","refresh_token"]`,
`id_token_signing_alg=["RS256"]`, `code_challenge_methods=["S256"]`,
`scopes=["openid","profile","email"]`.

---

## 2. Los tres tokens (y para qué sirve cada uno)

| Token | Firma | `aud` | Vida | Contenido |
|---|---|---|---|---|
| **access_token** | RS256 | slug de la app | corto (15 min) | `sub`, `email`, `name`, `roles`, `permissions`, `jti` |
| **id_token** | RS256 | `client_id` | corto | identidad pura: `sub`, `email`, `name`, `nonce`, `auth_time` |
| **refresh_token** | opaco (hash en BD) | — | 30 días | rota en cada uso; reúso → revoca la familia |

- El **access_token** es para autorizar acciones: lleva la semántica de **permisos**
  de Minerva. Es lo que tu sistema valida en cada request.
- El **id_token** es para el cliente (identidad). Su `aud` es el `client_id`, distinto
  del access token, a propósito.
- El **refresh_token** renueva el access token corto sin re-login. Cada uso lo **rota**;
  si se reusa uno ya rotado (posible robo), se revoca toda la familia.

---

## 3. El flujo end-to-end

```
Navegador            Tu backend                 Minerva
   │ "Iniciar sesión"
   ├───────────────► GET /auth/login
   │                   │ arma URL authorize + state + PKCE (code_challenge S256)
   │ ◄─────────────────┘ 302 → {ISSUER}/auth/authorize?client_id&redirect_uri
   │                                              &response_type=code&scope=openid...
   │                                              &code_challenge&code_challenge_method=S256
   │                                              &nonce&state
   ├──────────────────────────────────────────► /authorize  (login en Minerva si hace falta)
   │ ◄──────────────────────────────────────────┘ 302 → {redirect_uri}?code&state
   ├───────────────► GET /auth/callback?code&state
   │                   │ valida state, POST {ISSUER}/auth/token (form-urlencoded):
   │                   │   grant_type=authorization_code, code, redirect_uri,
   │                   │   client_id, client_secret, code_verifier
   │                   │ recibe { access_token, id_token, refresh_token, expires_in }
   │ ◄─────────────────┘ guarda tokens (sesión del usuario en tu sistema)
   │
   │  ...en cada request protegida, tu backend valida el access_token (RS256/JWKS)
   │  y consulta permisos en /api/v1/me/permissions (el SDK lo hace por ti).
   │
   │  cuando el access token expira (15 min):
   ├───────────────► tu backend: POST /auth/token grant_type=refresh_token
   │ ◄─────────────────┘ nuevo access_token + nuevo refresh_token (rotación)
```

PKCE es **opcional pero vinculante**: si mandas `code_challenge` en `/authorize`,
el canje exige el `code_verifier` correcto. Recomendado siempre.

---

## 4. Integrar el lado servidor con `minerva_sdk`

El SDK valida la firma RS256 contra el JWKS (sin secreto) y resuelve permisos.

```bash
pip install -e ./sdk     # desde el repo de Minerva, o publícalo internamente
```

```python
from fastapi import FastAPI, Depends
from minerva_sdk.fastapi import require_permission, get_current_user

app = FastAPI()

@app.get("/whoami")
async def whoami(user=Depends(get_current_user)):
    return {"email": user["email"], "sub": user["sub"]}

@app.post("/oficios")
async def crear_oficio(user=Depends(require_permission("godin.oficios.create"))):
    return {"ok": True}
```

> `get_current_user` y `require_permission` son **async**. Se valida **permiso**,
> nunca rol.

### Variables del SDK

| Variable | Default | Nota |
|---|---|---|
| `MINERVA_ISSUER_URL` | `http://localhost:9000` | **Lo único imprescindible.** De aquí sale el JWKS. |
| `MINERVA_APPLICATION_CODE` | `` | Tu slug; es el `aud` esperado del access token. |
| `MINERVA_VERIFY_AUD` | `true` | Verifica que el token sea para tu app. |
| `MINERVA_EXPECTED_ISSUER` | `` | Si se define, valida el claim `iss`. |
| `MINERVA_PERMISSIONS_CACHE_TTL` | `300` | Caché de permisos (s). |
| `MINERVA_JWKS_CACHE_TTL` | `3600` | Caché del JWKS (s). |

**La revocación se aplica del lado de Minerva:** `require_permission` consulta
`/api/v1/me/permissions`, y un token revocado recibe `401`, que el SDK propaga.

---

## 5. Registrar la app y declarar permisos

### 5.1 Registrar la aplicación

Necesitas un `client_id` y un `client_secret`:

- **Panel admin** (recomendado): *Nueva aplicación* → nombre y `slug` (el slug es el
  `application_code`, p. ej. `godin`). Copia el **Client ID** y el **Client Secret**
  (el secret **solo se muestra una vez**; si lo pierdes, usa *Regenerar client secret*).
  Luego agrega la **redirect URI** exacta (botón 🔗).
- **API**:
  ```bash
  POST /applications
  { "name": "Godín", "slug": "godin", "homepage_url": "http://localhost:3000" }
  # → devuelve client_id y client_secret (una sola vez)

  POST /applications/{app_id}/redirect-uris
  { "uri": "http://localhost:3000/api/auth/callback", "environment": "development" }
  ```

> Si Minerva **auto-importa** el manifiesto al arrancar, la app se crea con un secret
> aleatorio que no se muestra: usa *Regenerar client secret* en el panel.

### 5.2 Declarar permisos y roles (manifiesto)

El `manifest.minerva.yml` declara la aplicación, sus **permisos** y sus **roles**:

```yaml
application:
  code: godin                 # slug único, == MINERVA_APPLICATION_CODE
  name: Godín
  redirect_uris:
    - http://localhost:3000/api/auth/callback

permissions:
  - key: godin.oficios.view     # {application_code}.{recurso}.{accion}
    name: Ver oficios
  - key: godin.oficios.create
    name: Crear oficios

roles:
  - name: Capturista
    permissions: [godin.oficios.view, godin.oficios.create]
```

- `key` sigue `{application_code}.{recurso}.{accion}` (acciones válidas:
  `view create update delete assign approve authorize export import manage`).
- Los roles solo referencian permisos del mismo manifiesto.
- Importar: `POST /api/v1/manifests/import -F "file=@manifest.minerva.yml"`, o automático
  al arrancar dejándolo en `MINERVA_MANIFESTS_PATH` (idempotente, no regenera secrets).

> Importar el manifiesto **no asigna** roles a usuarios: eso se hace en el panel o por
> `POST /api/v1/access-assignments`. Un usuario sin rol de tu app autentica pero debe
> tratarse como "sin acceso".

### 5.3 Single logout y reemplazo del login propio

- **Logout**: tras cerrar la sesión local, redirige a
  `{MINERVA_LOGIN_URL}/logout?redirect_uri={FRONTEND_URL}/` para cerrar **también** la
  sesión en Minerva (si no, Minerva re-autoriza en silencio y el usuario no puede salir).
- **Si tu sistema ya tenía login propio, quita**: el formulario de login y su manejo de
  contraseñas, los endpoints `login`/`register`, los **roles locales** y cualquier
  `if user.role == 'admin'` (el acceso se decide por **permisos** de Minerva). Sustitúyelo
  por: botón → `/auth/login`, página de callback, y la validación con el SDK.

---

## 6. Migrar de un flujo con secreto compartido

Si tu sistema usaba el flujo previo con `MINERVA_JWT_SECRET` (HS256):

1. Sube la versión del `minerva_sdk` (valida RS256/JWKS).
2. **Elimina `MINERVA_JWT_SECRET`** de tu `.env`: ya no se usa. La firma se valida
   contra el JWKS público.
3. Conserva `MINERVA_ISSUER_URL` y `MINERVA_APPLICATION_CODE`.
4. No tienes que tocar tu lógica de permisos: `require_permission` no cambia.

> Minerva firma **todo** con RS256 (no hay HS256 ni secreto compartido en ningún
> lado). El JWKS publica la clave activa y las retiradas, así que la rotación de
> claves es transparente para tu sistema.

---

## 7. Arquitectura del proveedor (referencia para mantenedores)

- **Claves de firma** (`backend/app/modules/oidc/`): tabla `signing_keys` con la
  clave **activa** (firma) y las **retiradas** (se siguen publicando en el JWKS hasta
  que expiren los tokens que firmaron). Rotación con `rotate_key()`. El `kid` viaja en
  el header del JWT; el verificador elige la clave por `kid`.
- **Cifrado en reposo**: la clave privada RSA se guarda **cifrada con Fernet**
  (`MINERVA_KEY_ENCRYPTION_KEY`, obligatoria en producción). Nunca en texto plano.
- **Firma unificada RS256**: **todo** se firma con la clave RSA activa — tokens de
  consumidores (canje OIDC) y tokens de sesión interna del panel (login, dev-login).
  No hay HS256 ni secreto compartido. `get_current_user` valida siempre contra el JWKS.
- **Ciclo de vida del token**: access corto (`MINERVA_ACCESS_TOKEN_TTL_MINUTES=15`) +
  refresh con rotación y detección de reúso (`MINERVA_REFRESH_TOKEN_TTL_DAYS=30`). El
  TTL del canje está **separado** del de la sesión interna del panel.
- **Revocación**: blacklist por `jti` en Redis (`core/token_blacklist.py`), poblada al
  rotar/revocar; el enforcement vive en `get_current_user` (lo consulta el endpoint de
  permisos, que es donde pega el SDK).
- **Redis** tiene alcance acotado: rate limiting, blacklist y sesiones efímeras. La
  fuente de verdad sigue siendo PostgreSQL.

---

## 8. Troubleshooting

| Síntoma | Causa probable | Arreglo |
|---|---|---|
| `401` al validar el token | el SDK no alcanza el JWKS, o el `aud` no coincide | revisa `MINERVA_ISSUER_URL` (alcanzable desde tu backend) y que `MINERVA_APPLICATION_CODE` == tu slug |
| `No se pudo obtener el JWKS` | `MINERVA_ISSUER_URL` no resoluble desde el contenedor | usa `host.docker.internal:9000` + `extra_hosts` en tu compose |
| `redirect_uri no autorizada` | la URI no está registrada exacta | regístrala (panel 🔗 o API) idéntica a la que mandas en `/authorize` |
| `code_verifier inválido (PKCE)` | el `code_verifier` no corresponde al `code_challenge` | usa el mismo `verifier` que generó el `challenge` del `/authorize` |
| El access token expira muy seguido | es corto (15 min) por diseño | implementa el `grant_type=refresh_token` para renovarlo |
| Usuario entra pero todo da 403 | autenticado pero sin rol/permiso de tu app | asígnale un rol (panel o `POST /api/v1/access-assignments`) |
| No puede cerrar sesión (reentra solo) | falta el single logout | redirige a `{MINERVA_LOGIN_URL}/logout` |

## 9. Checklist de integración OIDC

- [ ] App registrada (`client_id` + `client_secret`) y redirect URI exacta.
- [ ] `manifest.minerva.yml` importado (permisos + roles) y roles asignados.
- [ ] Backend: `/auth/login` (con PKCE + state), `/auth/callback` (canje form-urlencoded),
      refresh cuando expira el access token.
- [ ] `minerva_sdk` instalado; `MINERVA_ISSUER_URL` + `MINERVA_APPLICATION_CODE` set;
      **sin** `MINERVA_JWT_SECRET`.
- [ ] Endpoints protegidos con `require_permission("<app>.<recurso>.<accion>")`.
- [ ] Logout que cierra también la sesión en Minerva (single logout).
