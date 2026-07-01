from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.dependencies import get_db, get_current_user
from app.models.perfil import Perfil
from app.models.user import User
from app.schemas.perfil import PerfilCreate, PerfilUpdate, PerfilRead

router = APIRouter(prefix="/api/perfiles", tags=["perfiles"])


@router.get("/", response_model=list[PerfilRead])
async def list_perfiles(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    if current_user.is_admin:
        result = await db.execute(select(Perfil).where(Perfil.is_active == True))
    else:
        result = await db.execute(
            select(Perfil).where(
                Perfil.user_id == current_user.id,
                Perfil.is_active == True,
            )
        )
    return result.scalars().all()


@router.post("/", response_model=PerfilRead, status_code=status.HTTP_201_CREATED)
async def create_perfil(
    data: PerfilCreate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    perfil = Perfil(user_id=current_user.id, **data.model_dump())
    db.add(perfil)
    await db.commit()
    await db.refresh(perfil)
    return perfil


@router.put("/{perfil_id}", response_model=PerfilRead)
async def update_perfil(
    perfil_id: int,
    data: PerfilUpdate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(select(Perfil).where(Perfil.id == perfil_id))
    perfil = result.scalar_one_or_none()

    if not perfil:
        raise HTTPException(status_code=404, detail="Perfil no encontrado")
    if perfil.user_id != current_user.id and not current_user.is_admin:
        raise HTTPException(status_code=403, detail="Sin permisos")

    for field, value in data.model_dump().items():
        setattr(perfil, field, value)

    await db.commit()
    await db.refresh(perfil)
    return perfil


@router.delete("/{perfil_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_perfil(
    perfil_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(select(Perfil).where(Perfil.id == perfil_id))
    perfil = result.scalar_one_or_none()

    if not perfil:
        raise HTTPException(status_code=404, detail="Perfil no encontrado")
    if perfil.user_id != current_user.id and not current_user.is_admin:
        raise HTTPException(status_code=403, detail="Sin permisos")

    perfil.is_active = False
    await db.commit()
