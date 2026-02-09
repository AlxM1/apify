"""Centralized configuration loaded from environment / .env file."""

from pathlib import Path
from typing import Optional

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # ── App ───────────────────────────────────────────────────
    app_name: str = "Apify Scraper Suite"
    debug: bool = False
    host: str = "0.0.0.0"
    port: int = 8000
    workers: int = 1
    log_level: str = "info"

    # ── Database ──────────────────────────────────────────────
    database_url: str = f"sqlite+aiosqlite:///{Path(__file__).resolve().parent.parent / 'data' / 'apify.db'}"

    # ── Auth ──────────────────────────────────────────────────
    api_key: str = ""  # empty = auth disabled
    jwt_secret: str = "change-me-in-production"
    jwt_algorithm: str = "HS256"
    jwt_expire_minutes: int = 1440  # 24 hours

    # ── Scraping defaults ─────────────────────────────────────
    default_max_results: int = 100
    default_delay: float = 1.0
    default_headless: bool = True
    default_proxy: str = ""
    proxy_list_file: str = ""

    # ── Scheduler ─────────────────────────────────────────────
    scheduler_enabled: bool = True
    scheduler_check_interval: int = 60  # seconds

    # ── Data retention ────────────────────────────────────────
    retention_enabled: bool = False
    retention_days: int = 30  # delete jobs older than this
    retention_check_interval: int = 3600  # seconds

    # ── Rate limiting (API) ───────────────────────────────────
    rate_limit_enabled: bool = True
    rate_limit: str = "60/minute"

    # ── Webhooks / n8n ────────────────────────────────────────
    webhook_url: str = ""  # POST here on job completion
    webhook_secret: str = ""  # HMAC secret for signing payloads
    n8n_base_url: str = ""  # e.g. http://localhost:5678

    # ── Telegram (for Telegram scraper) ───────────────────────
    telegram_api_id: str = ""
    telegram_api_hash: str = ""


settings = Settings()
