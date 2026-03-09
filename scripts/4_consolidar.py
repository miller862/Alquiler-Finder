import sys
import os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import pandas as pd
import geopandas as gpd
import pathlib
import googlemaps
import re
import json
import importlib

parametros = importlib.import_module('0_parametros')
cargar_configuraciones_scraping = parametros.cargar_configuraciones_scraping
PERFILES_DIR = parametros.PERFILES_DIR
url_normalize = parametros.url_normalize
precio_norm_value = parametros.precio_norm_value
join_key_direccion_precio = parametros.join_key_direccion_precio

DATA_DIR = PERFILES_DIR
GLOBAL_DIR = PERFILES_DIR / "global"
MASTER_GLOBAL_PATH = GLOBAL_DIR / "departamentos_master_global.xlsx"

PRIORIDAD_PORTALES = ["zonaprop", "argenprop", "cabaprop"]

# ================= SELECCION DE PERFIL =================

def elegir_perfil():
    configs = cargar_configuraciones_scraping()
    if not configs:
        print("No hay configuraciones guardadas.")
        return None
    
    print("\n=== PERFILES DISPONIBLES ===")
    for i, cfg in enumerate(configs, 1):
        nombre = cfg.get('nombre', 'Sin nombre')
        print(f"  {i}. {nombre}")
    
    sel = input("\nElegir perfil (numero): ").strip()
    if sel.isdigit() and 1 <= int(sel) <= len(configs):
        return configs[int(sel)-1]
    return None

# ================= CARGA DE CSVs =================

def get_latest_csv(folder_path):
    path = pathlib.Path(folder_path)
    files = list(path.glob("*.csv"))
    if not files:
        return None
    
    def extract_date(f):
        match = re.search(r'(\d{4}-\d{2}-\d{2})', f.name)
        return match.group(1) if match else ""
    
    return max(files, key=extract_date)

def cargar_csvs_perfil(perfil_nombre):
    dfs = []
    for portal in PRIORIDAD_PORTALES:
        folder = DATA_DIR / perfil_nombre / portal
        if not folder.exists():
            print(f"  No existe carpeta para {portal}")
            continue
        
        csv_path = get_latest_csv(folder)
        if csv_path is None:
            print(f"  No hay CSVs en {portal}")
            continue
        
        df = pd.read_csv(csv_path, sep=';', encoding='utf-8-sig')
        print(f"  {portal}: {len(df)} registros ({csv_path.name})")
        dfs.append(df)
    
    if not dfs:
        return None
    return pd.concat(dfs, ignore_index=True)

# ================= DEDUP =================
# Misma normalización que en 6_metrics: URL_norm y Direccion_norm|Precio_norm.

def dedup_inter_portal(df):
    df['Direccion_norm'] = df['Direccion'].astype(str).str.lower().str.strip()
    if 'URL' in df.columns:
        df['URL_norm'] = df['URL'].apply(url_normalize)
    else:
        df['URL_norm'] = ''
    
    df['portal_orden'] = df['Portal'].map(
        {p: i for i, p in enumerate(PRIORIDAD_PORTALES)}
    ).fillna(99).astype(int)
    df = df.sort_values('portal_orden')
    
    # Prioridad 1: dedup por URL normalizada (subset estable entre scrapes)
    df = df.drop_duplicates(subset=['URL_norm'], keep='first')
    # Prioridad 2: resto por Direccion_norm + Precio + Tipo + Ambientes
    df = df.drop_duplicates(
        subset=['Direccion_norm', 'Precio', 'Tipo', 'Ambientes'],
        keep='first'
    )
    
    df = df.drop(columns=['portal_orden', 'URL_norm'], errors='ignore')
    return df.reset_index(drop=True)

# ================= GEOCODIFICACION =================

def geocode_google(gmaps_client, address):
    if pd.isna(address) or str(address).strip() == "":
        return None, None
    
    address_clean = re.sub(r'C\.A\.B\.A|CABA| - ', ' ', str(address), flags=re.I)
    full_address = f"{address_clean}, Ciudad Autónoma de Buenos Aires, Argentina"
    
    try:
        result = gmaps_client.geocode(full_address)
        if result:
            location = result[0]['geometry']['location']
            return location['lat'], location['lng']
    except Exception as e:
        print(f"  Error geocodificando {address}: {e}")
    
    return None, None

def preservar_geocoding(df_nuevo, master_global):
    """Preserva geocoding en dos pasadas: 1) por URL normalizada, 2) por Direccion_norm|Precio_norm."""
    if master_global is None or master_global.empty:
        df_nuevo['lat'] = None
        df_nuevo['lon'] = None
        return df_nuevo
    
    df_nuevo['Direccion_norm'] = df_nuevo['Direccion'].astype(str).str.lower().str.strip()
    df_nuevo['Precio_norm'] = df_nuevo['Precio'].apply(precio_norm_value)
    df_nuevo['join_dir_precio'] = df_nuevo['Direccion_norm'] + '|' + df_nuevo['Precio_norm']
    if 'URL' in df_nuevo.columns:
        df_nuevo['URL_norm'] = df_nuevo['URL'].apply(url_normalize)
    else:
        df_nuevo['URL_norm'] = ''
    
    master_global = master_global.copy()
    master_global['Direccion_norm'] = master_global['Direccion'].astype(str).str.lower().str.strip()
    master_global['Precio_norm'] = master_global['Precio'].apply(precio_norm_value)
    master_global['join_dir_precio'] = master_global['Direccion_norm'] + '|' + master_global['Precio_norm']
    master_global['URL_norm'] = master_global['URL'].apply(url_normalize) if 'URL' in master_global.columns else ''
    
    if 'lat' in df_nuevo.columns:
        df_nuevo = df_nuevo.drop(columns=['lat', 'lon'])
    
    # Pasada 1: merge por URL normalizada
    geo_url = master_global[master_global['lat'].notna() & (master_global['URL_norm'] != '')][
        ['URL_norm', 'lat', 'lon']
    ].drop_duplicates(subset='URL_norm', keep='first')
    df_nuevo = df_nuevo.merge(geo_url, on='URL_norm', how='left')
    
    # Pasada 2: para los que no matchearon, merge por Direccion_norm|Precio_norm
    sin_geo = df_nuevo['lat'].isna()
    if sin_geo.any():
        geo_dir = master_global[master_global['lat'].notna()][
            ['join_dir_precio', 'lat', 'lon']
        ].drop_duplicates(subset='join_dir_precio', keep='first')
        df_fill = df_nuevo.loc[sin_geo, ['join_dir_precio']].merge(
            geo_dir, on='join_dir_precio', how='left'
        )
        df_nuevo.loc[sin_geo, 'lat'] = df_fill['lat'].values
        df_nuevo.loc[sin_geo, 'lon'] = df_fill['lon'].values
    
    df_nuevo = df_nuevo.drop(columns=['join_dir_precio', 'URL_norm', 'Precio_norm'], errors='ignore')
    return df_nuevo

def geocodificar_nuevos(df, gmaps_client, checkpoint_interval=50):
    sin_coords = df['lat'].isna().sum()
    if sin_coords == 0:
        print("  Todas las direcciones ya estan geocodificadas.")
        return df
    
    print(f"  Geocodificando {sin_coords} direcciones nuevas...")
    count = 0
    
    for i, row in df.iterrows():
        if pd.isna(row.get('lat')) or pd.isna(row.get('lon')):
            lat, lon = geocode_google(gmaps_client, row['Direccion'])
            df.at[i, 'lat'] = lat
            df.at[i, 'lon'] = lon
            count += 1
            
            if count % checkpoint_interval == 0:
                print(f"    Procesados: {count}/{sin_coords}...")
    
    print(f"  Geocodificacion completa: {count} direcciones procesadas.")
    return df

# ================= MASTER GLOBAL =================

def cargar_master_global():
    if MASTER_GLOBAL_PATH.exists():
        return pd.read_excel(MASTER_GLOBAL_PATH)
    return None

def actualizar_master_global():
    all_masters = []
    
    for perfil_dir in DATA_DIR.iterdir():
        if not perfil_dir.is_dir() or perfil_dir.name == "global":
            continue
        master_path = perfil_dir / "departamentos_master.xlsx"
        if master_path.exists():
            df = pd.read_excel(master_path)
            df['_perfil'] = perfil_dir.name
            all_masters.append(df)
    
    if not all_masters:
        return
    
    global_df = pd.concat(all_masters, ignore_index=True)
    global_df['Direccion_norm'] = global_df['Direccion'].astype(str).str.lower().str.strip()
    
    global_df['tiene_geo'] = global_df['lat'].notna().astype(int)
    global_df = global_df.sort_values('tiene_geo', ascending=False)
    global_df = global_df.drop_duplicates(subset='Direccion_norm', keep='first')
    global_df = global_df.drop(columns=['tiene_geo', '_perfil'], errors='ignore')
    
    GLOBAL_DIR.mkdir(parents=True, exist_ok=True)
    global_df.to_excel(MASTER_GLOBAL_PATH, index=False)
    print(f"  Master global actualizado: {len(global_df)} registros -> {MASTER_GLOBAL_PATH}")
    
    df_geo = global_df[global_df['lat'].notna() & global_df['lon'].notna()].copy()
    if not df_geo.empty:
        gdf = gpd.GeoDataFrame(
            df_geo,
            geometry=gpd.points_from_xy(df_geo['lon'], df_geo['lat']),
            crs="EPSG:4326"
        )
        output_geojson = GLOBAL_DIR / "departamentos_global.geojson"
        gdf.to_file(output_geojson, driver="GeoJSON")
        print(f"  GeoJSON global exportado: {output_geojson}")

def exportar_geojson(df, perfil_nombre):
    df_geo = df[df['lat'].notna() & df['lon'].notna()].copy()
    if df_geo.empty:
        print("  No hay registros geocodificados para exportar.")
        return
    
    gdf = gpd.GeoDataFrame(
        df_geo,
        geometry=gpd.points_from_xy(df_geo['lon'], df_geo['lat']),
        crs="EPSG:4326"
    )
    
    output = DATA_DIR / perfil_nombre / "departamentos.geojson"
    output.parent.mkdir(parents=True, exist_ok=True)
    gdf.to_file(output, driver="GeoJSON")
    print(f"  GeoJSON del perfil exportado: {output}")

# ================= MAIN =================

def main():
    config = elegir_perfil()
    if not config:
        return
    
    perfil_nombre = config.get('nombre', 'default')
    print(f"\nConsolidando perfil: {perfil_nombre}")
    
    print("\n--- Cargando CSVs ---")
    df = cargar_csvs_perfil(perfil_nombre)
    if df is None:
        print("No hay datos para consolidar.")
        return
    
    print(f"\nTotal bruto: {len(df)} registros")
    
    print("\n--- Deduplicando ---")
    df['Direccion_norm'] = df['Direccion'].astype(str).str.lower().str.strip()
    df = dedup_inter_portal(df)
    print(f"Despues de dedup: {len(df)} registros")
    
    print("\n--- Preservando geocoding existente ---")
    master_global = cargar_master_global()
    df = preservar_geocoding(df, master_global)
    ya_geo = df['lat'].notna().sum()
    print(f"  {ya_geo} ya geocodificados, {len(df) - ya_geo} pendientes")
    
    print("\n--- Geocodificacion ---")
    if df['lat'].isna().any():
        print("API Key de Google Maps necesaria para geocodificar nuevas direcciones.")
        api_key = input("Ingrese su Google API Key (Enter para omitir): ").strip()
        if api_key:
            gmaps_client = googlemaps.Client(key=api_key)
            df = geocodificar_nuevos(df, gmaps_client)
        else:
            print("  Geocodificacion omitida.")
    else:
        print("  No hay direcciones nuevas para geocodificar.")
    
    print("\n--- Guardando master del perfil ---")
    perfil_dir = DATA_DIR / perfil_nombre
    perfil_dir.mkdir(parents=True, exist_ok=True)
    master_path = perfil_dir / "departamentos_master.xlsx"
    
    cols_to_drop = ['Direccion_norm']
    df_save = df.drop(columns=[c for c in cols_to_drop if c in df.columns])
    df_save.to_excel(master_path, index=False)
    print(f"  Guardado: {master_path} ({len(df_save)} registros)")
    
    print("\n--- Actualizando master global ---")
    actualizar_master_global()
    
    print("\n--- Exportando GeoJSON del perfil ---")
    exportar_geojson(df_save, perfil_nombre)
    
    print("\nConsolidacion completa.")

if __name__ == "__main__":
    main()
