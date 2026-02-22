# DEPTOS_SCRAPER — Scraper de departamentos en alquiler (CABA)

Sistema para scrapear, consolidar, geocodificar y visualizar departamentos en alquiler de Zonaprop, Argenprop y Cabaprop en CABA. Incluye métricas de proximidad a subte, gimnasios y espacios verdes, con una app Streamlit protegida por login.

---

## Estructura del proyecto

```
deptos_scraper/
├── perfiles/                    # Datos por perfil (gitignored)
│   ├── configuraciones.json     # Configs + usuario/password por perfil
│   ├── MANUEL/                 # Ejemplo de perfil
│   │   ├── zonaprop/           # CSVs por fecha
│   │   ├── argenprop/
│   │   ├── cabaprop/
│   │   ├── departamentos_master.xlsx
│   │   ├── departamentos.geojson
│   │   ├── departamentos_enriquecido.xlsx
│   │   ├── departamentos_enriquecido.geojson
│   │   └── ranking.xlsx
│   └── global/                 # Vista consolidada de todos los perfiles
│       ├── departamentos_master_global.xlsx
│       ├── departamentos_enriquecido_global.xlsx
│       ├── departamentos_enriquecido_global.geojson
│       └── ranking_global.xlsx
├── shapes/                      # Capas base compartidas (barrios, subte, gimnasios, etc.)
├── data/gimnasios/             # Fuentes para geocodificación de gimnasios
├── scripts/
│   ├── 0_parametros.py         # Constantes, configuraciones, rutas
│   ├── 1_url_builder.py       # Construcción de URLs por portal
│   ├── 2_parsers.py            # Parsers HTML
│   ├── 3_main.py               # Scraper principal (Selenium)
│   ├── 4_consolidar.py         # Consolidación, dedup, geocodificación
│   ├── 5_auxiliar.py           # Colores, geocodificación gimnasios
│   ├── 6_metrics_new.py        # Métricas y scoring
│   ├── 7_visualize.py          # Mapa Folium por consola
│   └── 8_streamlit_deploy.py   # App Streamlit con login
├── configuraciones.ejemplo.json # Plantilla para perfiles
├── Dockerfile
├── requirements.txt
└── README.md
```

---

## Configuración inicial

### 1. Crear la carpeta `perfiles/`

Si clonás el repo, la carpeta `perfiles/` no se sube (está en `.gitignore`). Creala y copiá la plantilla:

```bash
mkdir perfiles
copy configuraciones.ejemplo.json perfiles\configuraciones.json
```

**Nota**: Si migraste desde una versión anterior, las carpetas `data/` (excepto `data/gimnasios/`), `outputs/` y los archivos `shapes/departamentos_*.geojson` ya no se usan. Podés eliminarlos para evitar confusiones.

### 2. Editar `perfiles/configuraciones.json`

Cada perfil de búsqueda tiene:

- **Campos de búsqueda**: `barrios`, `tipos`, `precio`, `ambientes`, etc.
- **Usuario y contraseña**: para el login de la app Streamlit.

El perfil `global` (con `es_global: true`) permite ver todos los datos consolidados; también requiere usuario y contraseña.

Ejemplo mínimo:

```json
[
  {
    "nombre": "MI_PERFIL",
    "operacion": "alquiler",
    "barrios": ["belgrano", "palermo"],
    "tipos": ["departamento"],
    "precio": {"min": 400000, "max": 800000, "moneda": "pesos"},
    "usuario": "mi_usuario",
    "password": "mi_password"
  },
  {
    "nombre": "global",
    "es_global": true,
    "usuario": "admin",
    "password": "admin_password"
  }
]
```

---

## Workflow completo

Los scripts se ejecutan **en orden** desde la raíz del proyecto. Ejecutá cada uno desde la carpeta del proyecto (o con `python scripts/X_nombre.py`).

### Paso 1: Scraping (`3_main.py`)

- Lee configuraciones de `perfiles/configuraciones.json`
- Permite elegir un perfil existente o crear uno nuevo
- Scrapea Zonaprop, Argenprop y Cabaprop con Selenium/Brave
- Guarda CSVs en `perfiles/<perfil>/zonaprop/`, `argenprop/`, `cabaprop/`

**Requisitos**: Brave instalado, ejecutar desde Windows (o adaptar rutas de Brave).

```bash
python scripts/3_main.py
```

### Paso 2: Consolidar (`4_consolidar.py`)

- Elige un perfil
- Lee los CSVs más recientes de cada portal
- Deduplica por dirección/precio/tipo/ambientes
- Geocodifica direcciones nuevas con Google Maps API
- Guarda `departamentos_master.xlsx` y `departamentos.geojson` en `perfiles/<perfil>/`
- Actualiza el master global en `perfiles/global/`

**Requisitos**: API Key de Google Maps (se pide al geocodificar).

```bash
python scripts/4_consolidar.py
```

### Paso 3: Métricas (`6_metrics_new.py`)

- Elige un perfil
- Lee `perfiles/<perfil>/departamentos.geojson`
- Calcula distancias a subte, gimnasios, espacios verdes
- Genera Score ponderado
- Guarda `departamentos_enriquecido.xlsx`, `.geojson` y `ranking.xlsx` en `perfiles/<perfil>/`
- Actualiza automáticamente los archivos globales en `perfiles/global/`

```bash
python scripts/6_metrics_new.py
```

### Paso 4: Visualización

**Opción A — Consola (Folium)**  
`7_visualize.py` genera un mapa interactivo en el navegador.

```bash
python scripts/7_visualize.py
```

**Opción B — App Streamlit (recomendada)**  
`8_streamlit_deploy.py` levanta una app con login.

```bash
streamlit run scripts/8_streamlit_deploy.py
```

---

## App Streamlit y login

La app muestra primero una pantalla de login. Usuario y contraseña se definen en `perfiles/configuraciones.json`:

- Cada perfil tiene `usuario` y `password`
- El perfil `global` tiene su propio `usuario` y `password`
- Cada usuario ve solo los datos de su perfil (o del global si corresponde)

No hay selector de perfil: el perfil se determina por el usuario que inicia sesión.

---

## Docker

```bash
docker build -t deptos-scraper .
docker run -p 8501:8501 -v "%cd%\perfiles:/app/perfiles" deptos-scraper
```

**Importante**: Montá la carpeta `perfiles/` como volumen para que la app tenga acceso a configuraciones y datos. Sin ese volumen, la app no encontrará datos.

---

## Dependencias adicionales (solo para pipeline de scraping)

`requirements.txt` incluye lo necesario para la app Streamlit. Para ejecutar el pipeline completo (scripts 3, 4, 6):

```bash
pip install googlemaps selenium momepy networkx scipy beautifulsoup4 openpyxl
```

---

## Resumen del flujo de datos

```
configuraciones.json
        │
        ▼
   [3_main] ──► perfiles/<perfil>/zonaprop|argenprop|cabaprop/*.csv
        │
        ▼
   [4_consolidar] ──► perfiles/<perfil>/departamentos_master.xlsx
                   ──► perfiles/<perfil>/departamentos.geojson
                   ──► perfiles/global/departamentos_master_global.xlsx
        │
        ▼
   [6_metrics_new] ──► perfiles/<perfil>/departamentos_enriquecido.*
                    ──► perfiles/<perfil>/ranking.xlsx
                    ──► perfiles/global/departamentos_enriquecido_global.*
        │
        ▼
   [8_streamlit] ◄── Login (usuario/password de configuraciones)
                 ◄── Carga datos del perfil del usuario
```
