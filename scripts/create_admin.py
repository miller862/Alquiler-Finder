"""
Crea el usuario admin si no existe. Llamado desde entrypoint.sh.
Lee ADMIN_USERNAME y ADMIN_PASSWORD del entorno.
"""
import os
import sys

from sqlalchemy import create_engine, text

from app.core.security import hash_password

ADMIN_USERNAME = os.environ.get("ADMIN_USERNAME", "manuel")
ADMIN_PASSWORD = os.environ.get("ADMIN_PASSWORD", "")
SYNC_DATABASE_URL = os.environ["SYNC_DATABASE_URL"]

if not ADMIN_PASSWORD:
    print("ADMIN_PASSWORD no configurado, saltando creacion de admin.")
    sys.exit(0)

engine = create_engine(SYNC_DATABASE_URL)
with engine.connect() as conn:
    existing = conn.execute(
        text("SELECT id FROM users WHERE username = :u"),
        {"u": ADMIN_USERNAME}
    ).fetchone()
    if existing:
        print(f"Admin '{ADMIN_USERNAME}' ya existe.")
    else:
        hashed = hash_password(ADMIN_PASSWORD)
        conn.execute(
            text("INSERT INTO users (username, hashed_password, is_admin) VALUES (:u, :h, true)"),
            {"u": ADMIN_USERNAME, "h": hashed}
        )
        conn.commit()
        print(f"Admin '{ADMIN_USERNAME}' creado.")
