<div align="center">

<img src="minerva-banner.png" alt="Minerva — Autenticación y gestión de accesos" width="100%">

### El sistema institucional de identidad, autenticación y autorización del IIEG

[![CI](https://github.com/iieg-oficial/minerva/actions/workflows/ci.yml/badge.svg)](https://github.com/iieg-oficial/minerva/actions/workflows/ci.yml) [![Versión](https://img.shields.io/badge/versi%C3%B3n-1.0.0-5C2472)](CHANGELOG.md) ![OIDC](https://img.shields.io/badge/OIDC-OpenID%20Connect-5C2472) ![RS256](https://img.shields.io/badge/JWT-RS256%20%2F%20JWKS-2e4372) ![Python](https://img.shields.io/badge/python-3.12%2B-2e4372) [![Licencia](https://img.shields.io/badge/licencia-AGPL--3.0--only-FF8300)](LICENSE)

</div>

---

## 🎯 Qué es Minerva

Minerva es el proveedor de identidad del **Instituto de Información Estadística y Geográfica de
Jalisco (IIEG)**. Funciona como un inicio de sesión único (SSO) institucional interno: las plataformas del
instituto redirigen su login hacia Minerva, que autentica al usuario, revisa sus permisos y
devuelve un token firmado — nadie más vuelve a implementar login ni a guardar contraseñas.

## ✨ Qué resuelve

- 🔐 **OIDC / OAuth 2.0 completo** — Authorization Code + PKCE, discovery, JWKS, refresh con rotación y revocación.
- 🔑 **Firma RS256 con rotación de claves** — sin secretos compartidos entre sistemas.
- 🧩 **Permisos declarativos por manifiesto** — `{app}.{recurso}.{acción}`, nunca roles hardcodeados en el consumidor.
- 👥 **Selector de cuentas multi-sesión** — cambia de cuenta sin volver a teclear credenciales.
- 🧰 **SDK oficial para FastAPI** — `get_current_user` / `require_permission`, sin reimplementar validación de JWT.
- 🐳 **Docker-first** — un `docker compose up`, o consume las imágenes ya publicadas en `ghcr.io`.

## ⚖️ Principio rector

> Los sistemas definen *qué* acciones existen. Minerva define *quién* puede hacerlas.
> Los sistemas consumidores validan **permisos**, nunca roles.

Un sistema declara sus permisos (`portal_demo.documents.create`, `portal_demo.documents.view`, …) en un
manifiesto declarativo. Minerva administra qué usuarios tienen esos permisos, vía roles y grupos.
El sistema consumidor solo pregunta *"¿este usuario puede hacer X?"* — nunca decide localmente con
`if user.role == "Admin"`. Esa separación es lo que hace que la autorización sea auditable,
consistente entre plataformas y responsabilidad de un solo equipo.

## 💡 Por qué existe

Antes de Minerva, cada sistema del instituto resolvía login y permisos por su cuenta: contraseñas
propias, tablas de roles propias, criterios de "quién puede qué" distintos de un sistema a otro y
sin un lugar único donde auditarlo. Minerva centraliza esa responsabilidad sin acoplar los sistemas
entre sí: cada uno sigue dueño de *qué* funcionalidades expone, Minerva es la única fuente de
verdad de identidad y acceso.

Se distribuye también como **Minerva Dev Kit**: cualquier equipo puede levantar su propia instancia
local para desarrollar contra el mismo contrato OIDC que usará en producción, sin depender de un
servidor compartido — compatible con la futura Minerva Central del instituto.

## 🗂️ Mapa del proyecto

| Carpeta | Qué es |
|---|---|
| [`backend/`](backend) | API FastAPI + SQLModel + PostgreSQL — el proveedor de identidad en sí |
| [`frontend/`](frontend) | Panel administrativo y pantallas de login/autorización (React + Ant Design) |
| [`sdk/`](sdk) | `minerva_sdk`: login OIDC/PKCE, tokens y permisos sin reimplementar el protocolo |
| [`manifests/`](manifests) | Manifiestos YAML que declaran las aplicaciones, permisos y roles de los sistemas consumidores |
| [`examples/minerva-consumer/`](examples/minerva-consumer) | Mock ejecutable de login, logout, roles, permisos y errores 401/403 |
| [`docs/`](docs) | Arquitectura, glosario OIDC, despliegue e integración — ver abajo |

## 🏷️ Versionado

La versión del proyecto es la de [`backend/pyproject.toml`](backend/pyproject.toml), y es la misma
que el tag de release (`vX.Y.Z`) y la etiqueta de las imágenes en ghcr. El backend la reporta en
`GET /` y en `/openapi.json` leyéndola del paquete instalado; el badge de arriba,
`.env.production.example` y `frontend/package.json` la repiten, y
`backend/tests/test_version_alignment.py` falla si alguna se queda atrás.

**`minerva_sdk` versiona por su cuenta** ([`sdk/pyproject.toml`](sdk/pyproject.toml)): lo instalan
sistemas consumidores con su propio ritmo de actualización, así que su número no sigue al del
servidor. La diferencia es deliberada, no un descuido. Por eso tiene su propio
[changelog](sdk/CHANGELOG.md) y declara qué Python, FastAPI y httpx soporta —y qué versión del SDK
viaja en qué release— en [«Compatibilidad y versiones»](sdk/README.md#compatibilidad-y-versiones).

## 📚 Guías

Este README es la portada; el detalle técnico vive en `docs/` para no duplicarse ni quedar viejo:

- **[Arquitectura](docs/arquitectura.md)** — cómo está construido Minerva, diagramas de flujo OIDC, capas del backend.
- **[Integración](docs/integracion.md)** — guía paso a paso para conectar un sistema consumidor (manifiesto, PKCE, SDK, troubleshooting).
- **[Despliegue](docs/despliegue.md)** — desarrollo, producción, endurecimiento y mantenimiento (rotación de claves, backups).
- **[Uso por imagen Docker](docs/uso-imagen-docker.md)** — consumir Minerva desde `ghcr.io` sin clonar el repositorio.
- **[Glosario OIDC/OAuth](docs/glosario.md)** — los términos del protocolo, explicados una sola vez.
- **[Cómo contribuir](CONTRIBUTING.md)** — entorno, ramas, commits, validaciones y revisión.
- **[Política de seguridad](SECURITY.md)** — cómo reportar una vulnerabilidad en privado.

## 🚀 Arrancar en local

Requiere Docker Compose y [`just`](https://just.systems/).

```bash
cp .env.example .env
just build
just up
```

Panel en `http://localhost:3100`, API en `http://localhost:9000`. El resto — variables de entorno,
usuario administrador por defecto, checklist de producción — está en
**[`docs/despliegue.md`](docs/despliegue.md)**.

`just --list` muestra las recetas operativas: `build`, `rebuild`, `restart`, `down`,
`down-v`, `logs`, `logs-service`, `ps`, `shell`, `config`, `pull` y `dev`. Si `.env`
no existe, la primera receta lo crea desde `.env.example`.

Las mismas recetas operan el despliegue por imágenes de `ghcr.io`
(`docker-compose.deploy.yml`): declara `MINERVA_COMPOSE=docker-compose.deploy.yml` en el `.env`
—o pásalo suelto con `just file=docker-compose.deploy.yml <receta>`— y ahí el `.env` se siembra
desde `.env.production.example`. Detalle en
**[`docs/uso-imagen-docker.md`](docs/uso-imagen-docker.md)**.

## 📄 Licencia

Copyright (C) 2026 **Instituto de Información Estadística y Geográfica de Jalisco (IIEG)**.

Minerva es software libre bajo la **[GNU Affero General Public License v3.0](LICENSE)**
(`AGPL-3.0-only`). Puedes usarlo, estudiarlo, modificarlo y redistribuirlo; si lo despliegas
como servicio accesible por red, la AGPL te obliga a ofrecer el código fuente —con tus
modificaciones— a quienes lo usen.

**Excepción: el SDK es Apache-2.0.** El paquete [`sdk/`](sdk/) (`minerva_sdk`) se distribuye
bajo la **[Apache License 2.0](sdk/LICENSE)**, no bajo AGPL. Es una librería que los sistemas
consumidores importan en su propio código: integrarse con Minerva no obliga a nadie a liberar
su plataforma.

Se distribuye **sin garantía** de ningún tipo, en los términos de cada licencia.
