from datetime import datetime
from typing import Optional, TYPE_CHECKING
from sqlalchemy import String, Boolean, Integer, ForeignKey, func, UniqueConstraint
from sqlalchemy.dialects.postgresql import ARRAY
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base

if TYPE_CHECKING:
    from app.models.user import User
    from app.models.departamento import Departamento
    from app.models.scrape_run import ScrapeRun


class Perfil(Base):
    __tablename__ = "perfiles"
    __table_args__ = (UniqueConstraint("user_id", "nombre", name="uq_perfil_user_nombre"),)

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    nombre: Mapped[str] = mapped_column(String(100), nullable=False)
    operacion: Mapped[str] = mapped_column(String(50), default="alquiler", nullable=False)

    # Arrays — stored as PostgreSQL TEXT[]
    barrios: Mapped[list[str]] = mapped_column(ARRAY(String), default=list, nullable=False)
    tipos: Mapped[list[str]] = mapped_column(ARRAY(String), default=list, nullable=False)

    precio_min: Mapped[Optional[int]] = mapped_column(Integer)
    precio_max: Mapped[Optional[int]] = mapped_column(Integer)
    precio_moneda: Mapped[str] = mapped_column(String(20), default="pesos")

    amb_min: Mapped[Optional[int]] = mapped_column(Integer)
    amb_max: Mapped[Optional[int]] = mapped_column(Integer)

    dorm_min: Mapped[Optional[int]] = mapped_column(Integer)
    dorm_max: Mapped[Optional[int]] = mapped_column(Integer)

    superficie_cubierta_min: Mapped[Optional[int]] = mapped_column(Integer)
    balcon: Mapped[bool] = mapped_column(Boolean, default=False)
    expensas_max: Mapped[Optional[int]] = mapped_column(Integer)

    filtros_exclusion: Mapped[list[str]] = mapped_column(ARRAY(String), default=list)

    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    created_at: Mapped[datetime] = mapped_column(server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        server_default=func.now(), onupdate=func.now(), nullable=False
    )

    # Relationships
    owner: Mapped["User"] = relationship("User", back_populates="perfiles")
    departamentos: Mapped[list["Departamento"]] = relationship(
        "Departamento", back_populates="perfil"
    )
    scrape_runs: Mapped[list["ScrapeRun"]] = relationship(
        "ScrapeRun", back_populates="perfil"
    )

    def to_config_dict(self) -> dict:
        """Convierte el perfil al formato de diccionario que usan los servicios de scraping."""
        return {
            "nombre": self.nombre,
            "operacion": self.operacion,
            "barrios": self.barrios,
            "tipos": self.tipos,
            "precio": {
                "min": self.precio_min,
                "max": self.precio_max,
                "moneda": self.precio_moneda,
            },
            "ambientes": {"min": self.amb_min, "max": self.amb_max},
            "dormitorios": {"min": self.dorm_min, "max": self.dorm_max},
            "superficie": {"cubierta_min": self.superficie_cubierta_min},
            "extras": {"balcon": self.balcon, "expensas_max": self.expensas_max},
            "filtros_exclusion": self.filtros_exclusion,
        }

    def __repr__(self) -> str:
        return f"<Perfil id={self.id} nombre={self.nombre!r}>"
