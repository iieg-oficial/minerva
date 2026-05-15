# Minerva

Gestor de identidad y accesos (IAM/SSO) centralizado del ecosistema IIEG, basado en
[Authentik](https://goauthentik.io/). Un solo lugar para usuarios, grupos, MFA y
single sign-on de todos los servicios del instituto.

> **Estado:** repo construido y listo. La conexión al ecosistema (gateway-hub y demás
> servicios) queda **pendiente** hasta después del lanzamiento LTS — ver
> [`docs/pendientes/conexion-ecosistema.md`](docs/pendientes/conexion-ecosistema.md).
> Primer servicio a proteger: la consola de Acervo.

## Requisitos

- Docker y Docker Compose
- Red Docker externa `iieg-network` (la crea `make network`)
- `openssl` (para generar secretos)

## Inicio rápido

```bash
cp .env.example .env
make secrets          # genera valores aleatorios; pegarlos en .env
# editar el resto del .env (emails, dominio)
make up               # levanta authentik server + worker + db + redis
```

Authentik queda en `http://127.0.0.1:9000` (sólo localhost en la VM). El acceso
público será vía gateway-hub bajo `/auth/` una vez integrado.

Primer login: usuario `AUTHENTIK_BOOTSTRAP_EMAIL` / `AUTHENTIK_BOOTSTRAP_PASSWORD`.

## Probar que funciona

El repo trae un ambiente de prueba que valida el flujo de forward auth de punta a
punta **sin tocar el ecosistema real**. Ver [`test/README.md`](test/README.md).

```bash
make up
make test-up
# abrir http://localhost:8088/acervo/console/
```

## Estructura

```
minerva/
├── docker-compose.yml      # authentik server + worker + db (postgres) + redis
├── .env.example
├── Makefile
├── blueprints/             # configuración declarativa de Authentik (se aplica al arrancar)
│   ├── 00-groups.yaml          # grupos RBAC (espejo del modelo de mariachi)
│   ├── 10-acervo-console.yaml  # proxy provider + app de la consola de Acervo
│   ├── 90-embedded-outpost.yaml# registra los proxy providers en el outpost
│   └── stubs/                  # blueprints OIDC preparados (.yaml.example, no se aplican)
├── gateway/                # snippets de nginx listos para copiar a gateway-hub
├── test/                   # ambiente de prueba local (gateway + app dummy)
└── docs/
    ├── context.md          # referencia completa del proyecto
    ├── integraciones.md    # cómo conectar cada servicio
    └── pendientes/
        └── conexion-ecosistema.md
```

## Comandos

```bash
make up / down / restart / logs / ps
make secrets         # genera secretos para el .env
make test-up / test-down / test-logs
```

## Componentes

| Contenedor | Imagen | Función |
|---|---|---|
| `minerva-server` | `ghcr.io/goauthentik/server` | API + UI + embedded outpost (forward auth) |
| `minerva-worker` | `ghcr.io/goauthentik/server` | Tareas async, aplica blueprints |
| `minerva-db` | `postgres:16-alpine` | Base de datos de Authentik (dedicada) |
| `minerva-redis` | `redis:7-alpine` | Cache y colas |

## Cómo funciona la protección de servicios

- **Servicios sin auth propia** (consola de Acervo): *forward auth*. gateway-hub
  consulta el embedded outpost (`auth_request`) en cada request; sin sesión,
  redirige al login de Minerva.
- **Servicios con auth propia o que soportan OIDC** (GeoServer, Grafana, MARIACHI,
  SIEEJ, MapaLab): *OIDC*. Cada servicio delega el login en Minerva y recibe un
  token con la identidad y los grupos del usuario.

Toda la configuración (apps, providers, grupos, outpost) se versiona como
**blueprints** en `blueprints/` — se aplican solos al arrancar, reproducibles.

## Licencia

MIT - IIEG Jalisco
