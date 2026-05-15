# Changelog

Todos los cambios notables del proyecto se documentan en este archivo.

El formato esta basado en [Keep a Changelog](https://keepachangelog.com/es-ES/1.1.0/),
y este proyecto se adhiere a [Versionado Semantico](https://semver.org/lang/es/). Bumps
por caracteristica registrada en commit; mientras el repo no esta conectado al ecosistema
(ver `docs/pendientes/conexion-ecosistema.md`) seguimos en `0.x`.

## [No publicado]

---

## [0.1.0] - 2026-05-15

### Initial release del stack Authentik

Repo construido como base para SSO/IAM del ecosistema IIEG. Pendiente de conexion al
gateway-hub y servicios protegidos (primer caso: consola de Acervo).

#### Agregado

- **`docker-compose.yml`** con Authentik (server + worker) + Postgres 18 + Redis 8 + 4
  volumenes nombrados (`minerva_db`, `minerva_redis`, `minerva_media`, `minerva_templates`,
  `minerva_certs`). Red propia `minerva-net` + `iieg-network` (external) para que en el
  futuro `gateway-hub` pueda apuntar al `server` por nombre DNS.
- **`Makefile`** con targets `up`, `down`, `restart`, `logs`, `ps`, `secrets`, `network`,
  y un subambiente de prueba (`test-up/down/logs/ps`) para validar el proxy authentik
  contra una app dummy sin tocar el resto del ecosistema.
- **`blueprints/`** y `gateway/` con configuraciones declarativas para Authentik (flujos,
  outposts, providers).
- **`docs/`** con propuesta, decisiones de arquitectura y `pendientes/conexion-ecosistema.md`.
- **`README.md`** con quickstart, requisitos y nota de estado (no conectado).

#### Notas

- Authentik server expuesto solo en `127.0.0.1:9000` (sin binding publico). El gateway-hub
  sera el unico punto de entrada cuando se conecte.
- `POSTGRES_PASSWORD`, `AUTHENTIK_SECRET_KEY`, `AUTHENTIK_BOOTSTRAP_TOKEN` se generan con
  `make secrets` y NO tienen default en `.env.example` (compose falla explicito si faltan).
- Pinning: `postgres:18-alpine` y `redis:8-alpine` (consistente con el resto del ecosistema:
  mariachi, dataengine y sitio2026 ya estan en PG18; solo CKAN se queda en PG16 por
  compatibilidad de la imagen base).
