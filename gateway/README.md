# Snippets de gateway-hub para Minerva

Configuración de nginx **lista para copiar a `gateway-hub`** cuando se integre Minerva.
No se aplica nada todavía — el ecosistema no se toca hasta después del lanzamiento LTS
(ver `../docs/pendientes/conexion-ecosistema.md`).

Estos archivos siguen las convenciones de `gateway-hub` (`nginx/conf.d/*.conf`,
`nginx/includes/*.inc`), así que integrarlos es copiar + incluir, sin rediseño.

| Archivo | Destino en gateway-hub | Qué hace |
|---|---|---|
| `upstreams.conf` | `nginx/conf.d/minerva-upstreams.conf` | Define los upstreams `minerva` y `acervo_console` |
| `minerva.locations.inc` | `nginx/includes/minerva.locations.inc` | Rutas `/auth/` y `/outpost.goauthentik.io/` |
| `acervo-console.locations.inc` | `nginx/includes/acervo-console.locations.inc` | Ruta `/acervo/console/` protegida por forward auth |

## Pasos de integración (resumen)

1. Copiar los 3 archivos a sus destinos en `gateway-hub`.
2. En `gateway.conf.template`, dentro del `server { listen 443 ... }`, agregar:
   ```nginx
   include /etc/nginx/includes/minerva.locations.inc;
   include /etc/nginx/includes/acervo-console.locations.inc;
   ```
3. Copiar los `.inc` en el `Dockerfile` de gateway-hub (ya lo hace con `COPY nginx/includes/`).
4. `docker compose build nginx && make restart` en gateway-hub.

Pasos detallados, variables de entorno y validación del subpath `/auth/`:
`../docs/pendientes/conexion-ecosistema.md`.
