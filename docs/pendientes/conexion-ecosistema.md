# Pendiente: conexión de Minerva al ecosistema IIEG

> Estado: **Minerva está construido y listo**. La conexión al ecosistema queda
> pendiente hasta después del lanzamiento LTS — no se tocan los demás repos por ahora.
>
> Este documento es el checklist para cuando se retome. Todo lo necesario ya vive
> en este repo (`blueprints/`, `gateway/`, `test/`); integrar = copiar config y
> wire de credenciales, **sin cambios de arquitectura**.

---

## 0. Orden recomendado

1. Validar Minerva en aislado con el ambiente de prueba (`test/`) — **ya se puede hacer hoy**.
2. Conectar gateway-hub (rutas `/auth/` y `/outpost.goauthentik.io/`).
3. Conectar la consola de Acervo (primer servicio real protegido).
4. Conectar el resto por OIDC, uno por uno (geoserver, grafana, mariachi, sieej, mapalab).

---

## 1. gateway-hub

Cambios en el repo `gateway-hub` (rama `develop`):

1. Copiar los snippets de `minerva/gateway/` (ver `minerva/gateway/README.md`):
   - `upstreams.conf` → `nginx/conf.d/minerva-upstreams.conf`
   - `minerva.locations.inc` → `nginx/includes/minerva.locations.inc`
   - `acervo-console.locations.inc` → `nginx/includes/acervo-console.locations.inc`
2. En `nginx/templates/gateway.conf.template`, dentro del `server { listen 443 ... }`:
   ```nginx
   include /etc/nginx/includes/minerva.locations.inc;
   include /etc/nginx/includes/acervo-console.locations.inc;
   ```
3. El `Dockerfile` ya hace `COPY nginx/includes/` y `COPY nginx/conf.d/`; no requiere
   cambios salvo que se quiera parametrizar algún host con `envsubst` (no hace falta:
   los upstreams usan nombres de contenedor de `iieg-network`).
4. `nginx/conf.d/minerva-upstreams.conf` **no es un `.template`** — no pasa por
   `envsubst`. Si se prefiere parametrizar, renombrar a `.conf.template` y añadir
   las variables al `CMD` del Dockerfile.
5. Actualizar la doc de gateway-hub: `docs/context.md` (enrutamiento), `README.md`,
   `docs/CHANGELOG.md`, `docs/arquitectura.mmd` (agregar Minerva en S1).
6. `docker compose build nginx && make restart`.

### Caveat: Authentik bajo subpath `/auth/`

Authentik está pensado para correr en su propio (sub)dominio. Hoy no es posible:
el wildcard `*.jalisco.gob.mx` no cubre `auth.iieg.jalisco.gob.mx` y no controlamos
el DNS estatal (ver `gateway-hub/docs/minerva.md` §4 y §7).

- **Opción actual:** servir bajo `/auth/` (el snippet `minerva.locations.inc` ya lo
  hace). Validar en el primer despliegue que los assets, los flows y el panel de
  admin del IdP cargan bien bajo el prefijo. Si rompen rutas absolutas, evaluar
  `sub_filter` o variables de Authentik para el path base.
- **Opción ideal:** gestionar `auth.iieg.jalisco.gob.mx` (o `auth.jalisco.gob.mx`)
  con su cert. Si se consigue, sólo cambia el `server_name`/`proxy_pass`; el resto
  de Minerva (blueprints, outpost) no cambia.

El endpoint `/outpost.goauthentik.io/` y el `auth_request` **no** dependen del
subpath y funcionan en ambos casos.

---

## 2. Consola de Acervo (primer servicio real)

Ya está todo del lado de Minerva: `blueprints/10-acervo-console.yaml` (proxy
provider + application + policy bindings) y `blueprints/90-embedded-outpost.yaml`
(registro en el outpost). El snippet `gateway/acervo-console.locations.inc` cablea
`/acervo/console/`.

Pendiente al conectar:

1. Confirmar que el Filer UI de SeaweedFS está escuchando en `acervo-seaweedfs:8888`
   dentro de `iieg-network` (el repo `acervo` corre `weed server` con filer por
   defecto; el puerto 8888 no se publica al host pero sí es alcanzable en la red).
2. **Subpath del Filer UI:** SeaweedFS sirve el UI con rutas de assets absolutas.
   Bajo el prefijo `/acervo/console/` podrían romperse. Mismo problema que tenía la
   vieja consola de MinIO (que se resolvía con `sub_filter`). Validar y, si hace
   falta, añadir el `sub_filter` correspondiente en `acervo-console.locations.inc`.
3. Crear un usuario de prueba en Minerva y meterlo al grupo `proj-acervo` (o
   `tetlamamakani`); verificar que sin grupo Authentik niega el acceso.
4. No se toca el repo `acervo`: el filer ya expone el puerto en la red interna.

---

## 3. Integración por OIDC del resto del ecosistema

Para cada servicio hay un blueprint stub en `blueprints/stubs/*.yaml.example`.
El procedimiento es el mismo para todos:

1. Renombrar el stub a `.yaml` (p.ej. `geoserver-oidc.yaml.example` → `geoserver-oidc.yaml`).
2. Ajustar la `redirect_uris` del blueprint a la URL real que espera el servicio.
3. `make restart` para que Authentik aplique el blueprint y cree el provider.
4. En Authentik (`Applications → Providers`), copiar el `client_id` y `client_secret`
   generados.
5. Configurar el servicio con esas credenciales (ver detalle abajo).
6. Asignar usuarios a los grupos correspondientes (`proj-*`, `editora`, etc.).

> El detalle de configuración por servicio está en `docs/integraciones.md`.

| Servicio | Stub | Tipo | Notas de conexión |
|---|---|---|---|
| GeoServer | `geoserver-oidc.yaml.example` | OIDC | Plugin `geoserver-sec-oauth2-openid`. Sustituye/coexiste con la auth propia del admin. |
| Grafana (Huachicol) | `grafana-oidc.yaml.example` | OIDC | `auth.generic_oauth` en `grafana.ini`/env. Elimina el `nginx-auth` con basic auth (ver `huachicol/docs/pendientes/authentik.md`). |
| MARIACHI | `mariachi-oidc.yaml.example` | OIDC | Hoy emite su propia auth (cookies + CSRF). Migrar `mariachi-api` a validar tokens OIDC y mapear claims de grupo a su RBAC. Es el cambio más grande. |
| SIEEJ | `sieej-oidc.yaml.example` | OIDC | Backend en `mariachi/api`. Admite el rol `externo`. |
| MapaLab | `mapalab-oidc.yaml.example` | OIDC | Sólo para features autenticadas futuras; el visor público sigue anónimo. |

### Migración de la lógica de negocio de MARIACHI

MARIACHI es hoy el emisor de auth "temporal" del ecosistema. Su RBAC
(`tetlamamakani` / `editora` / `externo` + `UserProject` con `editor`/`viewer`)
ya está reflejado en los grupos de Minerva (`blueprints/00-groups.yaml`).

Al migrar:
- Los grupos globales (`tetlamamakani`, `editora`, `externo`) y por proyecto
  (`proj-*`) viajan en el claim `groups` del token OIDC.
- `mariachi-api` deja de emitir su JWT propio y pasa a validar el token de
  Authentik, mapeando `groups` → su lógica de `require_role` / `require_project_access`.
- La distinción `editor`/`viewer` por proyecto se puede modelar con grupos hijos
  (`proj-mapalab-editor` / `proj-mapalab-viewer`) o con atributos de grupo —
  decidir al integrar MARIACHI.
- La cookie compartida entre subdominios (`COOKIE_DOMAIN`) la reemplaza la sesión
  de Authentik (`AUTHENTIK_COOKIE_DOMAIN`).

---

## 4. Recursos / despliegue

- Minerva corre en **S1**, junto a gateway-hub (forward auth de baja latencia).
  S1 tiene holgura (15 GB RAM, ~525 MB en uso). Authentik + Postgres + Redis
  consumen ~1.5 GB.
- Actualizar `gateway-hub/docs/recursos-servidores.md` con los contenedores
  `minerva-server`, `minerva-worker`, `minerva-db`, `minerva-redis` en S1.
- Workflow de despliegue (igual que el resto del ecosistema):
  ```bash
  cd /IIEG/minerva && git pull && make up
  ```
