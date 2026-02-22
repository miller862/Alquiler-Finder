# 1. Usamos una imagen oficial de Python ligera
FROM python:3.10-slim

# 2. Instalamos dependencias  para GeoPandas 
RUN apt-get update && apt-get install -y \
    gdal-bin \
    libgdal-dev \
    && rm -rf /var/lib/apt/lists/*

# 3. Establecemos el directorio de trabajo dentro del contenedor
WORKDIR /app

# 4. Copiamos el archivo de requerimientos primero (para aprovechar el caché de Docker)
COPY requirements.txt .

# 5. Instalamos las librerías de Python
RUN pip install --no-cache-dir -r requirements.txt

# 6. Copiamos TODO el contenido de tu proyecto al contenedor (scripts, shapes, outputs, etc.)
COPY . .

# 7. Exponemos el puerto que usa Streamlit
EXPOSE 8501

# 8. Comando para ejecutar tu app indicando la ruta correcta del script
CMD ["streamlit", "run", "scripts/8_streamlit_deploy.py", "--server.port=8501", "--server.address=0.0.0.0"]