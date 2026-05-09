import os
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    PROJECT_NAME: str = "Steam avatars search engine"
    SEARCH_CONFIG_PATH: str = "config/search.yaml"
    HNSW_DEFAULT_NUM_THREADS: int = max(1, min(8, os.cpu_count() or 1))

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )


settings = Settings()


def get_search_config_path() -> Path:
    return Path(__file__).resolve().parents[2] / settings.SEARCH_CONFIG_PATH
