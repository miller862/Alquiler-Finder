from datetime import datetime
from typing import Optional, TYPE_CHECKING
from sqlalchemy import String, Integer, Text, ForeignKey, func
from sqlalchemy.dialects.postgresql import ARRAY
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base

if TYPE_CHECKING:
    from app.models.perfil import Perfil
    from app.models.user import User


class ScrapeRun(Base):
    __tablename__ = "scrape_runs"

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    perfil_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("perfiles.id", ondelete="SET NULL"), nullable=True, index=True
    )
    initiated_by_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )

    # Status: 'pending' | 'running' | 'completed' | 'failed'
    status: Mapped[str] = mapped_column(String(20), default="pending", nullable=False, index=True)

    portales: Mapped[list[str]] = mapped_column(
        ARRAY(String),
        default=lambda: ["argenprop"],
    )

    total_scraped: Mapped[int] = mapped_column(Integer, default=0)
    total_inserted: Mapped[int] = mapped_column(Integer, default=0)
    total_updated: Mapped[int] = mapped_column(Integer, default=0)
    total_filtered: Mapped[int] = mapped_column(Integer, default=0)

    error_message: Mapped[Optional[str]] = mapped_column(Text)

    progress_log: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    started_at: Mapped[Optional[datetime]] = mapped_column()
    finished_at: Mapped[Optional[datetime]] = mapped_column()

    created_at: Mapped[datetime] = mapped_column(server_default=func.now(), nullable=False, index=True)

    # Relationships
    perfil: Mapped[Optional["Perfil"]] = relationship("Perfil", back_populates="scrape_runs")
    initiated_by_user: Mapped[Optional["User"]] = relationship("User", back_populates="scrape_runs")

    def __repr__(self) -> str:
        return f"<ScrapeRun id={self.id} status={self.status!r}>"
