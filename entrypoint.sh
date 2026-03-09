#!/bin/sh
set -e

echo "Corriendo migraciones Alembic..."
alembic upgrade head || echo "WARN: Alembic migration skipped (probably no versions yet)"

echo "Iniciando aplicacion..."
exec uvicorn app.main:app --host 0.0.0.0 --port 8000
