from pydantic_settings import BaseSettings, SettingsConfigDict
from functools import lru_cache


class Settings(BaseSettings):
    database_url: str = "postgresql+asyncpg://deptos:deptos@localhost:5432/deptos_scraper"
    sync_database_url: str = "postgresql+psycopg2://deptos:deptos@localhost:5432/deptos_scraper"
    secret_key: str = "changeme-use-a-real-256-bit-secret-in-production"
    access_token_expire_seconds: int = 28800  # 8 hours
    google_maps_api_key: str = ""
    debug: bool = False
    docker_env: bool = False
    allowed_origins: list[str] = ["http://localhost:8000"]
    shapes_dir: str = "shapes"

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
    )


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
