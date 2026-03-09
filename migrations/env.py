import os
from logging.config import fileConfig

from sqlalchemy import engine_from_config, pool
from alembic import context

# Importar todos los modelos para que Alembic los detecte
from app.database import Base
import app.models  # noqa: F401 — registra todos los modelos

config = context.config

# Leer DATABASE_URL desde el entorno si está disponible (sobreescribe alembic.ini)
db_url = os.getenv("SYNC_DATABASE_URL") or os.getenv("DATABASE_URL", "").replace(
    "postgresql+asyncpg", "postgresql+psycopg2"
)
if db_url:
    config.set_main_option("sqlalchemy.url", db_url)

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = Base.metadata


def run_migrations_offline() -> None:
    url = config.get_main_option("sqlalchemy.url")
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    connectable = engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )
    with connectable.connect() as connection:
        context.configure(connection=connection, target_metadata=target_metadata)
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
