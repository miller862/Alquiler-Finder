FROM python:3.12-slim

# Dependencias de sistema: GDAL (GeoPandas) + Firefox/Camoufox (StealthyFetcher)
RUN apt-get update && apt-get install -y --no-install-recommends \
    gdal-bin \
    libgdal-dev \
    postgresql-client \
    libgtk-3-0 \
    libdbus-glib-1-2 \
    libasound2 \
    libx11-xcb1 \
    libxcomposite1 \
    libxdamage1 \
    libxfixes3 \
    libxrandr2 \
    libnss3 \
    libnspr4 \
    libatk1.0-0 \
    libcups2 \
    fonts-liberation \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Instalar dependencias Python
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Descargar browser Camoufox para StealthyFetcher (no necesitamos Playwright)
RUN python -m camoufox fetch

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
