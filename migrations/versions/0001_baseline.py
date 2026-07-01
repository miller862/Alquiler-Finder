"""Baseline: schema ya creado por init_db.py

Revision ID: 0001_baseline
Revises:
Create Date: 2026-03-10
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '0001_baseline'
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("""
        CREATE TABLE IF NOT EXISTS users (
            id SERIAL PRIMARY KEY,
            username VARCHAR(100) NOT NULL UNIQUE,
            hashed_password TEXT NOT NULL,
            is_admin BOOLEAN NOT NULL DEFAULT false,
            created_at TIMESTAMP NOT NULL DEFAULT now(),
            updated_at TIMESTAMP NOT NULL DEFAULT now()
        );
        CREATE INDEX IF NOT EXISTS ix_users_id ON users (id);
        CREATE INDEX IF NOT EXISTS ix_users_username ON users (username);

        CREATE TABLE IF NOT EXISTS perfiles (
            id SERIAL PRIMARY KEY,
            user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            nombre VARCHAR(100) NOT NULL,
            operacion VARCHAR(50) NOT NULL DEFAULT 'alquiler',
            barrios TEXT[] NOT NULL DEFAULT '{}',
            tipos TEXT[] NOT NULL DEFAULT '{}',
            precio_min INTEGER,
            precio_max INTEGER,
            precio_moneda VARCHAR(20) DEFAULT 'pesos',
            amb_min INTEGER,
            amb_max INTEGER,
            dorm_min INTEGER,
            dorm_max INTEGER,
            superficie_cubierta_min INTEGER,
            balcon BOOLEAN DEFAULT false,
            expensas_max INTEGER,
            filtros_exclusion TEXT[] DEFAULT '{}',
            is_active BOOLEAN NOT NULL DEFAULT true,
            created_at TIMESTAMP NOT NULL DEFAULT now(),
            updated_at TIMESTAMP NOT NULL DEFAULT now(),
            CONSTRAINT uq_perfil_user_nombre UNIQUE (user_id, nombre)
        );
        CREATE INDEX IF NOT EXISTS ix_perfiles_id ON perfiles (id);
        CREATE INDEX IF NOT EXISTS ix_perfiles_user_id ON perfiles (user_id);

        CREATE TABLE IF NOT EXISTS departamentos (
            id SERIAL PRIMARY KEY,
            url TEXT UNIQUE,
            url_norm TEXT,
            direccion_norm TEXT,
            dedup_key TEXT,
            portal VARCHAR(50) NOT NULL,
            perfil_id INTEGER REFERENCES perfiles(id) ON DELETE SET NULL,
            barrio_scrapeado VARCHAR(100),
            tipo VARCHAR(50),
            titulo TEXT,
            descripcion_breve TEXT,
            direccion TEXT,
            precio INTEGER,
            expensas INTEGER,
            costo_total INTEGER GENERATED ALWAYS AS (precio + COALESCE(expensas, 0)) STORED,
            metros_totales INTEGER,
            metros_cubiertos INTEGER,
            ambientes INTEGER,
            dormitorios INTEGER,
            banios INTEGER,
            cocheras INTEGER DEFAULT 0,
            etiqueta_destacado TEXT,
            bajo_precio BOOLEAN DEFAULT false,
            porcentaje_rebaja VARCHAR(50),
            fecha_publicacion VARCHAR(50),
            visto_estado VARCHAR(100),
            visitas_count INTEGER,
            inmobiliaria VARCHAR(200),
            antiguedad INTEGER,
            lat FLOAT,
            lon FLOAT,
            barrio_geo VARCHAR(100),
            snap_warning BOOLEAN DEFAULT false,
            distancia_m_subte INTEGER,
            cant_subte INTEGER,
            distancia_m_gym INTEGER,
            cant_gym INTEGER,
            distancia_m_parque INTEGER,
            cant_parque INTEGER,
            distancia_m_plaza INTEGER,
            cant_plaza INTEGER,
            dist_verde_final INTEGER GENERATED ALWAYS AS (
                LEAST(COALESCE(distancia_m_plaza, 9999), COALESCE(distancia_m_parque, 9999))
            ) STORED,
            segmento VARCHAR(50),
            score FLOAT,
            apto_scoring BOOLEAN DEFAULT true,
            primera_vez_visto DATE DEFAULT CURRENT_DATE,
            ultima_vez_visto DATE DEFAULT CURRENT_DATE,
            activo BOOLEAN NOT NULL DEFAULT true,
            veces_visto INTEGER NOT NULL DEFAULT 1,
            revision TEXT,
            fecha_deteccion DATE DEFAULT CURRENT_DATE,
            created_at TIMESTAMP DEFAULT now(),
            updated_at TIMESTAMP DEFAULT now()
        );
        CREATE INDEX IF NOT EXISTS ix_departamentos_id ON departamentos (id);
        CREATE INDEX IF NOT EXISTS idx_depto_url_norm ON departamentos (url_norm);
        CREATE INDEX IF NOT EXISTS idx_depto_dedup_key ON departamentos (dedup_key);
        CREATE INDEX IF NOT EXISTS idx_depto_perfil_id ON departamentos (perfil_id);
        CREATE INDEX IF NOT EXISTS idx_depto_activo ON departamentos (activo);
        CREATE INDEX IF NOT EXISTS idx_depto_score ON departamentos (score);
        CREATE INDEX IF NOT EXISTS idx_depto_precio ON departamentos (precio);
        CREATE INDEX IF NOT EXISTS idx_depto_barrio_geo ON departamentos (barrio_geo);
        CREATE INDEX IF NOT EXISTS idx_depto_segmento ON departamentos (segmento);
        CREATE INDEX IF NOT EXISTS idx_depto_ultima_vez ON departamentos (ultima_vez_visto);

        CREATE TABLE IF NOT EXISTS scrape_runs (
            id SERIAL PRIMARY KEY,
            perfil_id INTEGER REFERENCES perfiles(id) ON DELETE SET NULL,
            initiated_by_id INTEGER REFERENCES users(id) ON DELETE SET NULL,
            status VARCHAR(20) NOT NULL DEFAULT 'pending',
            portales TEXT[] DEFAULT '{zonaprop,argenprop,cabaprop}',
            total_scraped INTEGER DEFAULT 0,
            total_inserted INTEGER DEFAULT 0,
            total_updated INTEGER DEFAULT 0,
            total_filtered INTEGER DEFAULT 0,
            error_message TEXT,
            started_at TIMESTAMP,
            finished_at TIMESTAMP,
            created_at TIMESTAMP NOT NULL DEFAULT now()
        );
        CREATE INDEX IF NOT EXISTS ix_scrape_runs_id ON scrape_runs (id);
        CREATE INDEX IF NOT EXISTS ix_scrape_runs_status ON scrape_runs (status);
        CREATE INDEX IF NOT EXISTS ix_scrape_runs_created_at ON scrape_runs (created_at);
    """)


def downgrade() -> None:
    op.execute("""
        DROP TABLE IF EXISTS scrape_runs;
        DROP TABLE IF EXISTS departamentos;
        DROP TABLE IF EXISTS perfiles;
        DROP TABLE IF EXISTS users;
    """)
