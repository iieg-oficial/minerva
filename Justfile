set dotenv-load := true

compose := "docker compose -f docker-compose.yml"

default:
    @just --list

[private]
env:
    @test -f .env || { cp .env.example .env; echo "Creado .env desde .env.example"; }

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
