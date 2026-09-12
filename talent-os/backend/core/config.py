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

    # RETENTION_PURGE_ENABLED (WS-E.8) used to live here -- an env
    # master-switch for a daily job that could actually anonymise/delete
    # rows. WS-E.10 (owner decision, retention-kolommen branch, fifth
    # round) removed that job entirely: retention now only ever produces
    # a monthly human-approved review queue (services/scheduler.py
    # generate_retention_review(), core/retention.py's own docstring),
    # which is safe to always run -- there is nothing left for a flag to
    # gate. Deliberately not kept as a dead/unused setting.

    # ── E-mail (WS3) ─────────────────────────────────────────────────────
    # EMAIL_PROVIDER kiest de provider in services/email_service.py;
    # "gmail" is het huidige gedrag (GmailApiProvider, ongewijzigd) en de
    # default zodat een bestaande deploy zonder .env-wijziging identiek
    # blijft werken. EMAIL_FROM's default is het huidige afzenderadres
    # (services/email_service.py regel 68, vóór dit spoor hardcoded) --
    # het subdomeinadres no-reply@mail.gsprecruitment.nl wordt pas gezet
    # zodra docs/EMAIL-SETUP.md is doorlopen (devops), niet door deze
    # default. OWNER_NOTIFY_EMAIL is leeg = geen eigenaarsmail (alleen
    # Telegram via services/notify.py); een lege waarde mag nooit een
    # e-mail naar niemand of naar EMAIL_FROM sturen.
    email_provider: str = "gmail"
    email_from: str = "GSP Recruitment <info@gsprecruitment.nl>"
    email_reply_to: str = "info@gsprecruitment.nl"
    owner_notify_email: str = ""

    smtp_host: str = "smtp.zoho.com"
    smtp_port: int = 587
    smtp_user: str = ""
    smtp_pass: str = ""

    # ── WS3b/WS3c: twee droog-standaard schakelaars ──────────────────────
    # Beide default False, en "uit" betekent hier niet "de job draait
    # niet" maar "de job draait en telt, maar verzendt niets" (droogloop):
    # de selectie is dan zichtbaar in de logs en in het teruggegeven dict
    # voordat er ook maar één mail uitgaat. Zelfde fail-closed keuze als
    # apollo_sync_enabled hierboven: een verse of staging-deploy mailt
    # nooit iemand zonder dat dat expliciet in env is aangezet.
    #
    # DORMANT_WARNING_ENABLED gaat over services/scheduler.py's
    # dormant_account_warning_job (dagelijks 04:45): de waarschuwing 30
    # dagen vóór de 18-maandengrens uit core/retention.py's
    # PORTAL_ACCOUNT_INACTIVE_SQL. Zolang deze uit staat wordt
    # users.dormant_warning_sent_at nooit gestempeld, en die kolom is
    # precies wat die selector eist -- er komt dus ook geen enkel account
    # op de maandelijkse beoordelingslijst. Dat is de bedoelde volgorde:
    # geen verwijderlijst zonder verstuurde waarschuwing.
    #
    # JOB_ALERTS_ENABLED gaat over job_alert_job (dagelijks 08:00) en
    # wordt aangevuld met de admin-bewerkbare DB-vlag
    # system_settings.job_alerts_enabled, net zoals bij Apollo: de env-
    # schakelaar is de master, de DB-vlag de tweede rem daarbovenop.
    # Die DB-rij wordt door migrations/042_alerts_token_binding_dormant_
    # skip.py idempotent op 'false' gezet -- zonder haar gaf
    # services/scheduler.py's _flag_enabled() True terug bij een
    # ontbrekende sleutel en was er in werkelijkheid maar één rem.
    dormant_warning_enabled: bool = False
    job_alerts_enabled: bool = False

    # Publieke basis-URL van deze API. Bestond nog niet als losse setting
    # (google_redirect_uri had hem tot nu toe als enige, ingebakken in een
    # langere default). WS3c heeft hem nodig voor de
    # List-Unsubscribe-header van een job-alert: RFC 8058 eist daar een
    # POST-bare https-URL, en dat kan per definitie niet de statische
    # website zijn. Geen schakelaar maar een adres; default is het echte
    # productieadres, zodat een deploy zonder deze key hetzelfde blijft
    # doen.
    api_base_url: str = "https://api.gsprecruitment.nl"

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

    # ── Sentry error monitoring (WS-E.9) ────────────────────────────────
    # Empty by default -- sentry_sdk.init() is never called when this is
    # unset (see main.py), so a fresh/staging deploy stays fully inert.
    sentry_dsn: str = ""
    # Free-text tag on every event (e.g. "production", "staging"). Not a
    # secret; kept as its own var rather than reusing dev_mode so it can
    # name environments dev_mode doesn't distinguish.
    sentry_environment: str = "production"

    webhook_secret: str = "CHANGE_ME_TO_A_UNIQUE_WEBHOOK_SECRET"
    api_key: str = "CHANGE_ME"  # For internal API authentication

    # ── Google OAuth (for Gmail API) ──────────────────────────────────────
    google_client_id: str = ""
    google_client_secret: str = ""
    google_refresh_token: str = ""

    # ── Google Sign-In (WS3) ─────────────────────────────────────────────
    # Reuses the same OAuth client as above; these two were hardcoded
    # module constants in routers/auth.py before this spoor -- moved here
    # so devops/frontend can point a staging deploy elsewhere without a
    # code change. Defaults are the current production values, so an
    # unset .env keeps today's behaviour.
    google_redirect_uri: str = "https://api.gsprecruitment.nl/api/auth/google/callback"
    frontend_url: str = "https://gsprecruitment.nl"

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

    # ── MFA (WS-E.12, admin TOTP) ────────────────────────────────────────
    # 32-byte urlsafe-base64 Fernet key (cryptography.fernet.Fernet.generate_key()).
    # Empty by default so the app still boots without it -- core/mfa.py
    # refuses to encrypt/decrypt a TOTP secret and POST /api/auth/mfa/setup
    # returns 503 until this is set, but nothing else in the app depends
    # on it (see core/mfa.py get_fernet()).
    mfa_enc_key: str = ""
    # Master switch: when true, an admin who has not enabled MFA gets 403
    # mfa_setup_required from admin endpoints once MFA_GRACE_UNTIL has
    # passed (core/deps.py). Defaults false so a fresh/staging deploy, or
    # the very first admin on a brand-new deploy, is never locked out
    # without an explicit opt-in -- see .env.example.
    mfa_required_for_admin: bool = False
    # ISO 8601 date/datetime (e.g. "2026-10-01"); before this moment admin
    # endpoints work regardless of mfa_required_for_admin so existing
    # admins have time to run the setup flow. Empty means "no grace" (the
    # 403 applies immediately once mfa_required_for_admin is true).
    mfa_grace_until: str = ""

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