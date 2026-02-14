import geopandas as gpd
import pathlib

# ================= CONSTANTES DE COLORES =================

color_subte_map = {
    'A': '#00AEEF', 'B': '#ED1C24', 'C': '#0054A6', 
    'D': '#00802F', 'E': '#662D91', 'H': '#FFD100'
}

color_gyms_map = {
    'SportClub': '#003366', 
    'Megatlon': '#ff6600', 
    'Smartfit': '#cc0000'
}

def aplicar_colores_subte(lineas_subte, estaciones_subte):
    lineas_subte['LINEASUB'] = lineas_subte['LINEASUB'].str.replace('LINEA ', '').str.strip()
    lineas_subte['color_map'] = lineas_subte['LINEASUB'].map(color_subte_map)
    
    estaciones_subte['linea'] = estaciones_subte['linea'].str.strip()
    estaciones_subte['color_map'] = estaciones_subte['linea'].map(color_subte_map)
    
    return lineas_subte, estaciones_subte

def aplicar_colores_gyms(gyms_total):
    gyms_total['color_map'] = gyms_total['cadena'].map(color_gyms_map)
    return gyms_total

# ================= GEOCODIFICACION DE GIMNASIOS (REFERENCIA) =================
# Este bloque ya fue ejecutado una vez para generar shapes/gimnasios.geojson
# No se ejecuta al importar este modulo.

if __name__ == "__main__":
    import pandas as pd
    import googlemaps
    import getpass
    import re
    
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
            print(f"Error geocodificando {address}: {e}")
        return None, None

    def process_gym_df(gmaps_client, df, nombre_cadena):
        print(f"Geocodificando {nombre_cadena} con Google API...")
        coords = df['Dirección'].apply(lambda a: geocode_google(gmaps_client, a))
        df[['lat', 'lon']] = pd.DataFrame(coords.tolist(), index=df.index)
        gdf = gpd.GeoDataFrame(
            df, geometry=gpd.points_from_xy(df.lon, df.lat), crs="EPSG:4326"
        )
        gdf = gdf[~gdf.geometry.is_empty & gdf.geometry.notna()].copy()
        gdf['cadena'] = nombre_cadena
        return gdf

    base_path = pathlib.Path.cwd()
    
    print("API Key de Google Maps")
    api_key = getpass.getpass("Ingrese su Google API Key: ")
    gmaps = googlemaps.Client(key=api_key)
    
    sportclub = gpd.read_file(base_path / ".." / "data" / "gimnasios" / "sportclub" / "sportclub.geojson")
    megatlon = pd.read_excel(base_path / ".." / "data" / "gimnasios" / "megatlon" / "megatlon.xlsx")
    smartfit = pd.read_excel(base_path / ".." / "data" / "gimnasios" / "smartfit" / "smartfit.xlsx")
    
    gyms_total = pd.concat([
        sportclub.assign(cadena="SportClub").rename(columns={'tipo_plan': 'plan', 'direccion': 'direccion_std'}),
        process_gym_df(gmaps, megatlon, "Megatlon").rename(columns={'Nombre': 'nombre', 'Dirección': 'direccion_std', 'Plan': 'plan'}),
        process_gym_df(gmaps, smartfit, "Smartfit").rename(columns={'sede': 'nombre', 'Dirección': 'direccion_std', 'smart-ui-text 8': 'plan'})
    ], ignore_index=True)[['nombre', 'direccion_std', 'plan', 'precio', 'cadena', 'geometry']]
    
    gyms_total = gpd.GeoDataFrame(gyms_total, geometry='geometry', crs="EPSG:4326")
    gyms_total = aplicar_colores_gyms(gyms_total)
    gyms_total.to_file(base_path / ".." / "shapes" / "gimnasios.geojson", driver="GeoJSON")
    print("Gimnasios guardados en shapes/gimnasios.geojson")
