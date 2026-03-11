"""
Script de migración one-time: Excel/JSON histórico → PostgreSQL.

Uso:
    python -m app.services.migration_service

O desde Python:
    from app.services.migration_service import run_migration
    run_migration()
"""
import json
import logging
import pathlib
from typing import Optional

import pandas as pd

from app.core.security import hash_password
from app.core.normalization import url_normalize, build_dedup_key, normalize_address, precio_norm_value

logger = logging.getLogger(__name__)

BASE_DIR = pathlib.Path(__file__).parent.parent.parent  # raíz del proyecto
CONFIG_PATH = BASE_DIR / "perfiles" / "configuraciones.json"
PERFILES_DIR = BASE_DIR / "perfiles"


def _load_config() -> list[dict]:
    if not CONFIG_PATH.exists():
        raise FileNotFoundError(f"No encontrado: {CONFIG_PATH}")
    with open(CONFIG_PATH, encoding="utf-8") as f:
        return json.load(f)


def migrate_users_and_perfiles(db) -> dict[str, int]:
    """
    Crea usuarios y perfiles desde configuraciones.json.
    Retorna {nombre_perfil: perfil_id}.
    """
    from app.models.user import User
    from app.models.perfil import Perfil
    from sqlalchemy import select

    configs = _load_config()
    perfil_id_map: dict[str, int] = {}

    for cfg in configs:
        username = (cfg.get("usuario") or "").strip().lower()
        plain_password = cfg.get("password", "changeme")
        is_admin = bool(cfg.get("es_global", False))
        nombre = cfg.get("nombre", "SIN_NOMBRE").upper()

        if not username:
            logger.warning(f"Config sin usuario, saltando: {nombre}")
            continue

        if cfg.get("es_global"):
            continue  # global no es un perfil de búsqueda

        # Upsert usuario — si ya existe, no tocar su password
        existing_user = db.execute(
            select(User).where(User.username == username)
        ).scalar_one_or_none()

        if existing_user:
            user = existing_user
            logger.info(f"  Usuario ya existe: {username}")
        else:
            user = User(
                username=username,
                hashed_password=hash_password(plain_password),
                is_admin=is_admin,
            )
            db.add(user)
            db.flush()
            logger.info(f"  Usuario creado: {username}")

        # Crear perfil
        existing_perfil = db.execute(
            select(Perfil).where(Perfil.user_id == user.id, Perfil.nombre == nombre)
        ).scalar_one_or_none()

        if existing_perfil:
            logger.info(f"  Perfil ya existe: {nombre}")
            perfil_id_map[nombre] = existing_perfil.id
            continue

        precio = cfg.get("precio", {})
        amb = cfg.get("ambientes", {})
        dorm = cfg.get("dormitorios", {})
        sup = cfg.get("superficie", {})
        extras = cfg.get("extras", {})

        perfil = Perfil(
            user_id=user.id,
            nombre=nombre,
            operacion=cfg.get("operacion", "alquiler"),
            barrios=cfg.get("barrios", []),
            tipos=cfg.get("tipos", []),
            precio_min=precio.get("min"),
            precio_max=precio.get("max"),
            precio_moneda=precio.get("moneda", "pesos"),
            amb_min=amb.get("min"),
            amb_max=amb.get("max"),
            dorm_min=dorm.get("min"),
            dorm_max=dorm.get("max"),
            superficie_cubierta_min=sup.get("cubierta_min"),
            balcon=bool(extras.get("balcon", False)),
            expensas_max=extras.get("expensas_max"),
            filtros_exclusion=cfg.get("filtros_exclusion", []),
        )
        db.add(perfil)
        db.flush()
        perfil_id_map[nombre] = perfil.id
        logger.info(f"  Perfil creado: {nombre} (id={perfil.id})")

    db.commit()
    return perfil_id_map


def migrate_departamentos_from_excel(db, perfil_id_map: dict[str, int]) -> int:
    """
    Migra datos de departamentos_enriquecido.xlsx por perfil a la tabla departamentos.
    Usa los datos enriquecidos (con métricas y scores).
    Retorna total de registros insertados.
    """
    from app.models.departamento import Departamento
    from sqlalchemy import select
    from datetime import date

    total = 0

    # Mapeo de columnas Excel → campos de DB
    COL_MAP = {
        "Portal": "portal",
        "Barrio": "barrio_scrapeado",
        "Tipo": "tipo",
        "Titulo": "titulo",
        "Descripcion_Breve": "descripcion_breve",
        "Direccion": "direccion",
        "Precio": "precio",
        "Expensas": "expensas",
        "Metros_Totales": "metros_totales",
        "Metros_Cubiertos": "metros_cubiertos",
        "Ambientes": "ambientes",
        "Dormitorios": "dormitorios",
        "Baños": "banios",
        "Cocheras": "cocheras",
        "URL": "url",
        "lat": "lat",
        "lon": "lon",
        "Barrio_Geo": "barrio_geo",
        "snap_warning": "snap_warning",
        "distancia_m_subte": "distancia_m_subte",
        "cant_subte": "cant_subte",
        "distancia_m_gym": "distancia_m_gym",
        "cant_gym": "cant_gym",
        "distancia_m_parque": "distancia_m_parque",
        "cant_parque": "cant_parque",
        "distancia_m_plaza": "distancia_m_plaza",
        "cant_plaza": "cant_plaza",
        "segmento": "segmento",
        "Score": "score",
        "apto_scoring": "apto_scoring",
        "REVISION": "revision",
        "FECHA_DETECCION": "fecha_deteccion",
        "Etiqueta_Destacado": "etiqueta_destacado",
        "Inmobiliaria": "inmobiliaria",
        "Fecha_Publicacion": "fecha_publicacion",
        "Visto_Estado": "visto_estado",
        "Visitas_Count": "visitas_count",
        "Antiguedad": "antiguedad",
        "Bajo_Precio": "bajo_precio",
        "Porcentaje_Rebaja": "porcentaje_rebaja",
    }

    for nombre, perfil_id in perfil_id_map.items():
        xlsx_path = PERFILES_DIR / nombre / "departamentos_enriquecido.xlsx"
        if not xlsx_path.exists():
            # Fallback: usar master si no hay enriquecido
            xlsx_path = PERFILES_DIR / nombre / "departamentos_master.xlsx"
            if not xlsx_path.exists():
                logger.warning(f"  Sin datos Excel para perfil {nombre}")
                continue

        logger.info(f"  Migrando {nombre} desde {xlsx_path.name}...")
        df = pd.read_excel(xlsx_path)
        logger.info(f"  {len(df)} registros encontrados en Excel")

        # Filtrar: excluir filas con REVISION que indique baja/descartado
        if "REVISION" in df.columns:
            baja_keywords = ["baja", "descartado", "eliminado"]
            mask = df["REVISION"].apply(
                lambda v: isinstance(v, str) and v.strip().lower() in baja_keywords
            )
            n_excluidos = mask.sum()
            if n_excluidos > 0:
                df = df[~mask]
                logger.info(f"  {n_excluidos} registros excluidos por REVISION (baja/descartado)")

        logger.info(f"  {len(df)} registros a migrar")

        for _, row in df.iterrows():
            portal = str(row.get("Portal", "")).lower()
            precio_raw = row.get("Precio")
            direccion = str(row.get("Direccion", "") or "")
            url_raw = row.get("URL") or None

            # Verificar duplicado por url_norm
            url_n = url_normalize(str(url_raw) if url_raw else "")
            if url_n:
                existing = db.execute(
                    select(Departamento).where(Departamento.url_norm == url_n)
                ).scalar_one_or_none()
                if existing:
                    continue

            fields: dict = {"perfil_id": perfil_id, "activo": True, "veces_visto": 1}

            # Campos mapeados
            for excel_col, db_col in COL_MAP.items():
                val = row.get(excel_col)
                if val is None or (isinstance(val, float) and pd.isna(val)):
                    fields[db_col] = None
                    continue

                # Conversiones de tipo
                if db_col in ("precio", "expensas", "metros_totales", "metros_cubiertos",
                              "ambientes", "dormitorios", "banios", "cocheras",
                              "distancia_m_subte", "cant_subte", "distancia_m_gym", "cant_gym",
                              "distancia_m_parque", "cant_parque", "distancia_m_plaza", "cant_plaza",
                              "visitas_count", "antiguedad"):
                    try:
                        fields[db_col] = int(float(val))
                    except (ValueError, TypeError):
                        fields[db_col] = None
                elif db_col in ("lat", "lon", "score"):
                    try:
                        fields[db_col] = float(val)
                    except (ValueError, TypeError):
                        fields[db_col] = None
                elif db_col in ("snap_warning", "apto_scoring", "bajo_precio"):
                    fields[db_col] = bool(val)
                elif db_col == "fecha_deteccion":
                    try:
                        fields[db_col] = pd.to_datetime(val).date()
                    except Exception:
                        fields[db_col] = date.today()
                elif db_col == "portal":
                    fields[db_col] = str(val).lower()
                else:
                    fields[db_col] = str(val) if val else None

            # Calcular claves de normalización
            fields["url_norm"] = url_n or ""
            fields["direccion_norm"] = normalize_address(direccion)
            fields["dedup_key"] = build_dedup_key(
                fields.get("portal", ""), direccion, fields.get("precio")
            )

            # Fechas de historial
            fecha_det = fields.get("fecha_deteccion")
            fields["primera_vez_visto"] = fecha_det or date.today()
            fields["ultima_vez_visto"] = fecha_det or date.today()

            depto = Departamento(**fields)
            db.add(depto)
            total += 1

            if total % 200 == 0:
                db.commit()
                logger.info(f"    {total} registros migrados...")

        db.commit()
        logger.info(f"  {nombre}: migración completa")

    return total


def run_migration() -> None:
    """Ejecuta la migración completa."""
    from app.database import SyncSessionLocal

    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
    logger.info("=== Iniciando migración ===")

    with SyncSessionLocal() as db:
        logger.info("1. Migrando usuarios y perfiles...")
        perfil_id_map = migrate_users_and_perfiles(db)
        logger.info(f"   Perfiles: {perfil_id_map}")

        logger.info("2. Migrando departamentos desde Excel...")
        total = migrate_departamentos_from_excel(db, perfil_id_map)
        logger.info(f"   Total migrado: {total} registros")

    logger.info("=== Migración completada ===")
    logger.info(
        "IMPORTANTE: Agrega perfiles/configuraciones.json al .gitignore "
        "y elimina el archivo del repositorio."
    )


if __name__ == "__main__":
    run_migration()
