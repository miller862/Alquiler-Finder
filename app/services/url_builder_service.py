"""
Generador de URLs por portal y perfil.
Port de scripts/1_url_builder.py — sin estado global, funciones puras.
"""
from typing import Any

TYPE_SLUGS: dict[str, dict[str, str]] = {
    "argenprop": {"departamento": "departamentos", "ph": "ph"},
    "cabaprop": {"departamento": "departamento", "ph": "ph"},
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


def build_cabaprop_url(barrio: str, tipo_std: str, config: dict) -> str:
    base = "https://cabaprop.com.ar"
    tipo_slug = TYPE_SLUGS["cabaprop"][tipo_std]
    barrio_fmt = barrio.replace("-", "_")
    precio = config.get("precio", {})
    amb = config.get("ambientes", {})
    dorm = config.get("dormitorios", {})
    sup = config.get("superficie", {})

    parts = [
        "alquilar",
        tipo_slug,
        barrio_fmt,
        f"pesos_desde_{precio.get('min', '')}_hasta_{precio.get('max', '')}",
    ]
    if sup.get("cubierta_min"):
        parts.append(f"superficieCubierta_desde_{sup['cubierta_min']}")
    if amb.get("min") and amb.get("max"):
        parts.append(f"ambientes_{amb['min']}_{amb['max']}")
    if dorm.get("min") and dorm.get("max"):
        parts.append(f"dormitorios_{dorm['min']}_{dorm['max']}")

    return f"{base}/propiedades/{'-'.join(parts)}?pagina=1"


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
                "cabaprop": build_cabaprop_url(barrio, tipo, config),
            }
    return resultado
