from datetime import datetime
from typing import Optional, TYPE_CHECKING
from sqlalchemy import String, Boolean, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base

if TYPE_CHECKING:
    from app.models.perfil import Perfil
    from app.models.scrape_run import ScrapeRun


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    username: Mapped[str] = mapped_column(String(100), unique=True, nullable=False, index=True)
    hashed_password: Mapped[str] = mapped_column(nullable=False)
    is_admin: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    created_at: Mapped[datetime] = mapped_column(server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        server_default=func.now(), onupdate=func.now(), nullable=False
    )

    # Relationships
    perfiles: Mapped[list["Perfil"]] = relationship(
        "Perfil", back_populates="owner", cascade="all, delete-orphan"
    )
    scrape_runs: Mapped[list["ScrapeRun"]] = relationship(
        "ScrapeRun", back_populates="initiated_by_user"
    )

    def __repr__(self) -> str:
        return f"<User id={self.id} username={self.username!r}>"
