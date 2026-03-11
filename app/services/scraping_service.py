"""
Motor de scraping con Selenium + Brave/Chrome.
Port de scripts/3_main.py con:
  - Sin CLI interactivo (recibe config por parámetro)
  - WebDriverWait en lugar de time.sleep fijo
  - Sesión sincrónica para correr como BackgroundTask
  - En Docker: por defecto Chromium headless (uc); si SCRAPER_BROWSER_URL está definido,
    se conecta a un navegador en el host (tu perfil, Zonaprop sin captcha) y corre en segundo plano.
"""
import os
import time
import logging
from datetime import datetime, date

from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException, WebDriverException

from app.services.url_builder_service import build_all_urls
from app.services.parser_service import parse_zonaprop, parse_argenprop, parse_cabaprop
from app.services.consolidation_service import upsert_items_sync
from app.core.normalization import url_normalize
from app.core.constants import TIPOS_DISPONIBLES

logger = logging.getLogger(__name__)

HOME_DIR = os.path.expanduser("~")

# User-Agent de Chrome real (Windows) para anti-detección
CHROME_USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/131.0.0.0 Safari/537.36"
)

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

# Zonaprop: como el script 3_main — delay fijo y parse, sin esperar al primer card (evita timeout cuando hay captcha/lentitud)
ZONAPROP_INITIAL_DELAY = 8
ZONAPROP_RETRY_DELAY = 5


def _common_anti_detection_options(options: Options) -> None:
    """Opciones de anti-detección comunes (user-agent, ventana, idioma)."""
    options.add_argument("--disable-notifications")
    options.add_argument("--disable-blink-features=AutomationControlled")
    options.add_argument("--window-size=1920,1080")
    options.add_argument("--lang=es-AR")
    options.add_argument("--disable-infobars")
    options.add_argument(f"--user-agent={CHROME_USER_AGENT}")
    options.add_experimental_option("excludeSwitches", ["enable-automation"])
    options.add_experimental_option("useAutomationExtension", False)


def setup_driver(headless: bool = False) -> webdriver.Chrome:
    docker_env = os.environ.get("DOCKER_ENV", "false").lower() == "true"

    if docker_env or headless:
        # Por defecto intentamos conectar al navegador del host (Brave con tu perfil = Zonaprop sin captcha).
        # Si no está corriendo, hacemos fallback a Chromium en Docker.
        remote_url = os.environ.get("SCRAPER_BROWSER_URL", "").strip()
        if remote_url:
            try:
                return _setup_driver_remote_browser(remote_url)
            except Exception as e:
                logger.warning(
                    "No se pudo conectar al navegador del host (%s): %s. Usando Chromium en Docker.",
                    remote_url,
                    e,
                )

        # Chromium headless en Docker (o fallback si no hay navegador en el host)
        try:
            import undetected_chromedriver as uc
        except ImportError:
            logger.warning("undetected_chromedriver no instalado, usando Selenium estándar")
            return _setup_driver_selenium_headless()

        chrome_bin = os.environ.get("CHROME_BIN", "/usr/bin/chromium")
        options = uc.ChromeOptions()
        options.add_argument("--no-sandbox")
        options.add_argument("--disable-dev-shm-usage")
        options.add_argument("--disable-gpu")
        options.add_argument("--headless=new")
        _common_anti_detection_options(options)

        version_main = None
        if os.environ.get("CHROME_VERSION_MAIN"):
            try:
                version_main = int(os.environ.get("CHROME_VERSION_MAIN", "0"))
            except ValueError:
                pass

        kwargs: dict = {
            "options": options,
            "headless": True,
            "browser_executable_path": chrome_bin,
            "use_subprocess": True,
        }
        if version_main:
            kwargs["version_main"] = version_main

        driver = uc.Chrome(**kwargs)
        return driver

    # Local (app no en Docker): Brave con perfil real, como el script original
    options = Options()
    brave_paths = [
        r"C:\Program Files\BraveSoftware\Brave-Browser\Application\brave.exe",
        r"C:\Program Files (x86)\BraveSoftware\Brave-Browser\Application\brave.exe",
    ]
    brave_path = next((p for p in brave_paths if os.path.exists(p)), None)
    if brave_path:
        options.binary_location = brave_path
        user_data = os.path.join(
            HOME_DIR, r"AppData\Local\BraveSoftware\Brave-Browser\User Data"
        )
        options.add_argument(f"--user-data-dir={user_data}")
        options.add_argument("--profile-directory=Default")

    _common_anti_detection_options(options)

    driver = webdriver.Chrome(options=options)
    driver.execute_script(
        "Object.defineProperty(navigator, 'webdriver', {get: () => undefined})"
    )
    return driver


def _setup_driver_remote_browser(debugger_address: str) -> webdriver.Chrome:
    """
    Conecta al navegador que ya está corriendo en el host (remote debugging).
    Ese navegador puede ser Brave con tu perfil, en headless, así Zonaprop no pide captcha
    y todo corre en segundo plano.
    """
    if "://" in debugger_address:
        debugger_address = debugger_address.replace("http://", "").replace("https://", "")
    options = Options()
    options.add_experimental_option("debuggerAddress", debugger_address)
    logger.info("Conectando al navegador en el host: %s", debugger_address)
    return webdriver.Chrome(options=options)


def _setup_driver_selenium_headless() -> webdriver.Chrome:
    """Fallback: Selenium estándar headless cuando uc no está disponible."""
    options = Options()
    options.add_argument("--headless=new")
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")
    options.add_argument("--disable-gpu")
    options.binary_location = os.environ.get("CHROME_BIN", "/usr/bin/chromium")
    _common_anti_detection_options(options)

    driver = webdriver.Chrome(options=options)
    driver.execute_script(
        "Object.defineProperty(navigator, 'webdriver', {get: () => undefined})"
    )
    return driver


# Palabras clave para detectar página de captcha/bloqueo anti-bot
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


def _page_looks_like_captcha(driver: webdriver.Chrome) -> bool:
    """True si el título o el HTML sugieren captcha o bloqueo anti-bot."""
    try:
        title = (driver.title or "").lower()
        html_snippet = (driver.page_source or "")[:2000].lower()
        combined = title + " " + html_snippet
        return any(kw in combined for kw in _CAPTCHA_KEYWORDS)
    except Exception:
        return False


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
    driver: webdriver.Chrome,
    portal_name: str,
    urls_data: dict,
    config: dict,
    max_pages: int = 3,
    progress_callback=None,
) -> list[dict]:
    """
    Raspa un portal usando WebDriverWait (más confiable que time.sleep fijo).
    Retorna lista de items sin filtrar.
    Si progress_callback(line: str) está definido, se llama con cada mensaje de progreso.
    """
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
                logger.error(f"    Error de driver: {e}")
                if progress_callback:
                    progress_callback(f"    [ERROR] {portal_name}: {e}")
                continue

            # Zonaprop: delay fijo y parse (como 3_main); evita timeout cuando hay captcha o respuesta lenta
            if portal_name == "zonaprop":
                time.sleep(ZONAPROP_INITIAL_DELAY)
            else:
                try:
                    WebDriverWait(driver, 20).until(
                        EC.presence_of_element_located((By.CSS_SELECTOR, first_card_sel))
                    )
                except TimeoutException:
                    logger.warning(f"    Timeout esperando cards en {url_inicial}")
                    if progress_callback:
                        progress_callback(f"    [TIMEOUT] {portal_name}: sin cards en {url_inicial[:60]}...")
                    continue
                except WebDriverException as e:
                    logger.error(f"    Error de driver: {e}")
                    if progress_callback:
                        progress_callback(f"    [ERROR] {portal_name}: {e}")
                    continue

            current_page = 1
            while current_page <= max_pages:
                log(f"    Página {current_page}...")
                html = driver.page_source
                items = parser_func(html)
                # Zonaprop: un retry si primera página con 0 cards (puede ser lentitud o captcha)
                if portal_name == "zonaprop" and current_page == 1 and not items:
                    time.sleep(ZONAPROP_RETRY_DELAY)
                    html = driver.page_source
                    items = parser_func(html)
                if not items and current_page == 1 and portal_name == "zonaprop":
                    logger.warning(
                        "Zonaprop: 0 cards tras delay+retry. Posible captcha. Titulo: %s",
                        driver.title,
                    )
                    logger.debug(
                        "Zonaprop HTML snippet: %s",
                        (driver.page_source or "")[:500],
                    )
                    if progress_callback:
                        progress_callback(
                            "    [ZONAPROP] Posible captcha o bloqueo. Sin cards tras esperar. "
                            "Podés usar Brave en el host (scripts/start_browser_for_scraper_visible.bat) para este portal."
                        )
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

                # Paginación con WebDriverWait en lugar de sleep(5)
                try:
                    driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
                    first_card = driver.find_elements(By.CSS_SELECTOR, first_card_sel)
                    first_card_ref = first_card[0] if first_card else None

                    next_btns = driver.find_elements(By.XPATH, next_xpath)
                    if not next_btns or not next_btns[0].is_enabled():
                        break

                    driver.execute_script("arguments[0].click();", next_btns[0])
                    # Zonaprop: delay tras click (como 3_main) para que cargue la siguiente página
                    if portal_name == "zonaprop":
                        time.sleep(5)
                    if first_card_ref:
                        # Esperar que el primer card viejo desaparezca (página nueva cargada)
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


def run_scraping_pipeline(
    run_id: int,
    perfil_id: int,
    portales: list[str],
    config: dict,
) -> None:
    """
    Pipeline completo de scraping para un perfil.
    Se ejecuta como BackgroundTask en un thread separado (es sincrónico).
    Actualiza scrape_run en la base de datos directamente via sesión sync.
    """
    from app.database import SyncSessionLocal
    from app.models.scrape_run import ScrapeRun
    from sqlalchemy import select

    def _append_progress(line: str) -> None:
        with SyncSessionLocal() as db:
            run = db.execute(select(ScrapeRun).where(ScrapeRun.id == run_id)).scalar_one_or_none()
            if run:
                run.progress_log = (run.progress_log or "") + line + "\n"
                db.commit()

    logger.info(f"[run={run_id}] Iniciando pipeline para perfil_id={perfil_id}")
    _append_progress(f"[run={run_id}] Iniciando pipeline para perfil_id={perfil_id}")

    with SyncSessionLocal() as db:
        run = db.execute(select(ScrapeRun).where(ScrapeRun.id == run_id)).scalar_one_or_none()
        if not run:
            logger.error(f"ScrapeRun {run_id} no encontrado")
            return
        run.status = "running"
        run.started_at = datetime.utcnow()
        db.commit()

    urls_data = build_all_urls(config)
    driver = None
    total_scraped = 0
    total_inserted = 0
    total_updated = 0
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
            total_scraped += len(items)

            if items:
                inserted, updated = upsert_items_sync(
                    items=items,
                    perfil_id=perfil_id,
                    run_id=run_id,
                )
                total_inserted += inserted
                total_updated += updated

        # Marcar como inactivas propiedades no vistas en este run
        _mark_inactive(perfil_id)

        with SyncSessionLocal() as db:
            run = db.execute(select(ScrapeRun).where(ScrapeRun.id == run_id)).scalar_one()
            run.status = "completed"
            run.finished_at = datetime.utcnow()
            run.total_scraped = total_scraped
            run.total_inserted = total_inserted
            run.total_updated = total_updated
            run.total_filtered = total_filtered
            db.commit()

        logger.info(
            f"[run={run_id}] Completado: scraped={total_scraped} "
            f"inserted={total_inserted} updated={total_updated}"
        )

    except Exception as e:
        logger.exception(f"[run={run_id}] Error en pipeline: {e}")
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
                # No cerrar el navegador del host cuando usamos SCRAPER_BROWSER_URL (queda para el próximo scrape)
                if not os.environ.get("SCRAPER_BROWSER_URL", "").strip():
                    driver.quit()
            except Exception:
                pass


def _mark_inactive(perfil_id: int) -> None:
    """Marca como inactivas las propiedades no vistas en el scrape de hoy."""
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
