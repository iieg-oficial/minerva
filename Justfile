set dotenv-load := true

# Archivo Compose sobre el que operan TODAS las recetas. El default construye las
# imágenes desde el código de esta copia del repo; `docker-compose.deploy.yml`
# consume las ya publicadas en ghcr (`MINERVA_ORG`/`MINERVA_VERSION`, ver
# docs/uso-imagen-docker.md). Se elige de tres formas, de mayor a menor prioridad:
#   just file=docker-compose.deploy.yml up          # solo esta invocación
#   MINERVA_COMPOSE=docker-compose.deploy.yml just up
#   MINERVA_COMPOSE=docker-compose.deploy.yml en el .env   # fija el host entero
# Con el compose de deploy no hay nada que construir: `build` avisa y no hace nada,
# y actualizar es `just pull` + `just up`.
file := env_var_or_default("MINERVA_COMPOSE", "docker-compose.yml")

compose := "docker compose -f " + file

# El deploy NO parte del .env de desarrollo: levantaría las imágenes publicadas con
# APP_DEBUG, login de dev y secretos de ejemplo. Su plantilla es la de producción,
# que además trae MINERVA_ORG y MINERVA_VERSION.
env_template := if file == "docker-compose.deploy.yml" { ".env.production.example" } else { ".env.example" }

default:
    @just --list
    @echo ""
    @echo "Compose activo: {{ file }} — para las imágenes de ghcr usa MINERVA_COMPOSE=docker-compose.deploy.yml"

[private]
env:
    @test -f .env || { cp {{ env_template }} .env; echo "Creado .env desde {{ env_template }}; revisa sus valores antes de levantar"; }

# Valida la resolución final del Compose y sus variables.
config: env
    {{ compose }} config

# Construye las imágenes usando la caché disponible.
build: env
    {{ compose }} build

# Levanta Minerva en segundo plano.
up: env
    {{ compose }} up -d

# Levanta Minerva en primer plano y reconstruye si hace falta.
dev: env
    {{ compose }} up --build

# Reconstruye sin caché y recrea todos los contenedores.
rebuild: env
    {{ compose }} build --no-cache
    {{ compose }} up -d --force-recreate

# Reinicia los contenedores existentes.
restart: env
    {{ compose }} restart

# Detiene y elimina contenedores/redes; conserva los datos.
down: env
    {{ compose }} down --remove-orphans

# Detiene Minerva y elimina también PostgreSQL y Redis. Destructivo.
down-v: env
    {{ compose }} down --volumes --remove-orphans

# Sigue los logs de todos los servicios.
logs: env
    {{ compose }} logs -f --tail=200

# Sigue los logs de un servicio: just logs-service backend
logs-service service: env
    {{ compose }} logs -f --tail=200 "{{ service }}"

# Muestra contenedores y healthchecks.
ps: env
    {{ compose }} ps

# Abre una shell en un servicio: just shell backend
shell service="backend": env
    {{ compose }} exec "{{ service }}" sh

# Descarga versiones nuevas de imágenes externas.
pull: env
    {{ compose }} pull
