"""
Motor de scraping con Scrapling.
  - ArgenProp: Fetcher (HTTP con TLS fingerprint, rápido)
  - ZonaProp: Fetcher con cookie cf_clearance (pasa Cloudflare, sin navegador)
  - Resultados se guardan como JSON en staging/ (no se escribe a departamentos)
"""
import json
import os
import pathlib
import re
import time
import logging
from datetime import datetime, date

from scrapling import Fetcher

from app.services.url_builder_service import build_all_urls
from app.services.parser_service import parse_argenprop, parse_zonaprop
from app.core.normalization import url_normalize
from app.core.constants import TIPOS_DISPONIBLES

logger = logging.getLogger(__name__)

STAGING_DIR = pathlib.Path(__file__).parent.parent.parent / "staging"
STAGING_DIR.mkdir(exist_ok=True)

PARSERS = {
    "zonaprop": parse_zonaprop,
    "argenprop": parse_argenprop,
}


def _staging_path(run_id: int) -> pathlib.Path:
    return STAGING_DIR / f"run_{run_id}.json"


def save_staging(run_id: int, items: list[dict]) -> None:
    _staging_path(run_id).write_text(json.dumps(items, ensure_ascii=False, default=str), encoding="utf-8")


def load_staging(run_id: int) -> list[dict]:
    path = _staging_path(run_id)
    if not path.exists():
        return []
    return json.loads(path.read_text(encoding="utf-8"))


def delete_staging(run_id: int) -> None:
    path = _staging_path(run_id)
    if path.exists():
        path.unlink()


def fetch_page_html(url: str, portal: str, zonaprop_cookie: str | None = None, retries: int = 3) -> str | None:
    """Obtiene el HTML de una URL con Fetcher (HTTP con TLS fingerprint impersonation).

    ZonaProp está detrás de Cloudflare: se le inyecta la cookie cf_clearance que el
    usuario obtiene de su navegador, junto con el User-Agent e impersonate que la
    generaron (settings.zonaprop_*). ArgenProp va con headers sigilosos.
    Reintenta ante fallos transitorios de red / rate-limit.
    """
    from app.config import settings
    for attempt in range(1, retries + 1):
        try:
            if portal == "zonaprop":
                cookies = {"cf_clearance": zonaprop_cookie} if zonaprop_cookie else None
                page = Fetcher.get(
                    url,
                    headers={
                        "User-Agent": settings.zonaprop_user_agent,
                        "Accept-Language": "es-AR,es;q=0.9,en;q=0.8",
                    },
                    cookies=cookies,
                    impersonate=settings.zonaprop_impersonate,
                    stealthy_headers=False,
                    timeout=30,
                    follow_redirects=True,
                )
                if _is_cloudflare_block(page):
                    logger.warning("ZonaProp bloqueado por Cloudflare: cookie cf_clearance vencida o invalida")
                    return None  # no reintentar: la cookie no se renueva sola
                return page.body
            page = Fetcher.get(url, stealthy_headers=True, timeout=30)
            return page.body
        except Exception as e:
            if attempt < retries:
                time.sleep(1.5 * attempt)
                continue
            logger.warning(f"Error fetching {url} (intentos={retries}): {e}")
            return None


def _is_cloudflare_block(page) -> bool:
    # Cloudflare inyecta el script "challenge-platform" también en páginas válidas;
    # el bloqueo real se detecta por status de error o el título del interstitial.
    if getattr(page, "status", 200) in (403, 429, 503):
        return True
    body = page.body or b""
    if isinstance(body, (bytes, bytearray)):
        body = body.decode("utf-8", "replace")
    return "just a moment" in body.lower()


def _build_paginated_url(base_url: str, portal: str, page: int) -> str:
    """Construye la URL para la página N de resultados."""
    if page == 1:
        return base_url
    if portal == "argenprop":
        if "?" in base_url:
            path, qs = base_url.split("?", 1)
            return f"{path}/pagina-{page}?{qs}"
        return f"{base_url}/pagina-{page}"
    elif portal == "zonaprop":
        return base_url.replace(".html", f"-pagina-{page}.html")
    return base_url


def is_excluded(row: dict, filtros_exclusion: list[str]) -> bool:
    text_check = (
        str(row.get("Titulo", ""))
        + " "
        + str(row.get("Descripcion_Breve", ""))
        + " "
        + str(row.get("Ambientes", ""))
    ).lower()
    text_norm = text_check.replace(" ", "")

    for term in filtros_exclusion:
        term_clean = term.lower()
        if term_clean in text_check:
            return True
        if term_clean.replace(" ", "") in text_norm:
            return True

    if str(row.get("Ambientes")) == "1":
        return True
    return False


def is_valid_price(row: dict) -> bool:
    try:
        p = str(row.get("Precio", "")).strip()
        if not p.isdigit():
            return False
        val = int(p)
        return 10_000 <= val <= 999_999
    except Exception:
        return False


def scrape_portal(
    portal_name: str,
    urls_data: dict,
    config: dict,
    max_pages: int = 3,
    progress_callback=None,
    zonaprop_cookie: str | None = None,
) -> list[dict]:
    def log(msg: str) -> None:
        logger.info(msg)
        if progress_callback:
            progress_callback(msg)

    parser_func = PARSERS[portal_name]
    filtros_exclusion = config.get("filtros_exclusion", [])

    portal_data: list[dict] = []
    seen_urls: set[str] = set()
    total_filtered = 0

    log(f"Iniciando scraping de {portal_name.upper()}")

    for barrio, tipos_dict in urls_data.items():
        for tipo_inmueble, sitios in tipos_dict.items():
            url_inicial = sitios[portal_name]
            tipo_label = TIPOS_DISPONIBLES.get(tipo_inmueble, tipo_inmueble)

            log(f"  {barrio.upper()} | {tipo_label.upper()}")

            for current_page in range(1, max_pages + 1):
                page_url = _build_paginated_url(url_inicial, portal_name, current_page)
                log(f"    Pagina {current_page}...")

                html = fetch_page_html(page_url, portal_name, zonaprop_cookie)
                if not html:
                    log(f"    [ERROR] No se pudo obtener la pagina")
                    break

                items = parser_func(html)
                if not items:
                    if current_page == 1:
                        log(f"    0 resultados en pagina 1")
                    break

                new_count = 0
                for item in items:
                    url_prop = item.get("URL")
                    url_n = url_normalize(url_prop)
                    if url_n and url_n in seen_urls:
                        continue
                    if url_n:
                        seen_urls.add(url_n)

                    item["Portal"] = portal_name
                    item["Barrio"] = barrio
                    item["Tipo"] = tipo_label
                    item.pop("Ubicacion", None)

                    if is_excluded(item, filtros_exclusion):
                        total_filtered += 1
                        continue
                    if not is_valid_price(item):
                        total_filtered += 1
                        continue

                    portal_data.append(item)
                    new_count += 1

                log(f"      {new_count} nuevas propiedades")
                if new_count == 0:
                    log("      Sin novedades — cortando")
                    break

    log(f"{portal_name.upper()}: {len(portal_data)} items, {total_filtered} filtrados")
    return portal_data


def run_scraping_pipeline(
    run_id: int,
    perfil_id: int,
    portales: list[str],
    config: dict,
    zonaprop_cookie: str | None = None,
) -> None:
    from app.database import SyncSessionLocal
    from app.models.scrape_run import ScrapeRun
    from sqlalchemy import select

    def _append_progress(line: str) -> None:
        try:
            with SyncSessionLocal() as db:
                run = db.execute(select(ScrapeRun).where(ScrapeRun.id == run_id)).scalar_one_or_none()
                if run:
                    run.progress_log = (run.progress_log or "") + line + "\n"
                    db.commit()
        except Exception as exc:
            logger.warning(f"[run={run_id}] _append_progress failed: {exc}")

    logger.info(f"[run={run_id}] Iniciando scraping para perfil_id={perfil_id}")
    _append_progress(f"[run={run_id}] Iniciando scraping para perfil_id={perfil_id}")

    try:
        with SyncSessionLocal() as db:
            run = db.execute(select(ScrapeRun).where(ScrapeRun.id == run_id)).scalar_one_or_none()
            if not run:
                logger.error(f"ScrapeRun {run_id} no encontrado")
                return
            run.status = "scraping"
            run.started_at = datetime.utcnow()
            db.commit()
    except Exception as exc:
        logger.error(f"[run={run_id}] No se pudo actualizar status a 'scraping': {exc}")
        return

    urls_data = build_all_urls(config)
    all_items: list[dict] = []

    try:
        for portal_name in portales:
            if portal_name not in PARSERS:
                logger.warning(f"Portal desconocido: {portal_name}")
                continue

            items = scrape_portal(
                portal_name, urls_data, config,
                progress_callback=_append_progress,
                zonaprop_cookie=zonaprop_cookie,
            )
            all_items.extend(items)

        save_staging(run_id, all_items)
        _append_progress(f"Scraping finalizado. {len(all_items)} items guardados en staging.")

        with SyncSessionLocal() as db:
            run = db.execute(select(ScrapeRun).where(ScrapeRun.id == run_id)).scalar_one()
            run.status = "scraped"
            run.finished_at = datetime.utcnow()
            run.total_scraped = len(all_items)
            run.total_filtered = 0
            db.commit()

        logger.info(f"[run={run_id}] Scraping completado: {len(all_items)} items en staging")

    except Exception as e:
        logger.exception(f"[run={run_id}] Error en scraping: {e}")
        with SyncSessionLocal() as db:
            run = db.execute(select(ScrapeRun).where(ScrapeRun.id == run_id)).scalar_one_or_none()
            if run:
                run.status = "failed"
                run.finished_at = datetime.utcnow()
                run.error_message = str(e)
                db.commit()


def _mark_inactive(perfil_id: int) -> None:
    from app.database import SyncSessionLocal
    from app.models.departamento import Departamento
    from sqlalchemy import update

    today = date.today()
    with SyncSessionLocal() as db:
        db.execute(
            update(Departamento)
            .where(
                Departamento.perfil_id == perfil_id,
                Departamento.ultima_vez_visto < today,
                Departamento.activo == True,
            )
            .values(activo=False)
        )
        db.commit()
