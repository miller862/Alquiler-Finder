"""
Lógica de upsert y geocodificación.
Port de scripts/4_consolidar.py adaptado para PostgreSQL.

La deduplicación ya no usa pandas drop_duplicates — usa un upsert
en 2 pasadas (URL → dedup_key) que preserva el historial completo.
"""
import logging
from datetime import date
from typing import Optional

from app.core.normalization import url_normalize, build_dedup_key, normalize_address, precio_norm_value

logger = logging.getLogger(__name__)


def _parse_int(v) -> Optional[int]:
    """Convierte un valor de scraping (puede ser string vacío) a int o None."""
    if v is None or str(v).strip() == "":
        return None
    try:
        return int(str(v).strip())
    except (ValueError, TypeError):
        return None


def _map_item_to_fields(item: dict, perfil_id: int) -> dict:
    """Mapea un dict de scraping a los campos del modelo Departamento."""
    portal = str(item.get("Portal", "")).lower()
    precio = _parse_int(item.get("Precio"))
    direccion = item.get("Direccion", "") or ""

    return {
        "portal": portal,
        "perfil_id": perfil_id,
        "barrio_scrapeado": item.get("Barrio"),
        "tipo": item.get("Tipo"),
        "titulo": item.get("Titulo") or None,
        "descripcion_breve": item.get("Descripcion_Breve") or None,
        "direccion": direccion or None,
        "precio": precio,
        "expensas": _parse_int(item.get("Expensas")),
        "metros_totales": _parse_int(item.get("Metros_Totales")),
        "metros_cubiertos": _parse_int(item.get("Metros_Cubiertos")),
        "ambientes": _parse_int(item.get("Ambientes")),
        "dormitorios": _parse_int(item.get("Dormitorios")),
        "banios": _parse_int(item.get("Baños")),
        "cocheras": _parse_int(item.get("Cocheras")) or 0,
        "url": item.get("URL") or None,
        "url_norm": url_normalize(item.get("URL")),
        "direccion_norm": normalize_address(direccion),
        "dedup_key": build_dedup_key(portal, direccion, precio),
        "etiqueta_destacado": item.get("Etiqueta_Destacado") or None,
        "bajo_precio": bool(item.get("Bajo_Precio", False)),
        "porcentaje_rebaja": item.get("Porcentaje_Rebaja") or None,
        "fecha_publicacion": item.get("Fecha_Publicacion") or None,
        "visto_estado": item.get("Visto_Estado") or None,
        "visitas_count": _parse_int(item.get("Visitas_Count")),
        "inmobiliaria": item.get("Inmobiliaria") or None,
        "antiguedad": _parse_int(item.get("Antiguedad")),
        "activo": True,
        "ultima_vez_visto": date.today(),
        "primera_vez_visto": date.today(),
        "fecha_deteccion": date.today(),
        "veces_visto": 1,
    }


def upsert_items_sync(
    items: list[dict],
    perfil_id: int,
    run_id: int,
) -> tuple[int, int]:
    """
    Upsert sincrónico de items scrapeados en la base de datos.
    Retorna (total_inserted, total_updated).

    Estrategia de 2 pasadas:
    1. Buscar por url_norm (más fiable, mismo portal mismo día)
    2. Si no matchea: buscar por dedup_key (portal|dir_norm|precio_norm)
    3. Si tampoco: INSERT nuevo
    """
    from app.database import SyncSessionLocal
    from app.models.departamento import Departamento
    from sqlalchemy import select, update

    today = date.today()
    inserted = 0
    updated = 0

    with SyncSessionLocal() as db:
        for item in items:
            fields = _map_item_to_fields(item, perfil_id)
            url_n = fields.get("url_norm", "")
            dedup_k = fields.get("dedup_key", "")

            existing = None

            # Pasada 1: buscar por url_norm
            if url_n:
                result = db.execute(
                    select(Departamento).where(Departamento.url_norm == url_n)
                )
                existing = result.scalar_one_or_none()

            # Pasada 2: buscar por dedup_key
            if existing is None and dedup_k:
                result = db.execute(
                    select(Departamento).where(Departamento.dedup_key == dedup_k)
                )
                existing = result.scalar_one_or_none()

            if existing:
                # UPDATE — preservar revision, fecha_deteccion y primera_vez_visto
                existing.activo = True
                existing.ultima_vez_visto = today
                existing.veces_visto = (existing.veces_visto or 0) + 1
                # Actualizar precio/expensas (pueden cambiar entre scrapes)
                if fields.get("precio") is not None:
                    existing.precio = fields["precio"]
                if fields.get("expensas") is not None:
                    existing.expensas = fields["expensas"]
                # Si teníamos URL vieja y ahora tenemos una nueva, actualizar
                if url_n and not existing.url_norm:
                    existing.url = fields.get("url")
                    existing.url_norm = url_n
                db.add(existing)
                updated += 1
            else:
                # INSERT nuevo
                depto = Departamento(**fields)
                db.add(depto)
                inserted += 1

        db.commit()

    return inserted, updated


def geocodificar_pendientes_sync(perfil_id: int, api_key: str) -> int:
    """
    Geocodifica con Google Maps las propiedades del perfil sin lat/lon.
    Retorna cantidad geocodificada.
    Función sincrónica — llamar desde background task.
    """
    import googlemaps
    import re
    from app.database import SyncSessionLocal
    from app.models.departamento import Departamento
    from sqlalchemy import select

    gmaps = googlemaps.Client(key=api_key)
    geocodificadas = 0

    with SyncSessionLocal() as db:
        result = db.execute(
            select(Departamento).where(
                Departamento.perfil_id == perfil_id,
                Departamento.lat.is_(None),
                Departamento.direccion.isnot(None),
            )
        )
        pendientes = result.scalars().all()

        logger.info(f"Geocodificando {len(pendientes)} propiedades del perfil {perfil_id}...")

        for depto in pendientes:
            addr = depto.direccion or ""
            addr_clean = re.sub(r"C\.A\.B\.A|CABA| - ", " ", addr, flags=re.I)
            full_address = f"{addr_clean}, Ciudad Autónoma de Buenos Aires, Argentina"

            try:
                result_geo = gmaps.geocode(full_address)
                if result_geo:
                    loc = result_geo[0]["geometry"]["location"]
                    depto.lat = loc["lat"]
                    depto.lon = loc["lng"]
                    geocodificadas += 1
            except Exception as e:
                logger.warning(f"Error geocodificando {addr}: {e}")

            if geocodificadas % 50 == 0 and geocodificadas > 0:
                db.commit()
                logger.info(f"  Checkpoint: {geocodificadas}/{len(pendientes)} geocodificadas")

        db.commit()

    logger.info(f"Geocodificación completada: {geocodificadas} propiedades")
    return geocodificadas
