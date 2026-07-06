---
name: minerva-integration
description: Integrate consumer systems with Minerva, the IIEG identity and access platform, using the official minerva_sdk and OIDC contract. Use when adding, reviewing, or fixing Minerva login, Authorization Code + PKCE, manifest.minerva.yml, FastAPI get_current_user/require_permission dependencies, environment variables, or permission checks in another project, especially when the agent must avoid custom JWT or authorization helper functions.
---

# Minerva Integration

## Core Rule

Use Minerva as the source of truth for identity and authorization.

Consumer systems define what actions exist through `manifest.minerva.yml`; Minerva decides who has those actions. A consumer validates permissions, never roles:

```python
from fastapi import Depends
from minerva_sdk.fastapi import require_permission


@router.post("/oficios")
async def create_oficio(user: dict = Depends(require_permission("godin.oficios.create"))):
    ...
```

Never replace this with local role checks, copied JWT decoding code, or a local permission table.

## Workflow

1. Inspect the consumer project before editing:
   - Find the backend framework, package manager, app entrypoint, auth middleware, route structure, and `.env.example`.
   - Search for existing Minerva usage: `minerva_sdk`, `MINERVA_`, `require_permission`, `get_current_user`, `manifest.minerva.yml`.
   - Preserve existing session, cookie, router, dependency injection, and test patterns.

2. Add or reuse the official SDK:
   - Prefer `minerva_sdk.fastapi.get_current_user` and `minerva_sdk.fastapi.require_permission`.
   - If the project is Python/FastAPI, add `minerva-sdk` through the project's normal dependency flow.
   - If the SDK is available only as a local checkout, use an editable/path dependency to Minerva's `sdk/`.
   - Do not vendor or reimplement `minerva_sdk` unless the user explicitly asks.

3. Define the application contract:
   - Create or update `manifest.minerva.yml` with `application`, `permissions`, and `roles`.
   - Permission keys must follow `{application_code}.{resource}.{action}`.
   - Use roles only as Minerva administration groups; do not validate them in the consumer.
   - Read `references/manifest-contract.md` before creating or changing a manifest.

4. Implement delegated login only where needed:
   - Use OIDC Authorization Code + PKCE for browser login.
   - Store `state` and `code_verifier` in the consumer's normal session mechanism.
   - In `/callback`, make `code` optional and handle the OAuth2 `error` param: a user with
     no role in the app is redirected with `error=access_denied` and no `code`. Show a "no
     access" screen instead of exchanging the token; a `code`-required signature 422s.
   - Exchange `code` at Minerva's `/auth/token` server-to-server.
   - Optional popup login: add `response_mode=web_message` to the `/authorize` URL and open
     it with `window.open`; Minerva returns `{code, state, error}` to the opener via
     `postMessage` (validate `event.origin`) instead of a full-page redirect. Opt-in per
     request, no SDK/backend change. See `references/consumer-contract.md`.
   - Use the `access_token` for API calls; use `id_token` only for identity claims.
   - Read `references/consumer-contract.md` before implementing `/login`, `/callback`, refresh, revoke, or protected routes.

5. Protect backend endpoints with SDK dependencies:
   - Use `Depends(get_current_user)` for authenticated identity.
   - Use `Depends(require_permission("app.resource.action"))` for authorization.
   - Let the SDK verify RS256/JWKS, `aud`, optional `iss`, permission lookup, and error responses.
   - Do not call `/authorization/me/permissions` from a consumer; the SDK uses `/api/v1/me/permissions`.

6. Configure environments:
   - Required for SDK validation: `MINERVA_ISSUER_URL`, `MINERVA_APPLICATION_CODE`.
   - Required for login flow: `MINERVA_CLIENT_ID`, `MINERVA_REDIRECT_URI`; add `MINERVA_CLIENT_SECRET` only for confidential clients.
   - In production, keep `MINERVA_VERIFY_AUD=true` and set `MINERVA_EXPECTED_ISSUER` to Minerva's public issuer.
   - Do not introduce `MINERVA_JWT_SECRET` for consumers; Minerva signs with RS256 and publishes JWKS.

7. Validate the integration:
   - Add or update tests for missing token `401`, invalid token `401`, missing permission `403`, and the happy path.
   - For manifest work, validate bad key format, foreign application prefix, and idempotent import when practical.
   - Run the project's normal tests/lint for touched areas.

## Guardrails

- Do not implement authorization with `if user.role == ...`, role names, groups, or claims copied from a token.
- Do not decode JWTs manually in application code; use `get_current_user`.
- Do not verify tokens with HS256 or shared secrets; Minerva uses RS256/JWKS.
- Do not trust `id_token` for API authorization; protect APIs with the access token.
- Do not hardcode Minerva's dev port. Read URLs from env and account for local defaults commonly being `http://localhost:9000`.
- Do not store real `client_secret`, refresh tokens, or admin tokens in tracked files.
- If the project is not FastAPI/Python and no official SDK exists for that stack, state that clearly and ask before building a custom adapter.

## References

- Read `references/consumer-contract.md` for endpoints, SDK configuration, FastAPI snippets, login/callback flow, token semantics, and troubleshooting.
- Read `references/manifest-contract.md` for manifest structure, permission naming, registration/import, public vs confidential clients, and role assignment.
