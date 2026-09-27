from functools import lru_cache
from pathlib import Path

from pydantic import Field, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Runtime configuration loaded from environment variables and .env."""

    app_name: str = "HydroShield Backend"
    environment: str = "development"
    api_prefix: str = "/api/v1"
    app_version: str = "0.1.0"
    log_level: str = "INFO"
    database_url: str = "sqlite:///./hydroshield.db"
    db_connect_timeout_s: int = Field(default=10, gt=0, le=300)
    db_pool_size: int = Field(default=5, ge=1, le=50)
    db_max_overflow: int = Field(default=10, ge=0, le=100)
    db_pool_recycle_s: int = Field(default=1800, gt=0, le=86_400)

    allowed_origins: list[str] = Field(default_factory=lambda: ["http://localhost:5173"])
    allowed_hosts: list[str] = Field(default_factory=lambda: ["localhost", "127.0.0.1", "testserver"])
    enforce_https: bool = False
    docs_enabled: bool = True

    processing_work_dir: Path = Path("data/processed")
    storage_root: Path = Path("data/uploads")
    export_root: Path = Path("data/exports")
    model_work_dir: Path = Path("data/model_runs")
    max_upload_bytes: int = Field(default=50 * 1024 * 1024, gt=0, le=1_073_741_824)
    max_acquisition_download_bytes: int = Field(default=512 * 1024 * 1024, gt=0, le=2_147_483_648)
    max_request_body_bytes: int = Field(default=55 * 1024 * 1024, gt=0, le=1_100_000_000)
    model_timeout_s: float = Field(default=3600.0, gt=0, le=86_400)
    job_worker_count: int = Field(default=1, ge=1, le=32)
    demo_mode: bool = False

    # Concrete SPH engine: DualSPHysics v5.4.3.
    dual_sph_bin_dir: Path | None = None
    dual_sph_device: str = Field(default="gpu", pattern="^(gpu|cpu)$")
    dual_sph_gpu_id: int = Field(default=0, ge=0, le=64)
    dual_sph_gencase: str | None = None
    dual_sph_solver_gpu: str | None = None
    dual_sph_solver_cpu: str | None = None
    dual_sph_partvtk: str | None = None
    dual_sph_output_interval_s: float = Field(default=1.0, gt=0)

    earth_engine_project: str | None = None
    nominatim_url: str = "https://nominatim.openstreetmap.org/search"
    overpass_url: str = "https://overpass-api.de/api/interpreter"
    acquisition_user_agent: str = "HydroShield/0.1 (dam-break flood modelling)"
    acquisition_timeout_s: int = Field(default=120, gt=0, le=600)
    acquisition_cache_ttl_s: int = Field(default=86_400, ge=0, le=7_776_000)

    # Deprecated compatibility field. Phase 6 no longer uses a generic SPH command.
    sph_command: str = ""
    delft3d_executable: str = ""
    delft3d_bin_dir: Path | None = None
    run_migrations_on_startup: bool = False
    forwarded_allow_ips: str = "127.0.0.1"

    model_config = SettingsConfigDict(
        env_file=".env",
        env_prefix="HYDROSHIELD_",
        case_sensitive=False,
        extra="ignore",
    )

    @field_validator("log_level")
    @classmethod
    def validate_log_level(cls, value: str) -> str:
        normalized = value.upper()
        allowed = {"CRITICAL", "ERROR", "WARNING", "INFO", "DEBUG"}
        if normalized not in allowed:
            raise ValueError(f"Unsupported log level: {value}")
        return normalized

    @model_validator(mode="after")
    def validate_production_settings(self) -> "Settings":
        if self.environment.lower() == "production":
            if self.database_url.startswith("sqlite"):
                raise ValueError("Production requires PostgreSQL; SQLite is not supported.")
            if "*" in self.allowed_hosts:
                raise ValueError("Production allowed_hosts must not contain '*'.")
            if any(origin.startswith("http://localhost") for origin in self.allowed_origins) or "*" in self.allowed_origins:
                raise ValueError("Production allowed_origins must be explicit and must not use localhost or wildcard.")
            if self.docs_enabled:
                raise ValueError("Production API docs must be disabled.")
        return self


@lru_cache
def get_settings() -> Settings:
    return Settings()
