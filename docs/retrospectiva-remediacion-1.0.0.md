# Retrospectiva de la remediación hacia Minerva 1.0.0

**Fecha:** 22 de julio de 2026

**Comparación:** `origin/main` (`1d75f09`) → `origin/develop` (`adc1753`)

**Fuentes:** `docs/auditoria-1.0.0.md`, `docs/auditoria-claude.md`,
`docs/auditoria-codex.md`, diff Git, issues #36–#53 y PR #47–#61.

**Alcance:** retrospectiva; no propone ni aplica cambios de código.

## 1. Conclusión ejecutiva

Sí hubo un ciclo de trabajo inducido por la primera auditoría y por la forma en que se
convirtió en backlog. Yo recomendé ese roadmap y debo corregir tres errores de criterio:

1. convertí demasiados hallazgos en trabajo inmediato para 1.0.0;
2. agrupé fronteras distintas dentro de issues grandes y criterios de aceptación estrechos;
3. acepté como cierre pruebas escritas para confirmar cada issue, sin exigir una revisión
   adversarial independiente del flujo completo después de integrar los cambios.

Eso **no significa que el trabajo de `develop` sea inútil ni que deba revertirse**. La rama
es sustancialmente más segura que `main`: cerró una escalación administrativa, separó clases
de token, endureció el panel, hizo durable la revocación, corrigió carreras reales, estabilizó
la rotación de claves, eliminó un stub y reparó bugs funcionales. La mayor parte debe
conservarse.

El error fue de proceso y alcance: pasamos de una auditoría amplia a 13 PR en unos tres días,
sin una pausa de integración ni una revisión independiente entre bloques. Esto permitió que
se cerraran exactamente los escenarios descritos por los issues, mientras quedaron sin mirar
fronteras contiguas como audiencia en `/me/permissions`, transporte de `max_age`, configuración
de producción, transacción completa del canje y logout.

Las dos auditorías posteriores están descalibradas en sentidos opuestos:

- `auditoria-claude.md` es demasiado optimista: reduce el cierre a dos rojos y documentación,
  pero omite varios defectos reproducibles.
- `auditoria-codex.md` detecta más problemas reales, pero vuelve a inflar el bloqueo al tratar
  once hallazgos técnicos como P0 homogéneos.

El camino correcto no es abrir otros 19 issues. Es congelar funcionalidad y cerrar **cinco
paquetes acotados de estabilización**, descritos en §8.

## 2. Qué ocurrió en números

Entre `main` y el `develop` remoto actual hay:

| Métrica | Resultado |
|---|---:|
| PR integrados por la remediación | 13 (#47–#61, con huecos de numeración) |
| Archivos modificados | 125 |
| Inserciones | 7,005 |
| Eliminaciones | 1,634 |
| Crecimiento neto | 5,371 líneas |
| Crecimiento neto de pruebas backend + SDK | 3,060 líneas |
| Proporción del crecimiento neto que son pruebas | 57 % |
| Reviews registrados por GitHub en esos 13 PR | 0 |

El volumen por sí solo no demuestra sobreingeniería: más de la mitad del crecimiento neto son
pruebas, varias de concurrencia y seguridad. Sí demuestra que el cambio era demasiado grande
para validarlo como una sola ola.

La señal de proceso más grave es el tiempo de revisión. GitHub registra al mismo autor abriendo
y fusionando los PR sin reviews. Ejemplos:

| PR | Cambio | Tamaño | Tiempo apertura→merge |
|---|---|---:|---:|
| #49 | BFF/cookie/Redis/CSRF/frontend | +2,387 / −742, 53 archivos | ~2 min |
| #54 | concurrencia/revalidación/trigger | +910 / −32, 11 archivos | ~5 min |
| #55 | claves + SDK + migración + CI | +1,785 / −117, 30 archivos | ~4 min |
| #61 | mypy con cuarentena | +24, 2 archivos | ~5 min |

No es materialmente posible hacer una revisión humana adversarial de esos tres PR grandes en
ese intervalo. Las suites podían verificar el comportamiento esperado; no podían sustituir la
revisión de límites y fallos laterales.

## 3. Responsabilidad del resultado

### 3.1 Error de la auditoría y del roadmap que propuse

- El primer reporte sí separó semáforo de prioridad, pero después convertí casi todos los
  rojos en una secuencia de ejecución inmediata. En la práctica anulé esa distinción.
- Los issues agruparon varios problemas por tema, no por invariante. #38 mezcló doble canje,
  revalidación y relaciones cross-app; #40 mezcló rotación, cachés y fuga del bearer; #41
  mezcló sesión, multi-cuenta, CSRF, proxy y headers.
- Los criterios de cierre se concentraron en reproducir el bug original. No exigieron revisar
  callers hermanos ni hacer fault injection después del punto corregido.
- El roadmap no incluyó un gate de integración entre fases: actualizar `develop`, volver a
  auditar el flujo completo y decidir si el siguiente bloque aún era necesario.
- La primera auditoría no partió de un entorno reproducible. Eso permitió declarar después que
  el hang de pruebas estaba “descartado” en un entorno Conda, aunque una resolución limpia hoy
  vuelve a bloquearse.

### 3.2 Error del proceso de integración

- No hubo una segunda persona ni un agente independiente revisando los PR ya integrados.
- Los PR se auto-fusionaron pocos minutos después de abrirse y sin review registrado.
- Cerrar todos los issues se interpretó como backlog vacío, aunque varios “fuera de alcance”
  quedaron únicamente en el cuerpo de los PR.
- Los nombres de cierre fueron más fuertes que el comportamiento: “atomicidad del canje” solo
  garantizó un ganador; “cumplimiento OIDC” dejó elementos normativos fuera; “mypy limpio”
  significa realmente 14 módulos ignorados.

### 3.3 Qué no debe concluirse

- La asistencia de IA no vuelve incorrecto un cambio. Solo PR #49, #54, #56 y #57 dejan una
  marca explícita de generación con Claude Code en su cuerpo; no hay evidencia para atribuir
  automáticamente los demás defectos a IA.
- Las pruebas extensas no son automáticamente bloat. Las carreras de refresh, claves y
  constraints de PostgreSQL necesitan pruebas reales y deben conservarse.
- El usuario no provocó el ciclo por seguir el roadmap. El problema comprobable fue la falta
  de un mecanismo de desacuerdo y reevaluación dentro del propio roadmap.

## 4. Evaluación de cada issue y PR

| Issue / PR | Resultado real | Decisión retrospectiva |
|---|---|---|
| #36 / #47 — límite admin y registro | Cerró una escalación completa y eliminó 445 líneas de CRUD duplicado. | **Correcto y mínimo. Conservar.** Fue el mejor cambio de la ola. |
| #37 / #48 — clases de token | Impidió que access/dev/id cruzaran a sesión de panel. | **Correcto. Conservar.** Faltó vincular la aplicación pedida en permisos con `aud`; es un perímetro distinto, no fracaso de `typ`. |
| #41 / #49 — BFF del panel | Quitó JWT de `localStorage`, añadió cookie opaca, CSRF y SID rotado. | **La frontera es válida y debe conservarse.** El alcance multi-cuenta/proxy/frontend fue enorme e introdujo el open redirect y el falso éxito de logout. No reescribir el BFF; corregir su periferia. |
| #39 / #50 — Redis durable | AOF, `noeviction` y orden fail-closed evitan resurrección trivial de credenciales. | **Correcto. Conservar.** La coordinación Redis→PG es compleja porque protege una garantía real. |
| #44 / #51 — borrado de app | Añadió auth codes, refresh tokens y retención de audit logs a la cascada. | **Corrige el bug.** Amplía una cascada manual frágil ya existente. No rehacerla antes de 1.0 salvo para corregir atomicidad; migrar a FKs nativas después. |
| #38 / #54 — canje/revalidación/cross-app | Garantiza un ganador y revalida sujetos; el trigger protege la BD. | **Parcialmente correcto.** El título sobrevendió “atomicidad”: `mark_used()` confirma antes de emitir/persistir el resto. Mantener locks/trigger y completar una sola transacción, sin otra capa. |
| #40 / #55 — claves y SDK | Publish-before-use, retención correcta, refresh por `kid`, caché segura y sin bearer en claims. | **Correcto y justificado. Conservar.** El issue debió dividirse para revisión. Operación de emergencia puede quedar en runbook, no requiere otra arquitectura antes de 1.0. |
| #42 / #56 — authorize/auth_time | Corrigió URL, `state`, `response_type` y frescura real. | **Correcto pero incompleto.** La SPA sigue descartando `max_age`; “cumplimiento OIDC” no debía usarse como cierre general. Las pruebas amplias sí aportan valor. |
| #43 / #57 — Google | Eliminó stub, configuración y dependencia sin una decisión institucional para sostenerlo. | **Correcto y alineado con YAGNI. Conservar.** |
| #52 / #58 — UUID de auditoría | Corrigió un FK/value mismatch aislado. | **Correcto y mínimo. Conservar.** También evidenció que la auditoría administrativa completa sigue pendiente. |
| #46 / #59 — seed | Repara estado parcial e impide carrera en el seed admin. | **Bug real corregido, solución sobreextendida.** El advisory lock protege solo seed mientras autoimport sigue ejecutándose por worker. Para producción es más simple ejecutar init una vez. No retirar el lock ahora. |
| #45 / #60 — UI | Corrigió dos bugs visibles y eliminó un método muerto. | **Correcto y mínimo. Conservar.** |
| #53 / #61 — mypy | Impide errores nuevos fuera de 14 módulos en cuarentena. | **Útil como gate incremental.** No es “tipado limpio” y no bloquea 1.0; mostrar siempre el tamaño de la cuarentena. |

## 5. Origen de los hallazgos de la auditoría nueva

La pregunta importante no es cuántos hallazgos hay, sino si son regresiones de la remediación,
deuda previa omitida o trabajo ya diferido conscientemente.

### 5.1 Regresiones o cierres incompletos de esta ola

| Hallazgo Codex | Origen comprobado | Lectura retrospectiva |
|---|---|---|
| H-03 logout abierto y `.finally()` | Commit `7d5df857`, dentro de PR #49. | **Regresión directa.** Debió detectarla una prueba negativa de destino no registrado y fallo de red. |
| H-04 topología de cookie | La plantilla de dos hosts era previa; PR #49 añadió una cookie `__Host-` host-only sin reconciliar esa topología. | **Incompatibilidad activada por el BFF.** Falló la revisión de despliegue extremo a extremo. |
| H-06 canje confirmado por partes | El commit anticipado existía; PR #54 cambió el claim a update atómico pero conservó el commit antes de emitir tokens. | **Cierre semántico incompleto.** Se probó “un ganador”, no “todo o nada”. |
| H-17 contrato de logout/documentación | Deriva del nuevo contrato BFF y documentación actualizada de forma inconsistente. | **Regresión documental de la ola.** |

### 5.2 Deuda previa que la primera auditoría no detectó

| Hallazgo Codex | Evidencia de antigüedad | Valoración |
|---|---|---|
| H-01 URL/metadata Alembic | `alembic/env.py` y `effective_db_url` vienen de junio y están en `main`. | Real; es preparación de release, no una regresión. |
| H-02 permisos de B con token A | El override del SDK y `get_me_permissions` existen desde el primer Dev Kit y están en `main`. | Real y sensible; la primera auditoría se detuvo en confusión de tipos y no siguió la audiencia hasta el permiso remoto. |
| H-05 `max_age` perdido | `AuthorizePage` omite el parámetro desde antes de esta remediación. | Real; #42 corrigió backend sin probar navegador→BFF→backend. |
| H-07 autoimport concurrente | Modelos sin unicidad y select-then-insert son previos. | Real, pero el cierre mínimo es desactivar autoimport en producción o ejecutar init una vez; no construir otro coordinador. |
| H-10 límites bcrypt/PKCE | Los schemas no tenían esos límites; bcrypt 5 hace visible el problema. | Real y barato de corregir; severidad baja, sensibilidad roja por ser trust boundary. |
| H-11 corte del mismo segundo | La comparación `<` ya estaba en `main`. | Real; corrección y prueba pequeñas. |

### 5.3 Trabajo conocido que no se implementó en esta ola

- H-08 ya aparecía como Y1/Y2 y conformance en `auditoria-1.0.0.md`; PR #56 lo dejó
  explícitamente fuera. No es un descubrimiento totalmente nuevo.
- H-12 auditoría administrativa era Y4 del reporte original.
- H-13 reconciliación de manifests era Y3 y se decidió mantener importación aditiva.
- H-14 operación de clave comprometida quedó documentada como fuera de alcance en PR #55.
- H-15 licencia/comunidad era G1–G3 y nunca se implementó.
- H-16 supply chain era G5–G6/Y7; sigue pendiente.
- H-19 readiness, observabilidad y falta de pruebas frontend ya aparecían como trabajo de
  operación/calidad, aunque la pérdida de `max_age` demuestra que al menos un smoke web sí es
  necesario.

Por tanto, la auditoría nueva no demuestra que los 13 PR hayan creado once bloqueadores. Solo
H-03 es una vulnerabilidad nueva inequívoca; H-04 y H-17 son incompatibilidades derivadas del
BFF, y H-06 es un cierre incompleto. El resto es deuda anterior o alcance diferido.

## 6. Calibración de las tres auditorías

### 6.1 `auditoria-1.0.0.md`

**Acertó:** encontró riesgos severos y reproducibles que sí justificaban cambios: escalación
administrativa, confusión de tokens, Redis volátil, rotación defectuosa, bearer expuesto,
callbacks rotos, FK de borrado y seed parcial.

**Falló:** propuso cinco fases de uno o dos sprints cuando el objetivo era el camino mínimo;
después sus rojos se tradujeron casi completos a ejecución. No verificó suficientemente
configuración, migraciones, navegador completo ni una instalación limpia. Su roadmap debió
detenerse tras #47/#48 para volver a medir.

### 6.2 `auditoria-claude.md`

**Acertó:** reconoce que RS256, PKCE, refresh rotation, Redis fail-closed, BFF y key rotation
están bien resueltos; también identifica correctamente el open redirect, la documentación de
logout y duplicación de entitlements.

**Falló:** concluye que con open redirect, documentación y licencia Minerva ya es publicable.
No detecta el cruce de audiencia, `max_age`, configuración fail-open, transacción parcial,
autoimport concurrente, entradas que producen 500 ni la carrera de invalidación. Su resultado
de 185+13 pruebas depende de un entorno existente y no responde a la resolución limpia que se
bloquea. No es una base suficiente para liberar.

### 6.3 `auditoria-codex.md`

**Acertó:** siguió flujos completos y realizó pruebas negativas que las suites dirigidas no
cubrían. H-02, H-03, H-04, H-05, H-10 y H-11 tienen reproducción concreta. También separa qué
complejidad debe conservarse.

**Falló en prioridad:** agrupa vulnerabilidades, robustez de input, interoperabilidad,
reproducibilidad y deuda operativa bajo once P0. H-01, H-06, H-09 y H-10 son problemas reales,
pero no tienen el mismo riesgo inmediato que H-02/H-03. H-12–H-19 son mayormente backlog ya
conocido. Convertir cada H en un proyecto bloquearía otra vez la publicación y repetiría el
ciclo que esta retrospectiva busca cortar.

## 7. Qué complejidad conservar y qué no ampliar

### Conservar

- separación `typ` + `aud` por endpoint;
- BFF del panel, cookie opaca, CSRF, SID rotado y estado fuera del navegador;
- refresh rotation, detección de reúso y locks de PostgreSQL;
- orden fail-closed Redis→PostgreSQL;
- key rotation publish-before-use, índices parciales y refresh JWKS por `kid`;
- trigger cross-app de rol/permiso;
- pruebas de concurrencia y seguridad ya escritas.

Revertir cualquiera de estas piezas reabriría riesgos comprobados y costaría más que corregir
sus defectos periféricos.

### No ampliar antes de 1.0

- no limpiar los 14 módulos de mypy como proyecto separado;
- no crear un framework genérico de transacciones ni repositorios nuevos;
- no hacer una reconciliación destructiva de manifests; documentar modo aditivo;
- no automatizar toda respuesta a compromiso de claves; basta un runbook ensayado;
- no hacer code splitting ni rediseño visual sin una métrica de UX;
- no migrar toda la cascada manual a FKs en esta fase;
- no implementar MFA, SCIM, ABAC, multitenancy ni nuevos grants;
- no construir más compatibilidad para `response_mode=web_message`; primero comprobar si existe
  un consumidor real.

### Simplificar solo al tocar una causa raíz

- una URL de base de datos para runtime y Alembic;
- una señal de producción y un origen público coherente;
- un commit por caso de uso, no por método de repositorio;
- import/seed como paso único de inicialización en producción;
- cálculo compartido de entitlements solo si se toca H-02 y reduce realmente los tres caminos;
- `COUNT(*)` únicamente donde se corrija el total filtrado de auditoría.

No se recomienda un refactor general antes de 1.0.

## 8. Roadmap mínimo recalibrado

El siguiente ciclo debe empezar con congelamiento funcional: ningún feature nuevo ni limpieza
general. Los hallazgos se agrupan por una sola frontera verificable, no por archivo o módulo.

### Paquete 1 — fronteras de sesión y audiencia

- H-02: un access token solo puede pedir permisos de su propia audiencia.
- H-03: logout nunca acepta un destino externo no registrado y no navega si falla.
- H-05: transportar `max_age` o retirar la afirmación de soporte hasta hacerlo.
- H-11: invalidación inclusiva para tokens emitidos en el mismo segundo.

**Gate:** cuatro pruebas negativas pequeñas y un smoke de navegador. Sin refactor de BFF/SDK.

### Paquete 2 — configuración e inicialización reproducibles

- H-01: una URL efectiva para runtime/Alembic y metadata no vacía.
- H-04: una sola señal de producción y topología pública de un origen compatible con `__Host-`.
- H-07: autoimport apagado en producción o ejecutado una sola vez antes de los workers.

**Gate:** matriz de config que falla rápido, `alembic check` y arranque real detrás del proxy.
No agregar otro lock distribuido para manifests antes de demostrar que hace falta.

### Paquete 3 — contrato OAuth/OIDC e inputs

- errores estándar, `no-store`, metadata verdadera y métodos POST obligatorios del perfil OIDC;
- límites explícitos para password bcrypt y verifier PKCE;
- corregir la documentación de logout.

**Gate:** tabla pequeña de requests positivas/negativas. Si no se implementa una parte del
perfil, se deja de anunciar “completo”; no se crea compatibilidad especulativa.

### Paquete 4 — consistencia y validación de release

- completar la transacción del canje y del borrado de rol con fault injection;
- congelar/constreñir las dependencias que ejecutará CI;
- aislar suites backend/SDK y ejecutar todas las pruebas en instalación limpia;
- mantener PostgreSQL y Redis reales para las pruebas que dependen de sus garantías.

**Gate:** merge commit limpio con la misma resolución que el artefacto de release. No se acepta
“pasa en mi Conda” ni mypy verde sin reportar su cuarentena.

### Paquete 5 — publicación honesta

- decisión jurídica y `LICENSE`;
- `SECURITY.md` y `CONTRIBUTING.md` mínimos;
- versión única y corrección de documentación/topología;
- el workflow de tag debe depender del CI y usar `npm ci`.

**Gate:** release candidate instalable, documentación comprobada y un review externo. El resto
de supply chain, audit log exhaustivo, readiness avanzada y refactors pasan a 1.0.1.

## 9. Nueva regla de trabajo para evitar otro ciclo

1. **Un hallazgo no se convierte automáticamente en issue.** Primero debe estar reproducido y
   demostrar por qué bloquea el contrato elegido para 1.0.
2. **Un issue protege un invariante.** No se vuelven a mezclar backend, SDK, frontend, migración
   y operación salvo que sean inseparables para ese invariante.
3. **Prueba del bug + prueba del borde vecino.** Ejemplo: al corregir logout, probar destino
   inválido y fallo de red; al corregir `max_age`, probar navegador hasta ID token.
4. **Review independiente antes del merge.** Ningún cambio de auth, sesión, claves, migración o
   permisos se auto-fusiona sin un segundo pase sobre el diff final.
5. **Reauditoría breve por paquete.** No esperar a completar toda la lista para descubrir que el
   supuesto cierre creó una frontera nueva.
6. **Estado honesto.** “Mypy con 14 módulos en cuarentena”, “perfil OIDC soportado”, “un ganador
   concurrente”; no usar etiquetas más fuertes que la garantía real.
7. **Stop rule:** si un paquete crece a más de una frontera o exige una nueva abstracción, se
   detiene y se reconsidera la solución mínima antes de seguir escribiendo código.

## 10. Dictamen final

`develop` no debe desecharse ni fusionarse todavía a `main`.

La remediación previa arregló problemas graves y construyó una base más fuerte, pero su ritmo y
forma de validación produjeron una falsa sensación de cierre. La respuesta tampoco es otra ola
de arquitectura: es una estabilización corta, enfocada en cinco paquetes y seguida por una
revisión verdaderamente independiente.

La lección principal es concreta: **las pruebas demostraron que cada issue se había
implementado; no demostraron que Minerva, como sistema integrado, estuviera lista**. El proceso
1.0 debe invertir esa prioridad.

## 11. Referencias

- [OAuth 2.0 Security Best Current Practice — RFC 9700](https://www.rfc-editor.org/rfc/rfc9700.html)
- [OAuth 2.0 — RFC 6749](https://www.rfc-editor.org/rfc/rfc6749.html)
- [OpenID Connect Core 1.0](https://openid.net/specs/openid-connect-core-1_0-18.html)
- [JWT Best Current Practices — RFC 8725](https://www.rfc-editor.org/rfc/rfc8725.html)
- [PKCE — RFC 7636](https://www.rfc-editor.org/rfc/rfc7636.html)
- [GitHub PR #47–#61](https://github.com/iieg-oficial/minerva/pulls?q=is%3Apr+is%3Amerged+base%3Adevelop)
