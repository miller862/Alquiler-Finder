import sys
import os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import time
import re
import pandas as pd
from datetime import datetime
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By

import importlib
parametros = importlib.import_module('0_parametros')
url_builder = importlib.import_module('1_url_builder')
parsers = importlib.import_module('2_parsers')

obtener_configuracion = parametros.obtener_configuracion
TIPOS_DISPONIBLES = parametros.TIPOS_DISPONIBLES
generar_todas_urls = url_builder.generar_todas_urls
FILTROS_EXCLUSION = url_builder.FILTROS_EXCLUSION
configurar = url_builder.configurar
parse_zonaprop = parsers.parse_zonaprop
parse_argenprop = parsers.parse_argenprop
parse_cabaprop = parsers.parse_cabaprop

# ================= CONFIGURACIÓN =================
HOME_DIR = os.path.expanduser("~")
USER_DATA = os.path.join(HOME_DIR, r"AppData\Local\BraveSoftware\Brave-Browser\User Data")
BRAVE_PATH = r"C:\Program Files\BraveSoftware\Brave-Browser\Application\brave.exe"
if not os.path.exists(BRAVE_PATH):
    BRAVE_PATH = r"C:\Program Files (x86)\BraveSoftware\Brave-Browser\Application\brave.exe"

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
BASE_DATA_DIR = os.path.join(os.path.dirname(SCRIPT_DIR), 'data')
TODAY_STR = datetime.now().strftime("%Y-%m-%d")

# ================= FILTROS LÓGICOS =================

def is_excluded(row):
    """Filtro semántico."""
    text_check = (str(row.get('Titulo', '')) + " " + 
                  str(row.get('Descripcion_Breve', '')) + " " + 
                  str(row.get('Ambientes', ''))).lower()
    
    # Normalización simple para detectar palabras pegadas
    text_norm = text_check.replace(' ', '')
    
    for term in FILTROS_EXCLUSION:
        term_clean = term.lower()
        if term_clean in text_check: return True
        if term_clean.replace(' ', '') in text_norm: return True
        
    if str(row.get('Ambientes')) == '1': return True
    return False

def is_valid_price(row):
    try:
        p = str(row.get('Precio', ''))
        if not p.isdigit(): return False
        val = int(p)
        if 10000 <= val <= 999999: return True
        return False
    except: return False

# ================= SETUP =================
def setup_driver():
    options = Options()
    options.binary_location = BRAVE_PATH
    options.add_argument(f"--user-data-dir={USER_DATA}")
    options.add_argument("--profile-directory=Default")
    options.add_argument("--disable-notifications")
    options.add_argument("--disable-blink-features=AutomationControlled") 
    options.add_experimental_option("excludeSwitches", ["enable-automation"])
    options.add_experimental_option('useAutomationExtension', False)
    
    driver = webdriver.Chrome(options=options)
    driver.execute_script("Object.defineProperty(navigator, 'webdriver', {get: () => undefined})")
    return driver

# ================= MOTOR DE SCRAPING =================
def scrape_portal(driver, portal_name, urls_data, parser_func, next_xpath, max_pages=3):
    print(f"\n--- 🚀 INICIANDO {portal_name.upper()} ---")
    portal_data = []
    seen_urls = set()

    for barrio, tipos_dict in urls_data.items():
        for tipo_inmueble, sitios in tipos_dict.items():
            
            url_inicial = sitios[portal_name]
            tipo_label = TIPOS_DISPONIBLES.get(tipo_inmueble, tipo_inmueble)
            
            print(f"  📍 {barrio.upper()} | {tipo_label.upper()}")
            
            driver.get(url_inicial)
            time.sleep(3)
            
            current_page = 1
            while current_page <= max_pages:
                print(f"     📄 Pág {current_page}...")
                html = driver.page_source
                items = parser_func(html)
                
                new_items_count = 0
                if items:
                    for item in items:
                        url_prop = item.get('URL')
                        if url_prop and url_prop in seen_urls: continue
                        if url_prop: seen_urls.add(url_prop)
                        
                        item['Portal'] = portal_name
                        item['Barrio'] = barrio
                        item['Tipo'] = tipo_label
                        if 'Ubicacion' in item: del item['Ubicacion']
                        
                        portal_data.append(item)
                        new_items_count += 1
                    
                    print(f"        ✅ {new_items_count} nuevas.")
                    if new_items_count == 0:
                        print("        🛑 Sin novedades. Cortando sub-bucle.")
                        break
                else:
                    print("        ⚠️ 0 props.")
                
                try:
                    driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
                    time.sleep(1)
                    next_btns = driver.find_elements(By.XPATH, next_xpath)
                    if not next_btns or not next_btns[0].is_enabled(): break
                    driver.execute_script("arguments[0].click();", next_btns[0])
                    time.sleep(4)
                    current_page += 1
                except: break
    
    return portal_data

# ================= GUARDADO =================
def save_data(data_list, portal_name, perfil_nombre):
    if not data_list:
        print(f"❌ {portal_name}: Vacío.")
        return

    df = pd.DataFrame(data_list)
    initial_len = len(df)
    
    df['excluded'] = df.apply(is_excluded, axis=1)
    df = df[~df['excluded']].copy()
    
    df['valid_price'] = df.apply(is_valid_price, axis=1)
    df = df[df['valid_price']].copy()
    
    if 'URL' in df.columns:
        df.drop_duplicates(subset=['URL'], keep='first', inplace=True)
    
    clean_len = len(df)
    if initial_len - clean_len > 0:
        print(f"   🧹 Eliminados: {initial_len - clean_len} registros.")

    core_columns = [
        'Portal', 'Barrio', 'Tipo', 'Titulo', 'Precio', 'Expensas', 
        'Direccion', 
        'Metros_Totales', 'Metros_Cubiertos', 
        'Ambientes', 'Dormitorios', 'Baños', 
        'URL'
    ]
    
    existing = df.columns.tolist()
    for col in ['excluded', 'valid_price']:
        if col in existing: existing.remove(col)
        
    extras = [c for c in existing if c not in core_columns and c != 'Ubicacion']
    final_order = [c for c in core_columns if c in existing] + sorted(extras)
    
    df = df[final_order]
    
    target_folder = os.path.join(BASE_DATA_DIR, perfil_nombre, portal_name)
    if not os.path.exists(target_folder): os.makedirs(target_folder)
    
    filename = f"{portal_name}_{TODAY_STR}.csv"
    path = os.path.join(target_folder, filename)
    df.to_csv(path, index=False, sep=';', encoding='utf-8-sig')
    print(f"💾 GUARDADO: {path} ({len(df)} regs)")

# ================= RUN =================
def main():
    try:
        config = obtener_configuracion()
        configurar(config)
        perfil = config.get('nombre', 'default')
        
        os.system("taskkill /F /IM brave.exe >nul 2>&1")
        urls_dict = generar_todas_urls()
        driver = setup_driver()
        
        # Zonaprop
        data = scrape_portal(driver, "zonaprop", urls_dict, parse_zonaprop, "//a[@data-qa='PAGING_NEXT']")
        save_data(data, "zonaprop", perfil)

        # Argenprop
        data = scrape_portal(driver, "argenprop", urls_dict, parse_argenprop, "//li[contains(@class, 'pagination__page-next')]/a")
        save_data(data, "argenprop", perfil)

        # Cabaprop
        data = scrape_portal(driver, "cabaprop", urls_dict, parse_cabaprop, "//li[contains(@class, 'next')]/a")
        save_data(data, "cabaprop", perfil)

        print("\n🎉 LISTO.")
    except Exception as e:
        print(f"ERROR: {e}")
    finally:
        try: driver.quit()
        except: pass

if __name__ == "__main__":
    main()
