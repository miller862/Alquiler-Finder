from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, and_

from app.dependencies import get_db, get_current_user
from app.models.departamento import Departamento
from app.models.perfil import Perfil
from app.models.user import User
from app.schemas.departamento import DepartamentoRead, DepartamentoUpdate, DepartamentosGeoJSON

router = APIRouter(prefix="/api/departamentos", tags=["departamentos"])


def _depto_to_feature(d: Departamento) -> dict:
    return {
        "type": "Feature",
        "geometry": {
            "type": "Point",
            "coordinates": [d.lon, d.lat],
        }
        if d.lon and d.lat
        else None,
        "properties": {
            "id": d.id,
            "portal": d.portal,
            "perfil_id": d.perfil_id,
            "barrio": d.barrio_geo or d.barrio_scrapeado,
            "tipo": d.tipo,
            "titulo": d.titulo,
            "direccion": d.direccion,
            "precio": d.precio,
            "expensas": d.expensas,
            "costo_total": d.costo_total,
            "ambientes": d.ambientes,
            "dormitorios": d.dormitorios,
            "banios": d.banios,
            "cocheras": d.cocheras,
            "metros_cubiertos": d.metros_cubiertos,
            "metros_totales": d.metros_totales,
            "score": d.score,
            "segmento": d.segmento,
            "distancia_m_subte": d.distancia_m_subte,
            "distancia_m_gym": d.distancia_m_gym,
            "dist_verde_final": d.dist_verde_final,
            "cant_subte": d.cant_subte,
            "cant_gym": d.cant_gym,
            "activo": d.activo,
            "veces_visto": d.veces_visto,
            "revision": d.revision,
            "fecha_deteccion": str(d.fecha_deteccion) if d.fecha_deteccion else None,
            "url": d.url,
            "snap_warning": d.snap_warning,
        },
    }


@router.get("/", response_model=None)
async def get_departamentos_geojson(
    perfil_id: Optional[int] = Query(None),
    global_view: bool = Query(False),
    activo: Optional[bool] = Query(True),
    barrios: Optional[list[str]] = Query(None),
    precio_min: Optional[int] = Query(None),
    precio_max: Optional[int] = Query(None),
    score_min: Optional[float] = Query(None),
    dormitorios: Optional[list[int]] = Query(None),
    ambientes: Optional[list[int]] = Query(None),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    if global_view and not current_user.is_admin:
        raise HTTPException(status_code=403, detail="Se requieren permisos de administrador")

    filters = []

    if activo is not None:
        filters.append(Departamento.activo == activo)

    if global_view:
        # Vista global: todas las propiedades con coordenadas
        filters.append(Departamento.lat.isnot(None))
    else:
        if perfil_id:
            # Verificar que el perfil pertenece al usuario
            perfil_result = await db.execute(
                select(Perfil).where(
                    Perfil.id == perfil_id,
                    Perfil.user_id == current_user.id if not current_user.is_admin else True,
                )
            )
            if not perfil_result.scalar_one_or_none():
                raise HTTPException(status_code=404, detail="Perfil no encontrado")
            filters.append(Departamento.perfil_id == perfil_id)
        else:
            # Solo perfiles del usuario actual
            user_perfiles = await db.execute(
                select(Perfil.id).where(Perfil.user_id == current_user.id)
            )
            perfil_ids = [row[0] for row in user_perfiles.all()]
            if not perfil_ids:
                return {"type": "FeatureCollection", "features": []}
            filters.append(Departamento.perfil_id.in_(perfil_ids))

    if barrios:
        filters.append(Departamento.barrio_geo.in_(barrios))
    if precio_min is not None:
        filters.append(Departamento.precio >= precio_min)
    if precio_max is not None:
        filters.append(Departamento.precio <= precio_max)
    if score_min is not None:
        filters.append(Departamento.score >= score_min)
    if dormitorios:
        filters.append(Departamento.dormitorios.in_(dormitorios))
    if ambientes:
        filters.append(Departamento.ambientes.in_(ambientes))

    # Solo devolver propiedades con coordenadas (para el mapa)
    filters.append(Departamento.lat.isnot(None))

    result = await db.execute(select(Departamento).where(and_(*filters)))
    deptos = result.scalars().all()

    features = [_depto_to_feature(d) for d in deptos if d.lat and d.lon]

    return {"type": "FeatureCollection", "features": features}


@router.get("/{depto_id}", response_model=DepartamentoRead)
async def get_departamento(
    depto_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(select(Departamento).where(Departamento.id == depto_id))
    depto = result.scalar_one_or_none()

    if not depto:
        raise HTTPException(status_code=404, detail="No encontrado")

    # Verificar acceso
    if not current_user.is_admin and depto.perfil_id:
        perfil_result = await db.execute(
            select(Perfil).where(
                Perfil.id == depto.perfil_id,
                Perfil.user_id == current_user.id,
            )
        )
        if not perfil_result.scalar_one_or_none():
            raise HTTPException(status_code=403)

    return depto


@router.patch("/{depto_id}", response_model=DepartamentoRead)
async def update_departamento(
    depto_id: int,
    data: DepartamentoUpdate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Actualizar solo el campo revision (anotación manual del usuario)."""
    result = await db.execute(select(Departamento).where(Departamento.id == depto_id))
    depto = result.scalar_one_or_none()

    if not depto:
        raise HTTPException(status_code=404)

    if data.revision is not None:
        depto.revision = data.revision

    await db.commit()
    await db.refresh(depto)
    return depto
