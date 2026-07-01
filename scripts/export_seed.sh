#!/bin/sh
# Exporta un dump de datos actualizado a /app/seed/seed_data.dump
# Llamar desde el contenedor app: sh scripts/export_seed.sh
set -e

DUMP_FILE="/app/seed/seed_data.dump"

echo "Exportando datos a $DUMP_FILE ..."
PGPASSWORD="${POSTGRES_PASSWORD:-deptos_dev}" \
  pg_dump -h db -U deptos -Fc \
    --data-only \
    --exclude-table=alembic_version \
    deptos_scraper > "$DUMP_FILE"

SIZE=$(wc -c < "$DUMP_FILE" | tr -d ' ')
echo "Seed actualizado: $DUMP_FILE ($SIZE bytes)"
