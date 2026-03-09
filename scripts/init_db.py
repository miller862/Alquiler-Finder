"""
Inicializa la base de datos ejecutando SQL directamente en el contenedor Docker.
Evita todos los problemas de drivers Python en Windows.

Uso:
    python scripts/init_db.py --password mipassword
    python scripts/init_db.py --username manuel --password mipassword
"""
import argparse
import subprocess
import sys


CONTAINER = "deptos_scraper-db-1"
DB_USER = "deptos"
DB_NAME = "deptos_scraper"


def run_sql(sql: str) -> str:
    result = subprocess.run(
        ["docker", "exec", CONTAINER, "psql", "-U", DB_USER, "-d", DB_NAME, "-c", sql],
        capture_output=True, text=True, encoding="utf-8"
    )
    if result.returncode != 0:
        print(f"ERROR: {result.stderr.strip()}")
        sys.exit(1)
    return result.stdout.strip()


def run_sql_file(sql: str) -> str:
    """Ejecuta SQL largo pasandolo via stdin."""
    result = subprocess.run(
        ["docker", "exec", "-i", CONTAINER, "psql", "-U", DB_USER, "-d", DB_NAME],
        input=sql, capture_output=True, text=True, encoding="utf-8"
    )
    if result.returncode != 0:
        print(f"ERROR: {result.stderr.strip()}")
        sys.exit(1)
    return result.stdout.strip()


# DDL generado a partir de los modelos SQLAlchemy del proyecto
CREATE_TABLES_SQL = """
-- Users
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

-- Perfiles
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

-- Departamentos
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

-- Scrape Runs
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

-- Alembic version tracking
CREATE TABLE IF NOT EXISTS alembic_version (
    version_num VARCHAR(32) NOT NULL
);
INSERT INTO alembic_version (version_num)
SELECT 'initial_manual' WHERE NOT EXISTS (SELECT 1 FROM alembic_version);
"""


def create_admin(username: str, password: str) -> None:
    # Generar hash bcrypt dentro de Python (unica dependencia local)
    sys.path.insert(0, __import__("os").path.dirname(__import__("os").path.dirname(__import__("os").path.abspath(__file__))))
    from app.core.security import hash_password
    hashed = hash_password(password)

    # Escapar comillas simples para SQL
    hashed_escaped = hashed.replace("'", "''")
    username_clean = username.lower().strip().replace("'", "''")

    sql = f"""
    INSERT INTO users (username, hashed_password, is_admin)
    SELECT '{username_clean}', '{hashed_escaped}', true
    WHERE NOT EXISTS (SELECT 1 FROM users WHERE username = '{username_clean}');
    """
    output = run_sql(sql)
    print(output)


def main():
    parser = argparse.ArgumentParser(description="Inicializa la DB y crea el admin.")
    parser.add_argument("--username", default="manuel")
    parser.add_argument("--password", required=True)
    args = parser.parse_args()

    # Verificar que el contenedor este corriendo
    check = subprocess.run(
        ["docker", "exec", CONTAINER, "pg_isready", "-U", DB_USER],
        capture_output=True, text=True
    )
    if check.returncode != 0:
        print(f"ERROR: El contenedor '{CONTAINER}' no esta corriendo o PostgreSQL no responde.")
        print("Ejecuta primero: docker-compose up -d db")
        sys.exit(1)
    print("PostgreSQL listo.")

    # Crear tablas
    print("Creando tablas...")
    output = run_sql_file(CREATE_TABLES_SQL)
    print("Tablas creadas correctamente.")

    # Crear admin
    print(f"Creando usuario admin '{args.username}'...")
    create_admin(args.username, args.password)
    print(f"Usuario admin '{args.username}' creado.")

    print("\nBase de datos lista. Levantar la app con:")
    print("  docker-compose up --build")
    print("  O localmente: uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload")


if __name__ == "__main__":
    main()
