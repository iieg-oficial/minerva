FROM python:3.12-slim AS base
ENV PYTHONPATH=/app
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

FROM base AS builder
COPY pyproject.toml ./
COPY app/ ./app/
RUN pip install --prefix=/install .

FROM base AS runtime
COPY --from=builder /install /usr/local
COPY scripts/ /app/scripts/
COPY alembic.ini /app/
COPY alembic/ /app/alembic/
COPY app/ /app/app/

RUN mkdir -p /app/uploads /app/manifests
WORKDIR /app
EXPOSE 9000

CMD ["/app/scripts/backend-entrypoint.sh", "uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "9000"]
