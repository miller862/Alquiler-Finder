#!/bin/sh
set -e

echo "Corriendo migraciones Alembic..."
alembic upgrade head

echo "Creando usuario admin (si no existe)..."
PYTHONPATH=/app python scripts/create_admin.py

# Seed: si la base está vacía y existe el dump, restaurar datos iniciales
SEED_FILE="/app/seed/seed_data.dump"
if [ -f "$SEED_FILE" ]; then
  ROW_COUNT=$(PGPASSWORD="${POSTGRES_PASSWORD:-deptos_dev}" psql -h db -U deptos -d deptos_scraper -tAc "SELECT count(*) FROM departamentos;" 2>/dev/null || echo "0")
  if [ "$ROW_COUNT" = "0" ]; then
    echo "Base vacia detectada. Cargando seed de datos..."
    PGPASSWORD="${POSTGRES_PASSWORD:-deptos_dev}" pg_restore -h db -U deptos -d deptos_scraper --data-only --disable-triggers --no-owner "$SEED_FILE" || true
    echo "Seed cargado."
  else
    echo "Base ya tiene $ROW_COUNT departamentos, saltando seed."
  fi
fi

echo "Iniciando aplicacion..."
if [ "${DEBUG:-false}" = "true" ]; then
  exec uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload --reload-dir /app/app
else
  exec uvicorn app.main:app --host 0.0.0.0 --port 8000
fi
