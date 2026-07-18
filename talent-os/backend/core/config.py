"""Talent OS - Pydantic Settings (all secrets from .env, never hardcoded)."""
from pydantic import model_validator
from pydantic_settings import BaseSettings
from typing import List


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

    smtp_host: str = "smtp.zoho.com"
    smtp_port: int = 587
    smtp_user: str = ""
    smtp_pass: str = ""

    backend_host: str = "127.0.0.1"
    backend_port: int = 8000
    backend_workers: int = 4
    cors_origins: str = "https://gsprecruitment.nl,https://www.gsprecruitment.nl,http://localhost:3000,http://127.0.0.1:3000"

    @property
    def cors_origin_list(self) -> List[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]

    log_level: str = "INFO"

    webhook_secret: str = "CHANGE_ME_TO_A_UNIQUE_WEBHOOK_SECRET"
    api_key: str = "CHANGE_ME"  # For internal API authentication

    # ── Google OAuth (for Gmail API) ──────────────────────────────────────
    google_client_id: str = ""
    google_client_secret: str = ""
    google_refresh_token: str = ""

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