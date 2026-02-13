# -*- coding: utf-8 -*-
"""Configuration loaded from environment via Pydantic Settings.

Nested env vars use <section>__<key>, e.g. LOGGING__CONSOLE_LEVEL, API__DATA_API_HOST.
"""

from __future__ import annotations

from functools import lru_cache
from typing import Any, Literal, Optional

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class AppSettings(BaseSettings):
    """General application configuration."""

    model_config = SettingsConfigDict(extra="ignore")

    app_name: str = Field(default="polymarket-copy-trading", description="Application name.")
    service_name: Optional[str] = Field(default=None, description="Service name.")
    service_version: Optional[str] = Field(default=None, description="Service version.")
    environment: Literal["development", "test", "production"] = Field(
        default="development",
        description="Environment (development, test, production).",
    )


class LoggingSettings(BaseSettings):
    """Structured logging configuration for structlog/stdlib/Logfire."""

    model_config = SettingsConfigDict(extra="ignore")

    # Per-target levels (only the 5 standard levels)
    console_level: Literal["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"] = Field(
        default="INFO", description="Console log level."
    )
    file_level: Literal["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"] = Field(
        default="INFO", description="File log level."
    )
    logfire_level: Literal["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"] = Field(
        default="INFO", description="Logfire log level."
    )

    # Local outputs
    log_to_console: bool = Field(default=True, description="Whether to log to console.")
    log_to_file: bool = Field(default=False, description="Whether to log to file.")
    log_file_path: str = Field(
        default="logs/copy_trading.log",
        description="Path to log file.",
    )
    # TimedRotatingFileHandler: when to rotate (S/M/H/D/W0–W6/midnight), interval, backups to keep
    log_file_when: Literal[
        "S", "M", "H", "D", "W0", "W1", "W2", "W3", "W4", "W5", "W6", "midnight"
    ] = Field(default="midnight", description="Log rotation interval (e.g. midnight, H, D).")
    log_file_interval: int = Field(default=1, description="Number of intervals between rotations.")
    log_file_backup_count: int = Field(default=30, description="Number of backup log files to keep.")
    log_file_utc: bool = Field(default=True, description="Use UTC for log file timestamps.")

    # Main output format: JSONRenderer if True, ConsoleRenderer if False
    json_format: bool = Field(
        default=False,
        description="Use JSON format for log output (else ConsoleRenderer).",
    )

    # Logfire integration via structlog
    logfire_enabled: bool = Field(default=False, description="Enable Logfire integration.")
    logfire_token: Optional[str] = Field(default=None, description="Logfire token.")


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
    polygon_rpc_url: str = Field(
        default="https://polygon-rpc.com",
        description="Polygon RPC endpoint for JSON-RPC (eth_call, etc.). Env: API__POLYGON_RPC_URL.",
    )
    polygon_usdc_e_address: str = Field(
        default="0x2791Bca1f2de4661ED88A30C99A7a9449Aa84174",
        description="USDC.e (bridged) contract address on Polygon. Env: API__POLYGON_USDC_E_ADDRESS.",
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
    private_key: str = Field(..., description="Wallet private key.")
    api_key: str = Field(..., description="Polymarket API key.")
    api_secret: str = Field(..., description="Polymarket API secret.")
    api_passphrase: str = Field(..., description="Polymarket API passphrase.")
    funder: str = Field(..., description="Proxy wallet address (Wallet Address in Polymarket UI).")
    signer: Optional[str] = Field(default=None, description="Signer address (EOA that signs orders).")


class TelegramNotificationSettings(BaseSettings):
    """Telegram notifications (from env TELEGRAM__*)."""

    model_config = SettingsConfigDict(extra="ignore")

    enabled: bool = Field(default=False, description="Enable Telegram notifications.")
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

    enabled: bool = Field(default=True, description="Enable console notifications.")


class OrderExecutionSettings(BaseSettings):
    """Order execution configuration (from env ORDER_EXECUTION__*)."""

    model_config = SettingsConfigDict(extra="ignore")

    minimum_amount: float = Field(
        default=1.0,
        ge=0.01,
        le=1_000_000.0,
        description="Minimum USDC amount for place_buy_minimum (default $1).",
    )


class StrategySettings(BaseSettings):
    """Copy-trading strategy: sizing, open/close thresholds (from env STRATEGY__*)."""

    model_config = SettingsConfigDict(extra="ignore")

    fixed_position_amount_usdc: float = Field(
        default=10.0,
        ge=0.01,
        description="Amount in USDC to invest per bot position (each open uses this size). Env: STRATEGY__FIXED_POSITION_AMOUNT_USDC.",
    )
    max_positions_per_ledger: int = Field(
        default=5,
        ge=1,
        le=100,
        description="Maximum open BotPositions per ledger (per asset). Env: STRATEGY__MAX_POSITIONS_PER_LEDGER.",
    )
    max_active_ledgers: int = Field(
        default=10,
        ge=1,
        le=500,
        description="Maximum number of assets (ledgers) that can be traded at once per wallet. If 5, only 5 assets may have open positions. Env: STRATEGY__MAX_ACTIVE_LEDGERS.",
    )
    asset_min_position_percent: float = Field(
        default=0.0,
        ge=0.0,
        le=100.0,
        description="Minimum post-tracking exposure as % of account total value to consider opening (0 = disabled). Env: STRATEGY__ASSET_MIN_POSITION_PERCENT.",
    )
    asset_min_position_shares: float = Field(
        default=0.0,
        ge=0.0,
        description="Minimum post-tracking shares for the asset to consider opening. Env: STRATEGY__ASSET_MIN_POSITION_SHARES.",
    )
    close_total_threshold_pct: float = Field(
        default=80.0,
        ge=0.0,
        le=100.0,
        description="When trader has closed this % of post-tracking (per stage), bot closes positions progressively. E.g. 80 = 80%%. Env: STRATEGY__CLOSE_TOTAL_THRESHOLD_PCT.",
    )


class OrderAnalysisSettings(BaseSettings):
    """Configuration for OrderAnalysisWorker (reconcile placed orders with CLOB trades)."""

    model_config = SettingsConfigDict(extra="ignore")

    queue_size: int = Field(
        default=500,
        ge=1,
        le=5000,
        description="Max size of the pending-orders queue (orders waiting for trade confirmation). Env: ORDER_ANALYSIS__QUEUE_SIZE.",
    )
    poll_interval_sec: float = Field(
        default=2.0,
        ge=0.5,
        le=60.0,
        description="Polling interval in seconds when waiting for trade to appear in get_trades. Env: ORDER_ANALYSIS__POLL_INTERVAL_SEC.",
    )
    max_attempts: int = Field(
        default=30,
        ge=1,
        le=120,
        description="Max polling attempts before giving up on a trade. Env: ORDER_ANALYSIS__MAX_ATTEMPTS.",
    )


class TrackingSettings(BaseSettings):
    """Configuration for trade tracking (polling)."""

    model_config = SettingsConfigDict(extra="ignore")

    target_wallet: str = Field(
        default="",
        description="Wallet address to track (single wallet). Env: TRACKING__TARGET_WALLET (or TRACKING__TARGET_WALLETS).",
        validation_alias="target_wallets",
    )

    @field_validator("target_wallet", mode="before")
    @classmethod
    def _take_first_wallet(cls, v: object) -> str:
        """If comma-separated (legacy), take only the first wallet."""
        if not v or not isinstance(v, str):
            return ""
        s = v.strip()
        if "," in s:
            s = s.split(",")[0].strip()
        return s

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
    queue_size: int = Field(
        default=1000,
        ge=1,
        le=5000,
        description="Max size of the trade queue (tracker -> consumer).",
    )


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

    app: AppSettings = Field(
        default_factory=AppSettings,
        description="General application configuration.",
    )
    logging: LoggingSettings = Field(
        default_factory=LoggingSettings,
        description="Structured logging configuration.",
    )
    api: ApiSettings = Field(
        default_factory=ApiSettings,
        description="Polymarket Data API and Gamma API configuration.",
    )
    tracking: TrackingSettings = Field(
        default_factory=TrackingSettings,
        description="Trade tracking (polling) configuration.",
    )
    order_analysis: OrderAnalysisSettings = Field(
        default_factory=OrderAnalysisSettings,
        description="Order analysis worker (reconcile orders with CLOB trades).",
    )
    polymarket: PolymarketClobSettings = Field(
        ...,
        description="Polymarket CLOB/trading credentials and wallet.",
    )
    telegram: TelegramNotificationSettings = Field(
        default_factory=TelegramNotificationSettings,
        description="Telegram notification configuration.",
    )
    console: ConsoleNotificationSettings = Field(
        default_factory=ConsoleNotificationSettings,
        description="Console notification configuration.",
    )
    order_execution: OrderExecutionSettings = Field(
        default_factory=OrderExecutionSettings,
        description="Order execution configuration (e.g. minimum_amount for place_buy_minimum).",
    )
    strategy: StrategySettings = Field(
        default_factory=StrategySettings,
        description="Copy-trading strategy: sizing, open/close thresholds (STRATEGY__*).",
    )

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
    return Settings()  # type: ignore[call-arg]
