"""Configuration for every service, read from environment variables and `.env` in the working
directory. Every variable is documented in `.env.example`."""

from datetime import UTC, datetime
from pathlib import Path

from pydantic import Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class CollectorSettings(BaseSettings):
    """P1 collector (docs/04-pipelines.md#p1--collector)."""

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    collector_id: str
    opensky_client_id: str
    opensky_client_secret: SecretStr
    ingest_url: str | None = None
    ingest_api_key: SecretStr | None = None
    cadence_seconds: int = 90
    spool_dir: Path = Path("spool")
    upload_enabled: bool = True
    flight_lists_enabled: bool = True
    # Archive upload and retention (M1.20). Without the R2 credentials nothing is uploaded and no
    # local archive is deleted.
    archive_retention_days: int = 30
    rclone_remote: str = "r2:airspace-archive"
    r2_account_id: str | None = None
    r2_access_key_id: SecretStr | None = None
    r2_secret_access_key: SecretStr | None = None


class IngestSettings(BaseSettings):
    """P2 ingest-api (docs/04-pipelines.md#p2--ingest), connecting as `ingest_writer`."""

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    database_url: SecretStr


class ApiSettings(BaseSettings):
    """public-api (docs/05-api-contract.md), connecting as `app_reader`."""

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    database_url: SecretStr
    # Public API CORS (docs/05-api-contract.md#cors). The production domain and the Pages
    # project origin are deployment-specific; defaults cover local development and previews.
    cors_allowed_origins: str = "http://localhost:5173,http://127.0.0.1:5173"
    cors_allowed_origin_regex: str = r"https://([a-z0-9-]+\.)?airspace-live-tracker\.pages\.dev"
    # In-memory defense-in-depth limit; Cloudflare also rate-limits at the edge.
    rate_limit_requests: int = Field(default=60, gt=0)
    rate_limit_window_seconds: float = Field(default=10.0, gt=0)

    @property
    def cors_origin_list(self) -> list[str]:
        return [origin.strip() for origin in self.cors_allowed_origins.split(",") if origin.strip()]


class StreamSettings(BaseSettings):
    """P3 stream-worker (docs/04-pipelines.md#p3--stream-worker), connecting as `stream_worker`."""

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    database_url: SecretStr


class AdminSettings(BaseSettings):
    """Ingest admin CLI, connecting as `airspace_owner`."""

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    admin_database_url: SecretStr


class BackupSettings(BaseSettings):
    """The `backup` job (docs/04-pipelines.md#backup), connecting as the read-only `backup` role.
    The rclone remote itself is configured by `RCLONE_CONFIG_<REMOTE>_*` variables."""

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    backup_password: SecretStr
    backup_db_host: str = "db"
    backup_remote: str = "r2"
    backup_bucket: str = "airspace-backup"
    archive_bucket: str = "airspace-archive"
    backup_keep_days: int = 14
    # D7: backups plus archives stay under this, below R2's 10 GB free tier.
    r2_cap_bytes: int = 8_000_000_000


class JobsSettings(BaseSettings):
    """Scheduled Dagster jobs (docs/04-pipelines.md#p4--orchestrated-jobs), connecting as `jobs`."""

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    jobs_password: SecretStr
    jobs_db_host: str = "db"
    # carbon-signal, cluster-internal (docs/adr/0006-carbon-aware-operations.md).
    carbon_signal_url: str = "http://carbon-signal:8002"
    # METAR source for `metar_fetch` (docs/02-data-sources.md#weather-metar).
    metar_url: str = "https://aviationweather.gov/api/data/metar"
    # `ref_refresh` reads its files from this directory instead of the internet (CI).
    ref_source_dir: str | None = None


class CarbonSignalSettings(BaseSettings):
    """carbon-signal, the simulated grid (docs/adr/0006-carbon-aware-operations.md). No database."""

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    # > 1 speeds up the simulated clock for a demo (60: one simulated day in 24 minutes).
    signal_time_scale: float = Field(default=1.0, gt=0)
    signal_seed: int = 2026
    # Where a sped-up clock starts; real and simulated time agree at this instant.
    signal_epoch: datetime = datetime(2026, 11, 23, tzinfo=UTC)
