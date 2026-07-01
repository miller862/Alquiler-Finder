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

# El pipeline completo (scrape + geocode + métricas) puede tardar 20+ min
STALE_MINUTES = 30

# Si una etapa se interrumpe o falla, se vuelve a su último checkpoint estable para
# poder reintentar desde el botón, en vez de quedar en 'failed' sin acción posible.
_RECOVERY_STATUS = {
    "geocoding": "scraped",
    "computing_metrics": "geocoded",
}


async def mark_stale_runs(db: AsyncSession) -> None:
    threshold = datetime.utcnow() - timedelta(minutes=STALE_MINUTES)
    stale = or_(
        ScrapeRun.started_at < threshold,
        and_(ScrapeRun.started_at.is_(None), ScrapeRun.created_at < threshold),
    )
    # Etapas con datos en staging: revertir al checkpoint para poder reintentar.
    await db.execute(
        update(ScrapeRun).where(ScrapeRun.status == "geocoding", stale).values(status="scraped")
    )
    await db.execute(
        update(ScrapeRun).where(ScrapeRun.status == "computing_metrics", stale).values(status="geocoded")
    )
    # Scraping/pending sin staging usable: marcar como fallido (se relanza con un run nuevo).
    await db.execute(
        update(ScrapeRun)
        .where(ScrapeRun.status.in_(["pending", "scraping"]), stale)
        .values(status="failed", error_message="Interrumpido (reinicio del servidor o timeout)")
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

    if "zonaprop" in data.portales and not (data.zonaprop_cookie or "").strip():
        raise HTTPException(
            status_code=400,
            detail="ZonaProp requiere la cookie cf_clearance. Pegala en el formulario o desmarca ZonaProp.",
        )

    await mark_stale_runs(db)

    running_result = await db.execute(
        select(ScrapeRun).where(
            ScrapeRun.perfil_id == data.perfil_id,
            ScrapeRun.status.in_(["pending", "scraping", "geocoding", "computing_metrics"]),
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
        _run_scraping_in_thread,
        run_id=run.id,
        perfil_id=data.perfil_id,
        portales=data.portales,
        config=config,
        zonaprop_cookie=data.zonaprop_cookie,
    )

    return run


def _run_scraping_in_thread(run_id: int, perfil_id: int, portales: list[str], config: dict, zonaprop_cookie: str | None = None) -> None:
    import logging
    logger = logging.getLogger(__name__)
    try:
        from app.services.scraping_service import run_scraping_pipeline
        run_scraping_pipeline(run_id=run_id, perfil_id=perfil_id, portales=portales, config=config, zonaprop_cookie=zonaprop_cookie)
    except Exception as exc:
        logger.exception(f"[run={run_id}] Fatal error in scraping thread")
        from app.database import SyncSessionLocal
        from app.models.scrape_run import ScrapeRun as _ScrapeRun
        from sqlalchemy import select as _select
        from datetime import datetime as _dt
        try:
            with SyncSessionLocal() as db:
                run = db.execute(_select(_ScrapeRun).where(_ScrapeRun.id == run_id)).scalar_one_or_none()
                if run and run.status not in ("failed", "completed"):
                    run.status = "failed"
                    run.error_message = str(exc)
                    run.progress_log = (run.progress_log or "") + f"[FATAL] {exc}\n"
                    run.finished_at = _dt.utcnow()
                    db.commit()
        except Exception:
            logger.exception(f"[run={run_id}] Could not write failure to DB")


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


@router.patch("/runs/{run_id}/interrupt", response_model=ScrapeRunRead)
async def interrupt_run(
    run_id: int,
    current_user: User = Depends(get_current_admin),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(select(ScrapeRun).where(ScrapeRun.id == run_id))
    run = result.scalar_one_or_none()
    if not run:
        raise HTTPException(status_code=404, detail="Run no encontrado")

    if run.status in ("failed", "completed"):
        return run

    recovered = _RECOVERY_STATUS.get(run.status)
    if recovered:
        run.status = recovered
        run.progress_log = (run.progress_log or "") + "[interrumpido] revertido para poder reintentar\n"
    else:
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


@router.post("/runs/{run_id}/geocode", status_code=status.HTTP_202_ACCEPTED)
async def trigger_run_geocode(
    run_id: int,
    background_tasks: BackgroundTasks,
    current_user: User = Depends(get_current_admin),
    db: AsyncSession = Depends(get_db),
):
    """Geocodifica items del staging de un run. Solo admin."""
    from app.config import settings

    if not settings.google_maps_api_key:
        raise HTTPException(status_code=400, detail="GOOGLE_MAPS_API_KEY no configurada en .env")

    result = await db.execute(select(ScrapeRun).where(ScrapeRun.id == run_id))
    run = result.scalar_one_or_none()
    if not run:
        raise HTTPException(status_code=404, detail="Run no encontrado")
    if run.status != "scraped":
        raise HTTPException(status_code=400, detail=f"Run debe estar en estado 'scraped', esta en '{run.status}'")

    run.status = "geocoding"
    await db.commit()

    background_tasks.add_task(
        _run_geocode_in_thread,
        run_id=run_id,
        api_key=settings.google_maps_api_key,
    )
    return {"message": "Geocodificacion iniciada"}


def _run_geocode_in_thread(run_id: int, api_key: str) -> None:
    from app.database import SyncSessionLocal
    from app.models.scrape_run import ScrapeRun
    from app.services.consolidation_service import geocode_run_items
    from sqlalchemy import select
    from datetime import datetime

    def _append_progress(line: str) -> None:
        with SyncSessionLocal() as db:
            run = db.execute(select(ScrapeRun).where(ScrapeRun.id == run_id)).scalar_one_or_none()
            if run:
                run.progress_log = (run.progress_log or "") + line + "\n"
                db.commit()

    try:
        count = geocode_run_items(run_id, api_key, progress_callback=_append_progress)
        with SyncSessionLocal() as db:
            run = db.execute(select(ScrapeRun).where(ScrapeRun.id == run_id)).scalar_one()
            run.status = "geocoded"
            db.commit()
    except Exception as e:
        with SyncSessionLocal() as db:
            run = db.execute(select(ScrapeRun).where(ScrapeRun.id == run_id)).scalar_one_or_none()
            if run:
                run.status = "scraped"  # revertir al checkpoint para reintentar
                run.error_message = f"Error en geocodificacion: {e}"
                run.progress_log = (run.progress_log or "") + f"[ERROR] {e}\n[reintentable] volve a tocar 'Geocodificar'\n"
                db.commit()


@router.post("/runs/{run_id}/metrics", status_code=status.HTTP_202_ACCEPTED)
async def trigger_run_metrics(
    run_id: int,
    background_tasks: BackgroundTasks,
    current_user: User = Depends(get_current_admin),
    db: AsyncSession = Depends(get_db),
):
    """Calcula metricas y commitea a la base de datos. Solo admin."""
    result = await db.execute(select(ScrapeRun).where(ScrapeRun.id == run_id))
    run = result.scalar_one_or_none()
    if not run:
        raise HTTPException(status_code=404, detail="Run no encontrado")
    if run.status != "geocoded":
        raise HTTPException(status_code=400, detail=f"Run debe estar en estado 'geocoded', esta en '{run.status}'")

    run.status = "computing_metrics"
    await db.commit()

    background_tasks.add_task(
        _run_metrics_in_thread,
        run_id=run_id,
        perfil_id=run.perfil_id,
    )
    return {"message": "Calculo de metricas iniciado"}


def _run_metrics_in_thread(run_id: int, perfil_id: int) -> None:
    from app.database import SyncSessionLocal
    from app.models.scrape_run import ScrapeRun
    from app.services.metrics_service import compute_metrics_and_commit
    from sqlalchemy import select
    from datetime import datetime

    def _append_progress(line: str) -> None:
        with SyncSessionLocal() as db:
            run = db.execute(select(ScrapeRun).where(ScrapeRun.id == run_id)).scalar_one_or_none()
            if run:
                run.progress_log = (run.progress_log or "") + line + "\n"
                db.commit()

    try:
        count = compute_metrics_and_commit(run_id, perfil_id, progress_callback=_append_progress)
        with SyncSessionLocal() as db:
            run = db.execute(select(ScrapeRun).where(ScrapeRun.id == run_id)).scalar_one()
            run.status = "completed"
            run.finished_at = datetime.utcnow()
            run.total_inserted = count  # approximate — actual insert/update split is in the log
            db.commit()
    except Exception as e:
        with SyncSessionLocal() as db:
            run = db.execute(select(ScrapeRun).where(ScrapeRun.id == run_id)).scalar_one_or_none()
            if run:
                run.status = "geocoded"  # revertir al checkpoint para reintentar
                run.error_message = f"Error en metricas/commit: {e}"
                run.progress_log = (run.progress_log or "") + f"[ERROR] {e}\n[reintentable] volve a tocar 'Metricas'\n"
                db.commit()


@router.post("/geocode/{perfil_id}", status_code=status.HTTP_202_ACCEPTED)
async def trigger_geocoding(
    perfil_id: int,
    background_tasks: BackgroundTasks,
    current_user: User = Depends(get_current_admin),
    db: AsyncSession = Depends(get_db),
):
    """Geocodifica propiedades sin coordenadas directamente en la DB. Solo admin."""
    from app.config import settings
    from app.services.consolidation_service import geocodificar_pendientes_sync

    if not settings.google_maps_api_key:
        raise HTTPException(status_code=400, detail="GOOGLE_MAPS_API_KEY no configurada en .env")

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
    """Recalcula metricas directamente sobre datos en la DB. Solo admin."""
    from app.services.metrics_service import compute_metrics_for_perfil

    background_tasks.add_task(compute_metrics_for_perfil, perfil_id=perfil_id)
    return {"message": "Cálculo de métricas iniciado en segundo plano"}
