#%% [1] Imports + paths
import os
from pathlib import Path
import zipfile

import geopandas as gpd
from shapely.geometry import (
    Point, LineString, Polygon,
    MultiPoint, MultiLineString, MultiPolygon,
    GeometryCollection
)

from lxml import etree  # viene en muchos entornos; si no, ver nota al final

BASE = Path.cwd()
os.chdir(BASE)

kmz_path = next(BASE.glob("*.kmz"))

extract_dir = BASE / "_kmz"
extract_dir.mkdir(exist_ok=True)

#%% [2] Extraer KMZ y leer KML como texto
with zipfile.ZipFile(kmz_path, "r") as z:
    z.extractall(extract_dir)

kml_path = next(extract_dir.rglob("*.kml"))
kml_bytes = kml_path.read_bytes()

root = etree.fromstring(kml_bytes)

# Namespace KML (suele ser este)
ns = {"kml": "http://www.opengis.net/kml/2.2"}

#%% [3] Helpers de parseo
def _text(node, xpath):
    el = node.find(xpath, namespaces=ns)
    return el.text.strip() if el is not None and el.text is not None else None

def _parse_coords(coord_text):
    """
    coord_text: 'lon,lat,alt lon,lat,alt ...' o con saltos de línea
    devuelve lista [(lon, lat), ...]
    """
    if not coord_text:
        return []
    parts = coord_text.replace("\n", " ").replace("\t", " ").split()
    out = []
    for p in parts:
        vals = p.split(",")
        if len(vals) >= 2:
            lon = float(vals[0])
            lat = float(vals[1])
            out.append((lon, lat))
    return out

def _parse_extended_data(pm):
    """
    Extrae ExtendedData/Data(name)/value y SchemaData/SimpleData(name).
    """
    data = {}

    # ExtendedData/Data
    for d in pm.findall(".//kml:ExtendedData/kml:Data", namespaces=ns):
        key = d.get("name")
        val = _text(d, "./kml:value")
        if key:
            data[key] = val

    # ExtendedData/SchemaData/SimpleData
    for sd in pm.findall(".//kml:ExtendedData//kml:SimpleData", namespaces=ns):
        key = sd.get("name")
        val = sd.text.strip() if sd.text else None
        if key:
            data[key] = val

    return data

def _geom_point(node):
    coords = _parse_coords(_text(node, ".//kml:coordinates"))
    return Point(coords[0]) if coords else None

def _geom_linestring(node):
    coords = _parse_coords(_text(node, ".//kml:coordinates"))
    return LineString(coords) if len(coords) >= 2 else None

def _geom_polygon(node):
    outer = _parse_coords(_text(node, ".//kml:outerBoundaryIs//kml:LinearRing//kml:coordinates"))
    if len(outer) < 3:
        return None
    holes = []
    for inner in node.findall(".//kml:innerBoundaryIs//kml:LinearRing//kml:coordinates", namespaces=ns):
        ring = _parse_coords(inner.text if inner is not None else None)
        if len(ring) >= 3:
            holes.append(ring)
    return Polygon(outer, holes if holes else None)

def _parse_geometry(pm):
    """
    Devuelve una geometría Shapely para el Placemark:
    Point / LineString / Polygon / MultiGeometry
    """
    # Point
    p = pm.find(".//kml:Point", namespaces=ns)
    if p is not None:
        return _geom_point(p)

    # LineString
    ls = pm.find(".//kml:LineString", namespaces=ns)
    if ls is not None:
        return _geom_linestring(ls)

    # Polygon
    pol = pm.find(".//kml:Polygon", namespaces=ns)
    if pol is not None:
        return _geom_polygon(pol)

    # MultiGeometry
    mg = pm.find(".//kml:MultiGeometry", namespaces=ns)
    if mg is not None:
        geoms = []
        for p2 in mg.findall("./kml:Point", namespaces=ns):
            g = _geom_point(p2)
            if g is not None: geoms.append(g)
        for ls2 in mg.findall("./kml:LineString", namespaces=ns):
            g = _geom_linestring(ls2)
            if g is not None: geoms.append(g)
        for pol2 in mg.findall("./kml:Polygon", namespaces=ns):
            g = _geom_polygon(pol2)
            if g is not None: geoms.append(g)

        # compactar en Multi* si aplica
        pts = [g for g in geoms if g.geom_type == "Point"]
        lss = [g for g in geoms if g.geom_type == "LineString"]
        polys = [g for g in geoms if g.geom_type == "Polygon"]
        others = [g for g in geoms if g.geom_type not in ("Point","LineString","Polygon")]

        packed = []
        if pts: packed.append(MultiPoint(pts) if len(pts) > 1 else pts[0])
        if lss: packed.append(MultiLineString(lss) if len(lss) > 1 else lss[0])
        if polys: packed.append(MultiPolygon(polys) if len(polys) > 1 else polys[0])
        packed += others

        if not packed:
            return None
        if len(packed) == 1:
            return packed[0]
        return GeometryCollection(packed)

    return None

#%% [4] Recorrer folders (layers) y placemarks, armar records
records = []

def walk_container(container_node, current_layer=None):
    """
    container_node: Document o Folder
    current_layer: nombre del folder "selector" de Google My Maps
    """
    # si es Folder, actualizar layer con su nombre
    folder_name = _text(container_node, "./kml:name")
    layer = folder_name if folder_name else current_layer

    # placemarks directos dentro del container
    for pm in container_node.findall("./kml:Placemark", namespaces=ns):
        geom = _parse_geometry(pm)
        if geom is None:
            continue

        rec = {
            "__layer__": layer,
            "name": _text(pm, "./kml:name"),
            "description": _text(pm, "./kml:description"),
            "geometry": geom
        }
        rec.update(_parse_extended_data(pm))
        records.append(rec)

    # subfolders
    for subf in container_node.findall("./kml:Folder", namespaces=ns):
        walk_container(subf, layer)

# arrancar desde Document (o root)
doc = root.find(".//kml:Document", namespaces=ns)
if doc is None:
    # algunos KML no tienen Document explícito; usar root
    doc = root

walk_container(doc, current_layer=None)

len(records), (records[0].keys() if records else None)

#%% [5] GeoDataFrame final (EPSG:4326)
gdf_all = gpd.GeoDataFrame(records, geometry="geometry", crs="EPSG:4326")
gdf_all


#%% [7] Mejoras de parseo MyMaps: limpiar columnas + rellenar campos desde description
import re
import pandas as pd

def clean_colname(c: str) -> str:
    if c is None:
        return c
    # saca BOM y espacios raros
    c = c.replace("\ufeff", "").replace("\u200b", "").strip()
    # normaliza espacios múltiples
    c = re.sub(r"\s+", " ", c)
    return c

# 1) Limpiar nombres de columnas y eliminar duplicados por nombres raros
gdf_all = gdf_all.rename(columns={c: clean_colname(str(c)) for c in gdf_all.columns})

# si quedaron columnas duplicadas tras limpiar (raro pero pasa), quedate con la primera
if len(set(gdf_all.columns)) != len(gdf_all.columns):
    gdf_all = gdf_all.loc[:, ~pd.Index(gdf_all.columns).duplicated(keep="first")]

# 2) Asegurar columnas objetivo
for col in ["TIPO PLAN", "DIRECCION", "LOCALIDAD"]:
    if col not in gdf_all.columns:
        gdf_all[col] = None

# 3) Parser simple: saca "TIPO PLAN:", "DIRECCION:", "LOCALIDAD:" desde description HTML
def extract_fields_from_description(desc: str):
    if not isinstance(desc, str) or not desc.strip():
        return {}

    # quitar tags de imagen pero conservar el src aparte si lo querés
    desc_no_img = re.sub(r"<img[^>]*>", " ", desc, flags=re.I)

    # normalizar <br> a saltos
    desc_br = re.sub(r"<br\s*/?>", "\n", desc_no_img, flags=re.I)

    # quitar el resto de tags
    text = re.sub(r"<[^>]+>", " ", desc_br)
    text = re.sub(r"\s+", " ", text).strip()

    # buscar patrones tipo "TIPO PLAN: algo DIRECCION: algo LOCALIDAD: algo"
    out = {}

    def grab(label):
        # captura hasta el próximo label o fin
        m = re.search(
            rf"{label}\s*:\s*(.*?)(?=(TIPO\s*PLAN|DIRECCION|LOCALIDAD)\s*:|$)",
            text,
            flags=re.I,
        )
        if m:
            val = m.group(1).strip()
            return val if val else None
        return None

    out["TIPO PLAN"] = grab("TIPO PLAN")
    out["DIRECCION"] = grab("DIRECCION")
    out["LOCALIDAD"] = grab("LOCALIDAD")
    out["description_text"] = text
    return out

# aplica extracción
tmp = gdf_all["description"].apply(extract_fields_from_description).apply(pd.Series)

# crea description_text si no existía
if "description_text" in tmp.columns:
    gdf_all["description_text"] = tmp["description_text"]

# 4) Rellenar SOLO donde están vacíos / None
for col in ["TIPO PLAN", "DIRECCION", "LOCALIDAD"]:
    if col in tmp.columns:
        gdf_all[col] = gdf_all[col].where(gdf_all[col].notna() & (gdf_all[col].astype(str).str.strip() != ""), tmp[col])

# 5) Extra: sacar image_url desde description o gx_media_links
def extract_first_img_url(desc: str):
    if not isinstance(desc, str):
        return None
    m = re.search(r'<img[^>]+src="([^"]+)"', desc, flags=re.I)
    return m.group(1) if m else None

gdf_all["image_url"] = gdf_all["description"].apply(extract_first_img_url)

# si hay gx_media_links, quedate con eso cuando no haya image_url
if "gx_media_links" in gdf_all.columns:
    gdf_all["image_url"] = gdf_all["image_url"].fillna(gdf_all["gx_media_links"])

# 6) Limpiar columnas basura típicas (opcional)
for junk in ["unnamed (1)"]:
    if junk in gdf_all.columns:
        gdf_all = gdf_all.drop(columns=[junk])

gdf_all.head()


#%% [6] Línea lista para guardar GeoJSON
# gdf_all.to_file("sportclub_unificado.geojson", driver="GeoJSON")