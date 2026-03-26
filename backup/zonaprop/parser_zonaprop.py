"""
Backup de parse_zonaprop() — eliminado al migrar a MercadoLibre.
Para restaurar: copiar esta función a app/services/parser_service.py
"""
from bs4 import BeautifulSoup
import re


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
