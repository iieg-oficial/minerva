FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

COPY sdk /opt/minerva-sdk
COPY examples/minerva-consumer /app

RUN pip install --no-cache-dir /opt/minerva-sdk . \
    && useradd --create-home --uid 10001 appuser

USER appuser

EXPOSE 8100

CMD ["uvicorn", "minerva_example.main:app", "--host", "0.0.0.0", "--port", "8100"]
