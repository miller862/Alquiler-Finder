import pathlib
import json
import pandas as pd
import geopandas as gpd
import folium
import streamlit as st
from streamlit_folium import st_folium
import numpy as np

# set_page_config: PRIMERA llamada, UNICA, fuera de toda funcion
st.set_page_config(
    page_title="Departamentos CABA",
    page_icon="🗺️",
    layout="centered",
)

BASE_PATH    = pathlib.Path(__file__).parent.parent
PERFILES_DIR = BASE_PATH / "perfiles"
SHAPES_DIR   = (BASE_PATH / "shapes").resolve()
CONFIG_FILE  = PERFILES_DIR / "configuraciones.json"

def cargar_configuraciones():
    if CONFIG_FILE.exists():
        with open(CONFIG_FILE, 'r', encoding='utf-8') as f:
            return json.load(f)
    return []

def verificar_credenciales(usuario, password):
    for cfg in cargar_configuraciones():
        u = cfg.get('usuario', '').strip()
        p = cfg.get('password', '')
        if u and u.lower() == usuario.strip().lower() and p == password:
            return cfg.get('nombre', 'default'), None
    return None, "Usuario o contraseña incorrectos."

COLOR_SUBTE_MAP = {
    'A': '#00AEEF', 'B': '#ED1C24', 'C': '#0054A6',
    'D': '#00802F', 'E': '#662D91', 'H': '#FFD100'
}
COLOR_GYMS_MAP = {
    'SportClub': '#003366',
    'Megatlon':  '#ff6600',
    'Smartfit':  '#cc0000',
}
BINS_PRECIO   = [0, 300_000, 400_000, 500_000, 600_000, 700_000, 800_000, 10_000_000]
COLORS_PRECIO = ['#1a9850','#91cf60','#d9ef8b','#fee08b','#fc8d59','#d73027','#67000d']
BINS_SCORE    = [0, 20, 40, 60, 80, 100]
COLORS_SCORE  = ['#d73027','#fc8d59','#fee08b','#d9ef8b','#91cf60','#1a9850']

def get_color(valor, modo):
    if pd.isna(valor):
        return '#808080'
    bins, colors = (BINS_SCORE, COLORS_SCORE) if modo == 'score' else (BINS_PRECIO, COLORS_PRECIO)
    for i in range(len(bins) - 1):
        if bins[i] <= valor < bins[i + 1]:
            return colors[i]
    return colors[-1]

def aplicar_colores_subte(lineas_subte, estaciones_subte):
    lin = lineas_subte.copy()
    est = estaciones_subte.copy()
    lin['LINEASUB'] = lin['LINEASUB'].str.replace('LINEA ', '', regex=False).str.strip()
    lin['color_map'] = lin['LINEASUB'].map(COLOR_SUBTE_MAP)
    est['linea'] = est['linea'].str.strip()
    est['color_map'] = est['linea'].map(COLOR_SUBTE_MAP)
    return lin, est

def aplicar_colores_gyms(gyms):
    g = gyms.copy()
    g['color_map'] = g['cadena'].map(COLOR_GYMS_MAP)
    return g

@st.cache_data
def cargar_shapes():
    barrios      = gpd.read_file(SHAPES_DIR / "barrios.geojson")
    ev           = gpd.read_file(SHAPES_DIR / "espacio_verde_publico.geojson")
    lineas_subte = gpd.read_file(SHAPES_DIR / "subte_lineas.geojson")
    estaciones   = gpd.read_file(SHAPES_DIR / "estaciones_de_subte.geojson")
    gyms         = gpd.read_file(SHAPES_DIR / "gimnasios.geojson", driver="GeoJSON")
    ev = ev[ev['clasificac'].isin(['PARQUE', 'JARDÍN BOTANICO', 'PLAZA'])].copy()
    ev['cat'] = ev['clasificac'].replace({'JARDÍN BOTANICO':'parque','PARQUE':'parque','PLAZA':'plaza'})
    lineas_subte, estaciones = aplicar_colores_subte(lineas_subte, estaciones)
    gyms = aplicar_colores_gyms(gyms)
    return barrios, ev, lineas_subte, estaciones, gyms

@st.cache_data
def cargar_departamentos(perfil):
    if perfil == "global":
        path = PERFILES_DIR / "global" / "departamentos_enriquecido_global.geojson"
    else:
        path = PERFILES_DIR / perfil / "departamentos_enriquecido.geojson"
    if not path.exists():
        return None
    gdf = gpd.read_file(path)
    if gdf.crs is None or gdf.crs.to_epsg() != 4326:
        gdf = gdf.to_crs(epsg=4326)
    cols_num = ['Score','costo_total','Precio','Expensas',
                'distancia_m_subte','distancia_m_gym','dist_verde_final',
                'cant_subte','cant_gym','cant_parque','cant_plaza',
                'Ambientes','Dormitorios','Cocheras','Banios',
                'Metros_Totales','Metros_Cubiertos']
    for col in cols_num:
        if col in gdf.columns:
            gdf[col] = pd.to_numeric(gdf[col], errors='coerce')
    cols_int = ['cant_subte','cant_gym','cant_parque','cant_plaza',
                'Ambientes','Dormitorios','Cocheras','Banios',
                'distancia_m_subte','distancia_m_gym','dist_verde_final',
                'Metros_Totales','Metros_Cubiertos','Precio','Expensas','costo_total']
    for col in cols_int:
        if col in gdf.columns:
            gdf[col] = gdf[col].astype('Int64')
    if 'Score' in gdf.columns:
        gdf['Score'] = gdf['Score'].round(0).astype('Int64')
    return gdf

def clean_gdf(gdf):
    df = gdf.loc[:, ~gdf.columns.duplicated()].copy()
    for col in df.columns:
        if pd.api.types.is_datetime64_any_dtype(df[col]):
            df[col] = df[col].dt.strftime('%Y-%m-%d')
        if str(df[col].dtype) == 'Int64':
            df[col] = df[col].astype(float)
    return df.to_crs(epsg=4326)

TOOLTIP_FIELDS = [
    'Score','Tipo','Portal','Barrio','Direccion',
    'Precio','Expensas','costo_total',
    'Ambientes','Cocheras','Dormitorios','Banios',
    'Metros_Totales','Metros_Cubiertos',
    'distancia_m_subte','cant_subte',
    'distancia_m_gym','cant_gym',
    'dist_verde_final','cant_parque','cant_plaza',
]

def construir_mapa(df_filtrado, barrios, ev, lineas_subte, estaciones, gyms,
                   modo_color, capas_depto, capas_ext):
    m = folium.Map(location=[-34.6037, -58.3816], zoom_start=12, tiles='OpenStreetMap')
    if 'Barrios' in capas_ext:
        barrios_interes = df_filtrado['Barrio'].dropna().unique()
        folium.GeoJson(
            clean_gdf(barrios[barrios['nombre'].isin(barrios_interes)]), name='Barrios',
            style_function=lambda x: {'fillColor':'transparent','color':'black','weight':2.5,'opacity':0.8}
        ).add_to(m)
    if 'Espacios Verdes' in capas_ext:
        folium.GeoJson(
            clean_gdf(ev), name='Espacios Verdes',
            style_function=lambda x: {
                'fillColor':'#2ca25f' if x['properties'].get('cat')=='parque' else '#99d8c9',
                'color':'#00441b','weight':1,'fillOpacity':0.5
            },
            tooltip=folium.GeoJsonTooltip(fields=['nombre','cat'], aliases=['Nombre:','Tipo:'])
        ).add_to(m)
    if 'Lineas Subte' in capas_ext:
        folium.GeoJson(
            clean_gdf(lineas_subte), name='Lineas Subte',
            style_function=lambda x: {
                'color': x['properties'].get('color_map') or 'gray', 'weight':3.5, 'opacity':0.9
            }
        ).add_to(m)
    if 'Estaciones Subte' in capas_ext:
        layer_est = folium.FeatureGroup(name="Estaciones Subte")
        for _, row in clean_gdf(estaciones).iterrows():
            folium.CircleMarker(
                location=[row.geometry.y, row.geometry.x], radius=4,
                color='white', weight=0.8,
                fill=True, fill_color=row.get('color_map') or 'gray', fill_opacity=1
            ).add_to(layer_est)
        layer_est.add_to(m)
    if 'Gimnasios' in capas_ext:
        layer_gym = folium.FeatureGroup(name="Gimnasios")
        for _, row in clean_gdf(gyms).iterrows():
            folium.CircleMarker(
                location=[row.geometry.y, row.geometry.x], radius=6,
                color='black', weight=1,
                fill=True, fill_color=row.get('color_map') or '#555', fill_opacity=0.9,
                popup=f"{row.get('cadena','')}: {row.get('nombre','')}"
            ).add_to(layer_gym)
        layer_gym.add_to(m)
    valor_key = 'Score' if modo_color == 'score' else 'costo_total'
    for dorm in sorted(df_filtrado['Dormitorios'].dropna().unique()):
        capa_name = f'{int(dorm)} Dormitorios'
        if capa_name not in capas_depto:
            continue
        df_d = df_filtrado[df_filtrado['Dormitorios'] == dorm].copy()
        if df_d.empty:
            continue
        gdf_d = clean_gdf(gpd.GeoDataFrame(df_d, geometry=df_d.geometry, crs="EPSG:4326"))
        fields = [f for f in TOOLTIP_FIELDS if f in gdf_d.columns]
        folium.GeoJson(
            gdf_d.to_json(), name=capa_name,
            marker=folium.CircleMarker(radius=max(4, 4+int(dorm)), fill=True,
                                        fill_opacity=0.75, color='black', weight=1),
            style_function=lambda x, vk=valor_key: {'fillColor': get_color(x['properties'].get(vk), modo_color)},
            tooltip=folium.GeoJsonTooltip(fields=fields,
                aliases=[f.replace('_',' ').capitalize()+':' for f in fields]),
            show=True
        ).add_to(m)
    for coch in sorted(df_filtrado['Cocheras'].fillna(0).astype(int).unique()):
        if coch == 0:
            continue
        capa_name = f'{int(coch)} Cochera(s)'
        if capa_name not in capas_depto:
            continue
        df_c = df_filtrado[df_filtrado['Cocheras'].fillna(0).astype(int) == coch].copy()
        if df_c.empty:
            continue
        gdf_c = clean_gdf(gpd.GeoDataFrame(df_c, geometry=df_c.geometry, crs="EPSG:4326"))
        fields = [f for f in TOOLTIP_FIELDS if f in gdf_c.columns]
        folium.GeoJson(
            gdf_c.to_json(), name=capa_name,
            marker=folium.CircleMarker(radius=7, fill=True, fill_opacity=0.85, color='gold', weight=2.5),
            style_function=lambda x, vk=valor_key: {'fillColor': get_color(x['properties'].get(vk), modo_color)},
            tooltip=folium.GeoJsonTooltip(fields=fields,
                aliases=[f.replace('_',' ').capitalize()+':' for f in fields]),
            show=False
        ).add_to(m)
    return m

def mostrar_estadisticos(df):
    st.subheader("Estadisticos del conjunto filtrado")
    con_score = int(df['Score'].notna().sum()) if 'Score' in df.columns else 0
    col1, col2, col3 = st.columns(3)
    col1.metric("Total propiedades", len(df))
    col2.metric("Con Score", con_score)
    col3.metric("Barrios distintos", df['Barrio'].nunique() if 'Barrio' in df.columns else 0)
    st.markdown("---")
    num_cols = {
        'Score':'Score','costo_total':'Costo Total ($)','Precio':'Precio ($)',
        'Expensas':'Expensas ($)','distancia_m_subte':'Dist. Subte (m)',
        'dist_verde_final':'Dist. Verde (m)','distancia_m_gym':'Dist. Gym (m)',
        'Metros_Totales':'Metros Totales','Metros_Cubiertos':'Metros Cubiertos',
    }
    rows = []
    for col, label in num_cols.items():
        if col in df.columns and df[col].notna().any():
            s = pd.to_numeric(df[col], errors='coerce').dropna()
            rows.append({'Variable':label,'Media':int(round(s.mean())),
                'Mediana':int(round(s.median())),'Min':int(s.min()),'Max':int(s.max()),
                'P25':int(round(s.quantile(0.25))),'P75':int(round(s.quantile(0.75)))})
    if rows:
        st.dataframe(pd.DataFrame(rows).set_index('Variable'), width='stretch')
    if 'Score' in df.columns and df['Score'].notna().any():
        st.markdown("#### Top 10 por Score")
        cols_show = [c for c in ['Score','Barrio','Direccion','Tipo','Precio','Expensas',
                                  'costo_total','Dormitorios','Ambientes','Metros_Totales','URL']
                     if c in df.columns]
        st.dataframe(df.nlargest(10, 'Score')[cols_show], width='stretch')
    if 'Barrio' in df.columns:
        st.markdown("#### Propiedades por Barrio")
        agg = {'Cantidad': ('Barrio','count')}
        if 'Score' in df.columns:
            agg['Score medio'] = ('Score', lambda x: int(round(pd.to_numeric(x, errors='coerce').mean())))
        if 'costo_total' in df.columns:
            agg['Costo mediano'] = ('costo_total', lambda x: int(round(pd.to_numeric(x, errors='coerce').median())))
        st.dataframe(df.groupby('Barrio').agg(**agg).sort_values('Cantidad', ascending=False), width='stretch')

def mostrar_login():
    _, col, _ = st.columns([1, 2, 1])
    with col:
        st.markdown("## Iniciar sesion")
        st.markdown("Ingresa usuario y contrasena para acceder a tus datos.")
        with st.form("login_form", clear_on_submit=False):
            usuario  = st.text_input("Usuario", placeholder="ej: manuel")
            password = st.text_input("Contrasena", type="password", placeholder="...")
            submitted = st.form_submit_button("Entrar")
        if submitted:
            if not usuario or not password:
                st.error("Completa usuario y contrasena.")
            else:
                perfil, error = verificar_credenciales(usuario, password)
                if error:
                    st.error(error)
                else:
                    st.session_state["logged_in"] = True
                    st.session_state["user"]      = usuario
                    st.session_state["perfil"]    = perfil
                    st.rerun()

def mostrar_app():
    perfil_sel = st.session_state["perfil"]
    st.markdown("""
        <style>
        .block-container { max-width: 100% !important; padding: 1rem 2rem !important; }
        </style>
    """, unsafe_allow_html=True)
    st.title("Mapa Interactivo de Departamentos - CABA")
    barrios, ev, lineas_subte, estaciones, gyms = cargar_shapes()
    with st.sidebar:
        st.header("Configuracion")
        st.caption(f"Usuario: {st.session_state['user']} | Perfil: {perfil_sel}")
        if st.button("Cerrar sesion"):
            st.session_state.clear()
            st.rerun()
        st.markdown("---")
        df_raw = cargar_departamentos(perfil_sel)
        if df_raw is None:
            st.error(f"No existe archivo para el perfil '{perfil_sel}'.")
            st.stop()
        st.subheader("Barrios")
        barrios_disp = sorted(df_raw['Barrio'].dropna().unique()) if 'Barrio' in df_raw.columns else []
        barrios_sel  = st.multiselect("Mostrar barrios:", barrios_disp, default=barrios_disp)
        st.markdown("---")
        st.subheader("Filtros numericos")
        def slider_int(label, col, df, step=1000):
            if col not in df.columns or df[col].isna().all():
                return None, None
            s = pd.to_numeric(df[col], errors='coerce').dropna()
            mn, mx = int(s.min()), int(s.max())
            if mn == mx:
                return mn, mx
            return st.slider(label, min_value=mn, max_value=mx, value=(mn, mx), step=step)
        rng_costo = slider_int("Costo Total ($)",  'costo_total',       df_raw, step=10_000)
        rng_score = slider_int("Score",             'Score',             df_raw, step=1)
        rng_subte = slider_int("Dist. Subte (m)",  'distancia_m_subte', df_raw, step=50)
        rng_gym   = slider_int("Dist. Gym (m)",    'distancia_m_gym',   df_raw, step=50)
        rng_verde = slider_int("Dist. Verde (m)",  'dist_verde_final',  df_raw, step=50)
        rng_mt    = slider_int("Metros Totales",   'Metros_Totales',    df_raw, step=5)
        st.markdown("---")
        st.subheader("Tipo de propiedad")
        def multisel_int(label, col, df, fmt=None):
            if col not in df.columns:
                return []
            opts = sorted(pd.to_numeric(df[col], errors='coerce').dropna().astype(int).unique())
            return st.multiselect(label, opts, default=opts, format_func=fmt or str)
        amb_sel  = multisel_int("Ambientes:",   'Ambientes',   df_raw, fmt=lambda x: f"{x} amb.")
        dorm_sel = multisel_int("Dormitorios:", 'Dormitorios', df_raw, fmt=lambda x: f"{x} dorm.")
        coch_opts = sorted(df_raw['Cocheras'].fillna(0).astype(int).unique()) if 'Cocheras' in df_raw.columns else []
        coch_sel = st.multiselect("Cocheras:", coch_opts, default=coch_opts,
                                   format_func=lambda x: f"{x} coch.")
        st.markdown("---")
        st.subheader("Capas externas")
        capas_ext_opts = ['Barrios','Espacios Verdes','Lineas Subte','Estaciones Subte','Gimnasios']
        capas_ext = [c for c in capas_ext_opts
                     if st.checkbox(c, value=(c != 'Gimnasios'), key=f"ext_{c}")]
        st.markdown("---")
        st.subheader("Capas de departamentos")
        dorms_disp = sorted(df_raw['Dormitorios'].dropna().astype(int).unique()) if 'Dormitorios' in df_raw.columns else []
        cochs_disp = [c for c in sorted(df_raw['Cocheras'].fillna(0).astype(int).unique()) if c > 0] if 'Cocheras' in df_raw.columns else []
        capas_depto = []
        for d in dorms_disp:
            lbl = f"{d} Dormitorios"
            if st.checkbox(lbl, value=True, key=f"dorm_{d}"):
                capas_depto.append(lbl)
        for c in cochs_disp:
            lbl = f"{c} Cochera(s)"
            if st.checkbox(lbl, value=False, key=f"coch_{c}"):
                capas_depto.append(lbl)
    df = df_raw.copy()
    if barrios_sel:
        df = df[df['Barrio'].isin(barrios_sel)]
    def aplicar_rng(df, col, rng):
        if rng is None or rng[0] is None:
            return df
        s = pd.to_numeric(df[col], errors='coerce')
        return df[s.isna() | ((s >= rng[0]) & (s <= rng[1]))]
    df = aplicar_rng(df, 'costo_total',      rng_costo)
    df = aplicar_rng(df, 'Score',             rng_score)
    df = aplicar_rng(df, 'distancia_m_subte', rng_subte)
    df = aplicar_rng(df, 'distancia_m_gym',   rng_gym)
    df = aplicar_rng(df, 'dist_verde_final',  rng_verde)
    df = aplicar_rng(df, 'Metros_Totales',    rng_mt)
    if amb_sel  and 'Ambientes'   in df.columns:
        df = df[pd.to_numeric(df['Ambientes'], errors='coerce').isin(amb_sel)]
    if dorm_sel and 'Dormitorios' in df.columns:
        df = df[pd.to_numeric(df['Dormitorios'], errors='coerce').isin(dorm_sel)]
    if coch_sel and 'Cocheras'    in df.columns:
        df = df[df['Cocheras'].fillna(0).astype(int).isin(coch_sel)]
    st.caption(f"{len(df)} propiedades | perfil: {perfil_sel}")
    tab_mapa, tab_stats, tab_tabla = st.tabs(["Mapa", "Estadisticos", "Tabla"])
    with tab_mapa:
        if df.empty:
            st.warning("No hay propiedades con los filtros seleccionados.")
        else:
            modo_color_ui = st.radio(
                "Colorear puntos por:", ['Score', 'Precio (costo total)'],
                index=0, horizontal=True, key='modo_color_mapa'
            )
            modo_color_key = 'score' if modo_color_ui == 'Score' else 'precio'
            mapa = construir_mapa(df, barrios, ev, lineas_subte, estaciones, gyms,
                                   modo_color_key, capas_depto, capas_ext)
            st_folium(mapa, width="100%", height=680, returned_objects=[])
            with st.expander("Leyenda de colores"):
                if modo_color_key == 'score':
                    labels, colors, titulo = ['0-20','20-40','40-60','60-80','80-100'], COLORS_SCORE, "Score"
                else:
                    labels, colors, titulo = ['<300k','300-400k','400-500k','500-600k','600-700k','700-800k','>800k'], COLORS_PRECIO, "Costo Total ($)"
                html = f"<b>{titulo}</b><br>" + "".join(
                    f'<span style="background:{c};display:inline-block;width:18px;height:18px;margin-right:6px;border-radius:3px;vertical-align:middle"></span>{l}<br>'
                    for c, l in zip(colors, labels)
                )
                st.markdown(html, unsafe_allow_html=True)
                st.markdown("Tamano: crece con dormitorios | Borde dorado: cochera")
    with tab_stats:
        if df.empty:
            st.warning("No hay propiedades con los filtros seleccionados.")
        else:
            mostrar_estadisticos(df)
    with tab_tabla:
        if df.empty:
            st.warning("No hay propiedades con los filtros seleccionados.")
        else:
            cols_tabla = [c for c in [
                'Score','Barrio','Direccion','Tipo','Precio','Expensas','costo_total',
                'Dormitorios','Ambientes','Cocheras','Metros_Totales','Metros_Cubiertos',
                'distancia_m_subte','distancia_m_gym','dist_verde_final','URL'
            ] if c in df.columns]
            df_tabla = df[cols_tabla].copy()
            if 'Score' in df_tabla.columns:
                df_tabla = df_tabla.sort_values('Score', ascending=False, na_position='last')
            st.dataframe(df_tabla, width='stretch', height=600)
            st.download_button("Descargar CSV filtrado",
                data=df_tabla.to_csv(index=False).encode('utf-8'),
                file_name=f"propiedades_{perfil_sel}_filtrado.csv", mime='text/csv')

# ENTRY POINT: login o app, nunca los dos a la vez
if not st.session_state.get("logged_in", False):
    mostrar_login()
else:
    mostrar_app()