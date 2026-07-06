# Minerva Consumer Contract

Use this reference when implementing or reviewing a system that consumes Minerva.

## What Minerva Provides

Minerva is the IIEG identity provider. It exposes:

| Purpose | Endpoint |
|---|---|
| OIDC discovery | `GET /.well-known/openid-configuration` |
| Public signing keys | `GET /.well-known/jwks.json` |
| Browser authorization | `GET /auth/authorize` |
| SPA authorization helper | `GET /auth/authorize/url` |
| Token exchange and refresh | `POST /auth/token` |
| Refresh-token revocation | `POST /auth/revoke` |
| Identity claims | `GET /userinfo` |
| Canonical consumer permissions | `GET /api/v1/me/permissions?application=<code>` |

Consumers should not use `/authorization/me/permissions`; that endpoint is for Minerva's internal admin panel shape.

## SDK Setup

For FastAPI consumers, use the official SDK:

```python
from minerva_sdk.fastapi import get_current_user, require_permission
```

Expected SDK dependencies are FastAPI, HTTPX, and `python-jose[cryptography]`.

If Minerva is available as a sibling checkout during development:

```bash
pip install -e /path/to/minerva/sdk
```

If the package is published in the target environment, add `minerva-sdk` with the project's normal package manager. Do not copy the SDK source into the project unless the user explicitly chooses vendoring.

## Environment Variables

Backend SDK validation:

```env
MINERVA_ISSUER_URL=http://localhost:9000
MINERVA_APPLICATION_CODE=godin
MINERVA_VERIFY_AUD=true
MINERVA_EXPECTED_ISSUER=http://localhost:9000
MINERVA_JWKS_CACHE_TTL=3600
MINERVA_PERMISSIONS_CACHE_TTL=300
MINERVA_REQUEST_TIMEOUT=10
```

Login flow for the consumer:

```env
MINERVA_CLIENT_ID=<client_id>
MINERVA_REDIRECT_URI=http://localhost:8000/auth/callback
```

Only confidential clients need:

```env
MINERVA_CLIENT_SECRET=<client_secret>
```

Do not add `MINERVA_JWT_SECRET` to a consumer. The access token is RS256-signed and verified through Minerva's JWKS.

## Token Semantics

- `access_token`: send as `Authorization: Bearer <token>` to the consumer API. The SDK verifies it against JWKS. Its `aud` is the application code, for example `godin`.
- `id_token`: identity token for the client. Its `aud` is `client_id`; do not use it to call APIs or check permissions.
- `refresh_token`: rotate on each refresh. Store the newest value and treat the previous value as single-use.
- `jti`: token id used by Minerva for revocation.
- `scope`: OIDC identity scopes such as `openid profile email`; unrelated to fine-grained permissions like `godin.oficios.create`.

## FastAPI Protection Pattern

Use SDK dependencies directly in routers:

```python
from fastapi import APIRouter, Depends
from minerva_sdk.fastapi import get_current_user, require_permission

router = APIRouter(prefix="/oficios", tags=["Oficios"])


@router.get("/me")
async def me(user: dict = Depends(get_current_user)):
    return {"sub": user["sub"], "email": user.get("email")}


@router.post("")
async def create_oficio(user: dict = Depends(require_permission("godin.oficios.create"))):
    return {"created_by": user["email"]}
```

`require_permission` validates the token and then calls Minerva's `GET /api/v1/me/permissions?application=<code>` with the user's Bearer token. Missing permission returns `403`; invalid, missing, or revoked token returns `401`; inability to reach Minerva returns `502`.

If a route needs a permission for a different application code, pass it explicitly:

```python
Depends(require_permission("analytics.dashboard.view", application_code="analytics"))
```

## Browser Login Flow

Implement this in the consumer only if users log in through that system.

1. `GET /login` in the consumer:
   - Generate `state` and `code_verifier`.
   - Store both in the user's server-side session or trusted cookie/session storage.
   - Redirect the browser to Minerva:

```text
{MINERVA_ISSUER_URL}/auth/authorize
  ?client_id={MINERVA_CLIENT_ID}
  &redirect_uri={MINERVA_REDIRECT_URI}
  &response_type=code
  &scope=openid profile email
  &state={state}
  &code_challenge={BASE64URL_SHA256(code_verifier)}
  &code_challenge_method=S256
```

2. `GET /auth/callback` in the consumer:
   - Verify returned `state`.
   - Handle the OAuth2 `error` param first. Minerva only issues a `code` when the user has
     at least one role in the application. A user with no role is redirected to
     `redirect_uri?error=access_denied&state=...` with **no `code`**. Make `code` optional
     and, if `error` is present (e.g. `access_denied`, or `login_required` with
     `prompt=none`), show a "no access" screen instead of exchanging the token. A callback
     signature requiring `code` will otherwise 422 on denied logins.
   - Exchange `code` server-to-server:

```python
import httpx

async with httpx.AsyncClient(timeout=10) as client:
    response = await client.post(
        f"{settings.minerva_issuer_url}/auth/token",
        data={
            "grant_type": "authorization_code",
            "client_id": settings.minerva_client_id,
            "code": code,
            "redirect_uri": settings.minerva_redirect_uri,
            "code_verifier": code_verifier,
            # "client_secret": settings.minerva_client_secret,  # confidential clients only
        },
    )
    response.raise_for_status()
    tokens = response.json()
```

3. Store tokens using the project's existing session/security pattern. For a web app, prefer an HTTP-only secure session/cookie setup over exposing raw tokens to the browser.

Small PKCE helpers are acceptable when no OAuth client library exists, but do not create custom JWT validation or permission functions.

## Public vs Confidential Clients

- Public client: no `client_secret`; PKCE is required in `/auth/authorize` and `/auth/token`.
- Confidential client: has `client_secret`; PKCE may still be used, but secret validation is available server-to-server.
- Redirect URI must match exactly one registered in Minerva.

## Refresh And Logout

Refresh:

```text
POST /auth/token
grant_type=refresh_token
client_id=<client_id>
refresh_token=<current_refresh_token>
client_secret=<only for confidential client>
```

Always replace the stored refresh token with the new one. Reuse of a rotated token revokes the whole token family.

Logout/revoke:

```text
POST /auth/revoke
client_id=<client_id>
token=<refresh_token>
client_secret=<only for confidential client>
```

## Common Failures

- `401 Token no proporcionado`: missing Bearer header.
- `401 Token invalido`: malformed, expired, wrong algorithm, wrong `aud`, or wrong `iss`.
- `403 Requiere permiso`: token is valid but Minerva does not grant the permission.
- `500 MINERVA_APPLICATION_CODE no configurado`: set `MINERVA_APPLICATION_CODE`.
- `502 No se pudo obtener el JWKS`: consumer cannot reach `MINERVA_ISSUER_URL`.
- Redirect mismatch during login: register the exact `MINERVA_REDIRECT_URI` in Minerva.
- `422` on `/callback` for some users: the callback requires `code`, but Minerva returned
  `error=access_denied` (user has no role in the app) with no `code`. Make `code` optional
  and handle `error` (see Browser Login Flow step 2).

## Login Screen Branding

The login screen can show the requesting app's name, logo, and color instead of the
generic Minerva identity. This needs **no consumer or SDK change** — it is Minerva-side
configuration only. An admin sets `display_name`, `logo_url`, and/or `brand_color` on the
application (admin panel or `PATCH /applications/{id}`). Minerva's login page reads them
from the public read-only endpoint `GET /public/apps/{client_id}/branding`, which exposes
only those non-sensitive fields (never `client_secret` or redirect URIs).
