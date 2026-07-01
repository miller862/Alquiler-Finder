"""
Generador de URLs por portal y perfil.
Port de scripts/1_url_builder.py — sin estado global, funciones puras.
"""
from typing import Any

TYPE_SLUGS: dict[str, dict[str, str]] = {
    "argenprop": {"departamento": "departamentos", "ph": "ph"},
    "zonaprop": {"departamento": "departamentos", "ph": "ph"},
}


def build_argenprop_url(barrio: str, tipo_std: str, config: dict) -> str:
    base = "https://www.argenprop.com"
    tipo_slug = TYPE_SLUGS["argenprop"][tipo_std]
    precio = config.get("precio", {})
    moneda = precio.get("moneda", "pesos")

    rango = f"{moneda}-{precio.get('min', '')}-{precio.get('max', '')}"
    path = f"/{tipo_slug}/alquiler/{barrio}/{rango}"

    query: list[str] = []
    extras = config.get("extras", {})
    if extras.get("expensas_max"):
        query.append(f"*-{extras['expensas_max']}-expensas")
    if extras.get("balcon") and tipo_std != "ph":
        query.append("con-ambiente-balcon")
    query.append("solo-ver-pesos")

    return f"{base}{path}?{'&'.join(query)}"


def build_zonaprop_url(barrio: str, tipo_std: str, config: dict) -> str:
    base = "https://www.zonaprop.com.ar"
    tipo_slug = TYPE_SLUGS["zonaprop"][tipo_std]
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


def build_all_urls(config: dict) -> dict:
    """
    Genera todas las URLs para el perfil dado.
    Retorna: {barrio: {tipo: {portal: url}}}
    """
    resultado: dict = {}
    for barrio in config.get("barrios", []):
        resultado[barrio] = {}
        for tipo in config.get("tipos", []):
            resultado[barrio][tipo] = {
                "argenprop": build_argenprop_url(barrio, tipo, config),
                "zonaprop": build_zonaprop_url(barrio, tipo, config),
            }
    return resultado
