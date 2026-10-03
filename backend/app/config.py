import os
from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

PROJECT_ROOT = Path(__file__).resolve().parents[2]


def _parse_origins(value: str) -> list[str]:
    """Parse a comma-separated CORS origin string into a list.

    An empty value defaults to permissive localhost development origins.
    A literal "*" restores fully open CORS (development only — not recommended).
    """
    raw = (value or "").strip()
    if not raw:
        return [
            "http://localhost:8501",
            "http://127.0.0.1:8501",
        ]
    if raw == "*":
        return ["*"]
    return [origin.strip() for origin in raw.split(",") if origin.strip()]


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

    # --- Deployment hardening -------------------------------------------------
    # Shared secret required as "X-API-Key" header on mutating/expensive
    # endpoints. Empty string disables auth (local development default).
    api_key: str = ""
    # Comma-separated list of browser origins allowed to call the API.
    cors_origins: str = ""
    # Per-IP request limits for rate-limited endpoints (0 disables limiting).
    rate_limit_chat: str = "10/minute"
    rate_limit_upload: str = "5/minute"

    @property
    def allowed_origins(self) -> list[str]:
        return _parse_origins(self.cors_origins)

    @property
    def auth_enabled(self) -> bool:
        return bool(self.api_key.strip())

    @property
    def data_dir(self) -> Path:
        """Root directory for all persistent state (vectors + memory).

        Override with DATA_DIR when deploying to a host with a mounted volume.
        Read from the environment at call time so containers can set it.
        """
        override = os.environ.get("DATA_DIR", "").strip()
        return Path(override) if override else PROJECT_ROOT

    @property
    def chroma_path(self) -> Path:
        path = self.data_dir / "data" / "chroma"
        path.mkdir(parents=True, exist_ok=True)
        return path

    @property
    def memory_db_path(self) -> Path:
        path = self.data_dir / "data" / "memory.sqlite"
        path.parent.mkdir(parents=True, exist_ok=True)
        return path


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
