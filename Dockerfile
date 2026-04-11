FROM python:3.12-slim

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    ca-certificates \
    && rm -rf /var/lib/apt/lists/*

COPY pyproject.toml /app/
COPY app /app/app
COPY alembic.ini /app/
COPY alembic /app/alembic
COPY docker/entrypoint.sh /entrypoint.sh

RUN pip install --no-cache-dir --upgrade pip \
    && pip install --no-cache-dir /app

RUN chmod +x /entrypoint.sh

ENTRYPOINT ["/entrypoint.sh"]
