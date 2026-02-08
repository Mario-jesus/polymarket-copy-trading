# -*- coding: utf-8 -*-
"""Telegram notification strategy (async)."""

from __future__ import annotations

import asyncio
import time
import structlog
from typing import Any, Callable, Optional, TYPE_CHECKING

from telegram import Bot
from telegram.error import (
    BadRequest,
    Forbidden,
    NetworkError,
    RetryAfter,
    TelegramError,
    TimedOut,
)
from telegram.request import HTTPXRequest

from polymarket_copy_trading.notifications.types import NotificationMessage
from polymarket_copy_trading.notifications.strategies.base import BaseNotificationStrategy

if TYPE_CHECKING:
    from polymarket_copy_trading.config.config import Settings
    from polymarket_copy_trading.notifications.types import NotificationStyler


class TelegramNotifier(BaseNotificationStrategy):
    """Send notifications to Telegram using python-telegram-bot."""

    def __init__(
        self,
        settings: "Settings",
        styler: "NotificationStyler",
        *,
        get_logger: Callable[[str], Any] = structlog.get_logger,
        logger_name: Optional[str] = None,
    ) -> None:
        super().__init__(settings)
        self._logger = get_logger(logger_name or self.__class__.__name__)
        self._styler: "NotificationStyler" = styler

        cfg = self.settings.telegram
        token = cfg.api_key
        chat_id = cfg.chat_id
        if not cfg.enabled or not token or not chat_id:
            raise ValueError("TelegramNotifier requires token and chat_id.")

        self.token: str = str(token)
        self.chat_id: str = str(chat_id)
        self.messages_per_minute = cfg.messages_per_minute
        self.max_retries = cfg.max_retries
        self.backoff_base_seconds = cfg.backoff_base_seconds
        self.queue_size = cfg.queue_size

        self.connect_timeout = cfg.connect_timeout
        self.read_timeout = cfg.read_timeout
        self.write_timeout = cfg.write_timeout
        self.pool_timeout = cfg.pool_timeout

        self._bot: Optional[Bot] = None
        self._running = False
        self._message_timestamps: list[float] = []

    @property
    def is_running(self) -> bool:
        return self._running

    async def initialize(self) -> None:
        if not self.settings.telegram.enabled:
            return
        if self._running:
            self._logger.warning("telegram_already_running")
            return

        try:
            request = HTTPXRequest(
                connect_timeout=self.connect_timeout,
                read_timeout=self.read_timeout,
                write_timeout=self.write_timeout,
                pool_timeout=self.pool_timeout,
            )
            self._bot = Bot(token=self.token, request=request)
        except Exception as exc:  # pragma: no cover - fallback path
            self._logger.warning(
                "telegram_http_request_fallback",
                error_type=type(exc).__name__,
                error_message=str(exc),
            )
            self._bot = Bot(token=self.token)

        self._running = True

    async def shutdown(self) -> None:
        if not self._running:
            return

        self._bot = None
        self._running = False

    async def send_notification(self, message: NotificationMessage) -> None:
        if not self.settings.telegram.enabled:
            return
        if not self._running:
            self._logger.warning("telegram_not_running_cannot_send")
            return

        formatted = self._styler.render(message)
        await self._send_message(formatted)

    async def _send_message(self, message: str) -> None:
        if self._bot is None:
            self._logger.error("telegram_bot_not_initialized")
            return

        await self._apply_rate_limit()
        attempt = 1
        while attempt <= self.max_retries:
            try:
                await self._bot.send_message(
                    chat_id=self.chat_id,
                    text=message,
                    parse_mode="HTML",
                )
                self._message_timestamps.append(time.time())
                return
            except RetryAfter as exc:
                retry_seconds = float(getattr(exc, "retry_after", 1.0))
                self._logger.warning(
                    "telegram_rate_limit_retry_after",
                    retry_seconds=retry_seconds,
                )
                await asyncio.sleep(retry_seconds)
            except (NetworkError, TimedOut) as exc:
                backoff = min(60.0, self.backoff_base_seconds * (2 ** (attempt - 1)))
                self._logger.warning(
                    "telegram_network_error_retry",
                    error_type=type(exc).__name__,
                    attempt=attempt,
                    max_retries=self.max_retries,
                    backoff_seconds=backoff,
                )
                await asyncio.sleep(backoff)
            except (BadRequest, Forbidden) as exc:
                self._logger.error(
                    "telegram_fatal_error",
                    error_type=type(exc).__name__,
                    error_message=str(exc),
                )
                return
            except TelegramError as exc:
                backoff = min(60.0, self.backoff_base_seconds * (2 ** (attempt - 1)))
                self._logger.warning(
                    "telegram_error_retry",
                    error_type=type(exc).__name__,
                    attempt=attempt,
                    max_retries=self.max_retries,
                    backoff_seconds=backoff,
                )
                await asyncio.sleep(backoff)
            except Exception as exc:  # pragma: no cover
                backoff = min(60.0, self.backoff_base_seconds * (2 ** (attempt - 1)))
                self._logger.warning(
                    "telegram_unexpected_error_retry",
                    error_type=type(exc).__name__,
                    attempt=attempt,
                    max_retries=self.max_retries,
                    backoff_seconds=backoff,
                )
                await asyncio.sleep(backoff)
            attempt += 1

        self._logger.error("telegram_max_retries_exceeded_message_dropped")

    async def _apply_rate_limit(self) -> None:
        if self.messages_per_minute <= 0:
            return

        now = time.time()
        window_start = now - 60
        self._message_timestamps = [t for t in self._message_timestamps if t >= window_start]
        if len(self._message_timestamps) >= self.messages_per_minute:
            sleep_time = 60 - (now - self._message_timestamps[0])
            if sleep_time > 0:
                await asyncio.sleep(sleep_time)
