# Zonaprop Scraping Notes (Backup)

## Fetching
- Usaba `StealthyFetcher` de scrapling (browser headless con bypass de Cloudflare/CAPTCHA)
- Config: `StealthyFetcher.fetch(url, headless=True, solve_cloudflare=True, network_idle=True)`
- Los otros portales (argenprop, cabaprop) usan `Fetcher.get()` (HTTP sin browser)

## Paginacion
- URL base termina en `.html`
- Pagina N: `base_url.replace(".html", f"-pagina-{page}.html")`
- Ejemplo: `/departamentos-alquiler-belgrano.html` → `/departamentos-alquiler-belgrano-pagina-2.html`

## Parser
- BeautifulSoup con selectores CSS de zonaprop:
  - Cards: `div[class*="postingCardLayout-module__posting-card-layout"]`
  - Precio: `[class*="postingPrices-module__price"]`
  - Link: `[class*="postingCard-module__posting-description"] a`
  - Direccion: `[class*="postingLocations-module__location-address"]`
  - Expensas: `[class*="postingPrices-module__expenses"]`
  - Features: `[class*="postingMainFeatures-module__posting-main-features-span"]`

## Problema
- Cloudflare bloquea StealthyFetcher, incluso con solve_cloudflare=True
- CAPTCHA no se puede resolver automaticamente

## Para restaurar
1. Copiar `url_builder_zonaprop.py` → funciones en `app/services/url_builder_service.py`
2. Copiar `parser_zonaprop.py` → `parse_zonaprop()` en `app/services/parser_service.py`
3. Restaurar StealthyFetcher branch en `app/services/scraping_service.py`
4. Restaurar paginacion zonaprop en `_build_paginated_url()`
5. Actualizar PARSERS dict, PRIORIDAD_PORTALES, defaults en model/schema, template checkboxes
