"""
Rutas de la interfaz de usuario (HTML/Jinja2).
Reemplaza la app de Streamlit.
"""
from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy import select

from app.dependencies import get_db, get_optional_user, get_current_user, get_current_admin
from app.models.perfil import Perfil
from app.models.user import User
from app.models.scrape_run import ScrapeRun

router = APIRouter(tags=["ui"])
templates = Jinja2Templates(directory="app/templates")


async def _get_user_perfil(db, user):
    """Obtiene el unico perfil activo del usuario (1 user = 1 perfil)."""
    result = await db.execute(
        select(Perfil).where(Perfil.user_id == user.id, Perfil.is_active == True)
    )
    return result.scalars().first()


async def _get_all_perfiles(db):
    """Admin: obtiene todos los perfiles activos."""
    result = await db.execute(
        select(Perfil).where(Perfil.is_active == True)
    )
    return result.scalars().all()


@router.get("/", response_class=HTMLResponse)
async def root(request: Request, current_user=Depends(get_optional_user)):
    if current_user:
        return RedirectResponse(url="/map")
    return RedirectResponse(url="/login")


@router.get("/login", response_class=HTMLResponse)
async def login_page(request: Request):
    return templates.TemplateResponse("login.html", {"request": request})


@router.get("/map", response_class=HTMLResponse)
async def map_page(
    request: Request,
    db=Depends(get_db),
    current_user=Depends(get_current_user),
):
    perfil = await _get_user_perfil(db, current_user)
    all_perfiles = await _get_all_perfiles(db) if current_user.is_admin else []

    return templates.TemplateResponse(
        "map.html",
        {
            "request": request,
            "user": current_user,
            "perfil": perfil,
            "all_perfiles": all_perfiles,
            "active_page": "map",
        },
    )


@router.get("/ranking", response_class=HTMLResponse)
async def ranking_page(
    request: Request,
    db=Depends(get_db),
    current_user=Depends(get_current_user),
):
    perfil = await _get_user_perfil(db, current_user)
    all_perfiles = await _get_all_perfiles(db) if current_user.is_admin else []

    return templates.TemplateResponse(
        "ranking.html",
        {
            "request": request,
            "user": current_user,
            "perfil": perfil,
            "all_perfiles": all_perfiles,
            "active_page": "ranking",
        },
    )


@router.get("/stats", response_class=HTMLResponse)
async def stats_page(
    request: Request,
    db=Depends(get_db),
    current_user=Depends(get_current_user),
):
    perfil = await _get_user_perfil(db, current_user)
    all_perfiles = await _get_all_perfiles(db) if current_user.is_admin else []

    return templates.TemplateResponse(
        "stats.html",
        {
            "request": request,
            "user": current_user,
            "perfil": perfil,
            "all_perfiles": all_perfiles,
            "active_page": "stats",
        },
    )


@router.get("/mi-perfil", response_class=HTMLResponse)
async def mi_perfil_page(
    request: Request,
    db=Depends(get_db),
    current_user=Depends(get_current_user),
):
    perfil = await _get_user_perfil(db, current_user)

    return templates.TemplateResponse(
        "mi_perfil.html",
        {
            "request": request,
            "user": current_user,
            "perfil": perfil,
            "active_page": "mi-perfil",
        },
    )


@router.get("/admin/scraping", response_class=HTMLResponse)
async def scraping_panel(
    request: Request,
    db=Depends(get_db),
    current_user=Depends(get_current_admin),
):
    from sqlalchemy import desc
    from app.routers.scraping import mark_stale_runs

    all_perfiles = await _get_all_perfiles(db)

    # Limpiar runs obsoletos antes de renderizar el HTML para que no aparezcan como "running"
    await mark_stale_runs(db)

    result_runs = await db.execute(
        select(ScrapeRun).order_by(desc(ScrapeRun.created_at)).limit(20)
    )
    runs = result_runs.scalars().all()

    return templates.TemplateResponse(
        "admin_scraping.html",
        {
            "request": request,
            "user": current_user,
            "perfiles": all_perfiles,
            "runs": runs,
            "active_page": "scraping",
        },
    )
