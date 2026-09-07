"""12-factor configuration. All runtime config comes from env (.env) — no hard-coded secrets."""
from __future__ import annotations

from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    # Database
    database_url: str = "postgresql+psycopg://jobagent:jobagent@localhost:5432/jobagent"

    # LLM
    llm_provider: str = "anthropic"
    anthropic_api_key: str = ""
    llm_model: str = "claude-sonnet-4-5"
    llm_embed_model: str = "voyage-3"

    # Config file paths
    target_roles_config: str = "config/sources.yaml"
    profile_config: str = "config/profile.yaml"
    ranking_config: str = "config/ranking.yaml"

    # Freshness / anti-spam
    recent_window_days: int = 3
    daily_job_limit: int = 200
    per_company_cooldown_hours: int = 24

    # ATS description hydration (politeness + cost control)
    ats_hydrate_limit: int = 400          # max descriptions to fetch per run
    ats_hydrate_delay: float = 0.25       # seconds between ATS calls

    # Email
    smtp_host: str = "localhost"
    smtp_port: int = 587
    smtp_user: str = ""
    smtp_password: str = ""
    digest_from: str = ""
    digest_to: str = ""

    # Runtime
    log_level: str = "INFO"
    timezone: str = "America/Phoenix"


@lru_cache
def get_settings() -> Settings:
    return Settings()
