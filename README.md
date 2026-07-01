# Deptos Scraper

Aplicacion web para buscar, scrapear y analizar departamentos en alquiler de portales inmobiliarios de Buenos Aires (ZonaProp, ArgenProp). Incluye geocodificacion, metricas de proximidad (subte, espacios verdes, gimnasios), scoring y visualizacion en mapa interactivo.

## Stack

- **Backend:** FastAPI + SQLAlchemy 2.0 (async) + Alembic
- **Base de datos:** PostgreSQL 16
- **Scraping:** Scrapling Fetcher (HTTP con TLS fingerprint). ArgenProp va directo; ZonaProp pasa Cloudflare con una cookie `cf_clearance` que provee el usuario (ver [docs/zonaprop_cookie.md](docs/zonaprop_cookie.md))
- **Frontend:** Jinja2 templates + Leaflet.js (mapa interactivo)
- **Auth:** JWT en cookie HttpOnly (passlib + python-jose)
- **Deploy:** Docker Compose

## Requisitos previos

- [Docker Desktop](https://www.docker.com/products/docker-desktop/) instalado y corriendo
- Una API Key de [Google Maps Platform](https://console.cloud.google.com/) con la Geocoding API habilitada

## Setup

### 1. Clonar el repositorio

```bash
git clone <url-del-repo>
cd deptos_scraper
```

### 2. Crear archivo `.env`

```bash
cp .env.example .env
```

Editar `.env` con los siguientes valores:

```env
# Password de PostgreSQL (elegir la que quieras)
POSTGRES_PASSWORD=tu_password_seguro

# Clave secreta para JWT — generar con:
#   python -c "import secrets; print(secrets.token_hex(32))"
SECRET_KEY=clave-secreta-generada

# Credenciales del usuario admin
# ADMIN_USERNAME es opcional; si no se define, el usuario se llama "manuel"
# ADMIN_USERNAME=el_nombre_que_quieras
ADMIN_PASSWORD=tu_password

# API Key de Google Maps (para geocodificacion de direcciones)
GOOGLE_MAPS_API_KEY=tu-api-key
```

### 3. Construir y levantar

```bash
docker compose build
docker compose up -d
```

Esto automaticamente:

1. Levanta PostgreSQL 16
2. Construye la imagen de la app (dependencias Python)
3. Corre las migraciones de base de datos (`alembic upgrade head`)
4. Crea el usuario admin si `ADMIN_PASSWORD` esta configurado
5. Carga datos iniciales desde `seed/` si la base esta vacia
6. Inicia la app en **http://localhost:8000**

### 4. Acceder

Abrir http://localhost:8000 en el navegador y loguearse con las credenciales configuradas en `.env`.

## Desarrollo local (correr la app sin Docker)

Alternativa al Setup de arriba: en vez de correr la app dentro de un contenedor, se
levanta **solo PostgreSQL en Docker** y la app se ejecuta con `uvicorn` en la máquina
(más rápido para iterar, con hot-reload `--reload`).

Requisitos: Python **3.11, 3.12 o 3.13** (con conda o venv) + Docker Desktop.

### 1. Entorno de Python y dependencias

```powershell
# Con conda (ejemplo, entorno llamado PYR):
conda activate PYR
# o con venv:  python -m venv .venv ; .\.venv\Scripts\Activate.ps1

pip install -r requirements.txt
python -c "import pydantic_settings, fastapi, scrapling; print('ok')"
```

### 2. Base de datos en Docker

```powershell
docker compose up -d db
```

> **Conflicto de puerto 5432:** si ya tenés un PostgreSQL nativo instalado y corriendo,
> el puerto 5432 estará ocupado. Definí `DB_HOST_PORT=5433` en tu `.env` (Docker expondrá
> la base en 5433) y ajustá `DATABASE_URL` / `SYNC_DATABASE_URL` para que apunten a
> `localhost:5433`. El valor por defecto es 5432.

### 3. Migraciones y usuario admin (una sola vez)

`alembic` y `scripts/create_admin.py` importan el paquete `app`, así que necesitan la
raíz del proyecto en `PYTHONPATH`. `create_admin.py` lee `ADMIN_USERNAME` / `ADMIN_PASSWORD`
del **entorno** (no del `.env`).

```powershell
$env:PYTHONPATH = "."
python -m alembic upgrade head
$env:ADMIN_USERNAME = "tu_usuario"; $env:ADMIN_PASSWORD = "tu_password"
python scripts/create_admin.py   # si dice "ya existe", está ok (no cambia la password)
```

### 4. Levantar la app

```powershell
uvicorn app.main:app --reload --port 8000
```

La app lee la conexión desde el `.env`, así que no hace falta exportar `DATABASE_URL`
para este paso. Abrir http://localhost:8000.

### Uso diario

Una vez hecho el setup, para correr la app cada día:

```powershell
conda activate PYR
docker compose up -d db
uvicorn app.main:app --reload --port 8000
```

## Uso

### Panel de scraping

Acceder desde el menu de navegacion o directamente en `/admin/scraping`.

El pipeline de scraping tiene 3 pasos secuenciales por cada run:

1. **Scraping** — Boton "Iniciar Scraping": scrapea los portales seleccionados. Los datos se guardan temporalmente en un archivo JSON de staging (no se escribe a la base de datos todavia).
2. **Geocodificacion** — Boton "Geocodificar" (aparece cuando el run esta en estado `scraped`): geocodifica las direcciones usando la API de Google Maps.
3. **Metricas y commit** — Boton "Metricas" (aparece cuando el run esta en estado `geocoded`): calcula distancias a subtes, espacios verdes, gimnasios, genera el score de ranking y escribe todo a la base de datos.

Cada paso muestra progreso en tiempo real en el panel de logs.

### Mapa

Mapa interactivo con Leaflet.js que muestra los departamentos geocodificados. Se puede filtrar por barrio, rango de precio y score.

### Ranking

Tabla con los departamentos ordenados por score, con links directos a las publicaciones.

## Comandos utiles

```bash
# Ver logs en tiempo real
docker compose logs -f app

# Reiniciar la app sin rebuild (tras cambios en templates/static)
docker compose restart app

# Rebuild completo (tras cambios en Dockerfile o requirements.txt)
docker compose up --build -d

# Exportar un dump de datos (para compartir o hacer backup)
docker compose exec app sh scripts/export_seed.sh

# Conectarse a la base de datos
docker compose exec db psql -U deptos deptos_scraper
```

## Estructura del proyecto

```
app/
  main.py              # FastAPI app factory
  config.py            # pydantic-settings (lee .env)
  database.py          # SQLAlchemy async + sync engines
  dependencies.py      # get_db, get_current_user
  core/
    security.py        # bcrypt + JWT
    normalization.py   # deduplicacion de URLs y direcciones
    constants.py       # barrios disponibles, pesos de scoring
  models/              # SQLAlchemy ORM (User, Perfil, Departamento, ScrapeRun)
  schemas/             # Pydantic v2
  routers/             # auth, ui, departamentos, perfiles, scraping, shapes
  services/            # scraping, parsers, url_builder, consolidation, metrics
  templates/           # Jinja2 (login, mapa, ranking, admin_scraping)
  static/              # JS, CSS
migrations/            # Alembic
shapes/                # GeoJSON (barrios, subtes, espacios verdes, gimnasios)
seed/                  # Dump de datos iniciales (opcional)
```

## Variables de entorno

| Variable | Descripcion | Obligatoria |
|----------|-------------|:-----------:|
| `POSTGRES_PASSWORD` | Password de PostgreSQL | Si |
| `DB_HOST_PORT` | Puerto del host donde Docker expone Postgres (default: `5432`; usar `5433` si hay un Postgres nativo en 5432) | No |
| `SECRET_KEY` | Clave secreta para firmar tokens JWT | Si |
| `ADMIN_USERNAME` | Username del admin (default: `manuel`) | No |
| `ADMIN_PASSWORD` | Password del admin | Si |
| `GOOGLE_MAPS_API_KEY` | API key de Google Maps para geocodificacion | Si |
| `DEBUG` | `true` para hot-reload con uvicorn (default: `false`) | No |

## Notas

- Los cambios en `app/templates/` y `app/static/` se reflejan con F5 (estan montados como volumen).
- Los cambios en codigo Python (routers, services, models) requieren `docker compose restart app`.
- Los cambios en `Dockerfile` o `requirements.txt` requieren `docker compose up --build -d`.
