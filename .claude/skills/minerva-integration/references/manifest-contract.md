# Minerva Manifest Contract

Use this reference when creating or updating `manifest.minerva.yml` in a consumer project.

## Purpose

The manifest declares what the consumer application exposes:

- Application metadata and redirect URIs.
- Fine-grained permissions.
- Roles that group those permissions for Minerva admins.

The consumer still validates only permissions with `require_permission(...)`.

## Shape

```yaml
application:
  code: portal_demo
  name: Portal Demo
  description: Sistema documental de ejemplo
  base_url: http://localhost:8000
  redirect_uris:
    - http://localhost:8000/auth/callback

permissions:
  - key: portal_demo.documents.view
    name: Ver documentos
    description: Permite consultar documentos
  - key: portal_demo.documents.create
    name: Crear documentos

roles:
  - name: Consulta
    description: Solo lectura
    permissions:
      - portal_demo.documents.view
  - name: Capturista
    permissions:
      - portal_demo.documents.view
      - portal_demo.documents.create
```

## Validation Rules

- `application.code` is required and must match `^[a-z0-9_]+$`.
- Permission keys must match `^[a-z0-9_]+\.[a-z0-9_]+\.[a-z0-9_]+$`.
- Every permission key must start with `{application.code}.`.
- Every permission referenced by a role must exist in the manifest.
- Redirect URIs are exact-match values; include one per environment.

Recommended actions:

```text
view, create, update, delete, assign, approve, authorize, export, import, manage
```

Prefer resource names that match domain concepts in the consumer project, for example:

```text
portal_demo.documents.view
portal_demo.documents.create
portal_demo.requests.assign
portal_demo.reports.export
```

## Import Behavior

Manual import: open **Applications → Import manifest** in the Minerva admin panel and
upload the YAML. The internal `/applications/import-manifest` route uses the panel's BFF
cookie session; there is no consumer Bearer endpoint at `/api/v1/manifests/import`.

Development auto-import:

- Minerva reads manifests from `MINERVA_MANIFESTS_PATH` when `MINERVA_AUTO_IMPORT_MANIFESTS=true`.
- Auto-imported file names match `*.minerva.yml`, `*.minerva.yaml`, `manifest.yml`, or `manifest.yaml`.

Import is idempotent:

- Existing application metadata is updated.
- New permissions and roles are added.
- Existing permissions/roles are updated by name/description where applicable.
- Nothing is deleted.
- A newly created confidential app returns `client_id` and `client_secret` once.
- Reimporting does not regenerate or re-expose secrets.

## Registering The Application

Confidential app through manifest:

- If `application.code` does not exist, manifest import creates the app and returns `client_id` and `client_secret`.
- Store the secret immediately outside the repo.

Public app:

- If the consumer is a SPA/mobile/public client and must not store a secret, register it through Minerva's application API or panel with `is_public: true`.
- Then import the manifest with the same `application.code` to upsert permissions and roles.
- Public clients must use PKCE.

Create the application and its exact redirect URIs in the admin panel. The `/applications`
routes are panel BFF routes authenticated by cookie, not public automation endpoints.

## Assigning Access

After import, a user still needs roles assigned in Minerva.

Use the panel or Dev Kit API:

```bash
curl -X POST http://localhost:9000/api/v1/access-assignments \
  -H "Authorization: Bearer <token>" \
  -H "Content-Type: application/json" \
  -d '{"user_id": "<user_id>", "role_id": "<role_id>"}'
```

To inspect effective permissions for the current token:

```bash
curl "http://localhost:9000/api/v1/me/permissions?application=portal_demo" \
  -H "Authorization: Bearer <access_token>"
```

## Review Checklist

- The manifest only declares one application's permissions.
- Permission keys use `{application_code}.{resource}.{action}`.
- Roles are named for administration convenience, not for application logic.
- The consumer code checks permissions with `require_permission`.
- `.env.example` includes Minerva URLs/client IDs but no real secrets.
- Redirect URIs match the consumer's actual callback paths and ports.
