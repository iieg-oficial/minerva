# Auditoría independiente de Minerva — preparación para 1.0.0

**Fecha:** 2026-07-22 · **Rama auditada:** `chore/mypy-ci-gate` (HEAD `e57b5e5`) ·
**Versión declarada:** `backend/pyproject.toml` = 0.3.4 · **Alcance:** backend, frontend,
SDK, ejemplos, manifiestos, pruebas, infraestructura, despliegue, documentación y
preparación open source.

> Auditoría nueva e independiente: el diagnóstico parte del código realmente implementado,
> no de conclusiones ni documentación previas. Las auditorías/PR anteriores se contrastan
> solo al final (§8). **No se modificó código durante la auditoría.**

---

## 1. Resumen ejecutivo

Minerva es un proveedor de identidad OIDC/OAuth 2.0 **real y bien construido**, no un
esqueleto. El núcleo criptográfico y de protocolo está resuelto con cuidado poco común
para un proyecto institucional: firma RS256 con rotación de claves en dos fases
(*publish-before-use*), PKCE obligatorio para clientes públicos, rotación de refresh
tokens con detección de reúso y revocación de familia, segregación de tokens por `typ`,
sesión de panel BFF (cookie opaca + Redis) con CSRF, y una política *fail-closed* de
revocación con orden de commit Redis→PostgreSQL. Las 185 pruebas pasan (198 con las de
PostgreSQL real), ruff/mypy/build limpios.

**Qué tan cerca está de 1.0.0:** cerca. No hay fallas catastróficas en el motor OAuth/OIDC.
Lo que separa a Minerva de una publicación segura y honesta es un conjunto **pequeño y
acotado**: dos correcciones de comportamiento/contrato (un open redirect en logout y una
documentación de logout de consumidor que describe un flujo que no existe), la ausencia de
archivos legales de open source (LICENSE), y limpieza de inconsistencias de versión y
documentación desfasada.

**Veredicto:** el camino a 1.0.0 es corto y de bajo riesgo. La mayor parte del trabajo
pendiente es Verde (documentación/OSS) y Amarillo (mejoras no-rompientes). Solo dos
hallazgos Rojos bloquean, y ambos son de superficie reducida.

| Semáforo | Cuenta | Bloquean 1.0.0 |
|---|---|---|
| 🔴 Rojo | 2 | 2 |
| 🟡 Amarillo | 7 | 0 (recomendados) |
| 🟢 Verde | 6 | 1 (LICENSE) |

---

## 2. Qué hace realmente Minerva hoy

- **IdP OIDC/OAuth 2.0** con *Authorization Code + PKCE*. Endpoints: `/auth/authorize`,
  `/auth/token` (authorization_code y refresh_token), `/auth/revoke` (RFC 7009),
  `/.well-known/openid-configuration`, `/.well-known/jwks.json`, `/userinfo`.
- **Firma exclusivamente RS256/JWKS** (no hay HS256). Clave privada RSA-2048 cifrada en
  reposo con Fernet (`signing_keys.private_key_pem`). Rotación en dos fases vía
  `python -m app.cli rotate-key` / `promote-key`.
- **Modelo de permisos declarativo** `{app}.{recurso}.{accion}`: los sistemas declaran
  permisos/roles en `manifest.minerva.yml`; Minerva administra quién los tiene (roles
  directos + grupos); el consumidor valida con `require_permission`, nunca por rol local.
- **Panel admin** (React 19 + Ant Design 6): CRUD de usuarios, aplicaciones, roles,
  permisos, grupos, auditoría, import de manifiestos, branding de login por app.
- **Dos modelos de sesión deliberadamente distintos:** consumidores OIDC *stateless*
  (Bearer); panel admin *stateful* BFF (cookie opaca `__Host-minerva_sid` + contenedor
  multi-cuenta en Redis, CSRF synchronizer + validación de Origin). Selector multi-cuenta.
- **SDK `minerva_sdk`** para consumidores FastAPI: `get_current_user` (valida RS256 contra
  JWKS, fija `alg`, verifica `aud`/`iss`/`typ`) y `require_permission` (consulta
  `/api/v1/me/permissions` en tiempo real; revocación inmediata por defecto).
- **Revocación e invalidación:** blacklist de `jti` en Redis, cortes por usuario
  (`iat`) al cambiar credenciales/status, revocación de familia de refresh tokens.
- **Infra:** Docker Compose (dev y deploy por imágenes ghcr), nginx consolidado como único
  punto público, Redis con AOF + `noeviction`, PostgreSQL 16, migraciones Alembic
  automáticas al arrancar.

---

## 3. Áreas correctamente resueltas — **NO tocar antes de 1.0.0**

Estas decisiones protegen una frontera real de seguridad o compatibilidad. Aunque algunas
parezcan complejas, la complejidad está justificada; simplificarlas introduciría riesgo.

| Área | Evidencia | Por qué conservarla |
|---|---|---|
| RS256-only + fijación de `alg` en el SDK | `sdk/minerva_sdk/fastapi.py:74`; `security.py`; `dependencies/auth.py` | Evita ataques de confusión de algoritmo (RFC 8725). Un solo mecanismo de firma. |
| PKCE obligatorio para clientes públicos | `auth/service.py:277,325`; `authorize`/`exchange_token` | Liga el código al solicitante legítimo; se rechaza `plain`. |
| Rotación de refresh + detección de reúso + revocación de familia | `auth/service.py:442-533`; `auth/repository.py:111-170` | `FOR UPDATE NOWAIT` distingue contención (409, reintento) de reúso (robo → revoca familia). Correcto y probado (`test_refresh_race_pg.py`). |
| Rotación de claves en dos fases (*publish-before-use*) | `oidc/service.py:124-178`; índices únicos parciales (migración 009) | Firmar con clave recién creada cortaría el servicio; publicar-antes-de-usar lo evita. Invariante en la BD, no solo en el código. |
| Orden *fail-closed* Redis→PostgreSQL | `auth/router.py:406-421`; `users/router.py:38-47` | La revocación se escribe en Redis antes de confirmar PG; si Redis falla, rollback. Nunca queda un cambio de credenciales durable sin su invalidación. |
| Sesión de panel BFF (cookie opaca + Redis) | `core/panel_session.py`; `core/csrf.py`; `dependencies/auth.py:145-198` | El navegador nunca ve el JWT. `sid` de 256 bits, hasheado en Redis, rotado en cada login (anti-fijación). CSRF synchronizer + Origin. |
| Segregación de tokens por `typ` | `dependencies/auth.py:100-135`; `_resolve_token` | Un access de consumidor no vale en el panel ni viceversa (cierra R2 de auditorías previas). |
| Allowlist exacta de `redirect_uri` en `/authorize` | `auth/service.py:201-213`; validado **antes** de cualquier redirect | Evita open redirect en el flujo OAuth (contrasta con R1, ver §4). |
| `build_callback_url` preserva `state` byte-for-byte y limpia params de protocolo | `auth/service.py:54-73` | Defensa anti-CSRF del cliente intacta; no duplica `code`/`state`. |
| Cifrado Fernet de la clave privada en reposo | `core/crypto.py`; obligatorio en prod (`config.py:152`) | La clave que firma todos los tokens nunca se persiste en claro. |
| Trigger cross-app rol↔permiso (defensa en profundidad) | migración `007_role_permissions_cross_app.py` | La BD rechaza vínculos cruzados aunque se salte la capa de app. |
| `validate_production_config` fail-fast | `core/config.py:137-159` | Aborta el arranque si quedaron valores de dev (password default, dev-login, sin Fernet key). |

---

## 4. 🔴 Rojo — bloquean 1.0.0

### R1 · Open redirect en la página de logout del panel

- **Archivo/línea:** `frontend/src/features/auth/pages/LogoutPage.jsx:24-32`.
- **Comportamiento actual:** tras el logout, si el query param `redirect_uri` empieza con
  `http(s)://`, se hace `window.location.href = redirect` **sin validar el destino contra
  la allowlist de redirect URIs registradas**.
- **Impacto real:** vector de phishing. Un atacante distribuye
  `https://minerva.<dominio>/logout?redirect_uri=https://sitio-falso.example`; la víctima
  confía en el dominio de Minerva, se desloguea y termina en un sitio controlado por el
  atacante (p. ej. una pantalla de "vuelve a iniciar sesión" falsa). Es exactamente la
  clase de open redirect que el flujo `/authorize` sí evita con allowlist — la
  inconsistencia es el problema.
- **Reproducción:** navegar a `/logout?redirect_uri=https://example.org` con sesión
  activa → redirección a `example.org`.
- **Corrección mínima sugerida:** validar el `redirect_uri` contra las URIs registradas
  antes de redirigir (idealmente un endpoint que confirme la pertenencia), o restringir a
  destinos del mismo origen / a una allowlist explícita de `post_logout_redirect_uris` por
  aplicación (patrón OIDC RP-Initiated Logout). Como mínimo inmediato: aceptar solo rutas
  relativas del propio panel salvo que el destino esté registrado.
- **Riesgo de compatibilidad:** bajo. Los consumidores que hoy dependen de redirección
  externa tras logout tendrían que registrar su URI (cambio de configuración, no de código).
- **Prueba:** test e2e/unit que verifique que un `redirect_uri` no registrado cae a
  `/login` en vez de navegar fuera.
- **Referencias:** OWASP Unvalidated Redirects and Forwards; OpenID Connect RP-Initiated
  Logout 1.0 §2 (`post_logout_redirect_uri` debe estar registrado).
- **¿Bloquea 1.0.0?** **Sí.**

### R2 · La documentación de "logout de Minerva" para consumidores describe un flujo inexistente

- **Archivo/línea:** `docs/integracion.md:178-180`. Dice: *"`POST /auth/logout` (con el
  `access_token` en el header) revoca el token del lado del servidor"*.
- **Comportamiento real:** `POST /auth/logout` (`backend/app/modules/auth/router.py:201-221`)
  depende de `get_panel_session` (**cookie** de panel), **no** lee ningún Bearer, y es un
  *soft logout* que **no revoca** nada (solo desactiva la cuenta activa del contenedor).
  Un consumidor que siga la doc y llame con `Authorization: Bearer <access_token>` recibe
  **401** (no hay cookie). Verificado en pruebas de esta auditoría.
- **Impacto real:** el "single logout" server-side que promete la guía de integración no
  existe por esa vía. Un integrador confía en que cerró la sesión de Minerva cuando no lo
  hizo. Los mecanismos reales de terminación son: la página de navegador `/logout`
  (frontend, ver R1) y `/auth/revoke` (revoca el refresh token, RFC 7009). El `access_token`
  ya emitido sigue válido por firma hasta su `exp` (≤15 min) en cualquier caso.
- **Reproducción:** `curl -X POST {ISSUER}/auth/logout -H "Authorization: Bearer <at>"` → 401.
- **Corrección mínima sugerida:** reescribir §3.1 para describir el mecanismo real:
  (a) para revocar el refresh, `POST /auth/revoke`; (b) para terminar la sesión de navegador
  de Minerva, la ruta web `/logout` (RP-Initiated Logout); dejar claro que el access token
  no se invalida por firma. No requiere cambio de código, solo de documentación — pero es
  contrato de integración, por eso es Rojo y no Verde.
- **Riesgo de compatibilidad:** ninguno (documentación).
- **Prueba:** N/A (doc). Opcional: un test que afirme que `/auth/logout` con Bearer y sin
  cookie responde 401, para fijar el contrato.
- **Referencias:** RFC 7009 (Token Revocation); OIDC RP-Initiated Logout 1.0.
- **¿Bloquea 1.0.0?** **Sí** (contrato público de integración incorrecto).

---

## 5. 🟡 Amarillo — mejora real, incorporable sin romper consumidores

### Y1 · Errores del token endpoint no siguen el formato OAuth (RFC 6749 §5.2)
- **Evidencia:** `/auth/token` devuelve `{"detail": "..."}` con 400 (jerarquía
  `AppException`), no `{"error": "invalid_grant", ...}`. Verificado: reúso de código →
  `400 {"detail": "Código de autorización inválido o ya usado"}`.
- **Impacto:** librerías OIDC estrictas del lado del cliente esperan el campo `error` con
  códigos estándar (`invalid_grant`, `invalid_client`, `unsupported_grant_type`). Con
  Minerva no pueden discriminar la causa programáticamente.
- **Corrección mínima:** un handler específico para `/auth/token` que emita el cuerpo
  OAuth (`error`/`error_description`). Es **aditivo** (agregar `error`); se puede conservar
  `detail` para no romper a quien ya lo lee.
- **Compatibilidad:** no-rompiente si se conserva `detail`.
- **Referencia:** RFC 6749 §5.2. · **No bloquea 1.0.0** (recomendado si se busca sello de
  conformidad).

### Y2 · Falta `Cache-Control: no-store` en las respuestas del token endpoint
- **Evidencia:** respuesta 200 de `/auth/token` sin `Cache-Control`/`Pragma` (verificado).
- **Impacto:** RFC 6749 §5.1 exige `Cache-Control: no-store` y `Pragma: no-cache` en
  respuestas con credenciales. Riesgo de caché intermedia de tokens.
- **Corrección mínima:** fijar esos headers en las respuestas de `/auth/token` (y
  conviene también en `/userinfo`). · **Referencia:** RFC 6749 §5.1. · **No bloquea.**

### Y3 · `/userinfo` solo soporta GET
- **Evidencia:** `POST /userinfo` → 405 (verificado). `oidc/router.py:120-125` solo define GET.
- **Impacto:** OIDC Core 5.3 dice que el UserInfo Endpoint *SHOULD* soportar GET **y** POST.
  Algunos clientes usan POST.
- **Corrección mínima:** agregar handler POST que reutilice la misma dependencia.
  · **Referencia:** OIDC Core 1.0 §5.3. · **No bloquea.**

### Y4 · Resolución de roles/permisos efectivos duplicada en 3 servicios
- **Evidencia:** el patrón "roles directos + roles por grupo, dedup por id, permisos por
  rol filtrados por app" aparece casi idéntico en `auth/service.py:535-548`
  (`_get_user_permissions`), `authorization/service.py:22-35` y `devkit/service.py:32-38`.
- **Impacto:** mantenibilidad y riesgo de divergencia — un cambio en la lógica de
  autorización (p. ej. jerarquía de grupos) hay que replicarlo en tres lugares y es fácil
  dejar uno atrás. Es la clase de duplicación que un crecimiento asistido por IA suele dejar.
- **Corrección mínima:** extraer un helper compartido (p. ej. en `authorization/service.py`
  o `shared/`) que devuelva roles/permisos efectivos, y que los tres lo consuman.
- **Compatibilidad:** interno, sin cambio de contrato. · **No bloquea** (deuda de
  mantenibilidad, no bug).

### Y5 · Conteo de totales cargando todas las filas en memoria
- **Evidencia:** en cada repositorio, `list_all` hace `total = self.session.exec(select(X)).all()`
  y luego `len(total)` (`users/repository.py:26-30`, y equivalentes en applications,
  permissions, groups, roles, audit).
- **Impacto:** se materializan todas las filas solo para contarlas, en cada listado
  paginado. La tabla `audit_logs` crece sin cota (un registro por login/token/rate-limit);
  ahí el costo se vuelve real con el tiempo.
- **Corrección mínima:** `select(func.count()).select_from(X)` con los mismos filtros.
- **Compatibilidad:** ninguna (misma respuesta). · **No bloquea**, pero conviene antes de
  que las tablas crezcan en producción.

### Y6 · CORS con `localhost:5173` fijo y `APP_DEBUG` no cubierto por el fail-fast
- **Evidencia:** `main.py:200` incluye `http://localhost:5173` en `allow_origins` con
  `allow_credentials=True`, también en producción. `validate_production_config`
  (`config.py:137`) no valida `APP_DEBUG`, que alimenta `FastAPI(debug=...)` y el `echo` de
  SQL (`database.py:7`).
- **Impacto:** menor (un atacante necesitaría controlar `localhost:5173` en la máquina de
  la víctima), pero es superficie innecesaria en prod; y un `APP_DEBUG=true` olvidado
  expondría tracebacks y logs de SQL sin que el arranque avise.
- **Corrección mínima:** derivar `allow_origins` de `FRONTEND_URL` (+ orígenes de dev solo
  en modo dev); añadir `APP_DEBUG` a `validate_production_config`. · **No bloquea.**

### Y7 · `update_user` invalida sesiones aunque el correo no cambie
- **Evidencia:** `users/router.py:89-91` marca `invalidating` si `data.email is not None`,
  sin comparar contra el valor actual (el service sí compara para la unicidad, pero la
  invalidación ocurre igual).
- **Impacto:** un PATCH que reenvía el mismo correo cierra todas las sesiones del usuario
  innecesariamente. Molesto, no inseguro.
- **Corrección mínima:** decidir `invalidating` comparando el valor nuevo contra el actual.
  · **No bloquea.**

---

## 6. 🟢 Verde — documentación, OSS, limpieza segura (sin cambio de comportamiento)

### G1 · Faltan archivos legales/comunitarios de open source · **bloquea la publicación**
- **Evidencia:** no existen `LICENSE`, `CONTRIBUTING.md`, `SECURITY.md`,
  `CODE_OF_CONDUCT.md` (sí hay plantillas de issues/PR en `.github/`).
- **Impacto:** sin `LICENSE` el repositorio **no es legalmente open source** — nadie puede
  usarlo, revisarlo ni contribuir con seguridad jurídica. Para una publicación de una
  dependencia pública esto es indispensable (además, sienta el precedente que busca el
  proyecto).
- **Acción:** elegir licencia (p. ej. MIT o Apache-2.0), agregar `LICENSE`; `SECURITY.md`
  con canal de reporte de vulnerabilidades; `CONTRIBUTING.md` breve. · **Bloquea 1.0.0
  como publicación**, aunque no afecte el funcionamiento.

### G2 · Versión inconsistente en 5 lugares
- **Evidencia:** `backend/app/main.py:230` → `"version": "0.1.0"`; `pyproject.toml` → 0.3.4;
  badge de `README.md` → 0.3.3; `sdk/minerva_sdk/__init__.py:28` → 0.2.0;
  `.env.production.example:10` → `MINERVA_VERSION=0.2.1`.
- **Impacto:** el endpoint `/` reporta 0.1.0, que confunde a operadores y monitoreo. Para
  1.0.0 conviene una única fuente de verdad (leer de `importlib.metadata` o de un solo sitio).
- **Acción:** unificar; el endpoint raíz debe leer la versión real del paquete. · Sin
  impacto funcional.

### G3 · Documentación desfasada respecto al código
- **`docs/arquitectura.md:160-171`:** el diagrama de rotación de claves describe el modelo
  **viejo de una fase** (retira activa → genera nueva → purga por
  `MINERVA_ACCESS_TOKEN_TTL_MINUTES`). El código real es **dos fases** (`rotate-key` publica
  `pending`, `promote-key` activa) y la retención se **deriva** del TTL de sesión (485 min),
  no del TTL del access token. `docs/despliegue.md:160-206` sí lo describe bien: hay
  contradicción entre ambos.
- **`docs/arquitectura.md:112`** menciona `get_current_user` / `get_optional_user`, nombres
  que ya no existen (hoy son `get_current_panel_user` / `get_current_access_user` /
  `get_current_devkit_user`).
- **Acción:** corregir el diagrama y la tabla de `core/` en arquitectura.md. · Sin impacto
  funcional, pero es documentación de referencia para futuros lectores.

### G4 · Abstracción muerta: `import_models()` es un no-op
- **Evidencia:** `core/models.py` = `def import_models(): pass`, invocada en `main.py:135,174`
  y `cli.py:49,60`. No hace nada (los modelos se importan directamente en `main.py`).
- **Acción:** eliminar la función y sus llamadas. · Limpieza segura (ponytail: código que
  no existe no se mantiene).

### G5 · Warning de lint en el frontend
- **Evidencia:** `frontend/src/features/admin/pages/GroupsPage.jsx:24` — `pagination`
  asignada y no usada (único warning de `npm run lint`).
- **Acción:** eliminar la variable. · Trivial.

### G6 · Bundle del frontend en un solo chunk >500 KB
- **Evidencia:** `npm run build` advierte chunks >500 KB (sin code-splitting).
- **Acción (opcional):** `manualChunks` para Ant Design, o `import()` dinámico de páginas
  admin. · Mejora de carga, no bloquea.

---

## 7. Sobreingeniería: qué revisar, qué conservar

**Posible sobreingeniería / simplificable:**
- **`import_models()` no-op** (G4) — eliminar.
- **Duplicación de resolución de roles/permisos** (Y4) — consolidar. Es el caso más claro
  de código repetido que probablemente creció por generación asistida.
- **`PaginatedResponse.create`** es un wrapper trivial; es inofensivo, no vale la pena
  tocarlo antes de 1.0.

**Complejidad que PARECE sobreingeniería pero debe conservarse** (protege una frontera real):
- El baile *fail-closed* Redis→PostgreSQL en rotación/revocación (`auth/router.py:406-421`).
  Es intrincado, pero garantiza que una revocación nunca quede menos durable que el cambio
  que la motivó. Simplificarlo reabre una ventana de token-revocado-aún-válido.
- La rotación de claves en dos fases y los índices únicos parciales
  (`oidc/service.py`, migración 009). Protegen contra corte de servicio y contra dos claves
  activas. Conservar.
- Los dos endpoints de permisos (rich `/authorization/me/permissions` interno vs lean
  `/api/v1/me/permissions` para el SDK). La duplicación es deliberada y está documentada:
  uno es contrato público estable, el otro vista interna. Conservar.
- El contenedor de sesión BFF y el CSRF synchronizer. Es la única excepción al principio
  stateless y está bien acotada. Conservar.

**Mejoras que NO valen la pena antes de 1.0.0:**
- Code-splitting del bundle (G6) — cosmético.
- Migrar el count-all (Y5) puede esperar si la ventana de release es corta, salvo para
  `audit_logs` (esa sí conviene).
- Reescrituras de estilo/elegancia sin problema medible detrás.

---

## 8. Comparación con auditorías/PR previos

El historial de git muestra que varias observaciones típicas **ya fueron atendidas** en
esta rama y ramas recientes, lo que explica la solidez actual:
- Segregación de tokens por `typ` (referida como "R2" en commits): resuelta.
- Registro público cerrado por defecto ("R4"): `MINERVA_ENABLE_PUBLIC_REGISTER=false`.
- Vínculos rol↔permiso cross-app (issue #38): trigger en migración 007.
- Seed idempotente con advisory lock (PR #59), audit con UUID de app (PR #58), eliminación
  de Google Workspace (PR #57), `min_length=8` en password de alta y PATCH.
- `mypy app` como gate de CI con la deuda de tipos en cuarentena (commits de esta rama).

Los hallazgos de esta auditoría (R1, R2, Y1–Y3) son **nuevos** respecto a ese historial:
apuntan al perímetro de logout de consumidor y a conformidad fina de OAuth/OIDC, áreas que
las correcciones previas (centradas en tokens, seed y tipos) no cubrieron.

---

## 9. Roadmap mínimo a 1.0.0

**Indispensable (bloquea la publicación):**
1. **R1** — validar `redirect_uri` en `LogoutPage` contra allowlist (o restringir a rutas
   propias / `post_logout_redirect_uris` registrados).
2. **R2** — corregir `docs/integracion.md §3.1`: describir el logout real
   (`/auth/revoke` + página `/logout`), sin prometer revocación por `POST /auth/logout` con Bearer.
3. **G1** — agregar `LICENSE` (y `SECURITY.md`/`CONTRIBUTING.md` mínimos).

**Recomendado antes de publicar (barato, sube la calidad del sello OIDC):**
4. **G2** — unificar versión; el endpoint `/` debe reportar la real.
5. **G3** — corregir el diagrama de rotación de claves y los nombres de dependencias en
   `arquitectura.md`.
6. **Y1 + Y2 + Y3** — cuerpo de error OAuth + `Cache-Control: no-store` en `/auth/token`;
   POST en `/userinfo`. Es conformidad de bajo costo y no rompe a nadie.
7. **G4 + G5** — eliminar `import_models()` y el warning de lint.

**Puede esperar a 1.1 (deuda sana, no bloquea):**
8. **Y4** — consolidar la resolución de roles/permisos.
9. **Y5** — `func.count()` en los listados (prioridad para `audit_logs`).
10. **Y6 + Y7** — CORS/`APP_DEBUG` en el fail-fast; `update_user` sin sobre-invalidar.
11. **G6** — code-splitting del bundle.

**Corte sugerido:** con los puntos 1–3 Minerva es *publicable y segura*; con 4–7 es
*publicable, segura y conforme*. Los puntos 8–11 son mejoras de mantenibilidad y rendimiento
que no justifican retrasar el release.

---

## 10. Validaciones ejecutadas en esta auditoría

| Verificación | Resultado |
|---|---|
| `pytest tests/` (backend, SQLite + fakeredis) | **185 passed, 13 skipped** (los skip son PG-only) |
| PG-only contra PostgreSQL 16 efímero (`MINERVA_TEST_POSTGRES_URL`) | **13 passed** (refresh race, trigger, seed concurrente, invariante de claves) |
| `pytest tests/` (SDK) | **29 passed** |
| `ruff check app alembic tests` | limpio |
| `ruff format --check` | limpio |
| `mypy app` | sin errores (68 archivos; deuda histórica en cuarentena vía `pyproject`) |
| `npm run lint` (frontend) | 0 errores, 1 warning (G5) |
| `npm run build` (frontend) | OK (aviso de chunk >500 KB, G6) |
| Pruebas negativas propias (open redirect, reúso de code, CSRF, `/userinfo` POST, forma de error del token) | ver R1, R2, Y1–Y3 |

---

## 11. Referencias técnicas

- RFC 6749 — OAuth 2.0 (§4.1.2 authorize, §5.1 headers de token, §5.2 error responses, §10.4 rotación de refresh).
- RFC 7636 — PKCE (S256).
- RFC 7009 — OAuth 2.0 Token Revocation.
- RFC 7517 — JSON Web Key (JWKS).
- RFC 8414 — OAuth 2.0 Authorization Server Metadata (discovery).
- RFC 8725 — JWT Best Current Practices (confusión de algoritmo).
- OpenID Connect Core 1.0 — §3.1.2.1 (`prompt`/`max_age`), §5.3 (UserInfo), §5.4 (scope→claims).
- OpenID Connect RP-Initiated Logout 1.0 — `post_logout_redirect_uri`.
- OWASP — Unvalidated Redirects and Forwards; Session Management Cheat Sheet.
