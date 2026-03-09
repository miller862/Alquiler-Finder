from pydantic import BaseModel
from datetime import date, datetime
from typing import Optional


class DepartamentoRead(BaseModel):
    id: int
    portal: str
    perfil_id: Optional[int]
    barrio_scrapeado: Optional[str]
    tipo: Optional[str]
    titulo: Optional[str]
    descripcion_breve: Optional[str]
    direccion: Optional[str]
    precio: Optional[int]
    expensas: Optional[int]
    costo_total: Optional[int]
    metros_totales: Optional[int]
    metros_cubiertos: Optional[int]
    ambientes: Optional[int]
    dormitorios: Optional[int]
    banios: Optional[int]
    cocheras: Optional[int]
    url: Optional[str]
    lat: Optional[float]
    lon: Optional[float]
    barrio_geo: Optional[str]
    snap_warning: Optional[bool]
    distancia_m_subte: Optional[int]
    cant_subte: Optional[int]
    distancia_m_gym: Optional[int]
    cant_gym: Optional[int]
    dist_verde_final: Optional[int]
    cant_parque: Optional[int]
    cant_plaza: Optional[int]
    segmento: Optional[str]
    score: Optional[float]
    apto_scoring: bool
    activo: bool
    veces_visto: int
    revision: Optional[str]
    fecha_deteccion: date
    primera_vez_visto: date
    ultima_vez_visto: date

    model_config = {"from_attributes": True}


class DepartamentoGeoFeature(BaseModel):
    """GeoJSON Feature para Leaflet.js"""
    type: str = "Feature"
    geometry: dict
    properties: dict


class DepartamentosGeoJSON(BaseModel):
    type: str = "FeatureCollection"
    features: list[DepartamentoGeoFeature]


class DepartamentoUpdate(BaseModel):
    revision: Optional[str] = None
