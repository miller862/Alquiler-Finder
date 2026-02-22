import json
import os
import pathlib

# Rutas base: perfiles/ en la raíz del proyecto
SCRIPT_DIR = pathlib.Path(__file__).parent
BASE_PATH = SCRIPT_DIR.parent
PERFILES_DIR = BASE_PATH / "perfiles"
CONFIG_FILE = PERFILES_DIR / "configuraciones.json"

TIPOS_DISPONIBLES = {
    "departamento": "Departamento",
    "ph": "PH"
}

BARRIOS_DISPONIBLES = [
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
    "villa-soldati", "villa-urquiza"
]

def cargar_configuraciones():
    """Carga todas las configuraciones (incluye global)."""
    if CONFIG_FILE.exists():
        with open(CONFIG_FILE, 'r', encoding='utf-8') as f:
            return json.load(f)
    return []

def cargar_configuraciones_scraping():
    """Solo perfiles con config de búsqueda (excluye global)."""
    configs = cargar_configuraciones()
    return [c for c in configs if not c.get('es_global') and c.get('barrios')]

def guardar_configuracion(config):
    configs = cargar_configuraciones()
    configs.append(config)
    PERFILES_DIR.mkdir(parents=True, exist_ok=True)
    with open(CONFIG_FILE, 'w', encoding='utf-8') as f:
        json.dump(configs, f, indent=2, ensure_ascii=False)

def mostrar_lista(items):
    for i, item in enumerate(items, 1):
        print(f"  {i}. {item}")

def seleccionar_multiple(opciones, prompt):
    print(f"\n{prompt}")
    mostrar_lista(opciones)
    print("\nIngresa los numeros separados por comas (ej: 1,3,5)")
    entrada = input("Seleccion: ").strip()
    
    indices = [int(x.strip())-1 for x in entrada.split(',') if x.strip().isdigit()]
    return [opciones[i] for i in indices if 0 <= i < len(opciones)]

def obtener_numero(prompt, minimo=None, maximo=None):
    while True:
        try:
            valor = input(f"{prompt}: ").strip()
            if not valor:
                return None
            num = int(valor)
            if minimo and num < minimo:
                print(f"  Debe ser mayor o igual a {minimo}")
                continue
            if maximo and num > maximo:
                print(f"  Debe ser menor o igual a {maximo}")
                continue
            return num
        except:
            print("  Ingresa un numero valido")

def obtener_configuracion():
    configs = cargar_configuraciones_scraping()
    
    if configs:
        print("\n=== CONFIGURACIONES GUARDADAS ===")
        for i, cfg in enumerate(configs, 1):
            nombre = cfg.get('nombre', 'Sin nombre')
            barrios = cfg.get('barrios', [])
            tipos = cfg.get('tipos', [])
            barrios_txt = ', '.join(barrios[:3])
            if len(barrios) > 3:
                barrios_txt += f" (+{len(barrios)-3} mas)"
            print(f"\n{i}. {nombre}")
            print(f"   Barrios: {barrios_txt}")
            print(f"   Tipos: {', '.join(tipos)}")
            print(f"   Precio: ${cfg['precio']['min']:,} - ${cfg['precio']['max']:,}")
        
        usar = input("\nUsar configuracion existente? (numero o Enter para nueva): ").strip()
        if usar.isdigit() and 1 <= int(usar) <= len(configs):
            config_elegida = configs[int(usar)-1]
            print(f"\nUsando configuracion: {config_elegida.get('nombre', 'Sin nombre')}")
            return config_elegida
    
    print("\n=== NUEVA CONFIGURACION ===")
    
    barrios = seleccionar_multiple(sorted(BARRIOS_DISPONIBLES), "Selecciona barrios:")
    
    tipos_keys = list(TIPOS_DISPONIBLES.keys())
    tipos_labels = [TIPOS_DISPONIBLES[k] for k in tipos_keys]
    
    print("\nTipos de propiedad:")
    for i, label in enumerate(tipos_labels, 1):
        print(f"  {i}. {label}")
    print(f"  {len(tipos_labels) + 1}. Todos")
    
    tipo_sel = input("Opcion: ").strip()
    if tipo_sel.isdigit():
        idx = int(tipo_sel) - 1
        if 0 <= idx < len(tipos_keys):
            tipos = [tipos_keys[idx]]
        else:
            tipos = tipos_keys
    else:
        tipos = tipos_keys
    
    print("\n--- PRECIO ---")
    precio_min = obtener_numero("Minimo")
    precio_max = obtener_numero("Maximo")
    
    print("\n--- AMBIENTES ---")
    amb_min = obtener_numero("Minimo")
    amb_max = obtener_numero("Maximo")
    
    print("\n--- DORMITORIOS ---")
    dorm_min = obtener_numero("Minimo")
    dorm_max = obtener_numero("Maximo")
    
    print("\n--- SUPERFICIE ---")
    sup_min = obtener_numero("Metros cubiertos minimos")
    
    print("\n--- EXTRAS ---")
    balcon_resp = input("Balcon obligatorio? (s/n): ").strip().lower()
    balcon = balcon_resp == 's'
    expensas_max = obtener_numero("Expensas maximas")
    
    print("\n--- FILTROS DE EXCLUSION ---")
    print("Palabras a excluir (separadas por comas, Enter para omitir):")
    exclusion_input = input("Filtros: ").strip()
    filtros_exclusion = [x.strip() for x in exclusion_input.split(',') if x.strip()]
    
    config = {
        "operacion": "alquiler",
        "barrios": barrios,
        "tipos": tipos,
        "precio": {
            "min": precio_min,
            "max": precio_max,
            "moneda": "pesos"
        },
        "ambientes": {
            "min": amb_min,
            "max": amb_max
        },
        "dormitorios": {
            "min": dorm_min,
            "max": dorm_max
        },
        "superficie": {
            "cubierta_min": sup_min
        },
        "extras": {
            "balcon": balcon,
            "expensas_max": expensas_max
        },
        "filtros_exclusion": filtros_exclusion
    }
    
    guardar = input("\nGuardar esta configuracion? (s/n): ").strip().lower()
    if guardar == 's':
        nombre_config = input("Nombre para esta configuracion: ").strip()
        if not nombre_config:
            nombre_config = f"Config {len(cargar_configuraciones()) + 1}"
        config['nombre'] = nombre_config
        usuario = input("Usuario para login en la app (Enter = nombre del perfil): ").strip() or nombre_config.lower()
        password = input("Password para login (Enter = demo123): ").strip() or "demo123"
        config['usuario'] = usuario
        config['password'] = password
        guardar_configuracion(config)
        print(f"Configuracion '{nombre_config}' guardada.")
    
    return config
