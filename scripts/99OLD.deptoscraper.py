import time
import os
import re
import pandas as pd
from datetime import datetime
from bs4 import BeautifulSoup
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By

# ================= CONFIGURACIÓN =================
HOME_DIR = os.path.expanduser("~")
USER_DATA = os.path.join(HOME_DIR, r"AppData\Local\BraveSoftware\Brave-Browser\User Data")

# Busca Brave automáticamente
posibles_brave = [
    r"C:\Program Files\BraveSoftware\Brave-Browser\Application\brave.exe",
    r"C:\Program Files (x86)\BraveSoftware\Brave-Browser\Application\brave.exe"
]
BRAVE_PATH = None
for ruta in posibles_brave:
    if os.path.exists(ruta): BRAVE_PATH = ruta; break

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
BASE_DATA_DIR = os.path.join(os.path.dirname(SCRIPT_DIR), 'data')
TODAY_STR = datetime.now().strftime("%Y-%m-%d")

# ================= SETUP NAVEGADOR =================
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
    # Truco para que no detecten selenium
    driver.execute_script("Object.defineProperty(navigator, 'webdriver', {get: () => undefined})")
    return driver

# ================= MOTORES DE EXTRACCIÓN (RENOVADOS) =================

def parse_zonaprop(html):
    """
    Motor reconstruido basado en el Excel de Instant Data Scraper.
    Busca clases parciales como 'postingPrices-module__price'.
    """
    soup = BeautifulSoup(html, 'html.parser')
    listings = []
    
    # Buscamos las tarjetas usando una clase que contenga 'postingCardLayout'
    # Esto es lo que usa la extensión para identificar cada fila.
    cards = soup.find_all(lambda tag: tag.name == 'div' and 
                                      tag.get('class') and 
                                      any('postingCardLayout-module__posting-card-layout' in c for c in tag.get('class')))
    
    for card in cards:
        try:
            data = {}
            
            # 1. PRECIO (postingPrices-module__price)
            price_tag = card.find(lambda tag: tag.name and tag.get('class') and any('postingPrices-module__price' in c for c in tag.get('class')))
            data['Precio'] = price_tag.text.strip() if price_tag else ""
            
            # 2. EXPENSAS (postingPrices-module__expenses)
            exp_tag = card.find(lambda tag: tag.name and tag.get('class') and any('postingPrices-module__expenses' in c for c in tag.get('class')))
            data['Expensas'] = exp_tag.text.strip() if exp_tag else ""
            
            # 3. DIRECCIÓN (postingLocations-module__location-address)
            addr_tag = card.find(lambda tag: tag.name and tag.get('class') and any('postingLocations-module__location-address' in c for c in tag.get('class')))
            data['Direccion'] = addr_tag.text.strip() if addr_tag else ""
            
            # 4. URL (postingCard-module__posting-description href)
            # A veces el link está en la descripción o en toda la tarjeta. Buscamos el primer <a> con href
            link_tag = card.find('a', href=True)
            if link_tag:
                url = link_tag['href']
                if not url.startswith('http'):
                    url = "https://www.zonaprop.com.ar" + url
                data['URL'] = url
            else:
                data['URL'] = ""

            # 5. CARACTERÍSTICAS (postingMainFeatures-module__posting-main-features-span)
            # El Excel muestra Span 1, Span 2, etc. Vamos a juntarlos o separarlos.
            features = card.find_all(lambda tag: tag.name and tag.get('class') and any('postingMainFeatures-module__posting-main-features-span' in c for c in tag.get('class')))
            
            # Intentamos mapear inteligentemente (Metros, Ambientes, Baños, Cocheras)
            data['Metros'] = ""
            data['Ambientes'] = ""
            data['Dormitorios'] = "" # A veces dice dorm. en vez de amb.
            
            for f in features:
                text = f.text.strip()
                if 'm²' in text: data['Metros'] = text
                elif 'amb' in text.lower(): data['Ambientes'] = text
                elif 'dorm' in text.lower(): data['Dormitorios'] = text
                elif 'baño' in text.lower(): data['Baños'] = text
                elif 'coch' in text.lower(): data['Cocheras'] = text

            # 6. DESCRIPCIÓN CORTA
            desc_tag = card.find(lambda tag: tag.name == 'h2') # O el posting-description
            data['Titulo'] = desc_tag.text.strip() if desc_tag else ""

            listings.append(data)
        except Exception as e:
            continue
            
    return listings

def parse_argenprop(html):
    # Argenprop usa BEM standard, suele ser más limpio
    soup = BeautifulSoup(html, 'html.parser')
    listings = []
    cards = soup.find_all('div', class_='listing__item')
    
    for card in cards:
        try:
            data = {}
            # Precio
            price = card.find('p', class_='card__price')
            data['Precio'] = price.text.strip() if price else ""
            
            # Expensas
            exp = card.find('span', class_='card__expenses')
            data['Expensas'] = exp.text.strip() if exp else ""

            # Dirección
            addr = card.find('p', class_='card__address') 
            data['Direccion'] = addr.text.strip() if addr else ""
            
            # URL
            link_tag = card.find('a', href=True)
            if link_tag:
                data['URL'] = "https://www.argenprop.com" + link_tag['href']
            
            # Detalles
            details = card.find_all('li')
            for d in details:
                txt = d.text.strip()
                if 'm²' in txt: data['Metros'] = txt
                elif 'dorm' in txt.lower(): data['Dormitorios'] = txt
                elif 'baño' in txt.lower(): data['Baños'] = txt

            listings.append(data)
        except: continue
    return listings

def parse_cabaprop(html):
    soup = BeautifulSoup(html, 'html.parser')
    listings = []
    
    # CORRECCIÓN: Usamos la clase 'cards' que se ve en tu HTML
    cards = soup.find_all('div', class_='cards')
    
    for card in cards:
        try:
            data = {}
            
            # 1. PRECIO (span class="lc-price-normal")
            price = card.find('span', class_='lc-price-normal')
            data['Precio'] = price.text.strip() if price else "Consultar"
            
            # 2. EXPENSAS (span class="lc-price-small")
            exp = card.find('span', class_='lc-price-small')
            data['Expensas'] = exp.text.strip().replace("Expensas:", "").strip() if exp else ""

            # 3. DIRECCIÓN Y TÍTULO (div class="tc_content")
            content = card.find('div', class_='tc_content')
            if content:
                # Título
                title = content.find('h4')
                data['Titulo'] = title.text.strip() if title else ""
                
                # Dirección: Está dentro de un <p> después de un <br>.
                # Usamos get_text con separador para dividir "Departamento | Dirección"
                p_tag = content.find('p')
                if p_tag:
                    texto_completo = p_tag.get_text(separator="|")
                    partes = texto_completo.split('|')
                    # La dirección suele ser la última parte después del <br>
                    data['Direccion'] = partes[-1].strip() if len(partes) > 1 else texto_completo.strip()
            
            # 4. URL (div class="details" -> a href)
            details = card.find('div', class_='details')
            if details:
                link = details.find('a', href=True)
                if link:
                    data['URL'] = "https://cabaprop.com.ar" + link['href']
            
            # 5. DETALLES (ul class="prop_details")
            # Recorremos los <li> para sacar metros, ambientes, etc.
            prop_details = card.find('ul', class_='prop_details')
            if prop_details:
                items = prop_details.find_all('li')
                for item in items:
                    txt = item.get_text(separator=" ").strip()
                    if 'm² total' in txt: data['Metros_Totales'] = txt
                    elif 'm² cubierto' in txt: data['Metros_Cubiertos'] = txt
                    elif 'Ambientes' in txt: data['Ambientes'] = txt
                    elif 'Dorm' in txt: data['Dormitorios'] = txt
                    elif 'Baño' in txt: data['Baños'] = txt

            listings.append(data)
        except Exception as e:
            print(f"Error en una tarjeta: {e}")
            continue
            
    return listings

# ================= LÓGICA DE NAVEGACIÓN =================

def run_scraper_bs4(site_name, start_url, next_xpath, parser_func, max_pages=3):
    print(f"\n--- 🚀 INICIANDO {site_name.upper()} (V11: CLONANDO EXTENSIÓN) ---")
    driver.get(start_url)
    time.sleep(3) 
    
    all_data = []
    current_page = 1
    
    while current_page <= max_pages:
        print(f"   📄 Procesando página {current_page}...")
        
        # 1. PARSEAR
        html = driver.page_source
        page_data = parser_func(html)
        
        if page_data:
            print(f"      ✅ Capturados {len(page_data)} departamentos.")
            all_data.extend(page_data)
        else:
            print("      ⚠️ 0 departamentos encontrados. (Posible Captcha o fin de lista)")
            time.sleep(2)

        # 2. SIGUIENTE PAGINA
        try:
            # Scroll al fondo
            driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
            time.sleep(1)
            
            next_btn = driver.find_element(By.XPATH, next_xpath)
            
            # Chequeos de botón deshabilitado
            if not next_btn.is_enabled(): break
            class_attr = next_btn.get_attribute("class")
            if class_attr and ("disabled" in class_attr or "disable" in class_attr): break
                
            driver.execute_script("arguments[0].click();", next_btn)
            time.sleep(5) 
            current_page += 1
        except Exception:
            print("   🛑 Fin de páginas.")
            break
            
    # 3. GUARDAR
    if all_data:
        # Ordenamos las columnas para que queden prolijas
        column_order = ['Precio', 'Expensas', 'Direccion', 'Metros', 'Ambientes', 'Dormitorios', 'Baños', 'Cocheras', 'Titulo', 'URL']
        # Nos aseguramos de que existan las columnas aunque estén vacías
        df = pd.DataFrame(all_data)
        for col in column_order:
            if col not in df.columns: df[col] = ""
            
        # Reordenar y guardar
        df = df[column_order] # + cualquier otra columna extra que haya aparecido
        
        target_folder = os.path.join(BASE_DATA_DIR, site_name)
        if not os.path.exists(target_folder): os.makedirs(target_folder)
        
        filename = f"{site_name}_{TODAY_STR}.csv"
        save_path = os.path.join(target_folder, filename)
        
        df.to_csv(save_path, index=False, encoding='utf-8-sig', sep=';') # Uso ; para que Excel lo abra directo
        print(f"   💾 GUARDADO PERFECTO: {save_path}")
    else:
        print("   ❌ No se guardó nada.")

# ================= EJECUCIÓN =================

try:
    # Matar Brave previo
    os.system("taskkill /F /IM brave.exe >nul 2>&1")
    
    driver = setup_driver()
    
    # 1. ZONAPROP
    run_scraper_bs4(
        "zonaprop", 
        "https://www.zonaprop.com.ar/ph-alquiler-villa-urquiza.html", 
        "//a[@data-qa='PAGING_NEXT']", # Este selector suele ser estable
        parse_zonaprop,
        max_pages=3
    )

    # 2. ARGENPROP
    run_scraper_bs4(
        "argenprop", 
        "https://www.argenprop.com/ph/alquiler/villa-urquiza/1-dormitorio", 
        "//li[contains(@class, 'pagination__page-next')]/a", 
        parse_argenprop,
        max_pages=3
    )

    # 3. CABAPROP
    run_scraper_bs4(
        "cabaprop", 
        "https://cabaprop.com.ar/propiedades/alquilar-ph-villa_urquiza?pagina=1", 
        "//li[contains(@class, 'next')]/a", 
        parse_cabaprop,
        max_pages=3
    )

    print("\n🎉 FIN DEL PROCESO.")

except Exception as e:
    print(f"ERROR: {e}")