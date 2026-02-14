#%%
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import pathlib
import pandas as pd
import geopandas as gpd
import folium
import branca.colormap as cm
import importlib

parametros = importlib.import_module('0_parametros')
auxiliar = importlib.import_module('5_auxiliar')
cargar_configuraciones = parametros.cargar_configuraciones
color_subte_map = auxiliar.color_subte_map
color_gyms_map = auxiliar.color_gyms_map
aplicar_colores_subte = auxiliar.aplicar_colores_subte
aplicar_colores_gyms = auxiliar.aplicar_colores_gyms

script_dir = pathlib.Path(__file__).parent
base_path = script_dir / ".."
shapes_dir = (base_path / "shapes").resolve()
outputs_dir = (base_path / "outputs").resolve()

print("\n=== VISUALIZACION INTERACTIVA ===", flush=True)

configs = cargar_configuraciones()
perfiles_disponibles = [cfg.get('nombre', 'Sin nombre') for cfg in configs]

print("\nOpciones:", flush=True)
print("  0. Global (todos los perfiles)", flush=True)
for i, perfil in enumerate(perfiles_disponibles, 1):
    print(f"  {i}. {perfil}", flush=True)

sel = input("\nElegir fuente (numero): ").strip()

if sel == "0":
    fuente_nombre = "global"
else:
    idx = int(sel) - 1
    if 0 <= idx < len(perfiles_disponibles):
        fuente_nombre = perfiles_disponibles[idx]
    else:
        fuente_nombre = "global"

print("\nModo de color:", flush=True)
print("  1. Por Precio (costo_total)", flush=True)
print("  2. Por Score", flush=True)
modo = input("Opcion: ").strip()
modo_color = "score" if modo == "2" else "precio"

print(f"\nCargando datos: {fuente_nombre}, modo: {modo_color}", flush=True)

geojson_path = outputs_dir / f"departamentos_enriquecido_{fuente_nombre}.geojson"
if not geojson_path.exists():
    print(f"ERROR: No existe {geojson_path}", flush=True)
    print("Ejecuta primero 6_metrics_new.py", flush=True)
    sys.exit(1)

departamentos = gpd.read_file(geojson_path)
print(f"Registros: {len(departamentos)}", flush=True)

barrios = gpd.read_file(shapes_dir / "barrios.geojson")
EV = gpd.read_file(shapes_dir / "espacio_verde_publico.geojson")
lineas_subte = gpd.read_file(shapes_dir / "subte_lineas.geojson")
estaciones_subte = gpd.read_file(shapes_dir / "estaciones_de_subte.geojson")
gyms_total = gpd.read_file(shapes_dir / "gimnasios.geojson", driver="GeoJSON")

lineas_subte, estaciones_subte = aplicar_colores_subte(lineas_subte, estaciones_subte)
gyms_total = aplicar_colores_gyms(gyms_total)

def clean_for_map(gdf):
    df = gdf.loc[:, ~gdf.columns.duplicated()].copy()
    for col in df.columns:
        if pd.api.types.is_datetime64_any_dtype(df[col]):
            df[col] = df[col].dt.strftime('%Y-%m-%d')
        elif str(df[col].dtype) in ['Int64', 'float64', 'int64', 'int32']:
            df[col] = pd.to_numeric(df[col], errors='coerce').astype(float)
    return df.to_crs(epsg=4326)

barrios_interes = departamentos['Barrio'].unique()
barrios_filtrados = barrios[barrios['nombre'].isin(barrios_interes)]
EV = EV[EV['clasificac'].isin(['PARQUE', 'JARDÍN BOTANICO', 'PLAZA'])]
EV['cat'] = EV['clasificac'].replace({'JARDÍN BOTANICO': 'parque', 'PARQUE': 'parque', 'PLAZA': 'plaza'})

barrios_map = clean_for_map(barrios_filtrados)
ev_map = clean_for_map(EV)
subte_lin_map = clean_for_map(lineas_subte)
subte_est_map = clean_for_map(estaciones_subte)
gyms_map = clean_for_map(gyms_total)

bins_precio = [0, 300000, 400000, 500000, 600000, 700000, 800000, 10000000]
colors_precio = ['#1a9850', '#91cf60', '#d9ef8b', '#fee08b', '#fc8d59', '#d73027', '#67000d']

def get_color_precio(valor):
    if pd.isna(valor): return '#808080'
    for i in range(len(bins_precio)-1):
        if bins_precio[i] <= valor < bins_precio[i+1]:
            return colors_precio[i]
    return colors_precio[-1]

bins_score = [0, 20, 40, 60, 80, 100]
colors_score = ['#d73027', '#fc8d59', '#fee08b', '#d9ef8b', '#91cf60', '#1a9850']

def get_color_score(valor):
    if pd.isna(valor): return '#808080'
    for i in range(len(bins_score)-1):
        if bins_score[i] <= valor < bins_score[i+1]:
            return colors_score[i]
    return colors_score[-1]

m = folium.Map(location=[-34.6037, -58.3816], zoom_start=12, tiles='OpenStreetMap')

folium.GeoJson(
    barrios_map, name='Barrios',
    style_function=lambda x: {'fillColor': 'transparent', 'color': 'black', 'weight': 2.5, 'opacity': 1}
).add_to(m)

folium.GeoJson(
    ev_map, name='Espacios Verdes',
    style_function=lambda x: {
        'fillColor': '#2ca25f' if x['properties']['cat'] == 'parque' else '#99d8c9',
        'color': '#00441b', 'weight': 1, 'fillOpacity': 0.6
    },
    tooltip=folium.GeoJsonTooltip(fields=['nombre', 'cat'], aliases=['Nombre:', 'Tipo:'])
).add_to(m)

folium.GeoJson(
    subte_lin_map, name='Lineas Subte',
    style_function=lambda x: {'color': x['properties'].get('color_map', 'black'), 'weight': 3.5, 'opacity': 0.8}
).add_to(m)

estaciones_layer = folium.FeatureGroup(name="Estaciones Subte")
for _, row in subte_est_map.iterrows():
    folium.CircleMarker(
        location=[row.geometry.y, row.geometry.x], radius=4, color='white', weight=0.5,
        fill=True, fill_color=row['color_map'], fill_opacity=1
    ).add_to(estaciones_layer)
estaciones_layer.add_to(m)

gyms_layer = folium.FeatureGroup(name="Gimnasios")
for _, row in gyms_map.iterrows():
    folium.CircleMarker(
        location=[row.geometry.y, row.geometry.x], radius=6,
        color='black', weight=1, fill=True, 
        fill_color=row['color_map'], fill_opacity=0.9,
        popup=f"{row['cadena']}: {row['nombre']}"
    ).add_to(gyms_layer)
gyms_layer.add_to(m)

tooltip_fields = [
    'Score', 'Tipo', 'Portal', 'Barrio', 'Direccion',
    'Precio', 'Expensas', 'costo_total',
    'Ambientes', 'Cocheras', 'Dormitorios', 'Baños',
    'Metros_Totales', 'Metros_Cubiertos',
    'distancia_m_subte', 'cant_subte',
    'distancia_m_gym', 'cant_gym',
    'dist_verde_final', 'cant_parque', 'cant_plaza'
]

dormitorios_unicos = sorted(departamentos['Dormitorios'].dropna().unique())
cocheras_unicas = sorted(departamentos['Cocheras'].fillna(0).astype(int).unique())

color_func = get_color_score if modo_color == "score" else get_color_precio
valor_key = 'Score' if modo_color == "score" else 'costo_total'

for dorm in dormitorios_unicos:
    df_dorm = departamentos[departamentos['Dormitorios'] == dorm].copy()
    if len(df_dorm) == 0:
        continue
    
    gdf_dorm = gpd.GeoDataFrame(df_dorm, geometry=df_dorm.geometry, crs="EPSG:4326")
    gdf_dorm_map = clean_for_map(gdf_dorm)
    
    radius_dorm = 4 + int(dorm)
    
    folium.GeoJson(
        gdf_dorm_map.to_json(),
        name=f'{int(dorm)} Dormitorios',
        marker=folium.CircleMarker(
            radius=radius_dorm, 
            fill=True, 
            fill_opacity=0.7, 
            color='black', 
            weight=1
        ),
        style_function=lambda x, vk=valor_key: {'fillColor': color_func(x['properties'].get(vk))},
        tooltip=folium.GeoJsonTooltip(
            fields=[f for f in tooltip_fields if f in gdf_dorm_map.columns],
            aliases=[f.replace('_', ' ').capitalize() + ":" for f in tooltip_fields if f in gdf_dorm_map.columns]
        ),
        show=False
    ).add_to(m)

for coch in cocheras_unicas:
    if coch == 0:
        continue
    
    df_coch = departamentos[departamentos['Cocheras'].fillna(0).astype(int) == coch].copy()
    if len(df_coch) == 0:
        continue
    
    gdf_coch = gpd.GeoDataFrame(df_coch, geometry=df_coch.geometry, crs="EPSG:4326")
    gdf_coch_map = clean_for_map(gdf_coch)
    
    folium.GeoJson(
        gdf_coch_map.to_json(),
        name=f'{int(coch)} Cocheras',
        marker=folium.CircleMarker(
            radius=6, 
            fill=True, 
            fill_opacity=0.8,
            color='gold',
            weight=2
        ),
        style_function=lambda x, vk=valor_key: {'fillColor': color_func(x['properties'].get(vk))},
        tooltip=folium.GeoJsonTooltip(
            fields=[f for f in tooltip_fields if f in gdf_coch_map.columns],
            aliases=[f.replace('_', ' ').capitalize() + ":" for f in tooltip_fields if f in gdf_coch_map.columns]
        ),
        show=False
    ).add_to(m)

colormap = cm.StepColormap(
    colors_score if modo_color == "score" else colors_precio,
    vmin=0,
    vmax=100 if modo_color == "score" else 900000,
    index=bins_score if modo_color == "score" else bins_precio,
    caption='Score (0-100)' if modo_color == "score" else 'Costo Total'
)
colormap.add_to(m)

folium.LayerControl(collapsed=False).add_to(m)

print(f"\nMapa generado: {fuente_nombre} - modo {modo_color}", flush=True)
print("Capas por dormitorios (radio crece con dormitorios)", flush=True)
print("Capas con cochera (borde dorado grueso)", flush=True)
m
#%%