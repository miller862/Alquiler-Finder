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

def dedup_inter_portal(df):
    df['Direccion_norm'] = df['Direccion'].astype(str).str.lower().str.strip()
    
    df['portal_orden'] = df['Portal'].map(
        {p: i for i, p in enumerate(PRIORIDAD_PORTALES)}
    ).fillna(99).astype(int)
    
    df = df.sort_values('portal_orden')
    
    df = df.drop_duplicates(
        subset=['Direccion_norm', 'Precio', 'Tipo', 'Ambientes'],
        keep='first'
    )
    
    df = df.drop(columns=['portal_orden'])
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
    if master_global is None or master_global.empty:
        df_nuevo['lat'] = None
        df_nuevo['lon'] = None
        return df_nuevo
    
    master_global['Direccion_norm'] = master_global['Direccion'].astype(str).str.lower().str.strip()
    
    geo_cache = master_global[master_global['lat'].notna()][
        ['Direccion_norm', 'lat', 'lon']
    ].drop_duplicates(subset='Direccion_norm', keep='first')
    
    if 'lat' in df_nuevo.columns:
        df_nuevo = df_nuevo.drop(columns=['lat', 'lon'])
    
    df_nuevo = df_nuevo.merge(geo_cache, on='Direccion_norm', how='left')
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
