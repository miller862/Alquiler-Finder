from pydantic import BaseModel
from datetime import datetime
from typing import Optional


class ScrapeRunCreate(BaseModel):
    perfil_id: int
    portales: list[str] = ["zonaprop", "argenprop", "cabaprop"]


class ScrapeRunRead(BaseModel):
    id: int
    perfil_id: Optional[int]
    status: str
    portales: list[str]
    total_scraped: int
    total_inserted: int
    total_updated: int
    total_filtered: int
    error_message: Optional[str]
    started_at: Optional[datetime]
    finished_at: Optional[datetime]
    created_at: datetime

    model_config = {"from_attributes": True}
