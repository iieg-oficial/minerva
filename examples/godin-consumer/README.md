# Ejemplo: Godín como consumidor de Minerva

Demuestra cómo un sistema valida permisos contra Minerva Dev Kit usando el SDK.

## Pasos

1. Levanta Minerva Dev Kit desde la raíz del repo:

   ```bash
   docker compose up --build
   ```

   Esto importa automáticamente `manifests/manifest.minerva.yml` (aplicación `godin`).

2. Instala dependencias del ejemplo y el SDK:

   ```bash
   cd examples/godin-consumer
   pip install -r requirements.txt
   pip install -e ../../sdk
   ```

3. Configura y arranca el consumidor:

   ```bash
   export MINERVA_ISSUER_URL=http://localhost:9000
   export MINERVA_APPLICATION_CODE=godin
   export MINERVA_JWT_SECRET=dev-secret
   uvicorn main:app --reload --port 8000
   ```

4. Obtén un token de desarrollo desde Minerva:

   ```bash
   curl -s -X POST http://localhost:9000/api/v1/auth/dev-login \
     -H 'Content-Type: application/json' \
     -d '{"email":"admin@local.dev"}'
   ```

5. Llama al consumidor con el token:

   ```bash
   TOKEN=...   # access_token del paso anterior
   curl -s http://localhost:8000/whoami -H "Authorization: Bearer $TOKEN"
   curl -s http://localhost:8000/oficios -H "Authorization: Bearer $TOKEN"
   ```

   Si el usuario no tiene asignado un rol de Godín con el permiso requerido,
   recibirás `403`. Asígnale un rol desde el panel o vía API
   (`POST /api/v1/access-assignments`) y vuelve a intentar.
