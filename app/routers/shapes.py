"""
Sirve los archivos GeoJSON de referencia (shapes/) para el frontend Leaflet.js.
"""
import pathlib
from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse

from app.config import settings

router = APIRouter(prefix="/api/shapes", tags=["shapes"])
_SHAPES = pathlib.Path(settings.shapes_dir)


def _serve_geojson(filename: str) -> FileResponse:
    path = _SHAPES / filename
    if not path.exists():
        raise HTTPException(status_code=404, detail=f"Shape no encontrado: {filename}")
    return FileResponse(path, media_type="application/geo+json")


@router.get("/barrios")
async def get_barrios():
    return _serve_geojson("barrios.geojson")


@router.get("/ev")
async def get_espacios_verdes():
    return _serve_geojson("espacio_verde_publico.geojson")


@router.get("/subte/lineas")
async def get_subte_lineas():
    return _serve_geojson("subte_lineas.geojson")


@router.get("/subte/estaciones")
async def get_subte_estaciones():
    return _serve_geojson("estaciones_de_subte.geojson")


@router.get("/gyms")
async def get_gyms():
    return _serve_geojson("gimnasios.geojson")
