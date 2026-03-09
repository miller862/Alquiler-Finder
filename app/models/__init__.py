from app.database import Base
from app.models.user import User
from app.models.perfil import Perfil
from app.models.departamento import Departamento
from app.models.scrape_run import ScrapeRun

__all__ = ["Base", "User", "Perfil", "Departamento", "ScrapeRun"]
