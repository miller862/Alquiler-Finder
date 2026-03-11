"""
Motor de scraping con undetected_chromedriver.
  - Local: abre Chrome/Chromium visible (permite resolver CAPTCHAs manualmente)
  - Docker: headless con uc
  - Resultados se guardan como JSON en staging/ (no se escribe a departamentos)
  - CAPTCHA poll loop: si ZonaProp muestra captcha, espera hasta 2 min
"""
import json
import os
import pathlib
import time
import logging
from datetime import datetime, date

from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException, WebDriverException

from app.services.url_builder_service import build_all_urls
from app.services.parser_service import parse_zonaprop, parse_argenprop, parse_cabaprop
from app.core.normalization import url_normalize
from app.core.constants import TIPOS_DISPONIBLES

logger = logging.getLogger(__name__)

STAGING_DIR = pathlib.Path(__file__).parent.parent.parent / "staging"
STAGING_DIR.mkdir(exist_ok=True)

# Selectores CSS para WebDriverWait por portal
FIRST_CARD_SELECTORS = {
    "zonaprop": 'div[class*="postingCardLayout-module__posting-card-layout"]',
    "argenprop": "div.listing__item",
    "cabaprop": "div.cards",
}

NEXT_XPATHS = {
    "zonaprop": "//a[@data-qa='PAGING_NEXT']",
    "argenprop": "//li[contains(@class, 'pagination__page-next')]/a",
    "cabaprop": "//li[contains(@class, 'next')]/a",
}

PARSERS = {
    "zonaprop": parse_zonaprop,
    "argenprop": parse_argenprop,
    "cabaprop": parse_cabaprop,
}

ZONAPROP_INITIAL_DELAY = 8
ZONAPROP_RETRY_DELAY = 5
CAPTCHA_POLL_INTERVAL = 5
CAPTCHA_TIMEOUT = 120


# ---------------------------------------------------------------------------
# Staging helpers
# ---------------------------------------------------------------------------

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


# ---------------------------------------------------------------------------
# Driver setup — undetected_chromedriver for all environments
# ---------------------------------------------------------------------------

def setup_driver() -> "webdriver.Chrome":
    import undetected_chromedriver as uc

    docker_env = os.environ.get("DOCKER_ENV", "false").lower() == "true"

    if docker_env:
        chrome_bin = os.environ.get("CHROME_BIN", "/usr/bin/chromium")
        options = uc.ChromeOptions()
        options.add_argument("--no-sandbox")
        options.add_argument("--disable-dev-shm-usage")
        options.add_argument("--disable-gpu")
        options.add_argument("--headless=new")
        options.add_argument("--window-size=1920,1080")
        options.add_argument("--lang=es-AR")

        # Use system chromedriver (chromium-driver apt package) to avoid version mismatch
        # with the auto-downloaded one. Falls back to env var if system driver not found.
        driver_exec = None
        system_driver = os.environ.get("CHROMEDRIVER_BIN", "/usr/bin/chromedriver")
        if os.path.exists(system_driver):
            driver_exec = system_driver

        version_main = None
        if os.environ.get("CHROME_VERSION_MAIN"):
            try:
                version_main = int(os.environ["CHROME_VERSION_MAIN"])
            except ValueError:
                pass

        kwargs: dict = {
            "options": options,
            "headless": True,
            "browser_executable_path": chrome_bin,
            "use_subprocess": True,
        }
        if driver_exec:
            kwargs["driver_executable_path"] = driver_exec
        if version_main:
            kwargs["version_main"] = version_main

        return uc.Chrome(**kwargs)

    # Local: visible (para resolver CAPTCHAs manualmente)
    options = uc.ChromeOptions()
    options.add_argument("--window-size=1920,1080")
    options.add_argument("--lang=es-AR")
    options.add_argument("--disable-notifications")

    return uc.Chrome(options=options, headless=False)


# ---------------------------------------------------------------------------
# CAPTCHA detection
# ---------------------------------------------------------------------------

_CAPTCHA_KEYWORDS = (
    "captcha",
    "verificación",
    "verificacion",
    "cloudflare",
    "acceso denegado",
    "detectado",
    "robot",
    "automated",
    "blocked",
)


def _page_looks_like_captcha(driver) -> bool:
    try:
        title = (driver.title or "").lower()
        html_snippet = (driver.page_source or "")[:2000].lower()
        combined = title + " " + html_snippet
        return any(kw in combined for kw in _CAPTCHA_KEYWORDS)
    except Exception:
        return False


# ---------------------------------------------------------------------------
# Filters
# ---------------------------------------------------------------------------

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


# ---------------------------------------------------------------------------
# Portal scraping
# ---------------------------------------------------------------------------

def scrape_portal(
    driver,
    portal_name: str,
    urls_data: dict,
    config: dict,
    max_pages: int = 3,
    progress_callback=None,
) -> list[dict]:
    def log(msg: str) -> None:
        logger.info(msg)
        if progress_callback:
            progress_callback(msg)

    parser_func = PARSERS[portal_name]
    next_xpath = NEXT_XPATHS[portal_name]
    first_card_sel = FIRST_CARD_SELECTORS[portal_name]
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

            try:
                driver.get(url_inicial)
            except WebDriverException as e:
                log(f"    [ERROR] {portal_name}: {e}")
                continue

            # Zonaprop: delay fijo + CAPTCHA poll
            if portal_name == "zonaprop":
                time.sleep(ZONAPROP_INITIAL_DELAY)
            else:
                try:
                    WebDriverWait(driver, 20).until(
                        EC.presence_of_element_located((By.CSS_SELECTOR, first_card_sel))
                    )
                except TimeoutException:
                    log(f"    [TIMEOUT] {portal_name}: sin cards en {url_inicial[:60]}...")
                    continue
                except WebDriverException as e:
                    log(f"    [ERROR] {portal_name}: {e}")
                    continue

            current_page = 1
            while current_page <= max_pages:
                log(f"    Pagina {current_page}...")
                html = driver.page_source
                items = parser_func(html)

                # Zonaprop: retry + CAPTCHA poll
                if portal_name == "zonaprop" and current_page == 1 and not items:
                    time.sleep(ZONAPROP_RETRY_DELAY)
                    html = driver.page_source
                    items = parser_func(html)

                if not items and current_page == 1 and portal_name == "zonaprop":
                    if _page_looks_like_captcha(driver):
                        log("    [CAPTCHA] Detectado en Zonaprop. Resolvelo en la ventana del navegador...")
                        captcha_start = time.time()
                        resolved = False
                        while time.time() - captcha_start < CAPTCHA_TIMEOUT:
                            time.sleep(CAPTCHA_POLL_INTERVAL)
                            if not _page_looks_like_captcha(driver):
                                log("    [CAPTCHA] Resuelto! Continuando...")
                                driver.get(url_inicial)
                                time.sleep(ZONAPROP_INITIAL_DELAY)
                                html = driver.page_source
                                items = parser_func(html)
                                resolved = True
                                break
                        if not resolved:
                            log("    [CAPTCHA] Timeout (2 min). Salteando esta combinacion.")
                            break
                        if not items:
                            log("    [ZONAPROP] 0 cards tras resolver captcha. Salteando.")
                            break
                    else:
                        log("    [ZONAPROP] 0 cards tras delay+retry. Posible bloqueo.")
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

                # Paginacion
                try:
                    driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
                    first_card = driver.find_elements(By.CSS_SELECTOR, first_card_sel)
                    first_card_ref = first_card[0] if first_card else None

                    next_btns = driver.find_elements(By.XPATH, next_xpath)
                    if not next_btns or not next_btns[0].is_enabled():
                        break

                    driver.execute_script("arguments[0].click();", next_btns[0])
                    if portal_name == "zonaprop":
                        time.sleep(5)
                    if first_card_ref:
                        WebDriverWait(driver, 15).until(
                            EC.staleness_of(first_card_ref)
                        )
                    else:
                        WebDriverWait(driver, 15).until(
                            EC.presence_of_element_located((By.CSS_SELECTOR, first_card_sel))
                        )
                    current_page += 1
                except (TimeoutException, WebDriverException):
                    break

    log(f"{portal_name.upper()}: {len(portal_data)} items, {total_filtered} filtrados")
    return portal_data


# ---------------------------------------------------------------------------
# Pipeline: scrape only (stores JSON staging, does NOT write to departamentos)
# ---------------------------------------------------------------------------

def run_scraping_pipeline(
    run_id: int,
    perfil_id: int,
    portales: list[str],
    config: dict,
) -> None:
    from app.database import SyncSessionLocal
    from app.models.scrape_run import ScrapeRun
    from sqlalchemy import select

    def _append_progress(line: str) -> None:
        with SyncSessionLocal() as db:
            run = db.execute(select(ScrapeRun).where(ScrapeRun.id == run_id)).scalar_one_or_none()
            if run:
                run.progress_log = (run.progress_log or "") + line + "\n"
                db.commit()

    logger.info(f"[run={run_id}] Iniciando scraping para perfil_id={perfil_id}")
    _append_progress(f"[run={run_id}] Iniciando scraping para perfil_id={perfil_id}")

    with SyncSessionLocal() as db:
        run = db.execute(select(ScrapeRun).where(ScrapeRun.id == run_id)).scalar_one_or_none()
        if not run:
            logger.error(f"ScrapeRun {run_id} no encontrado")
            return
        run.status = "scraping"
        run.started_at = datetime.utcnow()
        db.commit()

    urls_data = build_all_urls(config)
    driver = None
    all_items: list[dict] = []
    total_filtered = 0

    try:
        driver = setup_driver()

        for portal_name in portales:
            if portal_name not in PARSERS:
                logger.warning(f"Portal desconocido: {portal_name}")
                continue

            items = scrape_portal(
                driver, portal_name, urls_data, config,
                progress_callback=_append_progress,
            )
            all_items.extend(items)

        # Save to staging JSON (NOT to departamentos)
        save_staging(run_id, all_items)
        _append_progress(f"Scraping finalizado. {len(all_items)} items guardados en staging.")

        with SyncSessionLocal() as db:
            run = db.execute(select(ScrapeRun).where(ScrapeRun.id == run_id)).scalar_one()
            run.status = "scraped"
            run.finished_at = datetime.utcnow()
            run.total_scraped = len(all_items)
            run.total_filtered = total_filtered
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
    finally:
        if driver:
            try:
                driver.quit()
            except Exception:
                pass


# ---------------------------------------------------------------------------
# Mark inactive (called at commit time, after metrics)
# ---------------------------------------------------------------------------

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
