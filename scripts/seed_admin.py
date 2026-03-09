"""
Script para crear el primer usuario administrador.
Ejecutar una sola vez antes del primer arranque.

Uso:
    python scripts/seed_admin.py
    python scripts/seed_admin.py --username manuel --password mipassword
"""
import argparse
import sys
import os

# Permite importar desde la raiz del proyecto
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

from app.config import settings
from app.database import Base
from app.models.user import User  # noqa: registers model
from app.core.security import hash_password


def create_admin(username: str, password: str) -> None:
    engine = create_engine(settings.sync_database_url)

    with Session(engine) as session:
        existing = session.execute(select(User).where(User.username == username)).scalar_one_or_none()
        if existing:
            print(f"Ya existe un usuario con username '{username}'. No se hizo nada.")
            return

        user = User(
            username=username.lower().strip(),
            hashed_password=hash_password(password),
            is_admin=True,
        )
        session.add(user)
        session.commit()
        print(f"Usuario admin '{username}' creado correctamente (id={user.id}).")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Crea el primer usuario admin.")
    parser.add_argument("--username", default="manuel", help="Nombre de usuario (default: manuel)")
    parser.add_argument("--password", required=True, help="Contrasena del admin")
    args = parser.parse_args()

    create_admin(args.username, args.password)
