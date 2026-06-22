# OIDC en Minerva — trabajo pendiente

Estado al 2026-06: el **núcleo OIDC está implementado** (Authorization Code + PKCE,
discovery, JWKS, `id_token`/`access_token` RS256, refresh tokens con rotación y
revocación, SDK RS256/JWKS async). Ver `docs/oidc-integracion.md`.

Este documento lista lo que **falta** para completar la conformidad OIDC y dejar el
proveedor listo para producción plena. Sirve de base para el issue de seguimiento.
La **integración de Google como IdP entrante se rastrea en un issue aparte** y no se
incluye aquí.

---

## 1. Conformidad OIDC pendiente

### UserInfo + mapeo scope → claims
- `GET /userinfo` (Bearer RS256, CORS abierto) que devuelva claims filtrados por scope.
- Helper `claims_for_scopes(user, scopes)` en `oidc/service.py`
  (`openid` → `sub`; `profile` → `name`, `preferred_username`; `email` → `email`,
  `email_verified = auth_provider == "google"`).
- **Brecha relacionada:** hoy los scopes se aceptan pero **no filtran los claims** del
  `id_token` (siempre incluye `email`/`name`). Al implementar el helper, aplicarlo
  también a la emisión del `id_token`.

### Clientes públicos (SPA / móvil sin `client_secret`)
- Soportar `token_endpoint_auth_method=none`: PKCE **obligatorio** y sin `client_secret`
  cuando `application.client_secret_hash is null`.
- Anunciar `"none"` en `token_endpoint_auth_methods_supported` del discovery.

### `prompt` y `max_age`
- `prompt=none` → `login_required` si no hay sesión; `prompt=login` → forzar re-auth;
  `max_age=N` → re-auth si `now - auth_time > N` (el `auth_time` ya se persiste).

### Modo B — clientes externos sin sesión previa
- Hoy `/authorize` exige Bearer (Modo A: SPA con sesión en Minerva). Para plataformas
  externas (Nextcloud, Gitea, otros sistemas de gobierno) que inician el flujo sin
  sesión: redirigir a login con el estado del `/authorize` guardado en Redis
  (`minerva:authorize_session:{id}`, TTL 600 s) y continuar tras el login.
- **Cruza al frontend** (la UI de login debe retomar el `authorize` pendiente).

---

## 2. Cierre (Fase 8)

> HS256 fue **eliminado por completo** (todo es RS256): no hay flags de legacy ni
> plan de deprecación que documentar.

- `examples/godin-consumer/`: ejemplo mínimo de consumidor con el SDK actualizado
  (RS256, PKCE, refresh) — referenciado en `CLAUDE.md` pero ausente.
- README raíz con el flujo OIDC completo.
- Limpiar stubs/TODOs resueltos.

---

## 3. Endurecimiento para producción (no es código de feature)

- **TLS/HTTPS** extremo a extremo; el issuer del discovery debe coincidir con la URL
  pública.
- **`MINERVA_KEY_ENCRYPTION_KEY`** desde un secret manager (obligatoria en prod; en dev
  se deriva del secreto JWT).
- Config endurecida: `MINERVA_MODE=production`, `MINERVA_ENABLE_DEV_LOGIN=false`,
  `ADMIN_PASSWORD` real.
- **Rotación de claves** operacionalizada (cron/runbook; `rotate_key()` ya existe) con
  ventana de solapamiento.
- Observabilidad (logs sin secretos, métricas de login/rate-limit), backups de
  PostgreSQL (incluye `signing_keys`), y decisión sobre persistencia/HA de Redis
  (la blacklist vive ahí).

---

## 4. Mejoras menores

- Cachear el JWKS en `get_current_user` (hoy construye el JWKS desde BD por request).
- Unificar/expandir tests OIDC bajo una convención común (hoy repartidos en
  `test_discovery`, `test_pkce`, `test_token`, `test_refresh`, `test_rs256_auth`,
  `test_signing_keys`).
