FROM python:3.12-slim

# Dependencias de sistema: GDAL (GeoPandas), Chromium (Selenium headless)
RUN apt-get update && apt-get install -y --no-install-recommends \
    gdal-bin \
    libgdal-dev \
    chromium \
    chromium-driver \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Instalar dependencias Python
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copiar código fuente
COPY app/ ./app/
COPY migrations/ ./migrations/
COPY alembic.ini .
COPY shapes/ ./shapes/

# Puerto FastAPI
EXPOSE 8000

# Variables de entorno para Selenium headless en Docker
ENV DOCKER_ENV=true
ENV CHROME_BIN=/usr/bin/chromium

# Entrypoint: corre migraciones y luego inicia la app
COPY entrypoint.sh .
RUN chmod +x entrypoint.sh
CMD ["./entrypoint.sh"]
