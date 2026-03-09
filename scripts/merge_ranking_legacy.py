"""
Script one-off: cruza REVISION y FECHA_DETECCION del archivo legacy
(outputs/ranking_MANUEL.xlsx) con el ranking actual (perfiles/MANUEL/ranking.xlsx)
y escribe el resultado en perfiles/MANUEL/.
"""
import pathlib
import pandas as pd

BASE_PATH = pathlib.Path(__file__).parent.parent
PERFILES_DIR = BASE_PATH / "perfiles"
OUTPUTS_LEGACY = BASE_PATH / "outputs"
PERFIL = "MANUEL"

def _txt_norm(v):
    if pd.isna(v):
        return ""
    return " ".join(str(v).lower().strip().split())

def _precio_norm(v):
    if pd.isna(v):
        return ""
    try:
        return str(int(float(v)))
    except Exception:
        return _txt_norm(v)

def _desc_row(df):
    if "Descripcion" in df.columns:
        return df["Descripcion"].astype(str)
    if "Titulo" in df.columns and "Descripcion_Breve" in df.columns:
        return (df["Titulo"].fillna("").astype(str) + " " + df["Descripcion_Breve"].fillna("").astype(str))
    if "Titulo" in df.columns:
        return df["Titulo"].astype(str)
    if "Descripcion_Breve" in df.columns:
        return df["Descripcion_Breve"].astype(str)
    return pd.Series([""] * len(df), index=df.index)

def _safe_series(df, col):
    if col in df.columns:
        return df[col]
    return pd.Series([""] * len(df), index=df.index)

# 1) Cargar ranking actual (nuevo - puede tener varias hojas)
ranking_nuevo_path = PERFILES_DIR / PERFIL / "ranking.xlsx"
ranking_legacy_path = OUTPUTS_LEGACY / f"ranking_{PERFIL}.xlsx"

if not ranking_legacy_path.exists():
    print(f"ERROR: No existe {ranking_legacy_path}")
    exit(1)

if not ranking_nuevo_path.exists():
    print(f"ERROR: No existe {ranking_nuevo_path}. Ejecutá primero 6_metrics_new.py")
    exit(1)

print("Cargando archivo legacy (REVISION/FECHA)...")
sheets_legacy = pd.read_excel(ranking_legacy_path, sheet_name=None)
datos_previos = []

for _, df_prev in sheets_legacy.items():
    if "Portal" not in df_prev.columns or "Direccion" not in df_prev.columns or "Precio" not in df_prev.columns:
        continue
    df_prev_local = df_prev.copy()
    df_prev_local["join_key"] = (
        df_prev_local["Portal"].map(_txt_norm) + "|" +
        df_prev_local["Direccion"].map(_txt_norm) + "|" +
        _desc_row(df_prev_local).map(_txt_norm) + "|" +
        df_prev_local["Precio"].map(_precio_norm)
    )
    df_prev_local["join_key_nod"] = (
        df_prev_local["Portal"].map(_txt_norm) + "|" +
        df_prev_local["Direccion"].map(_txt_norm) + "|" +
        df_prev_local["Precio"].map(_precio_norm)
    )
    cols = ["join_key", "join_key_nod"]
    if "REVISION" in df_prev_local.columns:
        cols.append("REVISION")
    if "FECHA_DETECCION" in df_prev_local.columns:
        cols.append("FECHA_DETECCION")
    datos_previos.append(df_prev_local[cols])

previos_df = pd.concat(datos_previos, ignore_index=True)
previos_df = previos_df.drop_duplicates(subset="join_key", keep="first")
print(f"  {len(previos_df)} registros previos en legacy")

# 2) Cargar ranking actual y aplicar merge por cada hoja
print("Cargando ranking actual y aplicando cruce...")
sheets_nuevo = pd.read_excel(ranking_nuevo_path, sheet_name=None)
fecha_hoy = pd.Timestamp.now().strftime('%Y-%m-%d')

with pd.ExcelWriter(ranking_nuevo_path, engine='openpyxl') as writer:
    for sheet_name, df in sheets_nuevo.items():
        df = df.copy()
        df["join_key"] = (
            _safe_series(df, "Portal").map(_txt_norm) + "|" +
            _safe_series(df, "Direccion").map(_txt_norm) + "|" +
            _desc_row(df).map(_txt_norm) + "|" +
            _safe_series(df, "Precio").map(_precio_norm)
        )
        df["join_key_nod"] = (
            _safe_series(df, "Portal").map(_txt_norm) + "|" +
            _safe_series(df, "Direccion").map(_txt_norm) + "|" +
            _safe_series(df, "Precio").map(_precio_norm)
        )

        # Merge principal (dropear columnas previas para evitar _x/_y)
        df = df.drop(columns=["REVISION", "FECHA_DETECCION"], errors="ignore")
        merge_cols = [c for c in ["join_key", "REVISION", "FECHA_DETECCION"] if c in previos_df.columns]
        df = df.merge(previos_df[merge_cols], on="join_key", how="left")

        # Fallback join_key_nod
        faltan_rev = df["REVISION"].isna() if "REVISION" in df.columns else pd.Series([True] * len(df), index=df.index)
        faltan_fecha = df["FECHA_DETECCION"].isna() if "FECHA_DETECCION" in df.columns else pd.Series([True] * len(df), index=df.index)
        if (faltan_rev | faltan_fecha).any():
            prev_fb = previos_df.drop_duplicates(subset="join_key_nod", keep="first").set_index("join_key_nod")
            if "REVISION" in df.columns and "REVISION" in prev_fb.columns:
                df.loc[faltan_rev, "REVISION"] = df.loc[faltan_rev, "join_key_nod"].map(prev_fb["REVISION"])
            if "FECHA_DETECCION" in df.columns and "FECHA_DETECCION" in prev_fb.columns:
                df.loc[faltan_fecha, "FECHA_DETECCION"] = df.loc[faltan_fecha, "join_key_nod"].map(prev_fb["FECHA_DETECCION"])

        df["REVISION"] = df["REVISION"] if "REVISION" in df.columns else None
        df["FECHA_DETECCION"] = df.get("FECHA_DETECCION", pd.Series([fecha_hoy] * len(df)))
        df["FECHA_DETECCION"] = pd.to_datetime(df["FECHA_DETECCION"], errors="coerce").dt.strftime("%Y-%m-%d").fillna(fecha_hoy)

        df = df.drop(columns=["join_key", "join_key_nod"], errors="ignore")
        df.to_excel(writer, sheet_name=sheet_name, index=False)
        print(f"  Hoja '{sheet_name}': {len(df)} registros, {df['REVISION'].notna().sum()} con REVISION")

# 3) Actualizar departamentos_enriquecido.xlsx y .geojson con REVISION/FECHA
enriquecido_path = PERFILES_DIR / PERFIL / "departamentos_enriquecido.xlsx"
if enriquecido_path.exists():
    print(f"\nActualizando {enriquecido_path} con REVISION/FECHA...")
    df_enr = pd.read_excel(enriquecido_path)
    all_ranking = pd.concat(list(sheets_nuevo.values()), ignore_index=True)
    df_enr["join_key"] = (
        _safe_series(df_enr, "Portal").map(_txt_norm) + "|" +
        _safe_series(df_enr, "Direccion").map(_txt_norm) + "|" +
        _desc_row(df_enr).map(_txt_norm) + "|" +
        _safe_series(df_enr, "Precio").map(_precio_norm)
    )
    df_enr["join_key_nod"] = (
        _safe_series(df_enr, "Portal").map(_txt_norm) + "|" +
        _safe_series(df_enr, "Direccion").map(_txt_norm) + "|" +
        _safe_series(df_enr, "Precio").map(_precio_norm)
    )
    prev_merge = previos_df.drop_duplicates(subset="join_key", keep="first")
    df_enr = df_enr.drop(columns=["REVISION", "FECHA_DETECCION"], errors="ignore")
    merge_cols = [c for c in ["join_key", "REVISION", "FECHA_DETECCION"] if c in prev_merge.columns]
    df_enr = df_enr.merge(prev_merge[merge_cols], on="join_key", how="left")
    faltan_rev = df_enr["REVISION"].isna()
    faltan_fecha = df_enr["FECHA_DETECCION"].isna()
    if faltan_rev.any() or faltan_fecha.any():
        prev_fb = previos_df.drop_duplicates(subset="join_key_nod", keep="first").set_index("join_key_nod")
        if "REVISION" in df_enr.columns and "REVISION" in prev_fb.columns:
            df_enr.loc[faltan_rev, "REVISION"] = df_enr.loc[faltan_rev, "join_key_nod"].map(prev_fb["REVISION"])
        if "FECHA_DETECCION" in df_enr.columns and "FECHA_DETECCION" in prev_fb.columns:
            df_enr.loc[faltan_fecha, "FECHA_DETECCION"] = df_enr.loc[faltan_fecha, "join_key_nod"].map(prev_fb["FECHA_DETECCION"])

    df_enr["FECHA_DETECCION"] = pd.to_datetime(df_enr["FECHA_DETECCION"], errors="coerce").dt.strftime("%Y-%m-%d").fillna(fecha_hoy)

    df_enr.drop(columns=["join_key", "join_key_nod"], errors="ignore").to_excel(enriquecido_path, index=False)
    print(f"  {df_enr['REVISION'].notna().sum()} revisiones preservadas en enriquecido")

    # GeoJSON: merge por join_key para preservar REVISION/FECHA
    geojson_path = PERFILES_DIR / PERFIL / "departamentos_enriquecido.geojson"
    if geojson_path.exists():
        try:
            import geopandas as gpd
            gdf = gpd.read_file(geojson_path)
            gdf["join_key"] = (
                _safe_series(gdf, "Portal").map(_txt_norm) + "|" +
                _safe_series(gdf, "Direccion").map(_txt_norm) + "|" +
                _desc_row(gdf).map(_txt_norm) + "|" +
                _safe_series(gdf, "Precio").map(_precio_norm)
            )
            rev_fecha = df_enr[["join_key", "REVISION", "FECHA_DETECCION"]].copy() if "join_key" in df_enr.columns else None
            if rev_fecha is not None and "join_key" in gdf.columns:
                gdf = gdf.drop(columns=["REVISION", "FECHA_DETECCION"], errors="ignore")
                gdf = gdf.merge(rev_fecha, on="join_key", how="left")
                gdf = gdf.drop(columns=["join_key"], errors="ignore")
                gdf.to_file(geojson_path, driver="GeoJSON")
                print(f"  GeoJSON actualizado")
        except Exception as e:
            print(f"  GeoJSON no actualizado: {e}")

print("\nCruce completado.")
