FROM python:3.12-slim AS base
ENV PYTHONPATH=/app
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

FROM base AS builder
COPY pyproject.toml constraints.txt ./
COPY app/ ./app/
# `-c constraints.txt`: la imagen se construye con la misma resolución que valida CI.
RUN pip install --prefix=/install -c constraints.txt .

FROM base AS runtime
COPY --from=builder /install /usr/local
COPY scripts/ /app/scripts/
COPY alembic.ini /app/
COPY alembic/ /app/alembic/
COPY app/ /app/app/

RUN mkdir -p /app/uploads /app/manifests
WORKDIR /app
EXPOSE 9000

# El entrypoint elige uvicorn (dev) o gunicorn (prod) según MINERVA_MODE.
CMD ["/app/scripts/backend-entrypoint.sh"]
