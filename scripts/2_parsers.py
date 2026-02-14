from bs4 import BeautifulSoup
import re

# ================= HERRAMIENTAS =================

def clean_text(text):
    if not text: return ""
    return " ".join(text.replace('\n', ' ').replace('\r', '').split())

def force_int(text):
    if not text: return ""
    text_lower = text.lower()
    if "estrenar" in text_lower: return "0"
    
    clean = text.replace('.', '').replace(',', '')
    digits = re.sub(r'[^\d]', '', clean)
    return digits

def is_usd(text):
    if not text: return False
    t = text.upper()
    return 'USD' in t or 'U$S' in t or 'DOLARES' in t or 'US$' in t

def extract_ambientes_regex(text):
    """
    Busca patrones como:
    - '2 amb', '3 ambientes'
    - 'dos ambientes', 'tres ambientes'
    """
    if not text: return ""
    
    # 1. Busqueda numérica directa (Ej: "2 amb", "3amb")
    # El regex busca un número seguido opcionalmente de espacio y luego 'amb'
    match_num = re.search(r'(\d+)\s*amb', text, re.IGNORECASE)
    if match_num:
        return match_num.group(1)
        
    # 2. Búsqueda por palabras (Ej: "dos ambientes", "tres ambientes")
    text_lower = text.lower()
    if 'dos amb' in text_lower: return "2"
    if 'tres amb' in text_lower: return "3"
    if 'cuatro amb' in text_lower: return "4"
    
    return ""

# ================= PARSERS =================

def parse_zonaprop(html):
    soup = BeautifulSoup(html, 'html.parser')
    listings = []
    cards = soup.select('div[class*="postingCardLayout-module__posting-card-layout"]')
    
    for card in cards:
        data = { 'Bajo_Precio': False, 'Porcentaje_Rebaja': '' }
        try:
            # Precio
            price_container = card.select_one('[class*="postingPrices-module__price"]')
            if price_container:
                raw = price_container.get_text()
                if is_usd(raw): continue
                discount = price_container.select_one('[class*="discount"]')
                if discount:
                    data['Bajo_Precio'] = True
                    data['Porcentaje_Rebaja'] = clean_text(discount.text)
                    discount.decompose()
                data['Precio'] = force_int(price_container.text)
            else:
                data['Precio'] = ""

            # Titulo y Dirección
            link_tag = card.select_one('[class*="postingCard-module__posting-description"] a')
            data['Titulo'] = clean_text(link_tag.text) if link_tag else ""

            addr_tag = card.select_one('[class*="postingLocations-module__location-address"]')
            raw_addr = clean_text(addr_tag.text) if addr_tag else ""
            
            if not any(char.isdigit() for char in raw_addr) and link_tag:
                 title_parts = data['Titulo'].split('-')
                 if len(title_parts) > 0 and any(char.isdigit() for char in title_parts[0]):
                     data['Direccion'] = title_parts[0].strip()
                 else:
                     data['Direccion'] = raw_addr
            else:
                data['Direccion'] = raw_addr

            exp = card.select_one('[class*="postingPrices-module__expenses"]')
            data['Expensas'] = force_int(exp.text) if exp else ""

            features = card.select('[class*="postingMainFeatures-module__posting-main-features-span"]')
            for f in features:
                txt = clean_text(f.text)
                low = txt.lower()
                val = force_int(txt)
                if 'tot' in low: data['Metros_Totales'] = val
                elif 'cub' in low or 'm²' in low: data['Metros_Cubiertos'] = val
                elif 'amb' in low: data['Ambientes'] = val
                elif 'dorm' in low: data['Dormitorios'] = val
                elif 'baño' in low: data['Baños'] = val
                elif 'coch' in low: data['Cocheras'] = val

            if link_tag:
                href = link_tag.get('href')
                if href: data['URL'] = "https://www.zonaprop.com.ar" + href if href.startswith('/') else href

            highlight = card.select_one('[class*="postingCard-module__highlight"]')
            if highlight: data['Etiqueta_Destacado'] = clean_text(highlight.text)

            listings.append(data)
        except: continue
    return listings

def parse_argenprop(html):
    soup = BeautifulSoup(html, 'html.parser')
    listings = []
    cards = soup.find_all('div', class_='listing__item')
    
    for card in cards:
        data = {}
        try:
            price = card.find('p', class_='card__price')
            if price:
                full = price.get_text().strip()
                if is_usd(full): continue
                val = full.split('+')[0] if '+' in full else full
                data['Precio'] = force_int(val)

            exp = card.find('span', class_='card__expenses')
            if exp: data['Expensas'] = force_int(exp.text)

            addr = card.find('p', class_='card__address')
            if addr: data['Direccion'] = clean_text(addr.text)
            
            title = card.find('h2', class_='card__title')
            data['Titulo'] = clean_text(title.text) if title else ""
            
            info = card.find('p', class_='card__info')
            data['Descripcion_Breve'] = clean_text(info.text) if info else ""

            details = card.select('ul.card__main-features li')
            for d in details:
                txt = clean_text(d.text)
                low = txt.lower()
                val = force_int(txt)
                if 'm²' in low: data['Metros_Cubiertos'] = val
                elif 'baño' in low: data['Baños'] = val
                elif 'dorm' in low: data['Dormitorios'] = val
                elif 'amb' in low: data['Ambientes'] = val
                elif 'años' in low or 'estrenar' in low: 
                    data['Antiguedad'] = force_int(txt)

            # --- IMPUTACIÓN DE AMBIENTES (Corrección Solicitada) ---
            # Si el campo Ambientes está vacío, buscamos en el texto
            if not data.get('Ambientes'):
                # Combinamos Título y Descripción para buscar
                text_to_search = f"{data.get('Titulo', '')} {data.get('Descripcion_Breve', '')}"
                found = extract_ambientes_regex(text_to_search)
                if found: 
                    data['Ambientes'] = found

            link = card.find('a', href=True)
            if link: data['URL'] = "https://www.argenprop.com" + link['href']

            visited = card.find('span', class_='card__visited')
            if visited: data['Visto_Estado'] = clean_text(visited.text)
            
            points = card.find('p', class_='card__points')
            if points: data['Visitas_Count'] = force_int(points.text)

            listings.append(data)
        except: continue
    return listings

def parse_cabaprop(html):
    soup = BeautifulSoup(html, 'html.parser')
    listings = []
    cards = soup.find_all('div', class_='cards')
    
    for card in cards:
        data = {}
        try:
            pr = card.find('span', class_='lc-price-normal')
            if pr:
                if is_usd(pr.text): continue
                data['Precio'] = force_int(pr.text)
            
            ex = card.find('span', class_='lc-price-small')
            if ex: data['Expensas'] = force_int(ex.text)

            content = card.find('div', class_='tc_content')
            if content:
                t = content.find('h4')
                data['Titulo'] = clean_text(t.text) if t else ""
                
                # Dirección
                p_tag = content.find('p')
                if p_tag:
                    for element in p_tag.contents:
                        if isinstance(element, str):
                            text_limpio = clean_text(element)
                            if any(char.isdigit() for char in text_limpio) and len(text_limpio) > 3:
                                data['Direccion'] = text_limpio
                                break
                    if 'Direccion' not in data:
                        full_text = p_tag.get_text()
                        strong_text = p_tag.find('strong').get_text() if p_tag.find('strong') else ""
                        data['Direccion'] = clean_text(full_text.replace(strong_text, "").split('<br>')[-1])

                badge = content.find('div', class_='badge_icon')
                if badge: 
                    img = badge.find('img')
                    if img: data['Inmobiliaria'] = img.get('alt', '')

            lis = card.select('ul.prop_details li')
            for li in lis:
                txt = clean_text(li.text)
                low = txt.lower()
                val = force_int(txt)
                if 'amb' in low: data['Ambientes'] = val
                elif 'dorm' in low: data['Dormitorios'] = val
                elif 'baño' in low: data['Baños'] = val
                elif 'total' in low: data['Metros_Totales'] = val
                elif 'cubierto' in low: data['Metros_Cubiertos'] = val

            # --- IMPUTACIÓN DE AMBIENTES CABAPROP ---
            if not data.get('Ambientes'):
                found = extract_ambientes_regex(data.get('Titulo', ''))
                if found: data['Ambientes'] = found

            l = card.find('a', href=True)
            if l:
                href = l['href']
                data['URL'] = "https://cabaprop.com.ar" + href if href.startswith('/') else href

            footer_span = card.find('span', string=re.compile("Publicado el"))
            if footer_span:
                data['Fecha_Publicacion'] = clean_text(footer_span.text).replace('Publicado el', '').strip()

            listings.append(data)
        except: continue
    return listings