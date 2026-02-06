#%%
import pandas as pd
import geopandas as gpd
import pathlib
import googlemaps
import getpass
import re

# 1. Configuración de API Key (Solicitud por consola)
print("🔑 Configuración de Google Maps API")
api_key = getpass.getpass("Ingrese su Google API Key: ")
gmaps = googlemaps.Client(key=api_key)

# 2. Rutas y carga de datos
base_path = pathlib.Path.cwd()

estaciones_subte = gpd.read_file(base_path / ".." / "shapes" / "estaciones_de_subte.geojson")
lineas_subte = gpd.read_file(base_path / ".." / "shapes" / "subte_lineas.geojson")
sportclub = gpd.read_file(base_path / ".." / "data" / "gimnasios" / "sportclub" / "sportclub.geojson")
megatlon = pd.read_excel(base_path / ".." / "data" / "gimnasios" / "megatlon" / "megatlon.xlsx")
smartfit = pd.read_excel(base_path / ".." / "data" / "gimnasios" / "smartfit" / "smartfit.xlsx")
departamentos = pd.read_excel(base_path / ".." / "data" / "departamentos.xlsx")
#%%
# 3. Función de Geocodificación con Google Maps
def geocode_google(address):
    if pd.isna(address) or str(address).strip() == "":
        return None, None
    
    # Limpieza simple de la dirección
    address_clean = re.sub(r'C\.A\.B\.A|CABA| - ', ' ', str(address), flags=re.I)
    full_address = f"{address_clean}, Ciudad Autónoma de Buenos Aires, Argentina"
    
    try:
        # Llamada a la API de Google
        result = gmaps.geocode(full_address)
        if result:
            location = result[0]['geometry']['location']
            return location['lat'], location['lng']
    except Exception as e:
        print(f"⚠️ Error geocodificando {address}: {e}")
    
    return None, None

def process_gym_df(df, nombre_cadena):
    print(f"🚀 Geocodificando {nombre_cadena} con Google API...")
    
    # Aplicar geocodificación
    coords = df['Dirección'].apply(geocode_google)
    df[['lat', 'lon']] = pd.DataFrame(coords.tolist(), index=df.index)
    
    # Convertir a GeoDataFrame
    gdf = gpd.GeoDataFrame(
        df, 
        geometry=gpd.points_from_xy(df.lon, df.lat), 
        crs="EPSG:4326"
    )
    
    # Filtrar registros fallidos (sin geometría)
    gdf = gdf[~gdf.geometry.is_empty & gdf.geometry.notna()].copy()
    gdf['cadena'] = nombre_cadena
    return gdf
#%%
# [4 y 5] Procesamiento y Consolidación Inline
gyms_total = pd.concat([
    sportclub.assign(cadena="SportClub").rename(columns={'tipo_plan': 'plan', 'direccion': 'direccion_std'}),
    process_gym_df(megatlon, "Megatlon").rename(columns={'Nombre': 'nombre', 'Dirección': 'direccion_std', 'Plan': 'plan'}),
    process_gym_df(smartfit, "Smartfit").rename(columns={'sede': 'nombre', 'Dirección': 'direccion_std', 'smart-ui-text 8': 'plan'})
], ignore_index=True)[['nombre', 'direccion_std', 'plan', 'precio', 'cadena', 'geometry']]

# Convertir a GeoDataFrame final para asegurar métodos espaciales
gyms_total = gpd.GeoDataFrame(gyms_total, geometry='geometry', crs="EPSG:4326")

#%%
# 1. Definir los mapas de colores
color_subte_map = {
    'A': '#00AEEF', 'B': '#ED1C24', 'C': '#0054A6', 
    'D': '#00802F', 'E': '#662D91', 'H': '#FFD100'
}

color_gyms_map = {
    'SportClub': '#003366', 
    'Megatlon': '#ff6600', 
    'Smartfit': '#cc0000'
}

# 2. Normalización y Mapeo Manual (Subte)
lineas_subte['LINEASUB'] = lineas_subte['LINEASUB'].str.replace('LINEA ', '').str.strip()
lineas_subte['color_map'] = lineas_subte['LINEASUB'].map(color_subte_map)

estaciones_subte['linea'] = estaciones_subte['linea'].str.strip()
estaciones_subte['color_map'] = estaciones_subte['linea'].map(color_subte_map)

# 3. Mapeo Manual (Gimnasios)
# Creamos la columna de color física para evitar el error de índice
gyms_total['color_map'] = gyms_total['cadena'].map(color_gyms_map)
# %%
gyms_total.to_file(base_path / ".." / "shapes" / "gimnasios.geojson", driver="GeoJSON")
# %%
output_file = base_path / "departamentos_geocoded.xlsx"
checkpoint_interval = 100

print(f"🚀 Iniciando geocodificación de {len(departamentos)} filas...")

for i, row in departamentos.iterrows():
    # Solo geocodificar si no tiene coordenadas
    if pd.isna(row.get('lat')) or pd.isna(row.get('lon')):
        lat, lon = geocode_google(row['Direccion'])
        departamentos.at[i, 'lat'] = lat
        departamentos.at[i, 'lon'] = lon
    
    # Progreso y Checkpoint
    if (i + 1) % checkpoint_interval == 0:
        print(f"📍 Procesados: {i + 1}/{len(departamentos)}...")
        departamentos.to_csv(output_file, index=False)

# Guardado final
departamentos.to_excel(output_file, index=False)

# Convertir a GeoDataFrame
departamentos = gpd.GeoDataFrame(
    departamentos, 
    geometry=gpd.points_from_xy(departamentos.lon, departamentos.lat), 
    crs="EPSG:4326"
)
# %%
departamentos.to_file(base_path / ".." / "shapes" / "departamentos_geocoded.geojson", index=False)
# %%
