"""
Cálculo de métricas de distancia (NetworkX Dijkstra) y scoring.
Port de scripts/6_metrics.py adaptado para leer/escribir en PostgreSQL.
"""
import logging
import pathlib
from datetime import date
from typing import Optional

import numpy as np
import pandas as pd
import geopandas as gpd
import momepy
import networkx as nx
from scipy.spatial import KDTree

from app.core.constants import (
    DIJKSTRA_CUTOFF,
    DIJKSTRA_PENALIZACION_NAN,
    SNAP_WARNING_UMBRAL_M,
    SCORING_WEIGHTS,
    SCORING_VARIABLES,
)
from app.config import settings

logger = logging.getLogger(__name__)

# Rutas de shapes (relativas a la raíz del proyecto)
_SHAPES_DIR = pathlib.Path(settings.shapes_dir)

PROYECCION_UTM = 22185  # UTM 35S — zona de Buenos Aires


# ---------------------------------------------------------------------------
# Carga de capas base (se cachea en memoria al primer uso)
# ---------------------------------------------------------------------------

_graph_cache: Optional[nx.Graph] = None
_shapes_cache: dict = {}


def _load_shapes() -> dict:
    global _shapes_cache
    if _shapes_cache:
        return _shapes_cache

    logger.info("Cargando capas base desde shapes/...")
    barrios = gpd.read_file(_SHAPES_DIR / "barrios.geojson")
    ev = gpd.read_file(_SHAPES_DIR / "espacio_verde_publico.geojson")
    estaciones_subte = gpd.read_file(_SHAPES_DIR / "estaciones_de_subte.geojson")
    gyms = gpd.read_file(_SHAPES_DIR / "gimnasios.geojson")
    callejero = gpd.read_file(_SHAPES_DIR / "callejero.geojson")

    # Filtrar espacios verdes relevantes
    ev = ev[ev["clasificac"].isin(["PARQUE", "JARDÍN BOTANICO", "PLAZA"])].copy()
    ev["cat"] = ev["clasificac"].replace(
        {"JARDÍN BOTANICO": "parque", "PARQUE": "parque", "PLAZA": "plaza"}
    )

    _shapes_cache = {
        "barrios": barrios,
        "ev": ev,
        "estaciones_subte": estaciones_subte,
        "gyms": gyms,
        "callejero": callejero,
    }
    return _shapes_cache


def _get_graph() -> tuple[nx.Graph, np.ndarray, KDTree]:
    global _graph_cache
    shapes = _load_shapes()
    if _graph_cache is None:
        logger.info("Construyendo grafo de callejero (primera vez, puede tardar)...")
        callejero_m = shapes["callejero"].to_crs(epsg=PROYECCION_UTM)
        _graph_cache = momepy.gdf_to_nx(callejero_m, approach="primal")
        logger.info(f"Grafo construido: {_graph_cache.number_of_nodes()} nodos")

    nodos_coords = np.array(list(_graph_cache.nodes))
    tree = KDTree(nodos_coords)
    return _graph_cache, nodos_coords, tree


def _min_dist_or_penalty(d_list: list) -> float:
    return min(d_list) if d_list else float(DIJKSTRA_PENALIZACION_NAN)


# ---------------------------------------------------------------------------
# Cálculo de métricas para un perfil
# ---------------------------------------------------------------------------

def compute_metrics_for_perfil(perfil_id: int) -> int:
    """
    Calcula distancias de red y scoring para todas las propiedades geocodificadas
    del perfil dado. Escribe resultados en la tabla departamentos.
    Retorna cantidad de propiedades procesadas.
    """
    from app.database import SyncSessionLocal
    from app.models.departamento import Departamento
    from sqlalchemy import select

    with SyncSessionLocal() as db:
        result = db.execute(
            select(Departamento).where(
                Departamento.perfil_id == perfil_id,
                Departamento.lat.isnot(None),
                Departamento.lon.isnot(None),
            )
        )
        deptos = result.scalars().all()

    if not deptos:
        logger.warning(f"No hay propiedades geocodificadas para perfil {perfil_id}")
        return 0

    logger.info(f"Calculando métricas para {len(deptos)} propiedades...")

    # Crear GeoDataFrame desde los registros de DB
    df = pd.DataFrame(
        [
            {
                "id": d.id,
                "lat": d.lat,
                "lon": d.lon,
                "Precio": d.precio,
                "Expensas": d.expensas,
                "Ambientes": d.ambientes,
                "Cocheras": d.cocheras or 0,
                "Tipo": d.tipo,
                "Barrio": d.barrio_scrapeado or "",
            }
            for d in deptos
        ]
    )
    gdf = gpd.GeoDataFrame(
        df,
        geometry=gpd.points_from_xy(df["lon"], df["lat"]),
        crs="EPSG:4326",
    )

    shapes = _load_shapes()
    G, nodos_coords, tree = _get_graph()

    # Proyectar departamentos a UTM
    depts_m = gdf.to_crs(epsg=PROYECCION_UTM)
    dept_xy = np.column_stack([depts_m.geometry.x, depts_m.geometry.y])
    _, idx_org = tree.query(dept_xy)
    nodos_org = [tuple(nodos_coords[i]) for i in idx_org]

    # snap_warning si el nodo más cercano está a más de SNAP_WARNING_UMBRAL_M
    dists_snap = np.sqrt(np.sum((dept_xy - nodos_coords[idx_org]) ** 2, axis=1))
    df["snap_warning"] = dists_snap >= SNAP_WARNING_UMBRAL_M

    # --- Capas por centroide (gym, subte) ---
    capas_centroide = {
        "gym": shapes["gyms"].to_crs(epsg=PROYECCION_UTM),
        "subte": shapes["estaciones_subte"].to_crs(epsg=PROYECCION_UTM),
    }

    for label, poi_m in capas_centroide.items():
        logger.info(f"  Ruteo a {label}...")
        _, idx_dest = tree.query(
            np.column_stack([poi_m.geometry.centroid.x, poi_m.geometry.centroid.y])
        )
        nodos_dst = set(tuple(nodos_coords[i]) for i in idx_dest)

        res_dist, res_cant = [], []
        for i, n_start in enumerate(nodos_org):
            dists_dict = nx.single_source_dijkstra_path_length(
                G, n_start, cutoff=DIJKSTRA_CUTOFF, weight="mm_len"
            )
            d_en_red = [d for nodo, d in dists_dict.items() if nodo in nodos_dst]
            res_dist.append(_min_dist_or_penalty(d_en_red))
            res_cant.append(len(d_en_red))

        df[f"distancia_m_{label}"] = (
            pd.Series(res_dist).apply(lambda x: int(np.floor(x)) if pd.notna(x) else pd.NA).astype("Int64")
        )
        df[f"cant_{label}"] = pd.Series(res_cant).fillna(0).astype(int)

    # --- Capas por polígono (parque, plaza) ---
    ev = shapes["ev"]
    capas_poligono = {
        "parque": ev[ev["cat"] == "parque"].to_crs(epsg=PROYECCION_UTM),
        "plaza": ev[ev["cat"] == "plaza"].to_crs(epsg=PROYECCION_UTM),
    }

    for label, poi_m in capas_poligono.items():
        if poi_m.empty:
            df[f"distancia_m_{label}"] = DIJKSTRA_PENALIZACION_NAN
            df[f"cant_{label}"] = 0
            continue

        logger.info(f"  Ruteo a {label} (pre-snap optimizado)...")
        nodos_dst_list = []
        for _, row in poi_m.iterrows():
            boundary = row.geometry.boundary
            pt_ref = boundary.centroid if (boundary is not None and not boundary.is_empty) else row.geometry.centroid
            _, idx_d = tree.query([[pt_ref.x, pt_ref.y]], k=1)
            nodos_dst_list.append(tuple(nodos_coords[idx_d[0]]))
        nodos_dst_set = set(nodos_dst_list)

        res_dist, res_cant = [], []
        for n_start in nodos_org:
            dists_dict = nx.single_source_dijkstra_path_length(
                G, n_start, cutoff=DIJKSTRA_CUTOFF, weight="mm_len"
            )
            d_en_red = [d for nodo, d in dists_dict.items() if nodo in nodos_dst_set]
            res_dist.append(_min_dist_or_penalty(d_en_red))
            res_cant.append(len(d_en_red))

        df[f"distancia_m_{label}"] = (
            pd.Series(res_dist).apply(lambda x: int(np.floor(x)) if pd.notna(x) else pd.NA).astype("Int64")
        )
        df[f"cant_{label}"] = pd.Series(res_cant).fillna(0).astype(int)

    # --- Spatial join para barrio_geo ---
    barrios = shapes["barrios"].copy()
    barrios["nombre"] = barrios["nombre"].str.replace("-", " ").str.title()
    gdf_joined = gpd.sjoin(
        gdf,
        barrios[["nombre", "geometry"]],
        how="left",
        predicate="within",
    )
    df["barrio_geo"] = gdf_joined["nombre"].values

    # --- Scoring ---
    df = _compute_scoring(df)

    # --- Persistir en DB ---
    _write_metrics_to_db(df)

    return len(df)


def _normalizar_inversa(serie: pd.Series) -> pd.Series:
    min_val = serie.min()
    max_val = serie.max()
    if max_val == min_val:
        return pd.Series(50.0, index=serie.index)
    return 100 - ((serie - min_val) / (max_val - min_val)) * 100


def _compute_scoring(df: pd.DataFrame) -> pd.DataFrame:
    """Calcula segmento y score por segmento (port exacto de 6_metrics.py)."""
    df = df.copy()
    df["Cocheras"] = df["Cocheras"].fillna(0).astype(int)
    df["costo_total"] = df["Precio"].fillna(0) + df["Expensas"].fillna(0)
    df["dist_verde_final"] = df[["distancia_m_plaza", "distancia_m_parque"]].min(axis=1)

    # Segmento
    df["segmento"] = df.apply(
        lambda row: f"{int(row['Cocheras'])}coch"
        if row["Cocheras"] > 0
        else (f"{int(row['Ambientes'])}amb" if pd.notna(row.get("Ambientes")) else "sin_datos"),
        axis=1,
    )

    # Aptitud para scoring (deptos sin expensas no se puntúan)
    df["apto_scoring"] = True
    mask_sin_exp = (df["Tipo"] == "Departamento") & (
        df["Expensas"].isna() | (df["Expensas"] == 0)
    )
    df.loc[mask_sin_exp, "apto_scoring"] = False

    for var in SCORING_VARIABLES:
        df[f"{var}_norm"] = np.nan
    df["Score"] = np.nan

    for seg in df["segmento"].unique():
        mask_seg = (df["segmento"] == seg) & df["apto_scoring"]
        if mask_seg.sum() == 0:
            continue

        for var in SCORING_VARIABLES:
            if var not in df.columns:
                continue
            valores = df.loc[mask_seg, var]
            valores_validos = pd.to_numeric(valores, errors="coerce").dropna()
            if len(valores_validos) > 0:
                df.loc[mask_seg & pd.to_numeric(df[var], errors="coerce").notna(), f"{var}_norm"] = (
                    _normalizar_inversa(valores_validos)
                )

        score_comp = pd.DataFrame(index=df[mask_seg].index)
        for var, peso in SCORING_WEIGHTS.items():
            score_comp[var] = df.loc[mask_seg, var] * peso

        score_validos = score_comp.dropna(how="all")
        if len(score_validos) > 0:
            df.loc[score_validos.index, "Score"] = score_validos.sum(axis=1)

    return df


def _write_metrics_to_db(df: pd.DataFrame) -> None:
    """Escribe las columnas de métricas y scoring de vuelta a la DB."""
    from app.database import SyncSessionLocal
    from app.models.departamento import Departamento
    from sqlalchemy import select

    with SyncSessionLocal() as db:
        for _, row in df.iterrows():
            depto = db.execute(
                select(Departamento).where(Departamento.id == int(row["id"]))
            ).scalar_one_or_none()
            if not depto:
                continue

            depto.snap_warning = bool(row.get("snap_warning", False))
            depto.distancia_m_gym = _to_int_or_none(row.get("distancia_m_gym"))
            depto.cant_gym = _to_int_or_none(row.get("cant_gym"))
            depto.distancia_m_subte = _to_int_or_none(row.get("distancia_m_subte"))
            depto.cant_subte = _to_int_or_none(row.get("cant_subte"))
            depto.distancia_m_parque = _to_int_or_none(row.get("distancia_m_parque"))
            depto.cant_parque = _to_int_or_none(row.get("cant_parque"))
            depto.distancia_m_plaza = _to_int_or_none(row.get("distancia_m_plaza"))
            depto.cant_plaza = _to_int_or_none(row.get("cant_plaza"))
            depto.barrio_geo = row.get("barrio_geo") or None
            depto.segmento = row.get("segmento") or None
            depto.score = float(row["Score"]) if pd.notna(row.get("Score")) else None
            depto.apto_scoring = bool(row.get("apto_scoring", True))

        db.commit()


def _to_int_or_none(v) -> Optional[int]:
    try:
        if v is None or (isinstance(v, float) and np.isnan(v)):
            return None
        return int(v)
    except (TypeError, ValueError):
        return None


# ---------------------------------------------------------------------------
# Compute metrics on in-memory items (for staging pipeline)
# ---------------------------------------------------------------------------

def compute_metrics_for_items(items: list[dict]) -> list[dict]:
    """
    Compute distances and scoring for a list of dicts with lat/lon.
    Returns the same list enriched with metric fields.
    Items without lat/lon are returned unchanged.
    """
    geocoded = [i for i in items if i.get("lat") and i.get("lon")]
    if not geocoded:
        logger.warning("No hay items geocodificados para calcular metricas")
        return items

    logger.info(f"Calculando metricas para {len(geocoded)} items geocodificados...")

    df = pd.DataFrame(geocoded)
    # Ensure numeric types
    for col in ("Precio", "Expensas", "Ambientes", "Cocheras"):
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce")
    df["Cocheras"] = df.get("Cocheras", pd.Series(0, index=df.index)).fillna(0).astype(int)
    if "Tipo" not in df.columns:
        df["Tipo"] = ""
    if "Barrio" not in df.columns:
        df["Barrio"] = ""

    gdf = gpd.GeoDataFrame(
        df,
        geometry=gpd.points_from_xy(df["lon"].astype(float), df["lat"].astype(float)),
        crs="EPSG:4326",
    )

    shapes = _load_shapes()
    G, nodos_coords, tree = _get_graph()

    depts_m = gdf.to_crs(epsg=PROYECCION_UTM)
    dept_xy = np.column_stack([depts_m.geometry.x, depts_m.geometry.y])
    _, idx_org = tree.query(dept_xy)
    nodos_org = [tuple(nodos_coords[i]) for i in idx_org]

    dists_snap = np.sqrt(np.sum((dept_xy - nodos_coords[idx_org]) ** 2, axis=1))
    df["snap_warning"] = (dists_snap >= SNAP_WARNING_UMBRAL_M).tolist()

    # Centroid layers (gym, subte)
    capas_centroide = {
        "gym": shapes["gyms"].to_crs(epsg=PROYECCION_UTM),
        "subte": shapes["estaciones_subte"].to_crs(epsg=PROYECCION_UTM),
    }
    for label, poi_m in capas_centroide.items():
        logger.info(f"  Ruteo a {label}...")
        _, idx_dest = tree.query(
            np.column_stack([poi_m.geometry.centroid.x, poi_m.geometry.centroid.y])
        )
        nodos_dst = set(tuple(nodos_coords[i]) for i in idx_dest)

        res_dist, res_cant = [], []
        for n_start in nodos_org:
            dists_dict = nx.single_source_dijkstra_path_length(
                G, n_start, cutoff=DIJKSTRA_CUTOFF, weight="mm_len"
            )
            d_en_red = [d for nodo, d in dists_dict.items() if nodo in nodos_dst]
            res_dist.append(_min_dist_or_penalty(d_en_red))
            res_cant.append(len(d_en_red))

        df[f"distancia_m_{label}"] = (
            pd.Series(res_dist).apply(lambda x: int(np.floor(x)) if pd.notna(x) else pd.NA).astype("Int64")
        )
        df[f"cant_{label}"] = pd.Series(res_cant).fillna(0).astype(int)

    # Polygon layers (parque, plaza)
    ev = shapes["ev"]
    capas_poligono = {
        "parque": ev[ev["cat"] == "parque"].to_crs(epsg=PROYECCION_UTM),
        "plaza": ev[ev["cat"] == "plaza"].to_crs(epsg=PROYECCION_UTM),
    }
    for label, poi_m in capas_poligono.items():
        if poi_m.empty:
            df[f"distancia_m_{label}"] = DIJKSTRA_PENALIZACION_NAN
            df[f"cant_{label}"] = 0
            continue

        logger.info(f"  Ruteo a {label}...")
        nodos_dst_list = []
        for _, row in poi_m.iterrows():
            boundary = row.geometry.boundary
            pt_ref = boundary.centroid if (boundary is not None and not boundary.is_empty) else row.geometry.centroid
            _, idx_d = tree.query([[pt_ref.x, pt_ref.y]], k=1)
            nodos_dst_list.append(tuple(nodos_coords[idx_d[0]]))
        nodos_dst_set = set(nodos_dst_list)

        res_dist, res_cant = [], []
        for n_start in nodos_org:
            dists_dict = nx.single_source_dijkstra_path_length(
                G, n_start, cutoff=DIJKSTRA_CUTOFF, weight="mm_len"
            )
            d_en_red = [d for nodo, d in dists_dict.items() if nodo in nodos_dst_set]
            res_dist.append(_min_dist_or_penalty(d_en_red))
            res_cant.append(len(d_en_red))

        df[f"distancia_m_{label}"] = (
            pd.Series(res_dist).apply(lambda x: int(np.floor(x)) if pd.notna(x) else pd.NA).astype("Int64")
        )
        df[f"cant_{label}"] = pd.Series(res_cant).fillna(0).astype(int)

    # Spatial join for barrio_geo
    barrios = shapes["barrios"].copy()
    barrios["nombre"] = barrios["nombre"].str.replace("-", " ").str.title()
    gdf_joined = gpd.sjoin(
        gdf,
        barrios[["nombre", "geometry"]],
        how="left",
        predicate="within",
    )
    df["barrio_geo"] = gdf_joined["nombre"].values

    # Scoring
    df = _compute_scoring(df)

    # Write metrics back into the items list
    metric_cols = [
        "snap_warning", "barrio_geo", "segmento", "Score", "apto_scoring",
        "distancia_m_gym", "cant_gym", "distancia_m_subte", "cant_subte",
        "distancia_m_parque", "cant_parque", "distancia_m_plaza", "cant_plaza",
    ]
    geocoded_idx = 0
    for item in items:
        if not (item.get("lat") and item.get("lon")):
            continue
        if geocoded_idx >= len(df):
            break
        row = df.iloc[geocoded_idx]
        for col in metric_cols:
            val = row.get(col)
            if val is not None and not (isinstance(val, float) and np.isnan(val)):
                if isinstance(val, (np.integer, np.int64)):
                    item[col] = int(val)
                elif isinstance(val, (np.floating, np.float64)):
                    item[col] = float(val)
                elif isinstance(val, np.bool_):
                    item[col] = bool(val)
                else:
                    item[col] = val
        geocoded_idx += 1

    return items


def compute_metrics_and_commit(
    run_id: int,
    perfil_id: int,
    progress_callback=None,
) -> int:
    """
    Compute metrics on staged items, then commit everything to departamentos.
    This is the final step of the pipeline.
    """
    from app.services.scraping_service import load_staging, save_staging, delete_staging, _mark_inactive
    from app.services.consolidation_service import upsert_items_sync

    def log(msg: str) -> None:
        logger.info(msg)
        if progress_callback:
            progress_callback(msg)

    items = load_staging(run_id)
    if not items:
        log("No hay items en staging para calcular metricas.")
        return 0

    geocoded_count = sum(1 for i in items if i.get("lat") and i.get("lon"))
    log(f"Calculando metricas para {geocoded_count} items geocodificados de {len(items)} totales...")

    # Compute metrics in memory
    items = compute_metrics_for_items(items)
    save_staging(run_id, items)
    log("Metricas calculadas. Commitiendo a la base de datos...")

    # Now commit: upsert all items to departamentos
    inserted, updated = upsert_items_sync(
        items=items,
        perfil_id=perfil_id,
        run_id=run_id,
    )
    log(f"Commit: {inserted} nuevos, {updated} actualizados")

    # Mark inactive properties not seen today
    _mark_inactive(perfil_id)
    log("Propiedades inactivas marcadas.")

    # Clean up staging file
    delete_staging(run_id)

    return len(items)
