#!/bin/bash
# Backup de PostgreSQL (incluye la tabla signing_keys: las claves RSA de firma
# cifradas en reposo viven ahí; sin backup de la BD se pierden las claves OIDC).
#
# Uso recomendado, colgado de un cron del host (ej. diario):
#   docker compose exec -T postgres bash -c \
#     'PGPASSWORD="$POSTGRES_PASSWORD" pg_dump -U "$POSTGRES_USER" -d "$POSTGRES_DB"' \
#     > backups/minerva-$(date +%Y%m%d-%H%M%S).sql
#
# Este script asume que se ejecuta DENTRO del contenedor `postgres` (o con acceso
# directo a un psql/pg_dump compatible) y que las variables POSTGRES_USER,
# POSTGRES_PASSWORD, POSTGRES_DB están en el entorno (como en docker-compose.yml).
set -euo pipefail

BACKUP_DIR="${BACKUP_DIR:-/backups}"
TIMESTAMP="$(date +%Y%m%d-%H%M%S)"
OUTPUT_FILE="${BACKUP_DIR}/minerva-${TIMESTAMP}.sql"

mkdir -p "$BACKUP_DIR"

PGPASSWORD="${POSTGRES_PASSWORD:?Falta POSTGRES_PASSWORD}" \
    pg_dump -U "${POSTGRES_USER:?Falta POSTGRES_USER}" -d "${POSTGRES_DB:?Falta POSTGRES_DB}" \
    > "$OUTPUT_FILE"

echo "Backup creado: $OUTPUT_FILE"
