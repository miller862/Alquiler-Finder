from pydantic import BaseModel, field_validator
from datetime import datetime
from typing import Optional


class PerfilCreate(BaseModel):
    nombre: str
    operacion: str = "alquiler"
    barrios: list[str]
    tipos: list[str]
    precio_min: Optional[int] = None
    precio_max: Optional[int] = None
    precio_moneda: str = "pesos"
    amb_min: Optional[int] = None
    amb_max: Optional[int] = None
    dorm_min: Optional[int] = None
    dorm_max: Optional[int] = None
    superficie_cubierta_min: Optional[int] = None
    balcon: bool = False
    expensas_max: Optional[int] = None
    filtros_exclusion: list[str] = []

    @field_validator("nombre")
    @classmethod
    def nombre_upper(cls, v: str) -> str:
        return v.strip().upper()


class PerfilUpdate(PerfilCreate):
    pass


class PerfilRead(BaseModel):
    id: int
    nombre: str
    operacion: str
    barrios: list[str]
    tipos: list[str]
    precio_min: Optional[int]
    precio_max: Optional[int]
    precio_moneda: str
    amb_min: Optional[int]
    amb_max: Optional[int]
    dorm_min: Optional[int]
    dorm_max: Optional[int]
    superficie_cubierta_min: Optional[int]
    balcon: bool
    expensas_max: Optional[int]
    filtros_exclusion: list[str]
    is_active: bool
    created_at: datetime

    model_config = {"from_attributes": True}
