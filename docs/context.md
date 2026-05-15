# Minerva - Contexto Completo del Proyecto

> Documento de referencia. Leerlo da el contexto completo del repo sin explorar el código.
>
> Última actualización: 2026-05-14

---

## 1. Qué es Minerva

Minerva es el **gestor de identidad y accesos (IAM/SSO) centralizado** del ecosistema
del Instituto de Información Estadística y Geográfica de Jalisco (IIEG). Está basado en
**Authentik**, un Identity Provider open-source.

El nombre viene de La Minerva, monumento icónico de Guadalajara — la diosa romana de la
sabiduría y la protección.

**Problema que resuelve:** hoy cada servicio del ecosistema maneja su propia
autenticación. MARIACHI se usa "temporalmente" como emisor de auth para varios
frontends. Servicios sin autenticador propio (la consola/Filer UI de Acervo) no se
pueden exponer. Minerva centraliza: un solo login, un solo lugar de gestión de usuarios,
MFA, y SSO para todo.

**Estado:** repo construido y listo. La conexión al ecosistema está pendiente hasta
después del lanzamiento LTS (ver `docs/pendientes/conexion-ecosistema.md`). El primer
servicio a proteger será la consola de Acervo.

**Repositorio:** `git@github.com:iieg-oficial/minerva.git`
**Licencia:** MIT - IIEG Jalisco

---

## 2. Plataforma: Authentik

Se eligió Authentik (sobre Keycloak y FreeIPA) por personalización de login más fácil,
OTP completo de fábrica (TOTP, SMS, email, FIDO2/WebAuthn), interfaz moderna y menor
consumo. Trade-off aceptado: menos años de escrutinio que Keycloak, suficiente para un
entorno institucional bien configurado. Detalle de la evaluación en
`gateway-hub/docs/minerva.md`.

Authentik soporta **OIDC/OAuth2, SAML, LDAP** y un modo **proxy/forward-auth** para
proteger apps que no tienen auth propia.

---

## 3. Estructura del Proyecto

```
minerva/
├── docker-compose.yml          # authentik server + worker + db + redis
├── .env.example                # plantilla de variables
├── Makefile                    # up/down/restart/logs/secrets + targets de prueba
├── blueprints/                 # configuración declarativa de Authentik
│   ├── 00-groups.yaml          # grupos RBAC del ecosistema
│   ├── 10-acervo-console.yaml  # proxy provider + app de la consola de Acervo
│   ├── 90-embedded-outpost.yaml# registra los proxy providers en el embedded outpost
│   └── stubs/                  # blueprints OIDC preparados (.yaml.example)
│       ├── geoserver-oidc.yaml.example
│       ├── grafana-oidc.yaml.example
│       ├── mariachi-oidc.yaml.example
│       ├── sieej-oidc.yaml.example
│       └── mapalab-oidc.yaml.example
├── gateway/                    # snippets de nginx para gateway-hub
│   ├── upstreams.conf
│   ├── minerva.locations.inc
│   ├── acervo-console.locations.inc
│   └── README.md
├── test/                       # ambiente de prueba local
│   ├── docker-compose.test.yml
│   ├── nginx-test.conf
│   ├── proxy-params.inc
│   └── README.md
└── docs/
    ├── context.md              # este archivo
    ├── integraciones.md        # cómo conectar cada servicio
    └── pendientes/
        └── conexion-ecosistema.md
```

---

## 4. Contenedores (docker-compose.yml)

| Servicio | Contenedor | Imagen | Función |
|----------|-----------|--------|---------|
| `server` | `minerva-server` | `ghcr.io/goauthentik/server` | API + UI + **embedded outpost** (forward auth) |
| `worker` | `minerva-worker` | `ghcr.io/goauthentik/server` (command: worker) | Tareas async, aplica blueprints |
| `db` | `minerva-db` | `postgres:16-alpine` | Base de datos de Authentik (dedicada, no compartida) |
| `redis` | `minerva-redis` | `redis:7-alpine` | Cache y colas |

**Redes:**
- `minerva-net` (interna, bridge) — comunicación entre los 4 contenedores.
- `iieg-network` (externa) — sólo `server` se une a ella, para que gateway-hub
  alcance el embedded outpost y la UI.

**Volúmenes:** `minerva_db`, `minerva_redis`, `minerva_media`, `minerva_templates`,
`minerva_certs`.

**Puerto:** `server` publica `127.0.0.1:9000` (sólo localhost de la VM, para acceso
directo/debug). El tráfico público entra por gateway-hub bajo `/auth/`.

**Blueprints:** `./blueprints` se monta read-only en `/blueprints/custom` de `server` y
`worker`. Authentik los descubre y aplica al arrancar.

---

## 5. Variables de Entorno

Ver `.env.example`. Las principales:

| Variable | Descripción |
|----------|-------------|
| `AUTHENTIK_VERSION` | Tag de la imagen de Authentik |
| `AUTHENTIK_SECRET_KEY` | Clave de cifrado de Authentik (`openssl rand -base64 60`) |
| `POSTGRES_DB` / `POSTGRES_USER` / `POSTGRES_PASSWORD` | Credenciales de `minerva-db` |
| `AUTHENTIK_BOOTSTRAP_EMAIL` / `_PASSWORD` / `_TOKEN` | Usuario admin inicial (sólo primer arranque) |
| `MINERVA_HTTP_PORT` | Puerto local (127.0.0.1) — default 9000 |
| `MINERVA_COOKIE_DOMAIN` | Dominio para el que Authentik emite cookies (el del gateway) |
| `MINERVA_EXTERNAL_URL` | URL externa del ecosistema — usada por los blueprints vía `!Env` |
| `ACERVO_CONSOLE_UPSTREAM` | Host:puerto del Filer UI de SeaweedFS |

`make secrets` genera los valores aleatorios.

---

## 6. Blueprints (configuración declarativa)

Toda la config de Authentik (grupos, providers, apps, outpost) vive como blueprints
YAML versionados — nada se configura a mano por la UI. Authentik los aplica al
arrancar; `make restart` re-aplica.

### Activos (`blueprints/*.yaml`)

- **`00-groups.yaml`** — grupos RBAC, espejo del modelo de MARIACHI:
  - Globales: `tetlamamakani` (admin global, superuser), `editora` (staff), `externo`.
  - Por proyecto: `proj-portal`, `proj-mapalab`, `proj-sieej`, `proj-acervo`,
    `proj-geoserver`, `proj-huachicol`.
- **`10-acervo-console.yaml`** — Proxy Provider (`forward_single`) + Application +
  policy bindings (sólo `tetlamamakani` y `proj-acervo` acceden).
- **`90-embedded-outpost.yaml`** — registra los proxy providers en el embedded outpost.
  **Cada proxy provider nuevo debe agregarse aquí.**

### Stubs (`blueprints/stubs/*.yaml.example`)

Blueprints OIDC preparados para GeoServer, Grafana, MARIACHI, SIEEJ y MapaLab. **No se
aplican** (Authentik sólo lee `.yaml`/`.yml`). Para activar uno: renombrar a `.yaml`,
ajustar la `redirect_uris`, `make restart`, y wire del `client_id`/`client_secret` en
el servicio. Ver `docs/integraciones.md`.

---

## 7. Modelo de protección

| Modo | Para | Cómo |
|------|------|------|
| **Forward auth** (proxy provider + embedded outpost) | Servicios SIN auth propia: consola de Acervo | gateway-hub hace `auth_request` al outpost en cada request; sin sesión → redirige al login |
| **OIDC** (oauth2 provider) | Servicios con auth propia o que soportan OIDC: GeoServer, Grafana, MARIACHI, SIEEJ, MapaLab | El servicio delega el login en Minerva y recibe un token con identidad + grupos |

El **embedded outpost** corre dentro de `minerva-server` y expone
`/outpost.goauthentik.io/` — no requiere un contenedor outpost aparte.

---

## 8. RBAC — espejo del modelo de MARIACHI

MARIACHI define hoy el RBAC del ecosistema (`mariachi/docs/ROLES.md`):

- Roles globales (`Usuario.role`): `tetlamamakani` (admin global IIEG), `editora`
  (staff), `externo` (dependencias / ciudadanos).
- Membership por proyecto (`UserProject`): `project_role` ∈ {`editor`, `viewer`}.

Minerva replica esto con **grupos**: los 3 roles globales + un grupo `proj-*` por
proyecto. Los grupos viajan en el claim `groups` del token OIDC. La distinción
`editor`/`viewer` se modelará (grupos hijos o atributos) cuando se integre MARIACHI.

Cuando MARIACHI migre a Minerva, dejará de emitir su JWT propio y pasará a validar el
token de Authentik, mapeando `groups` a su lógica `require_role` / `require_project_access`.

---

## 9. Ambiente de prueba

`test/` levanta un gateway nginx de prueba + una app dummy (`traefik/whoami`) que hace
de "consola de Acervo". Monta **los mismos snippets** de `gateway/` que se copiarán a
gateway-hub, así que valida el flujo de forward auth de punta a punta sin tocar el
ecosistema real. Ver `test/README.md`.

---

## 10. Integración con el ecosistema (pendiente)

No se toca ningún otro repo hasta después del lanzamiento LTS. Todo lo necesario ya
está en este repo:

- **gateway-hub:** snippets listos en `gateway/` (siguen la convención
  `conf.d/*.conf` + `includes/*.inc` de gateway-hub).
- **Cada servicio:** blueprint stub + guía en `docs/integraciones.md`.
- **Checklist completo:** `docs/pendientes/conexion-ecosistema.md`.

Minerva está diseñado para encajar en la arquitectura actual (`iieg-network`, ruteo por
path en gateway-hub, convención de contenedores `minerva-*`) — integrarlo es copiar
config y wire de credenciales, sin rediseño.

### Caveat conocido: Authentik bajo subpath

Authentik está pensado para su propio (sub)dominio. Hoy no hay: el wildcard
`*.jalisco.gob.mx` no cubre `auth.iieg.jalisco.gob.mx` y no se controla el DNS estatal.
La opción actual es servir bajo `/auth/`; validar en el primer despliegue. El forward
auth (`/outpost.goauthentik.io/` + `auth_request`) no depende del subpath.

---

## 11. Despliegue

- Corre en **S1**, junto a gateway-hub (forward auth de baja latencia). Consumo
  estimado: ~1.5 GB RAM.
- Workflow estándar del ecosistema:
  ```bash
  cd /IIEG/minerva && git pull && make up
  ```
- En la VM de producción sólo se ejecuta (`git pull`, docker, logs); no se edita código.
