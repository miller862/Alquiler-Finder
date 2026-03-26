"""
Backup de build_zonaprop_url() — eliminado al migrar a MercadoLibre.
Para restaurar: copiar esta función a app/services/url_builder_service.py
y actualizar TYPE_SLUGS, build_all_urls(), PARSERS, etc.
"""

TYPE_SLUGS_ZONAPROP = {"departamento": "departamentos", "ph": "ph"}


def build_zonaprop_url(barrio: str, tipo_std: str, config: dict) -> str:
    base = "https://www.zonaprop.com.ar"
    tipo_slug = TYPE_SLUGS_ZONAPROP[tipo_std]
    parts = [tipo_slug, "alquiler", barrio]

    if config.get("extras", {}).get("balcon") and tipo_std != "ph":
        parts.append("con-balcon")

    dorm = config.get("dormitorios", {})
    amb = config.get("ambientes", {})
    sup = config.get("superficie", {})
    precio = config.get("precio", {})

    if dorm.get("min") and dorm.get("max"):
        parts.append(f"desde-{dorm['min']}-hasta-{dorm['max']}-habitaciones")
    if amb.get("min") and amb.get("max"):
        parts.append(f"desde-{amb['min']}-hasta-{amb['max']}-ambientes")
    if sup.get("cubierta_min"):
        parts.append(f"mas-{sup['cubierta_min']}-m2-cubiertos")
    if precio.get("min") and precio.get("max"):
        parts.append(f"{precio['min']}-{precio['max']}-{precio.get('moneda', 'pesos')}")

    return f"{base}/{'-'.join(parts)}.html"
