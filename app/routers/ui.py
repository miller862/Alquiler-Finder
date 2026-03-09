"""
Rutas de la interfaz de usuario (HTML/Jinja2).
Reemplaza la app de Streamlit.
"""
from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy import select

from app.dependencies import get_db, get_optional_user, get_current_user
from app.models.perfil import Perfil
from app.models.scrape_run import ScrapeRun

router = APIRouter(tags=["ui"])
templates = Jinja2Templates(directory="app/templates")


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
    # Cargar perfiles del usuario para el selector del sidebar
    result = await db.execute(
        select(Perfil).where(
            Perfil.user_id == current_user.id if not current_user.is_admin else True,
            Perfil.is_active == True,
        )
    )
    perfiles = result.scalars().all()

    return templates.TemplateResponse(
        "map.html",
        {
            "request": request,
            "user": current_user,
            "perfiles": perfiles,
            "active_page": "map",
        },
    )


@router.get("/ranking", response_class=HTMLResponse)
async def ranking_page(
    request: Request,
    db=Depends(get_db),
    current_user=Depends(get_current_user),
):
    result = await db.execute(
        select(Perfil).where(
            Perfil.user_id == current_user.id if not current_user.is_admin else True,
            Perfil.is_active == True,
        )
    )
    perfiles = result.scalars().all()

    return templates.TemplateResponse(
        "ranking.html",
        {
            "request": request,
            "user": current_user,
            "perfiles": perfiles,
            "active_page": "ranking",
        },
    )


@router.get("/stats", response_class=HTMLResponse)
async def stats_page(
    request: Request,
    db=Depends(get_db),
    current_user=Depends(get_current_user),
):
    result = await db.execute(
        select(Perfil).where(
            Perfil.user_id == current_user.id if not current_user.is_admin else True,
            Perfil.is_active == True,
        )
    )
    perfiles = result.scalars().all()

    return templates.TemplateResponse(
        "stats.html",
        {
            "request": request,
            "user": current_user,
            "perfiles": perfiles,
            "active_page": "stats",
        },
    )


@router.get("/admin/scraping", response_class=HTMLResponse)
async def scraping_panel(
    request: Request,
    db=Depends(get_db),
    current_user=Depends(get_current_user),
):
    from sqlalchemy import desc
    from app.dependencies import get_current_admin

    # Cargar perfiles y últimos runs
    result_perfiles = await db.execute(
        select(Perfil).where(
            Perfil.user_id == current_user.id if not current_user.is_admin else True,
            Perfil.is_active == True,
        )
    )
    perfiles = result_perfiles.scalars().all()

    result_runs = await db.execute(
        select(ScrapeRun).order_by(desc(ScrapeRun.created_at)).limit(20)
    )
    runs = result_runs.scalars().all()

    return templates.TemplateResponse(
        "admin_scraping.html",
        {
            "request": request,
            "user": current_user,
            "perfiles": perfiles,
            "runs": runs,
            "active_page": "scraping",
        },
    )
