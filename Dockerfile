FROM python:3.12-slim

# Sistema: GDAL (GeoPandas) + PostgreSQL client
RUN apt-get update && apt-get install -y --no-install-recommends \
    gdal-bin \
    libgdal-dev \
    postgresql-client \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Instalar dependencias Python
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Chromium para Playwright/Patchright (usado por StealthyFetcher de Scrapling)
RUN playwright install-deps chromium && playwright install chromium

# Copiar código fuente
COPY app/ ./app/
COPY migrations/ ./migrations/
COPY scripts/ ./scripts/
COPY alembic.ini .
COPY shapes/ ./shapes/
COPY seed/ ./seed/

# Puerto FastAPI
EXPOSE 8000

ENV DOCKER_ENV=true

# Entrypoint: corre migraciones y luego inicia la app
COPY entrypoint.sh .
RUN chmod +x entrypoint.sh
CMD ["./entrypoint.sh"]
