"""Talent OS - Pydantic Settings (all secrets from .env, never hardcoded)."""
from pydantic import model_validator
from pydantic_settings import BaseSettings
from typing import List

# Local-dev-only CORS origins, appended when DEV_MODE=true. Never used in
# production (see Settings.cors_origin_list below).
_DEV_CORS_ORIGINS = [
    "http://localhost:3000",
    "http://127.0.0.1:3000",
    "http://localhost:8081",
    "http://localhost:19006",
    "exp://localhost:8081",
]


class Settings(BaseSettings):
    postgres_host: str = "localhost"
    postgres_port: int = 5432
    postgres_db: str = "recruitment_db"
    postgres_user: str = "talentos_write"
    postgres_password: str = "CHANGE_ME"

    @property
    def database_url(self) -> str:
        return (
            f"postgresql+asyncpg://{self.postgres_user}:{self.postgres_password}"
            f"@{self.postgres_host}:{self.postgres_port}/{self.postgres_db}"
        )

    @property
    def database_url_sync(self) -> str:
        return (
            f"postgresql+psycopg2://{self.postgres_user}:{self.postgres_password}"
            f"@{self.postgres_host}:{self.postgres_port}/{self.postgres_db}"
        )

    redis_host: str = "localhost"
    redis_port: int = 6379
    redis_db: int = 0

    @property
    def redis_url(self) -> str:
        return f"redis://{self.redis_host}:{self.redis_port}/{self.redis_db}"

    @property
    def celery_broker_url(self) -> str:
        return f"redis://{self.redis_host}:{self.redis_port}/{self.redis_db}"

    openrouter_api_key: str = ""
    openrouter_base_url: str = "https://openrouter.ai/api/v1"
    openrouter_chat_model: str = "deepseek/deepseek-chat"

    apollo_api_key: str = ""
    # Master off-switch for the Apollo sourcing jobs (services/scheduler.py):
    # defaults False so a fresh/staging deploy never silently starts
    # scraping. Must be explicitly set true via env/.env to register the
    # jobs at all; system_settings.apollo_sync_enabled (DB-editable by an
    # admin, defaults to enabled when absent) is then checked on top of
    # this at each run.
    apollo_sync_enabled: bool = False

    # WS-E.8: master off-switch for the retention purge job
    # (services/scheduler.py run_retention_purge, core/retention.py).
    # Defaults False so a fresh/staging deploy never silently starts
    # anonymising or deleting rows -- the daily job runs in dry-run
    # (counts-only, no DB writes) until this is explicitly set true via
    # env/.env. The admin endpoint (POST /api/v1/admin/retention/run) is
    # independent of this flag -- its own dry_run body field (default
    # true) and the confirm="PURGE" requirement gate a real run there.
    retention_purge_enabled: bool = False

    smtp_host: str = "smtp.zoho.com"
    smtp_port: int = 587
    smtp_user: str = ""
    smtp_pass: str = ""

    backend_host: str = "127.0.0.1"
    backend_port: int = 8000
    backend_workers: int = 4
    # Production default: only the two real front-end origins. Never add
    # localhost/exp:// dev origins here -- set DEV_MODE=true instead (below),
    # which appends them at runtime. Override via CORS_ORIGINS if a
    # deployment genuinely needs a different origin list.
    cors_origins: str = "https://gsprecruitment.nl,https://www.gsprecruitment.nl"
    # Local-dev-only switch: set true (env DEV_MODE=true) to also allow the
    # localhost/Expo dev-server origins below. Must stay false/unset in
    # production -- see .env.example.
    dev_mode: bool = False

    @property
    def cors_origin_list(self) -> List[str]:
        origins = [o.strip() for o in self.cors_origins.split(",") if o.strip()]
        if self.dev_mode:
            origins += _DEV_CORS_ORIGINS
        return origins

    log_level: str = "INFO"

    webhook_secret: str = "CHANGE_ME_TO_A_UNIQUE_WEBHOOK_SECRET"
    api_key: str = "CHANGE_ME"  # For internal API authentication

    # ── Google OAuth (for Gmail API) ──────────────────────────────────────
    google_client_id: str = ""
    google_client_secret: str = ""
    google_refresh_token: str = ""

    # ── Cloudflare R2 (CV file storage, S3-compatible) ──────────────────────
    # Empty defaults so the app still boots before these are set; callers
    # must check services.storage.is_configured() before using R2.
    r2_endpoint: str = ""
    r2_access_key_id: str = ""
    r2_secret_access_key: str = ""
    r2_bucket: str = ""

    # ── JWT / Auth ────────────────────────────────────────────────────────
    jwt_secret: str = "CHANGE_ME_TO_A_STRONG_RANDOM_SECRET_AT_LEAST_32_CHARS"
    jwt_algorithm: str = "HS256"
    access_token_expire_minutes: int = 60

    model_config = {"env_file": ".env", "env_file_encoding": "utf-8", "case_sensitive": False}

    @model_validator(mode="after")
    def _reject_placeholder_secrets(self) -> "Settings":
        placeholders = {
            "postgres_password": "CHANGE_ME",
            "webhook_secret": "CHANGE_ME_TO_A_UNIQUE_WEBHOOK_SECRET",
            "api_key": "CHANGE_ME",
            "jwt_secret": "CHANGE_ME_TO_A_STRONG_RANDOM_SECRET_AT_LEAST_32_CHARS",
        }
        leftover = [name for name, default in placeholders.items() if getattr(self, name) == default]
        if leftover:
            raise ValueError(
                f"Refusing to start: these settings are still at their placeholder default "
                f"(set real values via environment/.env): {', '.join(leftover)}"
            )
        if len(self.jwt_secret) < 32:
            raise ValueError("jwt_secret must be at least 32 characters")
        return self


settings = Settings()