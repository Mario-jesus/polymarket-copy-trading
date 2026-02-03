# -*- coding: utf-8 -*-
"""Logging configuration for structlog + Logfire."""

from __future__ import annotations

import logging
import logfire
import structlog
from typing import Any
from structlog.types import EventDict, Processor
from logging.handlers import TimedRotatingFileHandler
from pathlib import Path

from polymarket_copy_trading.config import get_settings

# Map standard logging levels to Logfire levels
LOG_LEVEL_TO_LOGFIRE: dict[str, str] = {
    "DEBUG": "debug",
    "INFO": "info",
    "WARNING": "warn",
    "ERROR": "error",
    "CRITICAL": "fatal",
}


def _add_service_context(logger: Any, method_name: str, event_dict: EventDict) -> EventDict:
    """Attach logger name, service_name, service_version and environment to every log event."""
    stdlib_logger = getattr(logger, "_logger", None)
    event_dict["logger"] = (
        getattr(stdlib_logger, "name", None) or getattr(logger, "name", "") or ""
    )
    app_settings = get_settings().app
    event_dict["app_name"] = app_settings.app_name
    if app_settings.service_name:
        event_dict["service_name"] = app_settings.service_name
    if app_settings.service_version:
        event_dict["service_version"] = app_settings.service_version
    event_dict["environment"] = app_settings.environment
    return event_dict


def configure_logging() -> None:
    """Configure structlog + Logfire using settings."""
    app_settings = get_settings().app
    logging_settings = get_settings().logging

    handlers: list[logging.Handler] = []
    enabled_levels: list[int] = []

    if logging_settings.log_to_console:
        console_level = getattr(
            logging, logging_settings.console_level.upper(), logging.INFO
        )
        console_handler = logging.StreamHandler()
        console_handler.setLevel(console_level)
        console_handler.setFormatter(logging.Formatter("%(message)s"))
        handlers.append(console_handler)
        enabled_levels.append(console_level)

    if logging_settings.log_to_file:
        file_level = getattr(logging, logging_settings.file_level.upper(), logging.INFO)
        log_file_path = Path(logging_settings.log_file_path)
        log_file_path.parent.mkdir(parents=True, exist_ok=True)
        file_handler = TimedRotatingFileHandler(
            log_file_path,
            when=logging_settings.log_file_when,
            interval=logging_settings.log_file_interval,
            backupCount=logging_settings.log_file_backup_count,
            encoding="utf-8",
            utc=logging_settings.log_file_utc,
        )
        file_handler.setLevel(file_level)
        file_handler.setFormatter(logging.Formatter("%(message)s"))
        handlers.append(file_handler)
        enabled_levels.append(file_level)

    if handlers:
        logging.basicConfig(level=min(enabled_levels), handlers=handlers)

    # Configure Logfire only if enabled
    if logging_settings.logfire_enabled:
        logfire_min_level = LOG_LEVEL_TO_LOGFIRE.get(
            logging_settings.logfire_level, "info"
        )

        logfire.configure(
            token=logging_settings.logfire_token,
            service_name=app_settings.service_name or app_settings.app_name,
            service_version=app_settings.service_version,
            min_level=logfire_min_level, # type: ignore[arg-type]
            environment=app_settings.environment
        )

    # Build processor chain
    processors: list[Processor] = [
        # Filter by level first (before processing)
        structlog.stdlib.filter_by_level,
        structlog.contextvars.merge_contextvars,
        structlog.processors.add_log_level,
        structlog.processors.StackInfoRenderer(),
        structlog.dev.set_exc_info,
        structlog.processors.TimeStamper(fmt="iso", utc=True),
        _add_service_context,  # Add service context to all logs
    ]

    # Add Logfire processor only if enabled
    if logging_settings.logfire_enabled:
        processors.append(logfire.StructlogProcessor())  # type: ignore[arg-type]

    # Add renderer if any stdlib handlers are enabled.
    # File output is always structured JSON; console uses json_format unless file is also enabled.
    if logging_settings.log_to_console or logging_settings.log_to_file:
        use_json = (
            logging_settings.log_to_file  # file always JSON
            or logging_settings.json_format
        )
        renderer: Any = (
            structlog.processors.JSONRenderer()
            if use_json
            else structlog.dev.ConsoleRenderer()
        )
        processors.append(renderer)  # type: ignore[arg-type]

    structlog.configure(
        processors=processors,
        wrapper_class=structlog.stdlib.BoundLogger,
        context_class=dict,
        logger_factory=structlog.stdlib.LoggerFactory(),
        cache_logger_on_first_use=True,
    )
