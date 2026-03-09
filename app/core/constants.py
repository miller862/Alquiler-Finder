"""
Constantes del dominio: barrios, tipos de propiedad, colores por línea/gym.
Port de 0_parametros.py y 5_auxiliar.py.
"""

TIPOS_DISPONIBLES: dict[str, str] = {
    "departamento": "Departamento",
    "ph": "PH",
}

BARRIOS_DISPONIBLES: list[str] = sorted([
    "agronomia", "almagro", "balvanera", "barracas", "belgrano", "boedo",
    "caballito", "chacarita", "coghlan", "colegiales", "constitucion",
    "flores", "floresta", "la-boca", "la-paternal", "liniers",
    "mataderos", "monte-castro", "monserrat", "nueva-pompeya", "nunez",
    "palermo", "parque-avellaneda", "parque-chacabuco", "parque-chas",
    "parque-patricios", "puerto-madero", "recoleta", "retiro",
    "saavedra", "san-cristobal", "san-nicolas", "san-telmo", "velez-sarsfield",
    "versalles", "villa-crespo", "villa-del-parque", "villa-devoto",
    "villa-general-mitre", "villa-lugano", "villa-luro", "villa-ortuzar",
    "villa-pueyrredon", "villa-real", "villa-riachuelo", "villa-santa-rita",
    "villa-soldati", "villa-urquiza",
])

PRIORIDAD_PORTALES: list[str] = ["zonaprop", "argenprop", "cabaprop"]

COLOR_SUBTE_MAP: dict[str, str] = {
    "A": "#00AEEF",
    "B": "#ED1C24",
    "C": "#0054A6",
    "D": "#00802F",
    "E": "#662D91",
    "H": "#FFD100",
}

COLOR_GYMS_MAP: dict[str, str] = {
    "SportClub": "#003366",
    "Megatlon": "#ff6600",
    "Smartfit": "#cc0000",
}

# Constantes de ruteo NetworkX
DIJKSTRA_CUTOFF = 2000  # metros
DIJKSTRA_PENALIZACION_NAN = 1500  # metros (penalty cuando no hay camino)
SNAP_WARNING_UMBRAL_M = 150  # metros

# Pesos del scoring (deben sumar 1.0)
SCORING_WEIGHTS: dict[str, float] = {
    "costo_total_norm": 0.40,
    "distancia_m_subte_norm": 0.30,
    "dist_verde_final_norm": 0.20,
    "distancia_m_gym_norm": 0.10,
}

SCORING_VARIABLES: list[str] = [
    "costo_total",
    "distancia_m_subte",
    "dist_verde_final",
    "distancia_m_gym",
]
