# Auditoría independiente de Minerva

**Fecha de corte:** 2026-07-21 (America/Mexico_City)

**Rama:** `chore/mypy-ci-gate`

**Commit:** `e57b5e501d25a29aa5b283c8b20e19dab943d896`

**Descripción Git:** `v0.3.4-125-ge57b5e5`

**Alcance:** backend, frontend, OAuth 2.0, OpenID Connect, sesiones, SDK, ejemplo consumidor, base de datos, migraciones, pruebas, infraestructura, despliegue, documentación, preparación open source y sobreingeniería.
**Regla de trabajo:** revisión de solo lectura del producto. Este archivo y el resumen HTML son entregables; no se modificó código de ejecución.

## 1. Dictamen ejecutivo

Minerva ya es un proveedor de identidad institucional funcional: administra usuarios, aplicaciones, redirect URIs, grupos, roles y permisos; emite tokens RS256; publica discovery y JWKS; implementa Authorization Code con PKCE; mantiene refresh tokens opacos con rotación y detección de reutilización; ofrece un panel BFF con sesión opaca en Redis; y aporta un SDK FastAPI para validar tokens y consultar permisos.

La arquitectura de seguridad central no necesita una reescritura. En particular, son decisiones correctas la separación de clases de token, el uso de RS256/JWKS, el panel sin JWT en el navegador, CSRF, la rotación publish-before-use, la revocación fail-closed y la barrera de base de datos que impide enlazar roles y permisos de aplicaciones distintas.

Sin embargo, **el commit auditado no es publicable como 1.0.0**. Hay once bloqueos técnicos P0: migraciones desconectadas del runtime, cruce de audiencia en el endpoint que usa el SDK, logout con redirect abierto, configuración de producción fail-open, pérdida de `max_age`, operaciones no atómicas, concurrencia sin unicidad en manifiestos, contrato OAuth/OIDC parcialmente no conforme, una suite backend que se bloquea con dependencias permitidas por el propio proyecto, entradas que producen 500 e invalidación defectuosa en el mismo segundo. Además, la ausencia de una licencia aprobada es un bloqueo P0 de publicación y evita legalmente presentarlo como software open source.

No se recomienda ampliar alcance con MFA, federación, registro dinámico, microservicios, introspección, TypeScript o un rediseño general. El camino mínimo es corregir las fronteras anteriores, hacer reproducible la validación, completar el contrato público que ya se anuncia y publicar políticas/documentación coherentes.

## 2. Cómo leer el semáforo y la prioridad

El semáforo indica **sensibilidad del cambio**, no urgencia:

- **Verde:** documentación, UX, contribución, preparación open source o limpieza segura.
- **Amarillo:** mejora compatible o incorporable gradualmente.
- **Rojo:** vulnerabilidad, bug, inconsistencia de datos, función incompleta, sobreingeniería interna problemática o cambio potencialmente incompatible.

Prioridad independiente:

- **P0 — bloquea 1.0.0:** debe resolverse y verificarse antes de una release candidate.
- **P1 — antes de publicar:** puede no bloquear el binario, pero sí una publicación pública responsable.
- **P2 — post-1.0:** no aporta suficiente valor para retrasar 1.0.0.

## 3. Funcionamiento actual

### 3.1 Componentes y límites

| Componente | Implementación actual | Fuente de verdad |
|---|---|---|
| API | FastAPI + SQLModel, módulos por dominio | PostgreSQL |
| Panel | React/Vite/Ant Design servido por nginx | API y sesión BFF |
| Sesión del panel | Cookie opaca `__Host-minerva_sid`; cuentas, JWT internos y CSRF en Redis | Redis |
| OAuth/OIDC | Authorization Code, PKCE S256, refresh/revocación, UserInfo, discovery, JWKS | PostgreSQL + Redis |
| Firma | RSA/RS256; privadas cifradas con Fernet; estados pending/active/retired | PostgreSQL |
| Autorización | roles directos o por grupos, permisos por aplicación | PostgreSQL |
| SDK | dependencia FastAPI, validación local de JWT y consulta remota de permisos | JWKS + API Minerva |
| Manifiestos | YAML aditivo, importación manual o automática al arranque | Archivos + PostgreSQL |
| Despliegue | Compose: nginx/frontend, Gunicorn/Uvicorn, PostgreSQL, Redis | imágenes GHCR/configuración de entorno |

El backend sigue una separación router → dependency → service → repository → model. Es comprensible, pero los repositorios hacen `commit()` por operación; esa decisión rompe transacciones de servicio y produce dos hallazgos de consistencia. No se necesita agregar otra capa: basta con devolver la responsabilidad transaccional al servicio o a una única unidad de trabajo por caso de uso.

### 3.2 Modelo de identidad y autorización

- `User`: identidad, contraseña bcrypt, estado y fecha de autenticación.
- `Application`: cliente OAuth, `client_id`, hash de secreto y estado.
- `RedirectURI`: redirect exacto por aplicación.
- `Role` y `Permission`: pertenecen a una aplicación.
- `GroupUser`, `GroupRole`, `UserRole` y `RolePermission`: relaciones many-to-many.
- `AuthCode`: código de autorización de un uso.
- `RefreshToken`: token opaco almacenado como hash, familia, rotación y revocación.
- `SigningKey`: material RSA cifrado y ciclo pending/active/retired.
- `AuditLog`: eventos registrados de manera selectiva.
- `ManifestImport`: historial de importaciones.

La migración `007_role_permissions_cross_app` agrega una defensa valiosa en PostgreSQL: rechaza enlaces rol-permiso entre aplicaciones y vuelve inmutable `application_id` para ambos objetos. Debe conservarse.

### 3.3 Flujo Authorization Code + PKCE

1. El consumidor registra `client_id` y una redirect URI exacta.
2. El navegador entra a `/authorize`; el frontend conserva los parámetros y consulta `/auth/authorize/url`.
3. El backend valida cliente y redirect antes de cualquier redirección.
4. Si existe sesión BFF, resuelve cuenta activa; `prompt` y `max_age` deciden si reautentica.
5. Emite un `AuthCode` ligado a usuario, cliente, redirect, challenge, nonce y scopes.
6. `/auth/token` valida código, cliente, redirect, secreto si es confidencial y verifier si corresponde.
7. Emite access token RS256 con `aud` de aplicación; si se pidió `openid`, ID token con `aud=client_id`; opcionalmente refresh opaco.

La criptografía y los enlaces del código son sólidos. Los defectos están en el transporte web de `max_age`, la atomicidad del canje, la validación sintáctica del verifier y el formato HTTP de errores/respuestas.

### 3.4 Sesiones, revocación y rotación

El panel usa un patrón BFF: el navegador no recibe JWT. Redis almacena el contenedor multi-cuenta y un token CSRF; la cookie es HttpOnly y, fuera de dev, Secure con prefijo `__Host-`. La pérdida de Redis invalida el panel, comportamiento seguro.

Los refresh tokens son opacos y se guardan hasheados. La rotación usa bloqueo de fila en PostgreSQL, revoca la familia ante reutilización y escribe la blacklist antes de confirmar la revocación, por lo que falla cerrado. La invalidación por usuario tiene una carrera de un segundo descrita en H-11.

La rotación de firma en dos fases es correcta: publica una clave pending, espera propagación, la promueve y conserva la retired durante el mayor TTL firmado más skew. Falta una operación de incidente para una clave comprometida y para descartar una pending abandonada.

### 3.5 SDK y consumidor

El SDK valida `alg=RS256`, firma JWKS, `iss`, `aud` y `typ=access`; refresca JWKS ante `kid` desconocido y limita cachés. `require_permission` consulta en tiempo real `/api/v1/me/permissions` por defecto, por lo que una revocación se refleja inmediatamente. El defecto crítico es que su override `application_code` no cambia la audiencia validada, mientras el backend acepta consultar permisos de otra aplicación con el mismo token.

El ejemplo Godín demuestra login, callback, intercambio y popup. Es útil, pero construye URLs manualmente y mantiene PKCE en memoria global sin TTL; debe etiquetarse inequívocamente como demo y usar `urllib.parse.urlencode` para evitar que se copie un patrón frágil.

### 3.6 Superficie HTTP

Se localizaron 48 rutas de módulos: sesión/login/registro, authorize/token/revoke/refresh, administración de usuarios/aplicaciones/roles/permisos/grupos, autorización, auditoría y Dev Kit. A ellas se suman `/`, `/health`, discovery, JWKS y UserInfo. El panel administrativo está protegido por el rol `minerva.admin`; los endpoints OAuth usan bearer o sesión según su frontera.

## 4. Validación ejecutada

| Área | Comando/ejercicio | Resultado |
|---|---|---|
| Backend lint | `ruff check app alembic tests` | pasa |
| Backend formato | `ruff format --check app alembic tests` | pasa, 114 archivos |
| Tipos | `mypy app` | pasa, pero 14 módulos críticos tienen `ignore_errors` |
| Backend tests | `pytest tests/ -q` | se bloquea en la primera prueba; 198 recolectadas |
| Aislamiento del bloqueo | `pytest tests/test_admin_guard.py::test_non_admin_cannot_list_users -o faulthandler_timeout=6` | timeout dentro de `client.post('/auth/register')` del fixture |
| Subconjunto puro | config/Redis/firma | 17/17 pasan |
| SDK | `PYTHONPATH=.../sdk pytest` | 29/29 pasan |
| SDK sin aislamiento | `pytest` desde entorno compartido | falla colección por colisión con `backend/tests` |
| Frontend lint | `npm run lint` | 0 errores; 1 warning por `pagination` sin usar |
| Frontend build | `npm run build` | pasa; 1.303 MB, gzip 418 KB; warning >500 KB |
| Dependencias frontend | `npm audit --omit=dev` | 0 vulnerabilidades |
| Compose | `docker compose ... config -q` | pasa |
| Imágenes | build backend y frontend | pasan |
| Backend vivo | `/health`, `/`, discovery, JWKS | 200; `/` informa versión incorrecta 0.1.0 |
| SCA Python | `pip-audit` | 1 alerta: `ecdsa 0.19.2`, transitoria de python-jose |
| SAST Python | Bandit | 0 medium/high; 20 low |
| Dependencias instaladas | `pip check` | pasa |
| Secreto accidental | búsqueda dirigida | no se localizaron secretos reales ni llaves privadas |

La suite backend declara rangos abiertos y hoy resuelve FastAPI 0.136.3, Starlette 1.3.1, pytest 9.1, pytest-asyncio 1.4, Redis 8.0 y fakeredis 2.36.2. Esa combinación está permitida y bloquea 181 pruebas que no se alcanzan a ejecutar. No es aceptable considerar “verde” la suite por pruebas históricas.

### 4.1 Pruebas negativas adicionales

- Password de 73 bytes: `hash_password('a' * 73)` lanza `ValueError` con bcrypt 5; las entradas no tienen máximo.
- `APP_ENV=production` con `MINERVA_MODE=dev`, password default y dev-login: `validate_production_config()` lo acepta.
- `DATABASE_URL=A` y `MINERVA_DB_URL=B`: el runtime abre B y Alembic migra A.
- Tras `import_models()`, `SQLModel.metadata.tables` está vacío.
- `/auth/token` con grant no soportado devuelve `{"detail": ...}` y no `error`; no envía `Cache-Control: no-store` ni `Pragma: no-cache`.
- `/auth/revoke` con cliente inexistente devuelve un detalle no estándar.
- El código demuestra que un access token con audiencia A puede pedir permisos B por `/api/v1/me/permissions?application=B`.
- Un token emitido en el mismo segundo que `invalidate_user_tokens` tiene `iat == cutoff` y sobrevive porque el rechazo usa `<`.

## 5. Tabla consolidada de hallazgos

| ID | Semáforo | Prioridad | Hallazgo | ¿Bloquea 1.0? |
|---|---|---:|---|---|
| H-01 | Rojo | P0 | Alembic migra otra URL y trabaja con metadata vacía | Sí |
| H-02 | Rojo | P0 | Cruce de audiencia entre SDK y permisos remotos | Sí |
| H-03 | Rojo | P0 | Logout abierto y éxito aparente ante fallo | Sí |
| H-04 | Rojo | P0 | Configuración/topología de producción fail-open | Sí |
| H-05 | Rojo | P0 | `max_age` se pierde en el frontend | Sí |
| H-06 | Rojo | P0 | Canje y borrado de roles no son atómicos | Sí |
| H-07 | Rojo | P0 | Manifiestos concurrentes sin unicidad de dominio | Sí |
| H-08 | Rojo | P0 | Contrato OAuth/OIDC incompleto/no conforme | Sí, mientras se anuncie “completo” |
| H-09 | Rojo | P0 | Suite backend y builds no reproducibles | Sí |
| H-10 | Rojo | P0 | Password largo y verifier PKCE pueden producir 500 | Sí |
| H-11 | Rojo | P0 | Invalidación por usuario falla en el mismo segundo | Sí |
| H-12 | Rojo | P1 | Auditoría administrativa incompleta e inconsistente | Sí para publicación institucional |
| H-13 | Rojo | P1 | Manifiesto aditivo conserva privilegios retirados | No, con contrato explícito; sí si se presenta autoritativo |
| H-14 | Rojo | P1 | Operación de emergencia de claves es manual | No |
| H-15 | Verde | P0/P1 | No hay licencia ni archivos comunitarios básicos | Licencia: sí; resto: antes de publicar |
| H-16 | Amarillo | P1 | Cadena de suministro e imágenes no deterministas | Sí para release pública |
| H-17 | Verde | P1 | Documentación, versiones y SDK contradicen el runtime | Sí para publicación |
| H-18 | Rojo | P1/P2 | Duplicación y capas internas ya causan divergencia | Solo las simplificaciones ligadas a bugs |
| H-19 | Amarillo | P1/P2 | Cobertura frontend, accesibilidad y observabilidad | Solo pruebas de flujos críticos |

## 6. Hallazgos detallados

### H-01 — Alembic no representa la base usada por la aplicación

- **Evidencia:** `backend/app/core/database.py:5-12` crea el engine con `effective_db_url`; `backend/alembic/env.py:6-36` usa siempre `DATABASE_URL`; `backend/app/core/models.py:1-2` deja `import_models()` vacío.
- **Comportamiento:** con ambos URL distintos, el proceso migra A y sirve B. La metadata de Alembic queda sin tablas, por lo que autogenerate no ve el modelo real y puede interpretar tablas existentes como sobrantes.
- **Impacto:** esquema desactualizado, despliegues contra la base equivocada, migraciones peligrosas y pérdida de datos si se acepta un autogenerate incorrecto.
- **Reproducción:** instanciar Settings con ambas URL; comparar `engine.url` con la URL de Alembic; importar `import_models()` y observar `SQLModel.metadata.tables == {}`.
- **Corrección mínima:** una sola propiedad de URL para runtime y Alembic; importar explícitamente los modelos antes de asignar `target_metadata`; agregar un check que falle si la metadata está vacía.
- **Compatibilidad:** migración/configuración sensible; detectar despliegues que dependían de la ambigüedad.
- **Prueba de corrección:** test que configura solo cada alias y exige igualdad; `alembic check` contra una BD migrada; autogenerate vacío cuando no hay cambios.
- **Referencia:** [Alembic autogenerate y target_metadata](https://alembic.sqlalchemy.org/en/latest/autogenerate.html).
- **1.0.0:** bloquea.

### H-02 — Un token de la aplicación A puede consultar permisos de B

- **Evidencia:** `sdk/minerva_sdk/fastapi.py:228-249` permite `application_code` alternativo, pero la decodificación previa valida contra el código global; `backend/app/core/dependencies/auth.py:130-135` no fija audiencia; `backend/app/modules/devkit/router.py:41-53` acepta cualquier `application`; `backend/app/modules/devkit/service.py:88-104` devuelve sus permisos.
- **Comportamiento:** la identidad del token A se usa para obtener decisiones de autorización B. Un consumidor que use el override puede autorizar con una credencial que no fue emitida para él.
- **Impacto:** fuga de entitlements y posible bypass de autorización entre recursos.
- **Reproducción:** emitir access token `aud=A`, asignar al usuario un permiso B y llamar `/api/v1/me/permissions?application=B`; hoy devuelve B.
- **Corrección mínima:** comparar `application` con `aud` para access tokens; para dev tokens validar pertenencia a `applications`; retirar el override del SDK o rechazar si no coincide.
- **Compatibilidad:** rompe consumidores que usen deliberadamente un token para varias audiencias; esa conducta es insegura y debe migrarse.
- **Prueba de corrección:** A→A 200; A→B 401/403; token dev solo consulta aplicaciones declaradas.
- **Referencias:** [RFC 9700 §2.3](https://www.rfc-editor.org/rfc/rfc9700.html#section-2.3), [RFC 9068 §4](https://www.rfc-editor.org/rfc/rfc9068.html#section-4).
- **1.0.0:** bloquea.

### H-03 — Logout expone open redirect y oculta fallos

- **Evidencia:** `frontend/src/features/auth/pages/LogoutPage.jsx:24-39` acepta cualquier URL absoluta HTTP(S), redirige con `window.location.href` y usa `.finally(finish)`.
- **Comportamiento:** `/logout?redirect_uri=https://sitio-atacante` convierte Minerva en redirector confiable; aun si el POST de logout falla, la UI sale del dominio aparentando éxito.
- **Impacto:** phishing, encadenamiento de OAuth y falsa expectativa de cierre de sesión.
- **Reproducción:** abrir el URL anterior; simular fallo de red en `/auth/logout`; ambos terminan en el destino externo.
- **Corrección mínima:** para 1.0 eliminar redirect externo o implementar RP-Initiated Logout con `post_logout_redirect_uri` pre-registrada y vínculo a cliente/ID token; mostrar error si la invalidación falla.
- **Compatibilidad:** rompe integraciones que usan el parámetro custom no registrado; ofrecer migración explícita.
- **Prueba de corrección:** URI no registrada nunca redirige; registrada solo tras logout exitoso; falla deja mensaje y opción de reintento.
- **Referencias:** [RFC 9700 §4.10](https://www.rfc-editor.org/rfc/rfc9700.html#section-4.10), [OIDC RP-Initiated Logout §2](https://openid.net/specs/openid-connect-rpinitiated-1_0.html#RPLogout).
- **1.0.0:** bloquea.

### H-04 — La producción depende de una bandera que puede quedar en dev

- **Evidencia:** `backend/app/core/config.py:121-159` deriva seguridad solo de `MINERVA_MODE`; `.env.production.example:17-19` propone dominios de panel/API separados mientras la cookie `__Host-` es host-only y nginx usa un único origen.
- **Comportamiento:** `APP_ENV=production` no impide dev-login, password default ni cookie insegura si `MINERVA_MODE=dev`. Con panel y API en hosts distintos, la cookie creada por uno no llega al otro.
- **Impacto:** despliegue inseguro que parece producción o flujo de autorización roto.
- **Reproducción:** `APP_ENV=production MINERVA_MODE=dev ADMIN_PASSWORD=changeme123`; la validación retorna sin error. Desplegar panel/API en hosts separados y observar ausencia de cookie.
- **Corrección mínima:** una sola señal de entorno; fuera de dev exigir issuer HTTPS, dev-login false, credenciales no default, cifrado de llaves, debug false y TTL positivos. Documentar un origen canónico TLS salvo que se diseñe de forma explícita otra topología.
- **Compatibilidad:** puede impedir arrancar configuraciones antes toleradas; es un fail-fast intencional.
- **Prueba de corrección:** matriz de configuración insegura que debe fallar y smoke test real detrás del proxy final.
- **Referencias:** [OIDC Discovery: issuer HTTPS y endpoints](https://openid.net/specs/openid-connect-discovery-1_0.html#ProviderMetadata), [prefijo `__Host-` de cookies](https://developer.mozilla.org/en-US/docs/Web/HTTP/Headers/Set-Cookie#cookie_prefixes).
- **1.0.0:** bloquea.

### H-05 — `max_age` se descarta antes de llegar al backend

- **Evidencia:** `backend/app/modules/auth/router.py:263-320` implementa `max_age`; `frontend/src/features/auth/pages/AuthorizePage.jsx:44-70` no lo extrae; `frontend/src/api/auth.js:59-83` no lo envía.
- **Comportamiento:** un consumidor entra por la página pública con `max_age=0`, pero la llamada BFF omite el parámetro y puede reutilizar una autenticación anterior.
- **Impacto:** se incumple una solicitud de reautenticación usada para acciones sensibles.
- **Reproducción:** sesión activa, abrir `/authorize?...&max_age=0`; inspeccionar la llamada a `/auth/authorize/url` y el resultado.
- **Corrección mínima:** transportar `max_age` intacto, validar entero no negativo y probar el flujo web completo.
- **Compatibilidad:** aditiva; hará efectiva una semántica ya documentada.
- **Prueba de corrección:** e2e con reloj controlado: `max_age=0` obliga login y el ID token incluye `auth_time` nuevo.
- **Referencia:** [OIDC Core §3.1.2.1, `max_age`](https://openid.net/specs/openid-connect-core-1_0.html#AuthRequest).
- **1.0.0:** bloquea.

### H-06 — Casos de uso sensibles se confirman por partes

- **Evidencia:** `backend/app/modules/auth/repository.py:53-59` consume el código y hace commit; `backend/app/modules/auth/service.py:356-369` firma/persiste después. `backend/app/modules/roles/service.py:56-64` llama tres borrados cuyos repositorios hacen commits (`groups/repository.py:92-96,124-128`, `permissions/repository.py:75-79`).
- **Comportamiento:** si la firma, consulta o persistencia final falla, el authorization code queda gastado sin tokens. Si falla un borrado intermedio, el rol queda parcialmente desasignado.
- **Impacto:** fallos irrecuperables de login, inconsistencia de autorización y auditoría difícil.
- **Reproducción:** inyectar fallo tras `mark_used`; reintento da código usado. Inyectar fallo en el tercer cleanup de rol y revisar enlaces restantes.
- **Corrección mínima:** una transacción por caso de uso; repositorios hacen add/delete/flush, el servicio confirma una vez. No agregar una nueva jerarquía de abstractions.
- **Compatibilidad:** interna; mejora atomicidad sin cambiar API.
- **Prueba de corrección:** fault injection en cada punto: rollback completo o commit completo; dos canjes concurrentes producen exactamente un ganador.
- **Referencia:** [SQLAlchemy Session: transacciones](https://docs.sqlalchemy.org/en/20/orm/session_transaction.html).
- **1.0.0:** bloquea.

### H-07 — Importar manifiestos con varios workers puede duplicar autorización

- **Evidencia:** modelos `roles`, `permissions` y `redirect_uris` no tienen unicidad `(application_id, slug/uri)`; migración `001_initial.py:87-123` solo crea índices no únicos por aplicación. `devkit/manifest.py:111-199` usa select-then-insert; `main.py:141-184` autoimporta en cada proceso; el contenedor inicia 4 workers.
- **Comportamiento:** dos workers pueden observar ausencia y crear duplicados; un fallo se degrada a warning. La semilla admin sí usa advisory lock, evidencia de que la carrera fue reconocida solo en ese flujo.
- **Impacto:** permisos/roles ambiguos, asignaciones divergentes y despliegues no deterministas.
- **Reproducción:** lanzar importación simultánea del mismo manifiesto sobre PostgreSQL limpio y consultar duplicados por clave de dominio.
- **Corrección mínima:** constraints únicos compuestos en PostgreSQL y manejo de conflicto; ejecutar autoimport una vez o desactivarlo en producción y hacerlo como paso explícito.
- **Compatibilidad:** primero debe detectar/conciliar duplicados existentes; luego la restricción es segura.
- **Prueba de corrección:** N importaciones concurrentes dejan una fila por clave y el mismo conjunto de relaciones.
- **Referencias:** [PostgreSQL unique constraints](https://www.postgresql.org/docs/current/ddl-constraints.html#DDL-CONSTRAINTS-UNIQUE-CONSTRAINTS), [Alembic constraints](https://alembic.sqlalchemy.org/en/latest/ops.html).
- **1.0.0:** bloquea.

### H-08 — El perfil anunciado como OAuth/OIDC “completo” no cumple su contrato HTTP

- **Evidencia:** `auth/router.py:395-403` acepta form o JSON legacy; errores usan `{"detail":...}` y estatus propios; `/auth/token` no agrega no-store; authorize y UserInfo solo admiten GET; `oidc/router.py:26-49` declara claims distintos a los emitidos y no anuncia revocación; no existe logout OIDC estándar.
- **Comportamiento:** clientes conformes no pueden interpretar errores estándar; respuestas con tokens pueden cachearse; UserInfo y authorize carecen del método POST obligatorio; discovery sobrerreporta claims y no descubre una revocación que sí existe.
- **Impacto:** interoperabilidad frágil, clientes especiales y afirmación pública que excede lo implementado.
- **Reproducción:** grant desconocido devuelve `detail`; inspeccionar headers de `/auth/token`; POST authorize/UserInfo da 405; comparar discovery con ID token/UserInfo.
- **Corrección mínima:** un modelo pequeño de error OAuth (`error`, `error_description`), headers no-store, POST form en authorize y UserInfo, `WWW-Authenticate` bearer, metadata verdadera y pruebas contractuales. Mantener JSON legacy solo con deprecación si hay consumidores.
- **Compatibilidad:** errores y métodos son aditivos; retirar JSON requiere ventana de deprecación.
- **Prueba de corrección:** tabla de requests RFC positivas/negativas y, antes de declarar certificación, una suite de conformidad OIDC.
- **Referencias:** [RFC 6749 §5.1-5.2](https://www.rfc-editor.org/rfc/rfc6749.html#section-5), [RFC 6750 §3](https://www.rfc-editor.org/rfc/rfc6750.html#section-3), [OIDC Core authorize](https://openid.net/specs/openid-connect-core-1_0.html#AuthRequest), [OIDC Core UserInfo](https://openid.net/specs/openid-connect-core-1_0.html#UserInfo), [RFC 8414](https://www.rfc-editor.org/rfc/rfc8414.html).
- **1.0.0:** bloquea mientras README diga “completo”; alternativamente publicar un perfil soportado honesto.

### H-09 — La validación backend no es reproducible

- **Evidencia:** `backend/pyproject.toml:11-42` usa rangos amplios sin lock; `.github/workflows/ci.yml:24-28` instala de cero; 14 módulos críticos tienen `ignore_errors` en `pyproject.toml:71-92`.
- **Comportamiento:** la resolución permitida actual bloquea la primera prueba de 198. El gate de tipos omite routers/repositorios de autenticación y autorización.
- **Impacto:** no existe evidencia ejecutable de regresión para publicar 1.0 y un tag puede romperse sin cambios de código.
- **Reproducción:** instalación limpia con los rangos declarados y `pytest tests/ -q`; timeout en fixture de registro.
- **Corrección mínima:** lock/constraints probados, corregir la incompatibilidad del harness, ejecutar PostgreSQL/Redis reales para integración y reducir la cuarentena mypy por módulos de mayor riesgo.
- **Compatibilidad:** solo desarrollo/CI; puede revelar dependencias implícitas.
- **Prueba de corrección:** CI limpio ejecuta 198/198 sin timeout y repite la misma resolución; prueba aislada por paquete evita colisión `tests` SDK/backend.
- **Referencia:** [PyPA reproducible environments](https://pip.pypa.io/en/stable/topics/repeatable-installs/).
- **1.0.0:** bloquea.

### H-10 — Entradas válidas para el schema pueden causar 500

- **Evidencia:** `auth/schemas.py:4-12` solo exige password mínimo; `core/security.py:25-35` pasa bytes directamente a bcrypt y codifica verifier como ASCII.
- **Comportamiento:** bcrypt 5 rechaza >72 bytes con `ValueError`; un verifier PKCE no ASCII produce `UnicodeEncodeError`; no se convierten en errores 4xx.
- **Impacto:** registro/login/canje pueden fallar con 500 y ruido operativo; contraseñas multibyte alcanzan antes el límite.
- **Reproducción:** `hash_password('a'*73)`; enviar `code_verifier` con Unicode.
- **Corrección mínima:** rechazar passwords >72 bytes UTF-8 con 422 y validar verifier contra 43–128 caracteres unreserved antes de hashear. No introducir prehash sin plan de compatibilidad.
- **Compatibilidad:** usuarios con contraseñas antes truncadas necesitan tratamiento explícito; en la versión auditada bcrypt ya las rechaza.
- **Prueba de corrección:** límites 71/72/73 bytes, multibyte y matriz PKCE 42/43/128/129/no ASCII.
- **Referencias:** [bcrypt 5.0.0 behavior](https://pypi.org/project/bcrypt/), [RFC 7636 §4.1](https://www.rfc-editor.org/rfc/rfc7636.html#section-4.1).
- **1.0.0:** bloquea.

### H-11 — La invalidación global conserva tokens del mismo segundo

- **Evidencia:** `core/token_blacklist.py:34-41` guarda `int(time.time())`; `core/dependencies/auth.py:92-96` rechaza solo `iat < cutoff`.
- **Comportamiento:** un token emitido e invalidado en el mismo segundo tiene igualdad y sigue válido.
- **Impacto:** cambio de password/status/logout-all puede no invalidar la credencial más reciente.
- **Reproducción:** congelar reloj, emitir token, invalidar usuario y resolverlo; no se rechaza.
- **Corrección mínima:** semántica inclusiva (`iat <= cutoff`) o marcador monotónico posterior, conservando TTL.
- **Compatibilidad:** invalida exactamente tokens que la operación promete invalidar.
- **Prueba de corrección:** reloj congelado para antes/igual/después del corte.
- **Referencia:** contrato interno de `invalidate_user_tokens`; [RFC 7009 §2.1](https://www.rfc-editor.org/rfc/rfc7009.html#section-2.1) sobre efectos de revocación.
- **1.0.0:** bloquea.

### H-12 — La auditoría no cubre administración de identidad y autorización

- **Evidencia:** las llamadas a `AuditRepository.log` aparecen principalmente en auth y check de autorización; routers CRUD de usuarios, aplicaciones, roles, permisos y grupos no registran actor/cambio. `users/service.py:7-19` construye el repositorio pero no lo usa. `audit/repository.py:15-36` calcula `total` cargando todos los logs sin aplicar filtros y cada log confirma por separado.
- **Comportamiento:** cambios administrativos críticos no quedan trazados; la paginación muestra total incorrecto y puede cargar toda la tabla; un negocio ya confirmado puede fallar después por auditoría.
- **Impacto:** baja rendición de cuentas, investigación de incidentes incompleta y panel incorrecto.
- **Reproducción:** crear/asignar/eliminar un rol y consultar auditoría; filtrar logs y comparar `items` con `total`.
- **Corrección mínima:** registrar actor, acción, objeto, aplicación y resultado en la misma transacción para mutaciones administrativas; usar `COUNT(*)` con los mismos filtros.
- **Compatibilidad:** aditiva; revisar retención y datos personales antes de hacer público el log.
- **Prueba de corrección:** cada mutación produce exactamente un evento o hace rollback; total coincide con filtro; pruebas de autorización del visor.
- **Referencia:** [OWASP Logging Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Logging_Cheat_Sheet.html).
- **1.0.0:** bloquea la publicación institucional, aunque no el protocolo OAuth aislado.

### H-13 — Un manifiesto eliminado no retira privilegios

- **Evidencia:** `devkit/manifest.py:140-199` agrega/actualiza URIs, permisos, roles y enlaces, pero nunca elimina faltantes; `docs/arquitectura.md:207-212` lo denomina idempotente/aditivo.
- **Comportamiento:** quitar un permiso de un rol en YAML no quita el enlace existente. El estado desplegado deja de corresponder al manifiesto.
- **Impacto:** privilegios obsoletos si un operador interpreta el manifiesto como fuente declarativa.
- **Reproducción:** importar rol con P, retirar P del YAML, reimportar y consultar rol.
- **Corrección mínima:** antes de 1.0 definirlo como importador aditivo no autoritativo y exigir retiro explícito; si se requiere reconciliación, agregar modo `--reconcile --dry-run`, no hacerlo implícito.
- **Compatibilidad:** reconciliar por defecto sería destructivo; debe ser opt-in y auditable.
- **Prueba de corrección:** contrato de importación aditiva y, si se agrega, dry-run exacto + retiro solo dentro de la aplicación objetivo.
- **Referencia:** comportamiento interno documentado; no se requiere una abstracción nueva.
- **1.0.0:** no si el contrato queda explícito; sí si se vende como estado declarativo completo.

### H-14 — La rotación normal es sólida; el incidente no está automatizado

- **Evidencia:** `docs/despliegue.md:160-203` documenta rotate/promote y admite que clave comprometida requiere procedimiento manual; el CLI no descarta una pending abandonada ni retira de emergencia.
- **Comportamiento:** una clave comprometida sigue publicada durante la retención normal; una pending puede bloquear la siguiente rotación.
- **Impacto:** respuesta lenta o propensa a error durante incidente.
- **Reproducción:** crear pending y abandonar; intentar otra. Marcar active comprometida y seguir verificando tokens mientras permanezca en JWKS.
- **Corrección mínima:** comandos explícitos para descartar pending y retirar de emergencia, con confirmación, invalidación de caches y runbook de revocación/impacto. No cambiar el flujo normal.
- **Compatibilidad:** operación altamente sensible; exigir respaldo y dry-run/listado.
- **Prueba de corrección:** simulacro: retirar `kid`, JWKS deja de publicarlo, tokens fallan, nueva active firma y consumidores refrescan.
- **Referencias:** [RFC 8725 §3.2–3.12](https://www.rfc-editor.org/rfc/rfc8725.html#section-3), [NIST SP 800-57 Part 1](https://csrc.nist.gov/pubs/sp/800/57/pt1/r5/final).
- **1.0.0:** no bloquea si existe runbook verificado; automatización puede ser P1.

### H-15 — Aún no existe autorización legal para reutilizar el código

- **Evidencia:** no hay `LICENSE`, `CONTRIBUTING.md`, `SECURITY.md`, `CODE_OF_CONDUCT.md` ni CODEOWNERS; `README.md:84-86` restringe el uso al IIEG.
- **Comportamiento:** terceros pueden leer el repositorio, pero no reciben permisos de uso, modificación o distribución propios de open source.
- **Impacto:** objetivo principal de publicación incumplido; vulnerabilidades y contribuciones no tienen canal formal.
- **Reproducción:** inventario de archivos y sección Uso del README.
- **Corrección mínima:** decisión institucional/legal sobre licencia OSI; agregar licencia, aviso de copyright, SECURITY con reporte privado/versiones soportadas, CONTRIBUTING y conducta. No escoger licencia por inferencia técnica.
- **Compatibilidad:** gobernanza/legal; puede afectar dependencias, marca y contribuciones.
- **Prueba de corrección:** GitHub community profile reconoce los archivos y revisión legal aprueba su contenido.
- **Referencias:** [OSI FAQ](https://opensource.org/faq), [GitHub community profile](https://docs.github.com/en/communities/setting-up-your-project-for-healthy-contributions/about-community-profiles-for-public-repositories), [GitHub security policy](https://docs.github.com/en/code-security/how-tos/report-and-fix-vulnerabilities/configure-vulnerability-reporting/add-security-policy).
- **1.0.0:** la licencia bloquea la publicación open source; los demás archivos son P1.

### H-16 — Tags e imágenes no prueban ni congelan lo que publican

- **Evidencia:** `.github/workflows/docker-publish.yml:7-43` publica por tag sin depender de tests; `ci.yml:3-7` solo corre en develop/main; acciones usan tags mayores mutables. `frontend/Dockerfile:1-6` copia solo package.json y usa `npm install`; backend no tiene lock y ambas imágenes corren como root.
- **Comportamiento:** un tag en commit no validado se publica; build Docker frontend resolvió un bundle distinto al build con lock local; las imágenes tienen privilegios innecesarios.
- **Impacto:** artefactos no reproducibles, riesgo de supply chain y escalamiento de impacto de una vulnerabilidad.
- **Reproducción:** comparar dependencias/bundle de `npm ci` local con Docker; inspeccionar workflow y usuario final.
- **Corrección mínima:** gate de tests para tags, `npm ci` con lock, constraints/lock Python, versiones de Node coherentes, usuario no root y actions fijadas por SHA.
- **Compatibilidad:** solo pipeline/imagen; validar permisos de volúmenes y puertos.
- **Prueba de corrección:** rebuild produce árbol/hash equivalentes; contenedor no root pasa health/integración; tag no publica si falla CI.
- **Referencias:** [npm ci](https://docs.npmjs.com/cli/v8/commands/npm-ci/), [GitHub Actions: pin a SHA](https://docs.github.com/en/actions/reference/security/secure-use#using-third-party-actions).
- **1.0.0:** bloquea la release pública reproducible.

### H-17 — Documentación y versiones contradicen al sistema

- **Evidencia:** README badge 0.3.3; backend/frontend 0.3.4; SDK 0.2.0; `/` devuelve 0.1.0; `.env.production.example` 0.2.1. `docs/integracion.md:178-180` dice que `/auth/logout` recibe bearer y revoca access token, pero usa cookie BFF. Líneas 151-154 sugieren silent renew en iframe mientras nginx declara `frame-ancestors 'none'` y la cookie es SameSite Lax. `sdk/README.md:92-99` dice que endpoints se descubren solos aunque están hardcodeados.
- **Comportamiento:** operadores y consumidores implementan contratos inexistentes o despliegan versiones viejas.
- **Impacto:** integración fallida y falsa evaluación de seguridad.
- **Reproducción:** contrastar documentos con handlers, CSP, SDK y respuesta `/`.
- **Corrección mínima:** una fuente de versión; documentar soft logout BFF, eliminar afirmación iframe, decir qué URLs deriva el SDK, actualizar diagrama de rotación y topología.
- **Compatibilidad:** documental; confirmar con consumidores antes de retirar ejemplos.
- **Prueba de corrección:** doctest/smoke de comandos y enlaces; matriz documento→endpoint; release check que compara versiones.
- **Referencia:** los RFC citados en H-03/H-08 son el contrato normativo.
- **1.0.0:** debe corregirse antes de publicar.

### H-18 — Sobreingeniería y duplicación con costo demostrado

- **Evidencia:** cálculo de roles/permisos repetido en `auth/service.py:535-548`, `authorization/service.py:22-35` y `devkit/service.py:32-38,88-104`; commits en cada repositorio; cascada manual de aplicación de ~55 líneas (`applications/repository.py:48-103`); aliases dobles de configuración; `UserService.audit_repo` sin uso; conteos cargan filas; dependencias runtime sin import (`httpx`, `orjson`, `jinja2`).
- **Comportamiento:** las copias ya divergen en audiencia, forma de respuesta y filtros; la granularidad de commits causa H-06; la cascada replica semántica nativa de FK.
- **Impacto:** más superficie para bugs y mantenimiento sin valor funcional.
- **Reproducción:** comparar los tres algoritmos y sus callers; provocar fallo intermedio; buscar imports y aliases efectivos.
- **Corrección mínima:** **[native]** constraints/cascades donde proceda; **[delete]** dependencias y miembros muertos; **[shrink]** una consulta compartida de entitlements y un commit por caso; **[yagni]** retirar `response_mode=web_message` si ningún consumidor real lo usa.
- **Compatibilidad:** no reescribir todos los módulos. Hacer solo cambios ligados a H-01/H-02/H-06/H-07 antes de 1.0; el resto post-1.0.
- **Prueba de corrección:** mismos resultados de autorización, rollback atómico y reducción aproximada de 120–250 líneas + 2–3 dependencias sin perder rutas.
- **Referencia:** capacidades nativas de [constraints/FK en PostgreSQL](https://www.postgresql.org/docs/current/ddl-constraints.html).
- **1.0.0:** bloquean solo las partes que sostienen bugs comprobados.

### H-19 — Faltan pruebas web críticas y readiness real

- **Evidencia:** no hay archivos de test frontend; build alerta bundle >500 KB; `/health` en `backend/app/main.py:234-236` devuelve constante; login desactiva autocompletado y algunos selectores de cuenta dependen de elementos clicables.
- **Comportamiento:** max_age/logout/CSRF/multi-cuenta pueden romperse sin gate; orquestador considera listo un proceso sin verificar DB, Redis, migración o clave active.
- **Impacto:** regresiones de seguridad web y despliegues que reciben tráfico antes de estar operativos.
- **Reproducción:** desconectar DB/Redis y consultar `/health`; sigue 200. Revisar inventario de tests frontend.
- **Corrección mínima:** pruebas mínimas de los cinco flujos críticos, `autocomplete=username/current-password`, semántica de botón/teclado y `/ready` separado que compruebe dependencias. No optimizar bundle sin métrica de UX.
- **Compatibilidad:** aditivo; readiness puede requerir ajustar Compose/orquestador.
- **Prueba de corrección:** tests accesibles por teclado, e2e auth críticos y readiness falla selectivamente con cada dependencia.
- **Referencias:** [Kubernetes readiness probes](https://kubernetes.io/docs/concepts/configuration/liveness-readiness-startup-probes/), [WCAG 2.2 keyboard](https://www.w3.org/WAI/WCAG22/Understanding/keyboard.html).
- **1.0.0:** pruebas críticas/readiness son P1; bundle y refactor visual pueden esperar.

## 7. Lo que está correctamente resuelto y no necesita cambios

1. Validación exacta de redirect URI antes de redirigir.
2. PKCE S256 obligatorio para clientes públicos y enlace de código a cliente/redirect/verifier.
3. Firma RS256, algoritmo fijado, JWKS con `kid` y separación entre access/ID/session/dev.
4. ID token con `aud=client_id`, nonce/auth_time y sin permisos; access token con audiencia de recurso.
5. Refresh opaco hasheado, familias, rotación, detección de reutilización y locks PostgreSQL.
6. Panel BFF con cookie opaca HttpOnly, estado/CSRF en Redis y sin JWT en localStorage.
7. Registro público cerrado por defecto.
8. Trigger de base de datos para impedir role-permission cross-app.
9. Rotación publish-before-use y retención derivada del mayor TTL firmado.
10. Redis con AOF/noeviction y redes internas en Compose de producción.
11. SDK con validación local de firma/issuer/audience/type y refresh ante `kid` desconocido.
12. Caché de permisos desactivada por defecto, por lo que la revocación del chequeo remoto es inmediata.

Estas decisiones parecen complejas porque protegen fronteras reales. Simplificarlas eliminando CSRF, volviendo a JWT en el navegador, usando HS256 compartido, fusionando clases de token, purgando claves inmediatamente o confiando solo en validación de aplicación sería una regresión.

## 8. Qué simplificar, eliminar o conservar

### 8.1 Simplificación con valor concreto

- **[shrink] Entitlements:** tres implementaciones → una consulta/función compartida, sin crear interfaces o factories.
- **[native] Transacciones:** repositorios sin commit; una transacción de Session por caso de uso.
- **[native] Integridad:** unicidad y cascadas en PostgreSQL en vez de select-then-insert/cascadas manuales.
- **[delete] Código muerto:** `UserService.audit_repo`, imports/dependencias realmente sin uso y alias de configuración tras una deprecación corta.
- **[native] Conteos:** `COUNT(*)` en BD, no cargar toda la tabla.
- **[yagni] Popup `web_message`:** conservar solo si existe consumidor real; en otro caso elimina frontend, docs y ejemplo custom sin pruebas.

Estimación prudente: **120–250 líneas y 2–3 dependencias** pueden retirarse después de confirmar callers. La meta no es reducir capas por estética, sino eliminar los puntos que hoy divergen o rompen atomicidad.

### 8.2 Propuestas que no valen la pena antes de 1.0.0

- MFA/WebAuthn.
- Federación social/LDAP/SAML.
- Dynamic Client Registration.
- Device Authorization Grant.
- Introspección para tokens opacos de acceso.
- Front-channel/back-channel logout completo.
- Microservicios o separar cada dominio.
- Migración general a TypeScript.
- Rediseño visual completo o sustitución de Ant Design.
- Code splitting solo para silenciar el warning de tamaño.
- Event sourcing, CQRS, broker o outbox mientras una transacción local resuelva el caso.
- Certificación OIDC como condición previa: primero cumplir el perfil declarado y correr la suite; certificar puede ser post-1.0 si el costo no aporta al objetivo institucional inmediato.

### 8.3 Complejidad que debe conservarse

- BFF/CSRF/cookie opaca y contenedor multi-cuenta.
- Validación por clase de token y audiencia.
- Refresh rotation con reuse detection y locks.
- Redis fail-closed para revocación.
- Firma asimétrica y cifrado de claves privadas.
- Rotación de dos fases y solapamiento de JWKS.
- Defensa de integridad cross-app en la base.
- Validación exacta de redirect URIs.

## 9. Comparación mínima con proyectos similares

Keycloak y authentik exponen discovery, UserInfo, revocación y logout estándar, y permiten auditar eventos administrativos. La lección pertinente no es copiar sus decenas de módulos: Minerva solo necesita que el pequeño perfil que ya anuncia sea estándar, descubrible y auditable. Sus funciones de federación, MFA, brokering, flujos configurables y logout multicanal no son requisitos para 1.0.

Referencias: [Keycloak OIDC layers](https://www.keycloak.org/securing-apps/oidc-layers), [Keycloak Admin Guide](https://www.keycloak.org/docs/latest/server_admin/), [authentik logout](https://docs.goauthentik.io/add-secure-apps/providers/oauth2/frontchannel_and_backchannel_logout/).

## 10. Roadmap mínimo hacia 1.0.0

### Gate 0 — decisión pública

1. IIEG decide licencia OSI, copyright, marca y canal de seguridad.
2. Se congela el perfil 1.0 soportado: Authorization Code, PKCE S256, refresh, revocation, UserInfo, discovery/JWKS y logout que realmente se implemente.
3. Se identifican consumidores reales de JSON token legacy, override cross-app y `web_message`.

### Bloque A — seguridad y configuración (P0)

1. H-01: una URL/metadata de migración.
2. H-02: audiencia vinculada al endpoint de permisos y SDK.
3. H-03: retirar redirect abierto y definir logout.
4. H-04: fail-fast de producción y topología canónica TLS.
5. H-05/H-10/H-11: transportar max_age, validar inputs y corregir cutoff.

### Bloque B — consistencia y protocolo (P0)

1. H-06: transacciones por caso de uso.
2. H-07: unicidad compuesta e importación sin carrera.
3. H-08: errores/headers/métodos/metadata OAuth-OIDC.
4. H-09: entorno bloqueado y suite completa estable.

### Bloque C — publicación responsable (P1)

1. H-12: auditoría de mutaciones administrativas.
2. H-15: licencia, SECURITY, CONTRIBUTING, CODE_OF_CONDUCT.
3. H-16: artefactos reproducibles, no-root, tag gated y acciones por SHA.
4. H-17: documentación/versión/ejemplos coherentes.
5. H-19: pruebas web críticas, readiness y simulacro de backup/restore con llave maestra.

### Criterio de release candidate

- Suite backend completa, SDK y frontend verdes en instalación limpia.
- Pruebas negativas H-01 a H-11 pasan.
- Upgrade desde la última versión desplegada y rollback ensayados en copia de datos.
- Build de imágenes reproducible, SCA sin vulnerabilidad explotable no aceptada y SBOM/artefactos trazables.
- Smoke real detrás de TLS/proxy con al menos un consumidor.
- Restauración PostgreSQL + llave de cifrado y rotación/emergencia ensayadas.
- Documentos públicos y licencia aprobados.

Solo entonces etiquetar 1.0.0. Todo el backlog de §8.2 queda explícitamente fuera.

## 11. Fuentes normativas principales

- [RFC 6749 — OAuth 2.0](https://www.rfc-editor.org/rfc/rfc6749.html)
- [RFC 6750 — Bearer Token Usage](https://www.rfc-editor.org/rfc/rfc6750.html)
- [RFC 7009 — Token Revocation](https://www.rfc-editor.org/rfc/rfc7009.html)
- [RFC 7636 — PKCE](https://www.rfc-editor.org/rfc/rfc7636.html)
- [RFC 8414 — Authorization Server Metadata](https://www.rfc-editor.org/rfc/rfc8414.html)
- [RFC 8725 — JWT Best Current Practices](https://www.rfc-editor.org/rfc/rfc8725.html)
- [RFC 9700 — OAuth 2.0 Security BCP](https://www.rfc-editor.org/rfc/rfc9700.html)
- [OpenID Connect Core 1.0](https://openid.net/specs/openid-connect-core-1_0.html)
- [OpenID Connect Discovery 1.0](https://openid.net/specs/openid-connect-discovery-1_0.html)
- [OpenID Connect RP-Initiated Logout 1.0](https://openid.net/specs/openid-connect-rpinitiated-1_0.html)

## 12. Comparación con auditorías, issues y PRs anteriores

Esta comparación se realizó **después** de congelar §§1–11. No había una auditoría anterior versionada en `docs/`; el antecedente recuperable está en los issues #36–#53, sus PRs y el historial Git. Al corte remoto no existe ningún issue abierto.

### 12.1 Correcciones anteriores confirmadas en el estado actual

| Antecedente | Estado verificado hoy |
|---|---|
| #36 / PR #47: límite administrativo y registro | Corregido: el CRUD está en routers admin y el registro público está cerrado por defecto. |
| #37 / PR #48: clases de token | Corregido en su frontera original: access/session/dev/id se rechazan por tipo; panel y SDK validan issuer/audience donde la conocen. |
| #38 / PR #54: doble canje, revalidación y cross-app | Corregidos el ganador único, la revalidación de usuario/app y el vínculo role-permission cross-app, incluida barrera PostgreSQL. |
| #39 / PR #50: revocación Redis | Corregido: AOF/noeviction y secuencia fail-closed. |
| #40 / PR #55: rotación y SDK | Corregido: publish-before-use, retención por TTL máximo, refresh JWKS por `kid`, caché por jti/exp y bearer fuera del payload. |
| #41 / PR #49: sesión panel | Corregido con BFF, cookie opaca, CSRF, rotación de SID y headers defensivos. |
| #42 / PR #56: callbacks y auth_time | Corregido: URL builder, state, response_type y auth_time real. |
| #44/#45/#46/#52 | Borrado de tokens, redirect UI/menú, seed parcial/concurrente y UUID de auditoría están corregidos. |

Estas correcciones no deben reabrirse por preferencia. En especial, BFF y rotación agregaron código, pero su complejidad corresponde a riesgos reales y está respaldada por pruebas específicas.

### 12.2 Hallazgos nuevos o perímetros que quedaron fuera

- **H-01, H-03, H-04, H-07, H-10, H-11, H-12, H-15 y H-16** no tienen issue abierto ni aparecen cubiertos de forma suficiente en el backlog remoto.
- **H-02** es una segunda frontera de audiencia: PR #48 impidió cruzar tipos de token, pero mantuvo deliberadamente genérico `/api/v1/me*`; no vinculó el parámetro `application` al `aud` del access token.
- **H-06** no contradice el “un solo ganador” de #38: el `UPDATE ... used=false` sí es atómico frente a concurrencia, pero `mark_used()` hace commit antes de firma/creación del refresh. La unidad completa de canje aún puede quemar el código sin entregar tokens.
- **H-08** coincide con lo que PR #56 dejó explícitamente fuera: errores OAuth estándar Y1/Y2. La revisión actual añade POST authorize/UserInfo, no-store, challenge bearer y metadata honesta. Se eleva a P0 solo porque README anuncia “OIDC/OAuth completo”.
- **H-09** explica una aparente contradicción: #53 descartó el hang porque un entorno Conda existente ejecutó 138 pruebas en 54 s. La auditoría actual lo reprodujo con una instalación limpia dentro de los rangos declarados, que recolecta 198 y se bloquea en la primera. Ambos hechos pueden ser ciertos; el defecto es no congelar el entorno.
- **H-05** no fue cubierto por #42/PR #56: el backend calcula `max_age` correctamente, pero la SPA creada antes no lo transporta a `/auth/authorize/url`.

### 12.3 Cambios recientes y posible sobreingeniería asistida por agentes

Los cuerpos de PR #49 y #56 declaran expresamente generación con Claude Code; eso acredita asistencia, **no que el código sea incorrecto**. El historial permite conclusiones más precisas:

- PR #49 agregó el BFF (358 inserciones/93 borrados solo en el commit backend, más frontend y pruebas). El núcleo está justificado. En esa misma migración, el commit `7d5df857` introdujo el redirect abierto y `.finally()` de H-03; es un defecto periférico, no razón para retirar el BFF.
- PR #56 añadió dos archivos de pruebas extensos (487 líneas) para callbacks/auth_time. El volumen es alto, pero protege matrices de seguridad y no se propone borrarlo. Su “fuera de alcance” sobre errores estándar sí debe convertirse en trabajo 1.0.
- PR #55 y la migración 009 agregaron bastante código de rotación/concurrencia. La unicidad parcial, publish-before-use y pruebas de carrera están justificadas; simplificarlas sería peligroso. Solo falta el runbook/operación de incidente H-14.
- PR #61 hace que mypy aparezca verde poniendo 14 módulos —incluidos auth y autorización— en cuarentena. Es un gate incremental legítimo, pero no debe presentarse como tipado completo; la lista debe ser un burn-down visible.
- `response_mode=web_message` precede estos PRs y suma contrato custom, ejemplo y frontend. La decisión mínima es comprobar un consumidor real; si no existe, retirarlo en vez de construir más compatibilidad.

No hay evidencia suficiente para atribuir a IA H-01, H-02, H-05 o la arquitectura de repositorios: `git blame` los remonta a junio o a cambios previos. La auditoría evita usar “parece generado” como hallazgo; solo marca complejidad cuando existe costo demostrable.

### 12.4 Conclusión del contraste

La auditoría anterior produjo mejoras sustanciales y cerró riesgos severos. El estado actual es mejor, pero el cierre administrativo de todos los issues creó una falsa sensación de backlog vacío. El roadmap de §10 no repite trabajo corregido: cubre huecos nuevos, perímetros incompletos y condiciones de publicación que todavía no tienen seguimiento.
