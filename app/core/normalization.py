"""
Normalización de datos para deduplicación y merge entre scrapes.
Port directo de 0_parametros.py con mejoras en normalize_address().
"""
import re


def _is_na(v) -> bool:
    if v is None:
        return True
    if isinstance(v, float):
        return v != v  # NaN check
    return False


def url_normalize(v) -> str:
    """URL normalizada: strip + lowercase. Clave primaria de dedup."""
    if _is_na(v):
        return ""
    return str(v).strip().lower()


def precio_norm_value(v) -> str:
    """Precio normalizado como string entero. Parte de la clave secundaria."""
    if _is_na(v):
        return ""
    try:
        return str(int(float(v)))
    except (TypeError, ValueError):
        return ""


_ABBREV_MAP = [
    (r"\bav\.?(?=\s|\d|$)", "avenida "),
    (r"\bpte\.?(?=\s|\d|$)", "presidente "),
    (r"\bgeneral\b", "gral"),
    (r"\bc\.a\.b\.a\.?\b", ""),
    (r"\bcaba\b", ""),
    (r"\b(del|de la|de los|de las|de|la|el|los|las)\b", ""),
    (r"\bsobre\b", ""),
    (r"\bdpto\.?\b", ""),
    (r"\bpiso\s+\d+", ""),
    (r"\b\d+\s*[°ºa-zA-Z]\s*[a-z]?\b", ""),  # elimina "3° A", "2do B", etc.
]

_COMPILED_ABBREV = [(re.compile(p, re.IGNORECASE), r) for p, r in _ABBREV_MAP]


def normalize_address(addr) -> str:
    """
    Normalización robusta de direcciones para la clave de dedup secundaria.
    Expande abreviaturas, elimina ruido (piso/dpto/barrio), extrae calle+número.
    Resultado: cadena lowercase sin puntuación, solo calle y número.
    """
    if _is_na(addr) or str(addr).strip() == "":
        return ""

    s = str(addr).lower().strip()

    # Eliminar puntuación excepto guiones entre palabras y puntos de abreviaturas
    s = re.sub(r"[,;:()\[\]]", " ", s)

    # Aplicar expansiones y eliminaciones
    for pattern, replacement in _COMPILED_ABBREV:
        s = pattern.sub(replacement, s)

    # Normalizar espacios
    s = re.sub(r"\s+", " ", s).strip()

    # Extraer calle + número principal (primer número que aparece)
    m = re.match(r"^(.+?)\s+(\d+)", s)
    if m:
        street = re.sub(r"\s+", " ", m.group(1)).strip()
        number = m.group(2)
        return f"{street} {number}"

    return s


def build_dedup_key(portal: str, direccion: str, precio) -> str:
    """
    Clave secundaria de dedup: portal|direccion_norm|precio_norm
    Incluye el portal para evitar falsos merges cross-portal.
    """
    dir_norm = normalize_address(direccion)
    precio_str = precio_norm_value(precio)
    return f"{portal.lower()}|{dir_norm}|{precio_str}"
