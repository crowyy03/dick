#!/bin/sh
set -e
cd /app
alembic upgrade head
exec python -m app.main
