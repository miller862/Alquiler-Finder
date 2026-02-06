#%%
import pandas as pd
import geopandas as gpd
import pathlib
import numpy as np
import momepy
import networkx as nx
from shapely.ops import nearest_points
from scipy.spatial import KDTree
import folium
from folium import plugins
import branca.colormap as cm
#%%


# 2. Rutas y carga de datos
base_path = pathlib.Path.cwd()
barrios = gpd.read_file(base_path / ".." / "shapes" / "barrios.geojson")
EV = gpd.read_file(base_path / ".." / "shapes" / "espacio_verde_publico.geojson")
lineas_subte = gpd.read_file(base_path / ".." / "shapes" / "subte_lineas.geojson")
estaciones_subte = gpd.read_file(base_path / ".." / "shapes" / "estaciones_de_subte.geojson")
gyms_total= gpd.read_file(base_path / ".." / "shapes" / "gimnasios.geojson", driver="GeoJSON")
callejero= gpd.read_file(base_path / ".." / "shapes" / "callejero.geojson")
departamentos = gpd.read_file(base_path / ".." / "shapes" / "departamentos_geocoded.geojson")
#%% preparo capas de transporte y gimnasios

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


#%% preparo espacios verdes
EV=EV[EV.clasificac.isin(['PARQUE', 'JARDÍN BOTANICO', 'PLAZA'])]

#%% preparo departamentos
# 1. Normalización de nombres en 'departamentos'
# De 'villa-urquiza' a 'Villa Urquiza'
departamentos['Barrio'] = departamentos['Barrio'].str.replace('-', ' ').str.title()

# Corrección de 'Barrio Norte' (ya que no suele estar en el mapa oficial de CABA)
departamentos['Barrio'] = departamentos['Barrio'].replace('Barrio Norte', 'Recoleta')

# 2. Filtrar el GeoDataFrame de barrios por los que nos interesan
# Usamos .unique() para quedarnos solo con los polígonos necesarios
barrios_interes = departamentos['Barrio'].unique()
barrios_filtrados = barrios[barrios['nombre'].isin(barrios_interes)]

# 3. Join Espacial (Recorte)
# Solo conservamos puntos que caen dentro de los polígonos de barrios_filtrados
departamentos_final = gpd.sjoin(
    departamentos, 
    barrios_filtrados[['nombre', 'geometry']], 
    how="inner", 
    predicate="within"
)

# 4. Limpieza post-join
# Eliminamos la columna 'index_right' creada por el sjoin si existe
if 'index_right' in departamentos_final.columns:
    departamentos_final = departamentos_final.drop(columns=['index_right'])

# (Opcional) Renombrar la columna del join si quieres mantenerla limpia
departamentos_final = departamentos_final.rename(columns={'nombre': 'Barrio'})


print(f"Barrios procesados: {barrios_interes}")
print(f"Registros finales: {len(departamentos_final)}")
#%%
proyeccion = 22185
G = momepy.gdf_to_nx(callejero.to_crs(epsg=proyeccion), approach='primal')
nodos_coords = np.array(list(G.nodes))
tree = KDTree(nodos_coords)

# Categorizar EV: Botánico y Parque -> parque, Plaza -> plaza
EV['cat'] = EV['clasificac'].replace({'JARDÍN BOTANICO': 'parque', 'PARQUE': 'parque', 'PLAZA': 'plaza'})

# Pre-calcular nodos de origen (departamentos)
depts_m = departamentos_final.to_crs(epsg=proyeccion)
_, idx_org = tree.query(np.column_stack([depts_m.geometry.x, depts_m.geometry.y]))
nodos_org = [tuple(nodos_coords[i]) for i in idx_org]

# 2. Configurar capas a procesar
capas_objetivo = {
    'gym': gyms_total,
    'subte': estaciones_subte,
    'parque': EV[EV.cat == 'parque'],
    'plaza': EV[EV.cat == 'plaza']
}

# 2. Bucle de cálculo (solo guardamos la información cruda)
for etiqueta, gdf_poi in capas_objetivo.items():
    print(f"Calculando ruteo real a {etiqueta}...")
    poi_m = gdf_poi.to_crs(epsg=proyeccion)
    _, idx_dest = tree.query(np.column_stack([poi_m.geometry.centroid.x, poi_m.geometry.centroid.y]))
    nodos_dst = set(tuple(nodos_coords[i]) for i in idx_dest)
    
    res_dist, res_cant = [], []
    for n_start in nodos_org:
        dists_dict = nx.single_source_dijkstra_path_length(G, n_start, cutoff=1000, weight='mm_len')
        d_en_red = [d for nodo, d in dists_dict.items() if nodo in nodos_dst]
        
        res_dist.append(min(d_en_red) if d_en_red else np.nan)
        res_cant.append(len(d_en_red))
    
    # Guardamos como lista simple (esto crea columnas tipo float/object)
    departamentos_final[f'distancia_m_{etiqueta}'] = res_dist
    departamentos_final[f'cant_{etiqueta}'] = res_cant

# 3. CAMBIO DE TIPO DE DATO GLOBAL (Fuera del bucle)
for etiqueta in capas_objetivo.keys():
    d_col = f'distancia_m_{etiqueta}'
    c_col = f'cant_{etiqueta}'
    
    # Distancia: Forzamos a numérico -> truncamos decimales -> entero con nulos
    departamentos_final[d_col] = pd.to_numeric(departamentos_final[d_col], errors='coerce').apply(np.floor).astype('Int64')
    
    # Cantidad: Forzamos a numérico -> llenamos nulos con 0 -> entero
    departamentos_final[c_col] = pd.to_numeric(departamentos_final[c_col], errors='coerce').fillna(0).astype(int)
#%%
def clean_for_map(gdf):
    # Eliminar duplicados de columnas (ej. 'Barrio')
    df = gdf.loc[:, ~gdf.columns.duplicated()].copy()
    
    for col in df.columns:
        if pd.api.types.is_datetime64_any_dtype(df[col]):
            df[col] = df[col].dt.strftime('%Y-%m-%d')
        elif str(df[col].dtype) in ['Int64', 'float64', 'int64', 'int32']:
            df[col] = pd.to_numeric(df[col], errors='coerce').astype(float)
    
    return df.to_crs(epsg=4326)

# Asegurar costo_total y limpiar
departamentos_final['costo_total'] = departamentos_final['Precio'] + departamentos_final['Expensas'].fillna(0)

barrios_map = clean_for_map(barrios_filtrados)
ev_map = clean_for_map(EV)
subte_lin_map = clean_for_map(lineas_subte)
subte_est_map = clean_for_map(estaciones_subte)
gyms_map = clean_for_map(gyms_total)
deptos_map = clean_for_map(departamentos_final)

# 2. ESCALA DE COLORES (Departamentos)
bins = [0, 300000, 400000, 500000, 600000, 700000, 800000, 10000000]
colors = ['#1a9850', '#91cf60', '#d9ef8b', '#fee08b', '#fc8d59', '#d73027', '#67000d']
colormap_deptos = cm.StepColormap(colors, vmin=0, vmax=900000, index=bins, caption='Costo Total (Alquiler + Expensas)')

def get_color_depto(valor):
    if pd.isna(valor): return '#808080'
    for i in range(len(bins)-1):
        if bins[i] <= valor < bins[i+1]:
            return colors[i]
    return colors[-1]

# 3. CREACIÓN DEL MAPA
m = folium.Map(location=[-34.6037, -58.3816], zoom_start=12, tiles='OpenStreetMap')

# CAPA 1: Barrios (Líneas negras intensas)
folium.GeoJson(
    barrios_map, name='Barrios',
    style_function=lambda x: {'fillColor': 'transparent', 'color': 'black', 'weight': 2.5, 'opacity': 1}
).add_to(m)

# CAPA 2: Espacios Verdes
folium.GeoJson(
    ev_map, name='Espacios Verdes',
    style_function=lambda x: {
        'fillColor': '#2ca25f' if x['properties']['cat'] == 'parque' else '#99d8c9',
        'color': '#00441b', 'weight': 1, 'fillOpacity': 0.6
    },
    tooltip=folium.GeoJsonTooltip(fields=['nombre', 'cat'], aliases=['Nombre:', 'Tipo:'])
).add_to(m)

# CAPA 3: Líneas de Subte
folium.GeoJson(
    subte_lin_map, name='Líneas Subte',
    style_function=lambda x: {'color': x['properties'].get('color_map', 'black'), 'weight': 3.5, 'opacity': 0.8}
).add_to(m)

# CAPA 4: Estaciones de Subte
estaciones_layer = folium.FeatureGroup(name="Estaciones de Subte")
for _, row in subte_est_map.iterrows():
    folium.CircleMarker(
        location=[row.geometry.y, row.geometry.x], radius=4, color='white', weight=0.5,
        fill=True, fill_color=row['color_map'], fill_opacity=1
    ).add_to(estaciones_layer)
estaciones_layer.add_to(m)

# CAPA 5: Gimnasios (Círculos más grandes y capa independiente)
gyms_layer = folium.FeatureGroup(name="Gimnasios")
for _, row in gyms_map.iterrows():
    folium.CircleMarker(
        location=[row.geometry.y, row.geometry.x], radius=6, # Más grande para diferenciar
        color='black', weight=1, fill=True, 
        fill_color=row['color_map'], fill_opacity=0.9,
        popup=f"{row['cadena']}: {row['nombre']}"
    ).add_to(gyms_layer)
gyms_layer.add_to(m)

# CAPA 6: Departamentos (Incluye costo_total en tooltip)
tooltip_list = [
    'Portal', 'Barrio', 'Tipo', 'Precio', 'Expensas', 'costo_total', 
    'Direccion', 'Ambientes', 'Dormitorios', 'Baños', 'Metros_Totales', 
    'Metros_Cubiertos', 'Inmobiliaria', 'distancia_m_gym', 'cant_gym', 
    'distancia_m_subte', 'cant_subte', 'distancia_m_parque', 'cant_parque', 
    'distancia_m_plaza', 'cant_plaza'
]

folium.GeoJson(
    deptos_map.to_json(),
    name='Departamentos',
    marker=folium.CircleMarker(radius=5, fill=True, fill_opacity=0.8, color='white', weight=0.5),
    style_function=lambda x: {'fillColor': get_color_depto(x['properties']['costo_total'])},
    tooltip=folium.GeoJsonTooltip(fields=tooltip_list, aliases=[c.replace('_', ' ').capitalize() + ":" for c in tooltip_list])
).add_to(m)

# 4. CONTROLES
colormap_deptos.add_to(m)
folium.LayerControl(collapsed=False).add_to(m)
m
# %%
