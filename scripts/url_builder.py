import re

# ================= 1. CONFIGURACIÓN =================

LISTA_BARRIOS = [
    "palermo",
    "villa-urquiza",
    "parque-chas",     # <--- CAMBIO SOLICITADO
    "belgrano", 
    "recoleta", 
    "almagro",
    "colegiales",
    "barrio-norte",
]

# Palabras prohibidas (Filtro de exclusión que usa el main)
FILTROS_EXCLUSION = [
    "monoambiente", 
    "mono ambiente", 
    "monoamb",
    "1 ambiente",
    "1 amb"
]

PARAMS = {
    "operacion": "alquiler",
    "tipos": ["departamento", "ph"], # Iteramos sobre esto
    "precio": {
        "min": 350000,
        "max": 800000,
        "moneda": "pesos"
    },
    "ambientes": {
        "min": 2,
        "max": 3
    },
    "dormitorios": {
        "min": 1,
        "max": 2
    },
    "superficie": {
        "cubierta_min": 35
    },
    "extras": {
        "balcon": True,          
        "expensas_max": 300000   
    }
}

# Slugs específicos para cada portal
TYPE_SLUGS = {
    "zonaprop": {
        "departamento": "departamentos", # Plural
        "ph": "ph"
    },
    "argenprop": {
        "departamento": "departamentos", # <--- CORRECCIÓN: Ahora es PLURAL
        "ph": "ph"
    },
    "cabaprop": {
        "departamento": "departamento", # Singular
        "ph": "ph"
    }
}

# ================= 2. GENERADORES =================

def get_zonaprop_url(barrio, tipo_std, p):
    base = "https://www.zonaprop.com.ar"
    tipo_slug = TYPE_SLUGS["zonaprop"][tipo_std]
    
    # Base: tipo-operacion-barrio
    parts = [tipo_slug, "alquiler", barrio]
    
    # --- FILTRO BALCÓN (Condicional: Solo si NO es PH) ---
    if p['extras'].get('balcon') and tipo_std != 'ph':
        parts.append("con-balcon")
        
    # Habitaciones y Ambientes
    parts.append(f"desde-{p['dormitorios']['min']}-hasta-{p['dormitorios']['max']}-habitaciones")
    parts.append(f"desde-{p['ambientes']['min']}-hasta-{p['ambientes']['max']}-ambientes")
    
    # Superficie
    if p['superficie'].get('cubierta_min'):
        parts.append(f"mas-{p['superficie']['cubierta_min']}-m2-cubiertos")
        
    # Precio
    parts.append(f"{p['precio']['min']}-{p['precio']['max']}-{p['precio']['moneda']}")
    
    return f"{base}/{'-'.join(parts)}.html"

def get_argenprop_url(barrio, tipo_std, p):
    base = "https://www.argenprop.com"
    tipo_slug = TYPE_SLUGS["argenprop"][tipo_std]
    
    rango_precio = f"{p['precio']['moneda']}-{p['precio']['min']}-{p['precio']['max']}"
    path = f"/{tipo_slug}/alquiler/{barrio}/{rango_precio}"
    
    query = []
    
    # --- FILTRO EXPENSAS (Siempre activo si existe) ---
    if p['extras'].get('expensas_max'):
        query.append(f"*-{p['extras']['expensas_max']}-expensas")
        
    # --- FILTRO BALCÓN (Condicional: Solo si NO es PH) ---
    if p['extras'].get('balcon') and tipo_std != 'ph':
        query.append("con-ambiente-balcon")
        
    # Moneda
    query.append("solo-ver-pesos")
    
    return f"{base}{path}?{'&'.join(query)}"

def get_cabaprop_url(barrio, tipo_std, p):
    base = "https://cabaprop.com.ar"
    tipo_slug = TYPE_SLUGS["cabaprop"][tipo_std]
    barrio_fmt = barrio.replace('-', '_')
    
    # Cabaprop ignora balcón y expensas en URL, así que no se agregan
    parts = [
        "alquilar", 
        tipo_slug, 
        barrio_fmt,
        f"pesos_desde_{p['precio']['min']}_hasta_{p['precio']['max']}"
    ]
    
    if p['superficie'].get('cubierta_min'):
        parts.append(f"superficieCubierta_desde_{p['superficie']['cubierta_min']}")
    
    parts.append(f"ambientes_{p['ambientes']['min']}_{p['ambientes']['max']}")
    parts.append(f"dormitorios_{p['dormitorios']['min']}_{p['dormitorios']['max']}")
    
    return f"{base}/propiedades/{'-'.join(parts)}?pagina=1"

# ================= 3. FUNCIÓN MAESTRA =================

def generar_todas_urls():
    """
    Retorna estructura: { barrio: { tipo: { portal: url } } }
    """
    resultados = {}
    for barrio in LISTA_BARRIOS:
        resultados[barrio] = {}
        for tipo in PARAMS['tipos']:
            resultados[barrio][tipo] = {
                "zonaprop": get_zonaprop_url(barrio, tipo, PARAMS),
                "argenprop": get_argenprop_url(barrio, tipo, PARAMS),
                "cabaprop": get_cabaprop_url(barrio, tipo, PARAMS)
            }
    return resultados

