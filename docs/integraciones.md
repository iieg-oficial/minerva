# Integraciones — cómo conectar cada servicio a Minerva

Guía por servicio. Nada de esto se aplica todavía (ver
`pendientes/conexion-ecosistema.md`); es la referencia para cuando se retome.

Dos modelos:
- **Forward auth** — para servicios sin auth propia (consola de Acervo).
- **OIDC** — para servicios con auth propia o que soportan OpenID Connect.

---

## Procedimiento general (OIDC)

1. Renombrar el stub: `blueprints/stubs/<servicio>-oidc.yaml.example` → `blueprints/<servicio>-oidc.yaml`.
2. Ajustar `redirect_uris` en el blueprint a la URL real que espera el servicio.
3. `make restart` — Authentik aplica el blueprint y crea el provider.
4. En la UI de Authentik (`Applications → Providers → <servicio>`), copiar el
   `Client ID` y `Client Secret` generados.
5. Configurar el servicio con esas credenciales (secciones de abajo).
6. Asignar usuarios a los grupos correspondientes (`Directory → Groups`).

**Endpoints OIDC de Minerva** (sustituir `<MINERVA_EXTERNAL_URL>`):
- Issuer / discovery: `<MINERVA_EXTERNAL_URL>/auth/application/o/<app-slug>/.well-known/openid-configuration`
- Authorization: `<MINERVA_EXTERNAL_URL>/auth/application/o/authorize/`
- Token: `<MINERVA_EXTERNAL_URL>/auth/application/o/token/`
- Userinfo: `<MINERVA_EXTERNAL_URL>/auth/application/o/userinfo/`
- JWKS: `<MINERVA_EXTERNAL_URL>/auth/application/o/<app-slug>/jwks/`

> Las rutas asumen Authentik bajo `/auth/`. Si se migra a un subdominio dedicado,
> cambian sólo el host.

---

## Acervo — consola (forward auth)

**No usa OIDC.** Es el caso de forward auth ya cableado del lado de Minerva:
`blueprints/10-acervo-console.yaml` + `blueprints/90-embedded-outpost.yaml`.

Conexión (en gateway-hub, ver `gateway/README.md`):
- Copiar `gateway/upstreams.conf`, `minerva.locations.inc`, `acervo-console.locations.inc`.
- Incluir los `.inc` en el `server :443` de `gateway.conf.template`.

No se toca el repo `acervo`: el Filer UI de SeaweedFS ya escucha en
`acervo-seaweedfs:8888` dentro de `iieg-network`.

Pendiente al conectar: validar el subpath del Filer UI (assets absolutos — puede
requerir `sub_filter`, igual que la vieja consola de MinIO).

Acceso: grupos `tetlamamakani` y `proj-acervo`.

---

## GeoServer — OIDC

Plugin: `geoserver-sec-oauth2-openid` (ya contemplado en el repo `geoserver`).

En GeoServer (`Security → Authentication → Authentication Providers → OpenID Connect`):

| Campo | Valor |
|---|---|
| Client ID / Secret | los del provider `GeoServer` en Authentik |
| Discovery URL | `<MINERVA_EXTERNAL_URL>/auth/application/o/geoserver/.well-known/openid-configuration` |
| Scopes | `openid email profile` |
| Redirect URI | `<MINERVA_EXTERNAL_URL>/geoserver/web/login/oauth2/code/oidc` |
| Role source | claim `groups` del token |

Mapear el grupo `tetlamamakani` → rol `ADMIN` de GeoServer. La auth propia del admin
puede coexistir como fallback durante la transición.

Acceso: `tetlamamakani`, `proj-geoserver`.

---

## Grafana (Huachicol) — OIDC

Config `auth.generic_oauth` (en `grafana.ini` o env `GF_AUTH_GENERIC_OAUTH_*`):

```ini
[auth.generic_oauth]
enabled = true
name = Minerva
client_id = <client_id del provider Grafana>
client_secret = <client_secret>
scopes = openid email profile
auth_url = <MINERVA_EXTERNAL_URL>/auth/application/o/authorize/
token_url = <MINERVA_EXTERNAL_URL>/auth/application/o/token/
api_url = <MINERVA_EXTERNAL_URL>/auth/application/o/userinfo/
role_attribute_path = contains(groups, 'tetlamamakani') && 'Admin' || 'Viewer'
```

Al integrar: **eliminar el `nginx-auth`** (basic auth) de Huachicol y sus variables
`MONITORING_AUTH_USER`/`MONITORING_AUTH_PASSWORD` — ver
`huachicol/docs/pendientes/authentik.md`.

Acceso: `tetlamamakani`, `proj-huachicol`.

---

## MARIACHI — OIDC (migración de la auth temporal)

Es el cambio más grande: MARIACHI hoy **es** el emisor de auth del ecosistema
(cookies HttpOnly + CSRF + JWT propio, ver `mariachi/docs/COOKIES_CSRF.md`).

Al migrar, `mariachi-api`:
1. Deja de emitir su JWT propio; añade un callback OIDC
   (`<MINERVA_EXTERNAL_URL>/administrador/auth/callback`, ajustar al real).
2. Valida el token de Authentik y lee el claim `groups`.
3. Mapea `groups` a su RBAC existente: `require_role` (global) y
   `require_project_access` (por proyecto). Los grupos de Minerva ya están nombrados
   igual que los roles de MARIACHI.
4. La cookie compartida entre subdominios la reemplaza la sesión de Authentik.

Acceso: sólo staff — `tetlamamakani`, `editora`. El rol `externo` no entra al CMS.

---

## SIEEJ — OIDC

Frontend estático (servido por gateway-hub); backend en `mariachi/api`. La integración
OIDC vive en el backend de SIEEJ dentro de `mariachi/api`.

Redirect URI: `<MINERVA_EXTERNAL_URL>/sieej/auth/callback` (ajustar al real).

Acceso: `tetlamamakani`, `editora` y `proj-sieej` — SIEEJ **sí** admite el rol
`externo` (las dependencias de gobierno capturan datos ahí).

---

## MapaLab — OIDC

El visor público sigue siendo **anónimo**. Esta integración OIDC es sólo para features
autenticadas futuras (preview/admin embebido).

Redirect URI: `<MINERVA_EXTERNAL_URL>/mapalab/auth/callback` (ajustar al real).

Acceso: `tetlamamakani`, `proj-mapalab`.
