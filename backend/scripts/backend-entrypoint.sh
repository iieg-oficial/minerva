#!/bin/bash
set -e

cd /app

echo "Aplicando migraciones..."
alembic upgrade head

# Paso único, antes de levantar los workers: en el lifespan corría una vez por worker
# de gunicorn. `set -e` hace que un manifiesto inválido aborte el arranque en vez de
# quedar en un warning que nadie lee.
echo "Importando manifiestos..."
python -m app.cli import-manifests

# Separa desarrollo y producción según MINERVA_MODE.
# Puerto 9000 extremo a extremo (gotcha 8000 vs 9000 del CLAUDE.md raíz).
if [ "$MINERVA_MODE" = "dev" ]; then
    echo "Modo desarrollo — uvicorn con reload"
    exec uvicorn app.main:app --host 0.0.0.0 --port 9000 --reload
else
    echo "Modo producción — gunicorn con 4 workers (UvicornWorker)"
    exec gunicorn app.main:app \
        -w 4 \
        -k uvicorn.workers.UvicornWorker \
        --bind 0.0.0.0:9000 \
        --timeout 30 \
        --keep-alive 5 \
        --access-logfile -
fi
