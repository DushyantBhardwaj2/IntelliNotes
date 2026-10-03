from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

PROJECT_ROOT = Path(__file__).resolve().parents[2]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=str(PROJECT_ROOT / ".env"),
        env_file_encoding="utf-8-sig",
        extra="ignore",
    )

    google_api_key: str = ""
    tavily_api_key: str = ""

    chat_model: str = "gemini-3.5-flash-lite"
    embedding_model: str = "gemini-embedding-001"
    embedding_dimensions: int = 768

    collection_name: str = "intellinotes"
    chunk_size: int = 1000
    chunk_overlap: int = 200
    top_k: int = 4
    max_upload_mb: int = 20

    @property
    def chroma_path(self) -> Path:
        path = PROJECT_ROOT / "data" / "chroma"
        path.mkdir(parents=True, exist_ok=True)
        return path

    @property
    def memory_db_path(self) -> Path:
        path = PROJECT_ROOT / "data" / "memory.sqlite"
        path.parent.mkdir(parents=True, exist_ok=True)
        return path


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
