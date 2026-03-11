from datetime import datetime, timedelta
from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, update, and_, or_

from app.dependencies import get_db, get_current_user, get_current_admin
from app.models.scrape_run import ScrapeRun
from app.models.perfil import Perfil
from app.models.user import User
from app.schemas.scrape_run import ScrapeRunCreate, ScrapeRunRead

router = APIRouter(prefix="/api/scraping", tags=["scraping"])

# Umbral: runs en pending/running más antiguos que esto se marcan como failed
STALE_MINUTES = 5


async def mark_stale_runs(db: AsyncSession) -> None:
    """
    Marca como failed los runs que llevan más de STALE_MINUTES en pending/running.
    Llamar antes de cualquier select de runs para tener estado consistente.
    """
    threshold = datetime.utcnow() - timedelta(minutes=STALE_MINUTES)
    await db.execute(
        update(ScrapeRun)
        .where(
            ScrapeRun.status.in_(["pending", "running"]),
            or_(
                ScrapeRun.started_at < threshold,
                and_(ScrapeRun.started_at.is_(None), ScrapeRun.created_at < threshold),
            ),
        )
        .values(
            status="failed",
            error_message="Interrumpido (reinicio del servidor o timeout)",
        )
    )
    await db.commit()


@router.post("/run", response_model=ScrapeRunRead, status_code=status.HTTP_202_ACCEPTED)
async def trigger_scraping(
    data: ScrapeRunCreate,
    background_tasks: BackgroundTasks,
    current_user: User = Depends(get_current_admin),
    db: AsyncSession = Depends(get_db),
):
    """Dispara el scraping para un perfil como BackgroundTask. Solo admin."""
    perfil_result = await db.execute(
        select(Perfil).where(
            Perfil.id == data.perfil_id,
            Perfil.user_id == current_user.id if not current_user.is_admin else True,
        )
    )
    perfil = perfil_result.scalar_one_or_none()
    if not perfil:
        raise HTTPException(status_code=404, detail="Perfil no encontrado")

    # Limpiar runs obsoletos antes de verificar si hay uno en curso
    await mark_stale_runs(db)

    running_result = await db.execute(
        select(ScrapeRun).where(
            ScrapeRun.perfil_id == data.perfil_id,
            ScrapeRun.status.in_(["pending", "running"]),
        )
    )
    if running_result.scalar_one_or_none():
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Ya hay un scraping en curso para este perfil",
        )

    run = ScrapeRun(
        perfil_id=data.perfil_id,
        initiated_by_id=current_user.id,
        portales=data.portales,
        status="pending",
    )
    db.add(run)
    await db.commit()
    await db.refresh(run)

    config = perfil.to_config_dict()

    background_tasks.add_task(
        _run_in_thread,
        run_id=run.id,
        perfil_id=data.perfil_id,
        portales=data.portales,
        config=config,
    )

    return run


def _run_in_thread(run_id: int, perfil_id: int, portales: list[str], config: dict) -> None:
    """Wrapper para ejecutar el pipeline sincrónico en un thread."""
    from app.services.scraping_service import run_scraping_pipeline

    run_scraping_pipeline(
        run_id=run_id,
        perfil_id=perfil_id,
        portales=portales,
        config=config,
    )


@router.get("/runs", response_model=list[ScrapeRunRead])
async def list_runs(
    perfil_id: int | None = None,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    from sqlalchemy import desc

    await mark_stale_runs(db)

    query = select(ScrapeRun)
    if not current_user.is_admin:
        user_perfiles = await db.execute(
            select(Perfil.id).where(Perfil.user_id == current_user.id)
        )
        perfil_ids = [r[0] for r in user_perfiles.all()]
        query = query.where(ScrapeRun.perfil_id.in_(perfil_ids))

    if perfil_id:
        query = query.where(ScrapeRun.perfil_id == perfil_id)

    query = query.order_by(desc(ScrapeRun.created_at)).limit(50)
    result = await db.execute(query)
    return result.scalars().all()


# PATCH antes de GET /{run_id} para evitar conflictos de matching
@router.patch("/runs/{run_id}/interrupt", response_model=ScrapeRunRead)
async def interrupt_run(
    run_id: int,
    current_user: User = Depends(get_current_admin),
    db: AsyncSession = Depends(get_db),
):
    """
    Marca un run como failed (interrumpido). Solo admin.
    Idempotente: si el run ya está en failed o completed, devuelve 200 sin error.
    """
    result = await db.execute(select(ScrapeRun).where(ScrapeRun.id == run_id))
    run = result.scalar_one_or_none()
    if not run:
        raise HTTPException(status_code=404, detail="Run no encontrado")

    # Idempotente: si ya terminó, no hacer nada
    if run.status in ("failed", "completed"):
        return run

    run.status = "failed"
    run.error_message = "Interrumpido por el usuario"
    await db.commit()
    await db.refresh(run)
    return run


@router.get("/runs/{run_id}", response_model=ScrapeRunRead)
async def get_run(
    run_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(select(ScrapeRun).where(ScrapeRun.id == run_id))
    run = result.scalar_one_or_none()
    if not run:
        raise HTTPException(status_code=404, detail="Run no encontrado")
    return run


@router.post("/geocode/{perfil_id}", status_code=status.HTTP_202_ACCEPTED)
async def trigger_geocoding(
    perfil_id: int,
    background_tasks: BackgroundTasks,
    current_user: User = Depends(get_current_admin),
    db: AsyncSession = Depends(get_db),
):
    """Dispara la geocodificación de propiedades sin coordenadas. Solo admin."""
    from app.config import settings
    from app.services.consolidation_service import geocodificar_pendientes_sync

    if not settings.google_maps_api_key:
        raise HTTPException(
            status_code=400,
            detail="GOOGLE_MAPS_API_KEY no configurada en .env",
        )

    background_tasks.add_task(
        geocodificar_pendientes_sync,
        perfil_id=perfil_id,
        api_key=settings.google_maps_api_key,
    )
    return {"message": "Geocodificación iniciada en segundo plano"}


@router.post("/metrics/{perfil_id}", status_code=status.HTTP_202_ACCEPTED)
async def trigger_metrics(
    perfil_id: int,
    background_tasks: BackgroundTasks,
    current_user: User = Depends(get_current_admin),
    db: AsyncSession = Depends(get_db),
):
    """Dispara el cálculo de métricas de distancia y scoring para un perfil. Solo admin."""
    from app.services.metrics_service import compute_metrics_for_perfil

    background_tasks.add_task(compute_metrics_for_perfil, perfil_id=perfil_id)
    return {"message": "Cálculo de métricas iniciado en segundo plano"}
