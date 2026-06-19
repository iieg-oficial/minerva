#!/bin/bash
set -e

cd /app

echo "Running database migrations..."
alembic upgrade head

echo "Starting backend..."
exec "$@"
