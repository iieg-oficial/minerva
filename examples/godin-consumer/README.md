# Godín (ejemplo de integración OIDC con Minerva)

Sistema consumidor mínimo que se integra con Minerva como **cliente público**
(sin `client_secret`): Authorization Code + PKCE, `minerva_sdk` para validar el
access token (RS256/JWKS) y `require_permission` para proteger un endpoint. Ver
`docs/integracion.md` para el contrato completo y `docs/arquitectura.md`
para la visión general del sistema.

## 1. Levantar Minerva

```bash
cd ../..               # raíz del repo
docker compose up --build
```

Backend en `http://localhost:9000`, panel admin en `http://localhost:3000`.

## 2. Registrar la aplicación "Godín" como cliente público

Con sesión de administrador (Bearer del login del panel):

```bash
curl -X POST http://localhost:9000/applications \
  -H "Authorization: Bearer <admin_token>" \
  -H "Content-Type: application/json" \
  -d '{"name": "Godín", "slug": "godin", "is_public": true}'
```

La respuesta trae `client_id` (y `client_secret_hash: null`, porque es público —
no hay secret que mostrar). Regístra la redirect URI exacta:

```bash
curl -X POST http://localhost:9000/applications/{application_id}/redirect-uris \
  -H "Authorization: Bearer <admin_token>" \
  -H "Content-Type: application/json" \
  -d '{"uri": "http://localhost:8100/callback", "environment": "development"}'
```

Importa permisos/roles con el manifiesto de ejemplo (`manifests/godin.minerva.yml`
si existe en el repo, o crea los permisos `godin.oficios.*` desde el panel) y
asígnate un rol con `godin.oficios.create` desde el panel admin para poder probar
`/protegido`.

## 3. Configurar y correr este ejemplo

```bash
cp .env.example .env
# completa MINERVA_CLIENT_ID con el client_id devuelto en el paso 2
pip install -e ../../sdk -e .
uvicorn app.main:app --port 8100 --reload
```

## 4. Flujo de prueba manual

1. Abre `http://localhost:8100/login` en el navegador — redirige a Minerva.
2. Inicia sesión en Minerva (usuario con el rol asignado en el paso 2).
3. Minerva redirige a `http://localhost:8100/callback?code=...&state=...`, que
   muestra el JSON con `access_token`/`id_token`/`refresh_token` (sin haber
   mandado `client_secret`: el canje se validó solo con PKCE).
4. Copia el `access_token` y pruébalo:

   ```bash
   curl http://localhost:8100/whoami -H "Authorization: Bearer <access_token>"
   curl http://localhost:9000/userinfo -H "Authorization: Bearer <access_token>"
   curl http://localhost:8100/protegido -H "Authorization: Bearer <access_token>"
   ```

   `/protegido` responde `200` si el usuario tiene `godin.oficios.create`, `403`
   si no — la validación es en tiempo real contra Minerva, no por rol local.

## Notas

- Este ejemplo no implementa sesión/cookie (los tokens se devuelven crudos en
  `/callback` solo para la demo). Un consumidor real los guarda en la sesión del
  usuario, igual que describe `docs/integracion.md` sección 3.
- `_pkce_store` es un dict en memoria de un solo proceso — válido para la demo,
  no para producción (usar la sesión del usuario, como cualquier estado de OAuth).
