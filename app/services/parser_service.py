"""
Parsers HTML para los 3 portales.
Port directo de scripts/2_parsers.py — funciones puras, sin estado.
"""
from bs4 import BeautifulSoup
import re


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def clean_text(text) -> str:
    if not text:
        return ""
    return " ".join(str(text).replace("\n", " ").replace("\r", "").split())


def force_int(text) -> str:
    if not text:
        return ""
    text_lower = str(text).lower()
    if "estrenar" in text_lower:
        return "0"
    clean = str(text).replace(".", "").replace(",", "")
    digits = re.sub(r"[^\d]", "", clean)
    return digits


def is_usd(text) -> bool:
    if not text:
        return False
    t = str(text).upper()
    return "USD" in t or "U$S" in t or "DOLARES" in t or "US$" in t


def extract_ambientes_regex(text: str) -> str:
    if not text:
        return ""
    match_num = re.search(r"(\d+)\s*amb", text, re.IGNORECASE)
    if match_num:
        return match_num.group(1)
    text_lower = text.lower()
    if "dos amb" in text_lower:
        return "2"
    if "tres amb" in text_lower:
        return "3"
    if "cuatro amb" in text_lower:
        return "4"
    return ""


# ---------------------------------------------------------------------------
# Portal parsers
# ---------------------------------------------------------------------------

def parse_zonaprop(html: str) -> list[dict]:
    soup = BeautifulSoup(html, "html.parser")
    listings: list[dict] = []
    cards = soup.select('div[class*="postingCardLayout-module__posting-card-layout"]')

    for card in cards:
        data: dict = {"Bajo_Precio": False, "Porcentaje_Rebaja": ""}
        try:
            price_container = card.select_one('[class*="postingPrices-module__price"]')
            if price_container:
                raw = price_container.get_text()
                if is_usd(raw):
                    continue
                discount = price_container.select_one('[class*="discount"]')
                if discount:
                    data["Bajo_Precio"] = True
                    data["Porcentaje_Rebaja"] = clean_text(discount.text)
                    discount.decompose()
                data["Precio"] = force_int(price_container.text)
            else:
                data["Precio"] = ""

            link_tag = card.select_one('[class*="postingCard-module__posting-description"] a')
            data["Titulo"] = clean_text(link_tag.text) if link_tag else ""

            addr_tag = card.select_one('[class*="postingLocations-module__location-address"]')
            raw_addr = clean_text(addr_tag.text) if addr_tag else ""
            if not any(ch.isdigit() for ch in raw_addr) and link_tag:
                title_parts = data["Titulo"].split("-")
                if title_parts and any(ch.isdigit() for ch in title_parts[0]):
                    data["Direccion"] = title_parts[0].strip()
                else:
                    data["Direccion"] = raw_addr
            else:
                data["Direccion"] = raw_addr

            exp = card.select_one('[class*="postingPrices-module__expenses"]')
            data["Expensas"] = force_int(exp.text) if exp else ""

            features = card.select('[class*="postingMainFeatures-module__posting-main-features-span"]')
            for f in features:
                txt = clean_text(f.text)
                low = txt.lower()
                val = force_int(txt)
                if "tot" in low:
                    data["Metros_Totales"] = val
                elif "cub" in low or "m²" in low:
                    data["Metros_Cubiertos"] = val
                elif "amb" in low:
                    data["Ambientes"] = val
                elif "dorm" in low:
                    data["Dormitorios"] = val
                elif "baño" in low:
                    data["Baños"] = val
                elif "coch" in low:
                    data["Cocheras"] = val

            if link_tag:
                href = link_tag.get("href")
                if href:
                    data["URL"] = (
                        "https://www.zonaprop.com.ar" + href
                        if href.startswith("/")
                        else href
                    )

            highlight = card.select_one('[class*="postingCard-module__highlight"]')
            if highlight:
                data["Etiqueta_Destacado"] = clean_text(highlight.text)

            listings.append(data)
        except Exception:
            continue

    return listings


def parse_argenprop(html: str) -> list[dict]:
    soup = BeautifulSoup(html, "html.parser")
    listings: list[dict] = []
    cards = soup.find_all("div", class_="listing__item")

    for card in cards:
        data: dict = {}
        try:
            price = card.find("p", class_="card__price")
            if price:
                full = price.get_text().strip()
                if is_usd(full):
                    continue
                val = full.split("+")[0] if "+" in full else full
                data["Precio"] = force_int(val)

            exp = card.find("span", class_="card__expenses")
            if exp:
                data["Expensas"] = force_int(exp.text)

            addr = card.find("p", class_="card__address")
            if addr:
                data["Direccion"] = clean_text(addr.text)

            title = card.find("h2", class_="card__title")
            data["Titulo"] = clean_text(title.text) if title else ""

            info = card.find("p", class_="card__info")
            data["Descripcion_Breve"] = clean_text(info.text) if info else ""

            details = card.select("ul.card__main-features li")
            for d in details:
                txt = clean_text(d.text)
                low = txt.lower()
                val = force_int(txt)
                if "m²" in low:
                    data["Metros_Cubiertos"] = val
                elif "baño" in low:
                    data["Baños"] = val
                elif "dorm" in low:
                    data["Dormitorios"] = val
                elif "amb" in low:
                    data["Ambientes"] = val
                elif "años" in low or "estrenar" in low:
                    data["Antiguedad"] = force_int(txt)

            if not data.get("Ambientes"):
                text_to_search = f"{data.get('Titulo', '')} {data.get('Descripcion_Breve', '')}"
                found = extract_ambientes_regex(text_to_search)
                if found:
                    data["Ambientes"] = found

            link = card.find("a", href=True)
            if link:
                data["URL"] = "https://www.argenprop.com" + link["href"]

            visited = card.find("span", class_="card__visited")
            if visited:
                data["Visto_Estado"] = clean_text(visited.text)

            points = card.find("p", class_="card__points")
            if points:
                data["Visitas_Count"] = force_int(points.text)

            listings.append(data)
        except Exception:
            continue

    return listings


def parse_cabaprop(html: str) -> list[dict]:
    soup = BeautifulSoup(html, "html.parser")
    listings: list[dict] = []
    cards = soup.find_all("div", class_="cards")

    for card in cards:
        data: dict = {}
        try:
            pr = card.find("span", class_="lc-price-normal")
            if pr:
                if is_usd(pr.text):
                    continue
                data["Precio"] = force_int(pr.text)

            ex = card.find("span", class_="lc-price-small")
            if ex:
                data["Expensas"] = force_int(ex.text)

            content = card.find("div", class_="tc_content")
            if content:
                t = content.find("h4")
                data["Titulo"] = clean_text(t.text) if t else ""

                p_tag = content.find("p")
                if p_tag:
                    for element in p_tag.contents:
                        if isinstance(element, str):
                            text_limpio = clean_text(element)
                            if any(ch.isdigit() for ch in text_limpio) and len(text_limpio) > 3:
                                data["Direccion"] = text_limpio
                                break
                    if "Direccion" not in data:
                        full_text = p_tag.get_text()
                        strong = p_tag.find("strong")
                        strong_text = strong.get_text() if strong else ""
                        data["Direccion"] = clean_text(
                            full_text.replace(strong_text, "").split("<br>")[-1]
                        )

                badge = content.find("div", class_="badge_icon")
                if badge:
                    img = badge.find("img")
                    if img:
                        data["Inmobiliaria"] = img.get("alt", "")

            lis = card.select("ul.prop_details li")
            for li in lis:
                txt = clean_text(li.text)
                low = txt.lower()
                val = force_int(txt)
                if "amb" in low:
                    data["Ambientes"] = val
                elif "dorm" in low:
                    data["Dormitorios"] = val
                elif "baño" in low:
                    data["Baños"] = val
                elif "total" in low:
                    data["Metros_Totales"] = val
                elif "cubierto" in low:
                    data["Metros_Cubiertos"] = val

            if not data.get("Ambientes"):
                found = extract_ambientes_regex(data.get("Titulo", ""))
                if found:
                    data["Ambientes"] = found

            l = card.find("a", href=True)
            if l:
                href = l["href"]
                data["URL"] = (
                    "https://cabaprop.com.ar" + href if href.startswith("/") else href
                )

            footer_span = card.find("span", string=re.compile("Publicado el"))
            if footer_span:
                data["Fecha_Publicacion"] = (
                    clean_text(footer_span.text).replace("Publicado el", "").strip()
                )

            listings.append(data)
        except Exception:
            continue

    return listings
