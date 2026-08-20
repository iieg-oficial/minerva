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

The SDK is not published on PyPI. Install it from the Minerva repository, where `main` is the
release branch:

```bash
pip install "minerva-sdk @ git+https://github.com/iieg-oficial/minerva.git@main#subdirectory=sdk"
```

The repository is private, so the environment needs access; with an SSH key configured, use
`git+ssh://git@github.com/iieg-oficial/minerva.git@main#subdirectory=sdk`. Declare that same VCS
requirement in the project's `pyproject.toml` or `requirements.txt` — never a bare `minerva-sdk`,
which resolves to an unrelated third-party package on PyPI.

If Minerva is available as a sibling checkout during development:

```bash
pip install -e /path/to/minerva/sdk
```

Do not copy the SDK source into the project unless the user explicitly chooses vendoring.

## Environment Variables

Backend SDK validation:

```env
MINERVA_ISSUER_URL=http://localhost:9000
MINERVA_APPLICATION_CODE=portal_demo
```

Login flow for the consumer:

```env
MINERVA_CLIENT_ID=<client_id>
MINERVA_REDIRECT_URI=http://localhost:8100/callback
```

Only confidential clients need:

```env
MINERVA_CLIENT_SECRET=<client_secret>
```

Do not add `MINERVA_JWT_SECRET` to a consumer. The access token is RS256-signed and verified through Minerva's JWKS.
Advanced cache, timeout, and split-host settings are documented in `sdk/README.md`; do not
copy them into every consumer unless that deployment actually needs them.

## Token Semantics

- `access_token`: send as `Authorization: Bearer <token>` to the consumer API. The SDK verifies it against JWKS. Its `aud` is the application code, for example `portal_demo`.
- `id_token`: identity token for the client. Its `aud` is `client_id`; do not use it to call APIs or check permissions.
- `refresh_token`: rotate on each refresh. Store the newest value and treat the previous value as single-use.
- `jti`: token id used by Minerva for revocation.
- `scope`: OIDC identity scopes such as `openid profile email`; unrelated to fine-grained permissions like `portal_demo.documents.create`.
- Revocation latency differs by dependency: `get_current_user` verifies the JWT locally against
  JWKS and never calls Minerva, so it does not notice a server-side revocation until the token's
  own `exp` (≤15 min). `require_permission` calls Minerva's `/api/v1/me/permissions` in real time
  (subject to `MINERVA_PERMISSIONS_CACHE_TTL`, caching off by default) and returns
  `401` sooner. Prefer `require_permission` on routes where fast revocation matters.

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
async def create_document(user: dict = Depends(require_permission("portal_demo.documents.create"))):
    return {"created_by": user["email"]}
```

`require_permission` validates the token and then calls Minerva's `GET /api/v1/me/permissions?application=<code>` with the user's Bearer token. Missing permission returns `403`; invalid, missing, or revoked token returns `401`; inability to reach Minerva returns `502`.

The user dict holds **only token claims** — never the bearer, so it is safe to serialize or log. (SDK 0.1.0 attached the raw bearer as `user["_token"]`; 0.2.0 removed it. Get the credential from an `HTTPBearer` dependency if you need it.) Permission caching is **off by default** (`MINERVA_PERMISSIONS_CACHE_TTL=0`): every check queries Minerva, which is what enforces revocation, so revoking a token stops authorizing immediately. Setting a TTL > 0 opts into caching and accepts that a revoked token keeps authorizing for that long; the cache is then keyed by the token's `jti`, never outlives its `exp`, and is size-bounded. Call `invalidate_token(jti)` or `clear_caches()` to drop entries sooner. On an unknown `kid` the SDK refreshes the JWKS once, so a key rotation in Minerva does not cause spurious 401s.

If a route needs a permission for a different application code, pass it explicitly:

```python
Depends(require_permission("analytics.dashboard.view", application_code="analytics"))
```

## Browser Login Flow

Implement this in the consumer only if users log in through that system.

1. `GET /login` in the consumer:
   - Ask the SDK for the complete authorization request.
   - Store `state` and `code_verifier` in the user's server-side session.
   - Redirect the browser to `authorization.url`:

```python
from minerva_sdk import MinervaOIDC

oidc = MinervaOIDC()
authorization = oidc.authorization_request()
save_pending(authorization.state, authorization.code_verifier)
return RedirectResponse(authorization.url)
```

   Optional `prompt` / `max_age` parameters (OIDC Core 3.1.2.1):
   - `prompt=login` — force re-authentication (ask for credentials) even if a Minerva session exists.
   - `prompt=select_account` — show Minerva's **account picker**: the user chooses among the accounts
     already signed in on that browser, re-enters an expired one, or **adds another account**. Use it
     when your platform logs the user out and you want them able to sign in with a *different* account.
     Without it, Minerva does silent SSO with the last active account.
   - `prompt=none` — return `error=login_required` instead of showing login (silent renew in iframes).
   - `max_age={seconds}` — force re-auth if the Minerva session is older than that.

   Response contract:
   - `response_type` accepts **only** `code`. Anything else comes back as
     `error=unsupported_response_type`, not as a `code`.
   - `state` is returned byte-for-byte, even with spaces, `&`, `=` or `#`. Compare it verbatim.
   - A `redirect_uri` registered **with its own query** (`https://app/callback?tenant=jal`) keeps
     that query; `code`/`state` are appended to it. Register it in full. A `code`/`state`/`error`
     baked into that query is replaced by Minerva's, never duplicated.
   - `auth_time` in the `id_token` is when the user authenticated **in that browser session**, not
     when the code was issued. Signing in elsewhere does not rejuvenate this session, and refreshing
     the panel token is not re-authentication. Same reference Minerva uses to enforce `max_age`.

   Consumer logout deletes its own session and calls `MinervaOIDC.revoke(refresh_token)`.
   `/auth/logout` belongs to the panel cookie session and does not accept the consumer Bearer.
   A later `/authorize` may reuse the panel's SSO session; use `prompt=select_account` when the
   user needs to enter with another account.

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
tokens = await oidc.exchange_code(code, code_verifier)
```

3. Store tokens using the project's existing session/security pattern. For a web app, prefer an HTTP-only secure session/cookie setup over exposing raw tokens to the browser.

Do not create custom PKCE, JWT validation, or permission helpers in the consumer.

## Popup / web_message Login

Optional alternative to the full-page redirect: the consumer opens Minerva's login in a
popup so the user never leaves the app. It is **opt-in per request** — add
`response_mode=web_message` to the `/authorize` URL. In this mode Minerva does not navigate
the window to `redirect_uri`; it returns the result to the opener via `window.postMessage`
and closes the popup. **No SDK change and no per-app Minerva config are required**; full-page
redirect stays the default.

Key points:
- Open Minerva's **web panel** URL (where the login/authorize screen lives), which in dev may
  differ from the issuer/API origin (e.g. `:3100` vs `:9000`). Token exchange still happens
  server-to-server against the issuer.
- The message payload is `{ source: "minerva", code, state, error }`. The denied case
  (no role in the app) arrives as `{ error: "access_denied" }` on the same channel.
- Minerva sends the `postMessage` with `targetOrigin = origin of redirect_uri` (never `"*"`).
  Because Minerva validates `redirect_uri` against its allowlist before issuing the `code`,
  the `code` can only reach an origin already registered as yours — that is the trust
  boundary. Still, always validate `event.origin` in the listener before trusting the data.

```js
const MINERVA_ORIGIN = new URL(minervaWebUrl).origin;

window.addEventListener("message", async (e) => {
  if (e.origin !== MINERVA_ORIGIN || e.data?.source !== "minerva") return;
  if (e.data.error) { /* access_denied / login_required → show "no access" */ return; }
  // Exchange e.data.code server-to-server (with the code_verifier), never in the browser.
  await fetch("/popup/exchange", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ code: e.data.code, state: e.data.state }),
  });
});

// Opening the popup:
window.open(
  `${MINERVA_ORIGIN}/authorize?client_id=${clientId}` +
    `&redirect_uri=${encodeURIComponent(redirectUri)}&response_type=code` +
    `&scope=openid%20profile%20email&state=${state}` +
    `&code_challenge=${challenge}&code_challenge_method=S256&response_mode=web_message`,
  "minerva-login", "width=480,height=680",
);
```

Generate `state`/`code_verifier` with `MinervaOIDC.authorization_request()` and keep the
verifier server-side. Popup login is advanced; the reference example intentionally uses
the smaller full-page redirect flow.

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

Minerva also revokes a user's refresh tokens server-side when an admin changes their password or
email, or deactivates them. A refresh attempt after that gets the same `400` as reusing a rotated
token — treat it identically: drop the session and send the user back through `/login`.

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
- `400` on refresh, `"refresh token ya utilizado; la sesión fue revocada por seguridad"`: the
  refresh token was reused after rotation, **or** the user's password/email changed or they were
  deactivated (both cases return the same message). Re-run the login flow.
- `403 Usuario inválido o inactivo` on refresh/authorize: the user's account is not `active`.
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
