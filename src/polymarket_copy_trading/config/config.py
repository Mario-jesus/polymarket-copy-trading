# -*- coding: utf-8 -*-
"""Configuration loaded from environment via Pydantic Settings.

Nested env vars use <section>__<key>, e.g. LOGGING__CONSOLE_LEVEL, API__DATA_API_HOST.
"""

from __future__ import annotations

from functools import lru_cache
from typing import Any, Literal, Optional

from pydantic import Field, computed_field
from pydantic_settings import BaseSettings, SettingsConfigDict


class AppSettings(BaseSettings):
    """General application configuration."""

    model_config = SettingsConfigDict(extra="ignore")

    app_name: str = "polymarket-copy-trading"
    service_name: Optional[str] = None
    service_version: Optional[str] = None
    environment: Literal["development", "test", "production"] = "development"


class LoggingSettings(BaseSettings):
    """Structured logging configuration for structlog/stdlib/Logfire."""

    model_config = SettingsConfigDict(extra="ignore")

    # Per-target levels (only the 5 standard levels)
    console_level: Literal["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"] = "INFO"
    file_level: Literal["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"] = "INFO"
    logfire_level: Literal["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"] = "INFO"

    # Local outputs
    log_to_console: bool = True
    log_to_file: bool = False
    log_file_path: str = "logs/copy_trading.log"
    # TimedRotatingFileHandler: when to rotate (S/M/H/D/W0–W6/midnight), interval, backups to keep
    log_file_when: Literal[
        "S", "M", "H", "D", "W0", "W1", "W2", "W3", "W4", "W5", "W6", "midnight"
    ] = "midnight"
    log_file_interval: int = 1
    log_file_backup_count: int = 30
    log_file_utc: bool = True

    # Main output format: JSONRenderer if True, ConsoleRenderer if False
    json_format: bool = False

    # Logfire integration via structlog
    logfire_enabled: bool = False
    logfire_token: Optional[str] = None


class ApiSettings(BaseSettings):
    """Configuration for Polymarket Data API and Gamma API (HTTP)."""

    model_config = SettingsConfigDict(extra="ignore")

    data_api_host: str = Field(
        default="https://data-api.polymarket.com",
        description="Polymarket Data API base URL.",
    )
    gamma_host: str = Field(
        default="https://gamma-api.polymarket.com",
        description="Polymarket Gamma API base URL.",
    )
    timeout_seconds: float = Field(
        default=15.0,
        ge=1.0,
        le=120.0,
        description="HTTP request timeout in seconds.",
    )
    max_retries: int = Field(
        default=6,
        ge=1,
        le=20,
        description="Maximum number of retries for failed requests.",
    )


class PolymarketClobSettings(BaseSettings):
    """Polymarket CLOB/trading credentials and wallet (from env POLYMARKET__*)."""

    model_config = SettingsConfigDict(extra="ignore")

    clob_host: str = Field(
        default="https://clob.polymarket.com",
        description="Polymarket CLOB API base URL.",
    )
    chain_id: int = Field(default=137, description="Chain ID (e.g. 137 for Polygon).")
    signature_type: int = Field(default=0, description="Signature type for CLOB.")
    private_key: Optional[str] = Field(default=None, description="Wallet private key.")
    api_key: Optional[str] = Field(default=None, description="Polymarket API key.")
    api_secret: Optional[str] = Field(
        default=None,
        description="Polymarket API secret (env: APY_SECRET or API_SECRET).",
        validation_alias="apy_secret",
    )
    api_passphrase: Optional[str] = Field(default=None, description="Polymarket API passphrase.")
    funder: Optional[str] = Field(
        default=None,
        description="Proxy wallet address (Wallet Address in Polymarket UI).",
    )


class TelegramNotificationSettings(BaseSettings):
    """Telegram notifications (from env TELEGRAM__*)."""

    model_config = SettingsConfigDict(extra="ignore")

    enabled: bool = False
    api_key: Optional[str] = Field(default=None, description="Telegram bot API key.")
    chat_id: Optional[str] = Field(default=None, description="Telegram chat ID.")
    messages_per_minute: int = Field(default=30, ge=1, le=120)
    max_retries: int = Field(default=5, ge=0, le=20)
    backoff_base_seconds: float = Field(default=1.0, ge=0.1, le=60.0)
    queue_size: int = Field(default=200, ge=1, le=5000)
    connect_timeout: float = Field(default=10.0, ge=0.1, le=60.0)
    read_timeout: float = Field(default=20.0, ge=0.1, le=120.0)
    write_timeout: float = Field(default=20.0, ge=0.1, le=120.0)
    pool_timeout: float = Field(default=10.0, ge=0.1, le=60.0)


class ConsoleNotificationSettings(BaseSettings):
    """Console notification settings."""

    model_config = SettingsConfigDict(extra="ignore")

    enabled: bool = True


class TrackingSettings(BaseSettings):
    """Configuration for trade tracking (polling)."""

    model_config = SettingsConfigDict(extra="ignore")

    # Raw string from env so pydantic-settings does not try to JSON-decode it (list[str] would trigger json.loads).
    target_wallets_raw: str = Field(
        default="",
        description="Wallet addresses to track, comma-separated. Env: TRACKING__TARGET_WALLETS.",
        validation_alias="target_wallets",
    )
    poll_seconds: float = Field(
        default=3.0,
        ge=0.5,
        le=60.0,
        description="Polling interval in seconds for trade tracking.",
    )
    trades_limit: int = Field(
        default=20,
        ge=1,
        le=500,
        description="Number of trades to fetch per poll.",
    )
    gamma_batch_size: int = Field(
        default=50,
        ge=1,
        le=200,
        description="Batch size for Gamma API condition_id lookups.",
    )
    enable_gamma_lookup: bool = Field(
        default=True,
        description="Whether to resolve condition_id to market_id/title via Gamma API.",
    )

    @computed_field
    @property
    def target_wallets(self) -> list[str]:
        """Parse comma-separated target_wallets_raw into list of stripped strings."""
        if not self.target_wallets_raw or not self.target_wallets_raw.strip():
            return []
        return [s.strip() for s in self.target_wallets_raw.split(",") if s.strip()]


class Settings(BaseSettings):
    """Root application configuration.

    Groups all sub-configurations so the rest of the code does not
    read environment variables directly. Nested overrides use
    <section>__<key>, e.g. LOGGING__CONSOLE_LEVEL, API__DATA_API_HOST.
    """

    model_config = SettingsConfigDict(
        env_nested_delimiter="__",
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        frozen=True,
    )

    app: AppSettings = Field(default_factory=AppSettings)
    logging: LoggingSettings = Field(default_factory=LoggingSettings)
    api: ApiSettings = Field(default_factory=ApiSettings)
    tracking: TrackingSettings = Field(default_factory=TrackingSettings)
    polymarket: PolymarketClobSettings = Field(default_factory=PolymarketClobSettings)
    telegram: TelegramNotificationSettings = Field(default_factory=TelegramNotificationSettings)
    console: ConsoleNotificationSettings = Field(default_factory=ConsoleNotificationSettings)

    @classmethod
    def from_env(cls, **overrides: Any) -> Settings:
        """Build settings from environment (and .env), with optional overrides.

        Nested overrides can be passed as flat keys or nested dicts, e.g.:
        - from_env(api__timeout_seconds=30)
        - from_env(api={"timeout_seconds": 30})

        Returns:
            A new Settings instance.
        """
        return cls(**overrides)


@lru_cache
def get_settings() -> Settings:
    """Return a single cached instance of Settings.

    Typical usage:

        from polymarket_copy_trading.config import get_settings

        settings = get_settings()
        timeout = settings.api.timeout_seconds
        console_level = settings.logging.console_level
    """
    return Settings()
