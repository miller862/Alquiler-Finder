from datetime import date, datetime
from typing import Optional, TYPE_CHECKING
from sqlalchemy import (
    String, Boolean, Integer, Float, Text, Date, ForeignKey,
    func, Index, Computed
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base

if TYPE_CHECKING:
    from app.models.perfil import Perfil


class Departamento(Base):
    __tablename__ = "departamentos"
    __table_args__ = (
        Index("idx_depto_url_norm", "url_norm"),
        Index("idx_depto_dedup_key", "dedup_key"),
        Index("idx_depto_perfil_id", "perfil_id"),
        Index("idx_depto_activo", "activo"),
        Index("idx_depto_score", "score"),
        Index("idx_depto_precio", "precio"),
        Index("idx_depto_barrio_geo", "barrio_geo"),
        Index("idx_depto_segmento", "segmento"),
        Index("idx_depto_ultima_vez", "ultima_vez_visto"),
    )

    id: Mapped[int] = mapped_column(primary_key=True, index=True)

    # --- Claves de deduplicación (indexadas) ---
    url: Mapped[Optional[str]] = mapped_column(Text, unique=True, nullable=True)
    url_norm: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    direccion_norm: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    dedup_key: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    # --- Metadata de origen ---
    portal: Mapped[str] = mapped_column(String(50), nullable=False)
    perfil_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("perfiles.id", ondelete="SET NULL"), nullable=True, index=True
    )
    barrio_scrapeado: Mapped[Optional[str]] = mapped_column(String(100))
    tipo: Mapped[Optional[str]] = mapped_column(String(50))

    # --- Datos del listing ---
    titulo: Mapped[Optional[str]] = mapped_column(Text)
    descripcion_breve: Mapped[Optional[str]] = mapped_column(Text)
    direccion: Mapped[Optional[str]] = mapped_column(Text)
    precio: Mapped[Optional[int]] = mapped_column(Integer)
    expensas: Mapped[Optional[int]] = mapped_column(Integer)
    costo_total: Mapped[Optional[int]] = mapped_column(
        Integer,
        Computed("precio + COALESCE(expensas, 0)", persisted=True),
        nullable=True,
    )
    metros_totales: Mapped[Optional[int]] = mapped_column(Integer)
    metros_cubiertos: Mapped[Optional[int]] = mapped_column(Integer)
    ambientes: Mapped[Optional[int]] = mapped_column(Integer)
    dormitorios: Mapped[Optional[int]] = mapped_column(Integer)
    banios: Mapped[Optional[int]] = mapped_column(Integer)
    cocheras: Mapped[Optional[int]] = mapped_column(Integer, default=0)

    # Campos específicos por portal
    etiqueta_destacado: Mapped[Optional[str]] = mapped_column(Text)
    bajo_precio: Mapped[Optional[bool]] = mapped_column(Boolean, default=False)
    porcentaje_rebaja: Mapped[Optional[str]] = mapped_column(String(50))
    fecha_publicacion: Mapped[Optional[str]] = mapped_column(String(50))  # cabaprop
    visto_estado: Mapped[Optional[str]] = mapped_column(String(100))      # argenprop
    visitas_count: Mapped[Optional[int]] = mapped_column(Integer)          # argenprop
    inmobiliaria: Mapped[Optional[str]] = mapped_column(String(200))       # cabaprop
    antiguedad: Mapped[Optional[int]] = mapped_column(Integer)             # argenprop

    # --- Geocodificación ---
    lat: Mapped[Optional[float]] = mapped_column(Float)
    lon: Mapped[Optional[float]] = mapped_column(Float)
    barrio_geo: Mapped[Optional[str]] = mapped_column(String(100))
    snap_warning: Mapped[Optional[bool]] = mapped_column(Boolean, default=False)

    # --- Métricas de distancia (calculadas por metrics_service) ---
    distancia_m_subte: Mapped[Optional[int]] = mapped_column(Integer)
    cant_subte: Mapped[Optional[int]] = mapped_column(Integer)
    distancia_m_gym: Mapped[Optional[int]] = mapped_column(Integer)
    cant_gym: Mapped[Optional[int]] = mapped_column(Integer)
    distancia_m_parque: Mapped[Optional[int]] = mapped_column(Integer)
    cant_parque: Mapped[Optional[int]] = mapped_column(Integer)
    distancia_m_plaza: Mapped[Optional[int]] = mapped_column(Integer)
    cant_plaza: Mapped[Optional[int]] = mapped_column(Integer)
    dist_verde_final: Mapped[Optional[int]] = mapped_column(
        Integer,
        Computed(
            "LEAST(COALESCE(distancia_m_plaza, 9999), COALESCE(distancia_m_parque, 9999))",
            persisted=True,
        ),
        nullable=True,
    )

    # --- Scoring ---
    segmento: Mapped[Optional[str]] = mapped_column(String(50))
    score: Mapped[Optional[float]] = mapped_column(Float)
    apto_scoring: Mapped[bool] = mapped_column(Boolean, default=True)

    # --- Historial / ciclo de vida ---
    primera_vez_visto: Mapped[date] = mapped_column(Date, server_default=func.current_date())
    ultima_vez_visto: Mapped[date] = mapped_column(Date, server_default=func.current_date())
    activo: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    veces_visto: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    revision: Mapped[Optional[str]] = mapped_column(Text)
    fecha_deteccion: Mapped[date] = mapped_column(Date, server_default=func.current_date())

    # --- Timestamps ---
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        server_default=func.now(), onupdate=func.now()
    )

    # Relationship
    perfil: Mapped[Optional["Perfil"]] = relationship("Perfil", back_populates="departamentos")

    def __repr__(self) -> str:
        return f"<Departamento id={self.id} portal={self.portal!r} direccion={self.direccion!r}>"
