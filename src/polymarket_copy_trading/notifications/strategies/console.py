# -*- coding: utf-8 -*-
"""Console notifier (print-based)."""

from __future__ import annotations

from typing import TYPE_CHECKING

from polymarket_copy_trading.notifications.types import NotificationMessage
from polymarket_copy_trading.notifications.strategies.base import BaseNotificationStrategy
from polymarket_copy_trading.config import Settings

if TYPE_CHECKING:  # pragma: no cover
    from polymarket_copy_trading.notifications.types import NotificationStyler


class ConsoleNotifier(BaseNotificationStrategy):
    """Print notifications to stdout."""

    def __init__(
        self,
        settings: "Settings",
        styler: "NotificationStyler"
    ) -> None:
        super().__init__(settings)
        self._running = False
        self._styler = styler

    @property
    def is_running(self) -> bool:
        return self._running

    async def initialize(self) -> None:
        self._running = True

    async def shutdown(self) -> None:
        self._running = False

    async def send_notification(self, message: NotificationMessage) -> None:
        """Send a notification to the console."""
        if not self.is_running or not self.settings.console.enabled:
            return
        body = self._styler.render(message) if self._styler else message.message
        print(body)
