# Portal Demo: integración completa con Minerva

Proyecto pequeño y ejecutable que muestra el camino recomendado para un sistema web:

- login OIDC Authorization Code + PKCE;
- callback y errores `access_denied`;
- sesión local con cookie HttpOnly, sin exponer tokens al navegador;
- identidad, roles recibidos y permisos efectivos;
- rutas con `401` por falta de sesión y `403` por falta de permiso;
- refresh token rotatorio;
- logout local con revocación del refresh token;
- vistas navegables de documentos, administración y cuenta;
- previsualizaciones explícitas de los estados 401, 403 y sin acceso al sistema.

> Los roles se muestran únicamente para explicar qué entrega Minerva. El mock, igual que
> cualquier consumidor, autoriza con permisos y nunca con nombres de roles.

## Inicio rápido

### 1. Levanta Minerva

Desde la raíz del repositorio:

```bash
docker compose up --build
```

- Minerva (panel, issuer y API): `http://localhost:3100`
- Backend directo de diagnóstico: `http://localhost:9000`
- Este mock: `http://localhost:8100`

El consumidor solo configura `http://localhost:3100`; esa misma URL sirve login, token,
JWKS y permisos, y coincide con el `issuer` anunciado por Minerva.

### 2. Registra el mock sin escribir JSON ni URLs a mano

1. Entra al panel `http://localhost:3100` como administrador.
2. Abre **Aplicaciones** y selecciona **Importar manifiesto**.
3. Sube [`manifest.minerva.yml`](manifest.minerva.yml).
4. Copia el `Client ID` y el `Client Secret` que Minerva muestra una sola vez.

El manifiesto ya registra exactamente esta callback:

```text
http://localhost:8100/callback
```

### 3. Configura y ejecuta el mock

Requiere Docker Compose y [`just`](https://just.systems/).

```bash
cd examples/minerva-consumer
cp .env.example .env
# pega MINERVA_CLIENT_ID y MINERVA_CLIENT_SECRET en .env
just build
just up
```

El proyecto carga `.env` automáticamente. Abre `http://localhost:8100`: la primera
sección indica con precisión qué variable falta si la configuración está incompleta.

El Compose usa `network_mode: host` para que el contenedor y el navegador compartan
exactamente `http://localhost:3100`. Está pensado para el entorno Linux de desarrollo
de Minerva; no agrega una segunda URL interna al SDK.

`just --list` muestra las recetas disponibles: `build`, `rebuild`, `restart`, `down`,
`down-v`, `logs`, `ps`, `shell`, `config`, `dev` y `test`. Para ejecutarlo sin Docker:

```bash
pip install -e ../../sdk -e '.[dev]'
uvicorn minerva_example.main:app --port 8100 --reload
```

El `-e ../../sdk` no es opcional: es lo que satisface la dependencia `minerva-sdk` del ejemplo.
El SDK no está en PyPI — fuera del monorepo se instala como requisito VCS
(ver [`sdk/README.md`](../../sdk/README.md)).

## Estructura del ejemplo

```text
minerva_example/
├── main.py                    # compone FastAPI, routers y frontend
├── core/
│   ├── config.py              # carga y diagnóstico de configuración
│   └── database.py            # almacén sustituible por Redis/BD
├── modules/
│   ├── auth/
│   │   ├── consts.py          # cookies del módulo
│   │   ├── repository.py      # persistencia de state y sesiones
│   │   ├── service.py         # casos de uso OIDC
│   │   └── router.py          # HTTP: login, callback, refresh y logout
│   └── portal/
│       ├── consts.py          # permisos y datos de demostración
│       ├── repository.py      # acceso a datos del portal
│       ├── service.py         # identidad y autorización
│       └── router.py          # HTTP: configuración y endpoints protegidos
└── frontend/
    ├── index.html   # estructura de la pantalla
    ├── api.js       # llamadas al backend del consumidor
    ├── app.js       # navegación y coordinación de vistas
    ├── views.js     # componentes visuales por estado
    └── app.css      # presentación
```

FastAPI sirve tanto `/` como los assets bajo `/assets`. Cada dominio conserva sus capas,
igual que los módulos del backend de Minerva; `main.py` únicamente registra routers.

### 4. Asigna accesos y prueba resultados

Desde el panel de Minerva, asigna al usuario uno de los roles del manifiesto:

| Rol | Resultado esperado |
|---|---|
| Sin rol | Login termina en “No tienes acceso a esta aplicación” |
| Consulta | `view` devuelve 200; `create` y `manage` devuelven 403 |
| Captura | `view` y `create` devuelven 200; `manage` devuelve 403 |
| Administración | Las tres pruebas devuelven 200 |

El mock se comporta como un portal: sus páginas consultan endpoints protegidos y convierten
las respuestas reales en una vista de login (`401`) o de permiso insuficiente (`403`). En el
inicio también puedes previsualizar esos estados sin fabricar una sesión. La cuenta permite
refrescar tokens, cerrar sesión y elegir otro usuario.

## Qué valor lleva cada variable

| Variable | Valor |
|---|---|
| `MINERVA_ISSUER_URL` | Una sola URL pública de Minerva. Dev: `http://localhost:3100`. Producción: `https://minerva...` |
| `MINERVA_APPLICATION_CODE` | `application.code` del manifiesto: `portal_demo` |
| `MINERVA_CLIENT_ID` | Valor mostrado al crear/importar la aplicación |
| `MINERVA_CLIENT_SECRET` | Valor mostrado una sola vez. Vacío únicamente para clientes públicos |
| `MINERVA_REDIRECT_URI` | Debe coincidir carácter por carácter con el manifiesto: `http://localhost:8100/callback` |

En producción cambian como mínimo las dos URLs públicas: la de Minerva y la callback del
sistema. Usa siempre el código y las credenciales del registro correspondiente a ese entorno.

## Código que se replica en un consumidor real

El SDK genera PKCE y arma la URL; el sistema solo conserva `state` y `code_verifier` en
su almacén de sesión:

```python
from minerva_sdk import MinervaOIDC

oidc = MinervaOIDC()
authorization = oidc.authorization_request()
# guarda authorization.code_verifier por authorization.state
return RedirectResponse(authorization.url)
```

En callback:

```python
tokens = await oidc.exchange_code(code, code_verifier)
```

En APIs que reciben Bearer directamente, la protección sigue siendo una línea:

```python
user = Depends(require_permission("portal_demo.documents.create"))
```

El almacenamiento en memoria de `pending` y `sessions` existe solo para mantener el
mock autocontenido; el `state` sí queda ligado al navegador con una cookie HttpOnly
temporal. Un sistema real debe usar su almacén de sesión compartido existente.
