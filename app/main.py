import asyncio
import sys

# asyncpg en Windows no funciona con ProactorEventLoop (default en Python 3.8+)
if sys.platform == "win32":
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware

from app.config import settings
from app.routers import auth, ui, departamentos, perfiles, scraping, shapes


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup
    yield
    # Shutdown — nada que limpiar


app = FastAPI(
    title="Deptos Scraper API",
    description="API para scraping, análisis y ranking de departamentos en CABA",
    version="2.0.0",
    lifespan=lifespan,
    docs_url="/docs" if settings.debug else None,
    redoc_url="/redoc" if settings.debug else None,
)

# CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.allowed_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Archivos estáticos
app.mount("/static", StaticFiles(directory="app/static"), name="static")

# Routers
app.include_router(auth.router)
app.include_router(ui.router)
app.include_router(departamentos.router)
app.include_router(perfiles.router)
app.include_router(scraping.router)
app.include_router(shapes.router)
