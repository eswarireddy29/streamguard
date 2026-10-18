"""
Central configuration for StreamGuard.

Every setting in the application is defined here and loaded from the
.env file at startup. Nothing anywhere else in the codebase should
read environment variables directly.
"""

from functools import lru_cache
from pathlib import Path

from pydantic import Field, computed_field
from pydantic_settings import BaseSettings, SettingsConfigDict

# Project root = three levels up from this file
# settings.py -> config/ -> streamguard/ -> src/ -> PROJECT ROOT
PROJECT_ROOT = Path(__file__).resolve().parents[3]


class Settings(BaseSettings):
    """All application settings, validated at startup."""

    model_config = SettingsConfigDict(
        env_file=PROJECT_ROOT / ".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # --- Application ---
    app_name: str = "StreamGuard"
    app_env: str = "development"
    debug: bool = True
    log_level: str = "INFO"
    log_format: str = "console"

    # --- Database ---
    postgres_host: str = "localhost"
    postgres_port: int = 5432
    postgres_db: str = "streamguard"
    postgres_user: str = "postgres"
    postgres_password: str = "changeme"

    # --- Paths (relative strings from .env) ---
    data_dir: str = "data"
    raw_data_dir: str = "data/raw"
    processed_data_dir: str = "data/processed"
    event_log_dir: str = "data/events"
    model_dir: str = "data/models"
    log_dir: str = "logs"

    # --- Synthetic data generation ---
    random_seed: int = 42
    n_customers: int = Field(default=5000, gt=0)
    n_merchants: int = Field(default=800, gt=0)
    simulation_days: int = Field(default=90, gt=0)
    fraud_rate: float = Field(default=0.004, gt=0, lt=1)

    # --- Scoring thresholds ---
    score_threshold_review: float = Field(default=0.35, ge=0, le=1)
    score_threshold_block: float = Field(default=0.80, ge=0, le=1)

    # --- Cost model ---
    cost_false_negative: float = Field(default=5000, gt=0)
    cost_false_positive: float = Field(default=200, gt=0)

    # --- API ---
    api_host: str = "127.0.0.1"
    api_port: int = 8000

    # ---------- Derived values ----------

    @computed_field
    @property
    def database_url(self) -> str:
        """SQLAlchemy connection string, assembled from the parts above."""
        return (
            f"postgresql+psycopg://{self.postgres_user}:{self.postgres_password}"
            f"@{self.postgres_host}:{self.postgres_port}/{self.postgres_db}"
        )

    @computed_field
    @property
    def raw_data_path(self) -> Path:
        return PROJECT_ROOT / self.raw_data_dir

    @computed_field
    @property
    def processed_data_path(self) -> Path:
        return PROJECT_ROOT / self.processed_data_dir

    @computed_field
    @property
    def event_log_path(self) -> Path:
        return PROJECT_ROOT / self.event_log_dir

    @computed_field
    @property
    def model_path(self) -> Path:
        return PROJECT_ROOT / self.model_dir

    @computed_field
    @property
    def log_path(self) -> Path:
        return PROJECT_ROOT / self.log_dir

    def ensure_directories(self) -> None:
        """Create every directory the app writes to, if missing."""
        for path in (
            self.raw_data_path,
            self.processed_data_path,
            self.event_log_path,
            self.model_path,
            self.log_path,
        ):
            path.mkdir(parents=True, exist_ok=True)


@lru_cache
def get_settings() -> Settings:
    """
    Return the single shared Settings instance.

    @lru_cache means the .env file is read once per process. Every
    later call returns the same cached object.
    """
    return Settings()


settings = get_settings()