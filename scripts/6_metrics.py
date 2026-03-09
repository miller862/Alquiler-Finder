#%%
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import pandas as pd
import geopandas as gpd
import pathlib
import numpy as np
import momepy
import networkx as nx
from shapely.ops import nearest_points
from scipy.spatial import KDTree
import importlib
import folium
from folium import plugins
import branca.colormap as cm

parametros = importlib.import_module('0_parametros')
url_normalize = parametros.url_normalize
precio_norm_value = parametros.precio_norm_value
join_key_direccion_precio = parametros.join_key_direccion_precio
auxiliar = importlib.import_module('5_auxiliar')
color_subte_map = auxiliar.color_subte_map
color_gyms_map = auxiliar.color_gyms_map
aplicar_colores_subte = auxiliar.aplicar_colores_subte
aplicar_colores_gyms = auxiliar.aplicar_colores_gyms
cargar_configuraciones_scraping = parametros.cargar_configuraciones_scraping
PERFILES_DIR = parametros.PERFILES_DIR
BASE_PATH = parametros.BASE_PATH

#%% SELECCION DE PERFIL
script_dir = pathlib.Path(__file__).parent
shapes_dir = (BASE_PATH / "shapes").resolve()
perfil_outputs_dir = PERFILES_DIR  # cada perfil es subcarpeta

print("\n=== SELECCION DE PERFIL ===")
configs = cargar_configuraciones_scraping()
perfiles_disponibles = [cfg.get('nombre', 'Sin nombre') for cfg in configs]

if not perfiles_disponibles:
    print("No hay perfiles disponibles. Ejecuta 3_main.py primero.")
    sys.exit(1)

print("Perfiles disponibles:")
for i, perfil in enumerate(perfiles_disponibles, 1):
    print(f"  {i}. {perfil}")

sel = input("\nElegir perfil a calcular (numero): ").strip()
idx = int(sel) - 1

if not (0 <= idx < len(perfiles_disponibles)):
    print("Opcion invalida")
    sys.exit(1)

fuente_nombre = perfiles_disponibles[idx]
geojson_path = PERFILES_DIR / fuente_nombre / "departamentos.geojson"
outputs_dir = PERFILES_DIR / fuente_nombre

if not geojson_path.exists():
    print(f"ERROR: No existe {geojson_path}")
    print("Ejecuta primero 4_consolidar.py para este perfil.")
    sys.exit(1)

print(f"\nCalculando metricas para perfil: {fuente_nombre}")
departamentos = gpd.read_file(geojson_path)
print(f"Registros cargados: {len(departamentos)}")

# Constantes para distancias
DIJKSTRA_CUTOFF = 2000
DIJKSTRA_PENALIZACION_NAN = 1500
SNAP_WARNING_UMBRAL_M = 150

#%% CARGAR CAPAS BASE
barrios = gpd.read_file(shapes_dir / "barrios.geojson")
EV = gpd.read_file(shapes_dir / "espacio_verde_publico.geojson")
lineas_subte = gpd.read_file(shapes_dir / "subte_lineas.geojson")
estaciones_subte = gpd.read_file(shapes_dir / "estaciones_de_subte.geojson")
gyms_total = gpd.read_file(shapes_dir / "gimnasios.geojson", driver="GeoJSON")
callejero = gpd.read_file(shapes_dir / "callejero.geojson")

#%% preparo capas de transporte y gimnasios
lineas_subte, estaciones_subte = aplicar_colores_subte(lineas_subte, estaciones_subte)
gyms_total = aplicar_colores_gyms(gyms_total)

# preparo espacios verdes
EV = EV[EV.clasificac.isin(['PARQUE', 'JARDÍN BOTANICO', 'PLAZA'])]

# preparo departamentos
# 1. Normalización de nombres en 'departamentos'
departamentos['Barrio'] = departamentos['Barrio'].str.replace('-', ' ').str.title()
departamentos['Barrio'] = departamentos['Barrio'].replace('Barrio Norte', 'Recoleta')

# 2. Definir barrios permitidos (los del excel + adicionales)
barrios_excel = departamentos['Barrio'].unique()
barrios_adicionales = ['Saavedra', 'Nuñez', 'Villa Urquiza', 'Villa Crespo', 'Retiro']
barrios_permitidos = list(set(list(barrios_excel) + barrios_adicionales))

print(f"Barrios permitidos: {sorted(barrios_permitidos)}")

# 3. Filtrar polígonos de barrios
barrios_filtrados = barrios[barrios['nombre'].isin(barrios_permitidos)]

# 4. Join Espacial
departamentos_final = gpd.sjoin(
    departamentos,
    barrios_filtrados[['nombre', 'geometry']],
    how="inner",
    predicate="within"
)

# 5. Limpieza post-join
if 'index_right' in departamentos_final.columns:
    departamentos_final = departamentos_final.drop(columns=['index_right'])

departamentos_final = departamentos_final.rename(columns={'nombre': 'Barrio_Geo'})

print(f"Registros finales: {len(departamentos_final)}")
print(f"Barrios en resultado final: {sorted(departamentos_final['Barrio_Geo'].unique())}")

#%%
proyeccion = 22185
G = momepy.gdf_to_nx(callejero.to_crs(epsg=proyeccion), approach='primal')
nodos_coords = np.array(list(G.nodes))
tree = KDTree(nodos_coords)

# Verificar una sola componente conexa
componentes = list(nx.connected_components(G))
if len(componentes) > 1:
    print(f"ADVERTENCIA: el grafo tiene {len(componentes)} componentes conexas. "
          f"Tamaños: {[len(c) for c in sorted(componentes, key=len, reverse=True)]}")

# Categorizar EV: Botánico y Parque -> parque, Plaza -> plaza
EV['cat'] = EV['clasificac'].replace({'JARDÍN BOTANICO': 'parque', 'PARQUE': 'parque', 'PLAZA': 'plaza'})

# Pre-calcular nodos de origen (departamentos) y distancia al nodo snapeado
depts_m = departamentos_final.to_crs(epsg=proyeccion)
dept_xy = np.column_stack([depts_m.geometry.x, depts_m.geometry.y])
_, idx_org = tree.query(dept_xy)
nodos_org = [tuple(nodos_coords[i]) for i in idx_org]

# Validar distancia al nodo snapeado: si > 150m marcar snap_warning
dists_snap = np.sqrt(np.sum((dept_xy - nodos_coords[idx_org]) ** 2, axis=1))
departamentos_final['snap_warning'] = dists_snap >= SNAP_WARNING_UMBRAL_M

# Capas con destino por centroide (gym, subte)
capas_centroide = {
    'gym': gyms_total,
    'subte': estaciones_subte,
}

# Capas polígono: parque/plaza
capas_poligono = {
    'parque': EV[EV.cat == 'parque'],
    'plaza': EV[EV.cat == 'plaza'],
}

def _min_dist_penalizar(d_en_red):
    if d_en_red:
        return min(d_en_red)
    return DIJKSTRA_PENALIZACION_NAN

# ------------------------------------------------------------------
# Bucle para gym y subte (centroide) — sin cambios
# ------------------------------------------------------------------
for etiqueta, gdf_poi in capas_centroide.items():
    print(f"Calculando ruteo real a {etiqueta}...")
    poi_m = gdf_poi.to_crs(epsg=proyeccion)
    _, idx_dest = tree.query(np.column_stack([poi_m.geometry.centroid.x, poi_m.geometry.centroid.y]))
    nodos_dst = set(tuple(nodos_coords[i]) for i in idx_dest)

    res_dist, res_cant = [], []
    for i, n_start in enumerate(nodos_org):
        dists_dict = nx.single_source_dijkstra_path_length(G, n_start, cutoff=DIJKSTRA_CUTOFF, weight='mm_len')
        d_en_red = [d for nodo, d in dists_dict.items() if nodo in nodos_dst]
        res_dist.append(_min_dist_penalizar(d_en_red))
        res_cant.append(len(d_en_red))

        if (i + 1) % 50 == 0:
            print(f"    Procesados: {i+1}/{len(nodos_org)}...")

    departamentos_final[f'distancia_m_{etiqueta}'] = res_dist
    departamentos_final[f'cant_{etiqueta}'] = res_cant

# ------------------------------------------------------------------
# Bucle para parque/plaza — OPTIMIZADO
# En lugar de correr Dijkstra por cada par (depto × polígono),
# se pre-snappean todos los polígonos a nodos del grafo una sola vez,
# y luego se corre un único Dijkstra por departamento buscando
# todos los nodos destino dentro del resultado.
# Complejidad: O(deptos × Dijkstra) en vez de O(deptos × polígonos × Dijkstra)
# ------------------------------------------------------------------
for etiqueta, gdf_poi in capas_poligono.items():
    if gdf_poi.empty:
        n = len(departamentos_final)
        departamentos_final[f'distancia_m_{etiqueta}'] = [DIJKSTRA_PENALIZACION_NAN] * n
        departamentos_final[f'cant_{etiqueta}'] = [0] * n
        continue

    print(f"Calculando ruteo real a {etiqueta} (borde más cercano, modo optimizado)...")
    poi_m = gdf_poi.to_crs(epsg=proyeccion)

    # Pre-snapping: para cada polígono, encontrar el nodo del grafo
    # más cercano al centroide de su borde (una sola vez, fuera del bucle de deptos)
    nodos_dst_list = []
    for _, row in poi_m.iterrows():
        boundary = row.geometry.boundary
        if boundary is not None and not boundary.is_empty:
            pt_ref = boundary.centroid
        else:
            pt_ref = row.geometry.centroid
        _, idx_d = tree.query([[pt_ref.x, pt_ref.y]], k=1)
        nodos_dst_list.append(tuple(nodos_coords[idx_d[0]]))

    nodos_dst_set = set(nodos_dst_list)
    print(f"    Nodos destino pre-calculados: {len(nodos_dst_set)} nodos únicos para {len(nodos_dst_list)} polígonos")

    res_dist, res_cant = [], []
    for i, n_start in enumerate(nodos_org):
        dists_dict = nx.single_source_dijkstra_path_length(G, n_start, cutoff=DIJKSTRA_CUTOFF, weight='mm_len')
        d_en_red = [d for nodo, d in dists_dict.items() if nodo in nodos_dst_set]
        res_dist.append(_min_dist_penalizar(d_en_red))
        res_cant.append(len(d_en_red))

        if (i + 1) % 50 == 0:
            print(f"    Procesados: {i+1}/{len(nodos_org)}...")

    departamentos_final[f'distancia_m_{etiqueta}'] = res_dist
    departamentos_final[f'cant_{etiqueta}'] = res_cant

# ------------------------------------------------------------------
# Cambio de tipo de dato global (fuera del bucle)
# ------------------------------------------------------------------
for etiqueta in list(capas_centroide.keys()) + list(capas_poligono.keys()):
    d_col = f'distancia_m_{etiqueta}'
    c_col = f'cant_{etiqueta}'

    # Distancia: numérico -> floor -> entero con nulos
    departamentos_final[d_col] = (
        pd.to_numeric(departamentos_final[d_col], errors='coerce')
        .apply(np.floor)
        .astype('Int64')
    )

    # Cantidad: numérico -> nulos a 0 -> entero
    departamentos_final[c_col] = (
        pd.to_numeric(departamentos_final[c_col], errors='coerce')
        .fillna(0)
        .astype(int)
    )

#%%
# Asegurar costo_total
departamentos_final['costo_total'] = departamentos_final['Precio'] + departamentos_final['Expensas'].fillna(0)

#%% SCORING Y RANKING
print("\n=== CALCULANDO SCORING ===")

df_scoring = departamentos_final.copy()

print("1. Unificando distancias a espacios verdes...")
df_scoring['dist_verde_final'] = df_scoring[['distancia_m_plaza', 'distancia_m_parque']].min(axis=1)

print("2. Definiendo propiedades aptas para scoring...")
df_scoring['apto_scoring'] = True
mask_depto_sin_expensas = (
    (df_scoring['Tipo'] == 'Departamento') &
    (df_scoring['Expensas'].isna() | (df_scoring['Expensas'] == 0))
)
df_scoring.loc[mask_depto_sin_expensas, 'apto_scoring'] = False
print(f"  Aptas: {df_scoring['apto_scoring'].sum()}, No aptas: {(~df_scoring['apto_scoring']).sum()}")

print("3. Creando segmentos (Cocheras separadas, Ambientes con 0 cocheras)...")
df_scoring['Cocheras'] = df_scoring['Cocheras'].fillna(0).astype(int)

df_scoring['segmento'] = df_scoring.apply(
    lambda row: f"{int(row['Cocheras'])}coch" if row['Cocheras'] > 0
    else (f"{int(row['Ambientes'])}amb" if pd.notna(row['Ambientes']) else 'sin_datos'),
    axis=1
)

segmentos = sorted(df_scoring['segmento'].unique())
print(f"  Segmentos encontrados: {segmentos}")

print("4. Calculando scoring por segmento...")

def normalizar_inversa(serie):
    min_val = serie.min()
    max_val = serie.max()
    if max_val == min_val:
        return pd.Series(50, index=serie.index)
    return 100 - ((serie - min_val) / (max_val - min_val)) * 100

variables_a_normalizar = ['costo_total', 'distancia_m_subte', 'dist_verde_final', 'distancia_m_gym']
pesos = {
    'costo_total_norm': 0.40,
    'distancia_m_subte_norm': 0.30,
    'dist_verde_final_norm': 0.20,
    'distancia_m_gym_norm': 0.10
}

for var in variables_a_normalizar:
    df_scoring[f'{var}_norm'] = np.nan

df_scoring['Score'] = np.nan

for seg in segmentos:
    mask_seg = (df_scoring['segmento'] == seg) & df_scoring['apto_scoring']
    if mask_seg.sum() == 0:
        continue

    for var in variables_a_normalizar:
        valores = df_scoring.loc[mask_seg, var]
        valores_validos = valores[valores.notna()]
        if len(valores_validos) > 0:
            df_scoring.loc[mask_seg & valores.notna(), f'{var}_norm'] = normalizar_inversa(valores_validos)

    score_componentes = pd.DataFrame(index=df_scoring[mask_seg].index)
    for var, peso in pesos.items():
        score_componentes[var] = df_scoring.loc[mask_seg, var] * peso

    score_validos = score_componentes.dropna(how='all')
    if len(score_validos) > 0:
        df_scoring.loc[score_validos.index, 'Score'] = score_validos.sum(axis=1)

print(f"  Propiedades con score: {df_scoring['Score'].notna().sum()}")

print("5. Preservando columna REVISION y FECHA_DETECCION de archivo previo (dos pasadas: URL_norm, Direccion_norm|Precio_norm)...")
ranking_previo_path = outputs_dir / "ranking.xlsx"
fecha_hoy = pd.Timestamp.now().strftime('%Y-%m-%d')

# Claves alineadas con 4_consolidar
df_scoring["URL_norm"] = df_scoring["URL"].map(url_normalize) if "URL" in df_scoring.columns else ""
df_scoring["join_dir_precio"] = join_key_direccion_precio(df_scoring)

df_scoring["REVISION"] = None
df_scoring["FECHA_DETECCION"] = fecha_hoy

if ranking_previo_path.exists():
    print("  Archivo previo encontrado, cargando revisiones y fechas...")
    sheets_previas = pd.read_excel(ranking_previo_path, sheet_name=None)
    datos_previos = []
    for _, df_prev in sheets_previas.items():
        if "Portal" not in df_prev.columns or "Direccion" not in df_prev.columns or "Precio" not in df_prev.columns:
            continue
        df_prev_local = df_prev.copy()
        df_prev_local["URL_norm"] = df_prev_local["URL"].map(url_normalize) if "URL" in df_prev_local.columns else ""
        df_prev_local["join_dir_precio"] = join_key_direccion_precio(df_prev_local)
        cols = ["URL_norm", "join_dir_precio"]
        if "REVISION" in df_prev_local.columns:
            cols.append("REVISION")
        if "FECHA_DETECCION" in df_prev_local.columns:
            cols.append("FECHA_DETECCION")
        datos_previos.append(df_prev_local[cols])

    if datos_previos:
        previos_df = pd.concat(datos_previos, ignore_index=True)
        prev_url = previos_df.drop_duplicates(subset="URL_norm", keep="first")
        prev_dir = previos_df.drop_duplicates(subset="join_dir_precio", keep="first")

        # Pasada 1: merge por URL normalizada
        rev_fecha_cols = [c for c in ["REVISION", "FECHA_DETECCION"] if c in prev_url.columns]
        if rev_fecha_cols:
            df_scoring = df_scoring.merge(
                prev_url[["URL_norm"] + rev_fecha_cols],
                on="URL_norm",
                how="left",
                suffixes=("", "_prev")
            )
            if "REVISION_prev" in df_scoring.columns:
                df_scoring["REVISION"] = df_scoring["REVISION"].fillna(df_scoring["REVISION_prev"])
                df_scoring = df_scoring.drop(columns=["REVISION_prev"])
            if "FECHA_DETECCION_prev" in df_scoring.columns:
                df_scoring["FECHA_DETECCION"] = df_scoring["FECHA_DETECCION"].fillna(df_scoring["FECHA_DETECCION_prev"])
                df_scoring = df_scoring.drop(columns=["FECHA_DETECCION_prev"])

        # Pasada 2: sin match por URL — merge por Direccion_norm|Precio_norm
        faltan = df_scoring["REVISION"].isna() if "REVISION" in df_scoring.columns else pd.Series([True] * len(df_scoring), index=df_scoring.index)
        if faltan.any() and "join_dir_precio" in prev_dir.columns:
            prev_fb = prev_dir.set_index("join_dir_precio")
            if "REVISION" in prev_fb.columns:
                df_scoring.loc[faltan, "REVISION"] = df_scoring.loc[faltan, "join_dir_precio"].map(prev_fb["REVISION"])
            if "FECHA_DETECCION" in prev_fb.columns:
                df_scoring.loc[faltan, "FECHA_DETECCION"] = df_scoring.loc[faltan, "join_dir_precio"].map(prev_fb["FECHA_DETECCION"])

        df_scoring["FECHA_DETECCION"] = pd.to_datetime(df_scoring["FECHA_DETECCION"], errors="coerce").dt.strftime("%Y-%m-%d")
        df_scoring["FECHA_DETECCION"] = df_scoring["FECHA_DETECCION"].fillna(fecha_hoy)
        revisiones_recuperadas = df_scoring["REVISION"].notna().sum()
        fechas_recuperadas = (df_scoring["FECHA_DETECCION"] != fecha_hoy).sum()
        print(f"   {revisiones_recuperadas} revisiones preservadas, {fechas_recuperadas} fechas historicas preservadas")
    else:
        print("   No hay datos previos compatibles para merge")
else:
    print("   No hay archivo previo, todas las fechas son de hoy")

if "FECHA_DETECCION" in df_scoring.columns:
    df_scoring["FECHA_DETECCION"] = df_scoring["FECHA_DETECCION"].fillna(fecha_hoy)

# Limpiar columnas auxiliares de join
df_scoring = df_scoring.drop(columns=["URL_norm", "join_dir_precio"], errors="ignore")

print("\n6. Exportando ranking segmentado...")
output_ranking = outputs_dir / "ranking.xlsx"

columnas_export = [
    'REVISION', 'FECHA_DETECCION', 'Score', 'Tipo', 'Portal', 'Barrio', 'Direccion',
    'Titulo', 'Descripcion_Breve',
    'Precio', 'Expensas', 'costo_total',
    'Ambientes', 'Cocheras', 'Dormitorios', 'Baños',
    'Metros_Totales', 'Metros_Cubiertos',
    'distancia_m_subte', 'cant_subte',
    'distancia_m_gym', 'cant_gym',
    'dist_verde_final', 'cant_parque', 'cant_plaza',
    'snap_warning', 'URL'
]
columnas_disponibles = [c for c in columnas_export if c in df_scoring.columns]

with pd.ExcelWriter(output_ranking, engine='openpyxl') as writer:
    for seg in sorted(segmentos):
        df_seg = df_scoring[df_scoring['segmento'] == seg][columnas_disponibles].copy()
        df_seg = df_seg.sort_values('Score', ascending=False, na_position='last')
        df_seg.to_excel(writer, sheet_name=seg, index=False)
        print(f"   Hoja '{seg}': {len(df_seg)} propiedades")

print(f"\nRanking guardado en: {output_ranking}")
print("Columna REVISION lista para edicion manual.")

departamentos_final = df_scoring.copy()

print(f"\n7. Exportando datos enriquecidos...")
outputs_dir.mkdir(parents=True, exist_ok=True)
output_excel = outputs_dir / "departamentos_enriquecido.xlsx"
departamentos_final.to_excel(output_excel, index=False)
print(f"   Excel completo: {output_excel}")

gdf_output = gpd.GeoDataFrame(
    departamentos_final,
    geometry=departamentos_final.geometry,
    crs="EPSG:4326"
)
output_geojson = outputs_dir / "departamentos_enriquecido.geojson"
gdf_output.to_file(output_geojson, driver="GeoJSON")
print(f"   GeoJSON enriquecido: {output_geojson}")

#%% ACTUALIZACION AUTOMATICA DEL GLOBAL
print("\n=== ACTUALIZANDO GLOBAL ===")

all_enriquecidos = []
for perfil in perfiles_disponibles:
    excel_path = PERFILES_DIR / perfil / "departamentos_enriquecido.xlsx"
    if excel_path.exists():
        df_perfil = pd.read_excel(excel_path)
        df_perfil['_perfil_origen'] = perfil
        all_enriquecidos.append(df_perfil)
        print(f"  Cargado: {perfil} ({len(df_perfil)} registros)")

if all_enriquecidos:
    print("\n  Consolidando global...")
    global_df = pd.concat(all_enriquecidos, ignore_index=True)

    global_df['Direccion_norm'] = global_df['Direccion'].astype(str).str.lower().str.strip()
    global_df = global_df.sort_values('_perfil_origen')
    global_df = global_df.drop_duplicates(subset='Direccion_norm', keep='first')
    global_df = global_df.drop(columns=['Direccion_norm', '_perfil_origen'])

    print(f"  Recalculando scoring global...")
    global_df['Cocheras'] = global_df['Cocheras'].fillna(0).astype(int)
    global_df['segmento'] = global_df.apply(
        lambda row: f"{int(row['Cocheras'])}coch" if row['Cocheras'] > 0
        else (f"{int(row['Ambientes'])}amb" if pd.notna(row['Ambientes']) else 'sin_datos'),
        axis=1
    )

    global_df['apto_scoring'] = True
    mask_depto_sin_expensas = (
        (global_df['Tipo'] == 'Departamento') &
        (global_df['Expensas'].isna() | (global_df['Expensas'] == 0))
    )
    global_df.loc[mask_depto_sin_expensas, 'apto_scoring'] = False

    def normalizar_inversa(serie):
        min_val = serie.min()
        max_val = serie.max()
        if max_val == min_val:
            return pd.Series(50, index=serie.index)
        return 100 - ((serie - min_val) / (max_val - min_val)) * 100

    variables_a_normalizar = ['costo_total', 'distancia_m_subte', 'dist_verde_final', 'distancia_m_gym']
    pesos = {
        'costo_total_norm': 0.40,
        'distancia_m_subte_norm': 0.30,
        'dist_verde_final_norm': 0.20,
        'distancia_m_gym_norm': 0.10
    }

    for var in variables_a_normalizar:
        global_df[f'{var}_norm'] = np.nan

    global_df['Score'] = np.nan

    for seg in global_df['segmento'].unique():
        mask_seg = (global_df['segmento'] == seg) & global_df['apto_scoring']
        if mask_seg.sum() == 0:
            continue

        for var in variables_a_normalizar:
            valores = global_df.loc[mask_seg, var]
            valores_validos = valores[valores.notna()]
            if len(valores_validos) > 0:
                global_df.loc[mask_seg & valores.notna(), f'{var}_norm'] = normalizar_inversa(valores_validos)

        score_componentes = pd.DataFrame(index=global_df[mask_seg].index)
        for var, peso in pesos.items():
            score_componentes[var] = global_df.loc[mask_seg, var] * peso

        score_validos = score_componentes.dropna(how='all')
        if len(score_validos) > 0:
            global_df.loc[score_validos.index, 'Score'] = score_validos.sum(axis=1)

    print(f"  Global: {len(global_df)} registros unicos, {global_df['Score'].notna().sum()} con score")

    global_dir = PERFILES_DIR / "global"
    global_dir.mkdir(parents=True, exist_ok=True)
    output_global_excel = global_dir / "departamentos_enriquecido_global.xlsx"
    global_df.to_excel(output_global_excel, index=False)
    print(f"  Excel global: {output_global_excel}")

    global_df_geo = global_df[global_df['lat'].notna() & global_df['lon'].notna()].copy()
    if not global_df_geo.empty:
        gdf_global = gpd.GeoDataFrame(
            global_df_geo,
            geometry=gpd.points_from_xy(global_df_geo['lon'], global_df_geo['lat']),
            crs="EPSG:4326"
        )
        output_global_geojson = global_dir / "departamentos_enriquecido_global.geojson"
        gdf_global.to_file(output_global_geojson, driver="GeoJSON")
        print(f"  GeoJSON global: {output_global_geojson}")

    output_ranking_global = global_dir / "ranking_global.xlsx"
    columnas_export = [
        'Score', 'Tipo', 'Portal', 'Barrio', 'Direccion',
        'Precio', 'Expensas', 'costo_total',
        'Ambientes', 'Cocheras', 'Dormitorios', 'Baños',
        'Metros_Totales', 'Metros_Cubiertos',
        'distancia_m_subte', 'cant_subte',
        'distancia_m_gym', 'cant_gym',
        'dist_verde_final', 'cant_parque', 'cant_plaza',
        'URL'
    ]
    columnas_disponibles = [c for c in columnas_export if c in global_df.columns]

    with pd.ExcelWriter(output_ranking_global, engine='openpyxl') as writer:
        for seg in sorted(global_df['segmento'].unique()):
            df_seg = global_df[global_df['segmento'] == seg][columnas_disponibles].copy()
            df_seg = df_seg.sort_values('Score', ascending=False, na_position='last')
            df_seg.to_excel(writer, sheet_name=seg, index=False)

    print(f"  Ranking global: {output_ranking_global}")

print("\n=== CALCULO DE METRICAS COMPLETADO ===")