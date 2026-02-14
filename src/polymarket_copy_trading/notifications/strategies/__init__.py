"""Notification strategies."""

from polymarket_copy_trading.notifications.strategies.base import (
    BaseNotificationStrategy,
)
from polymarket_copy_trading.notifications.strategies.console import ConsoleNotifier
from polymarket_copy_trading.notifications.strategies.telegram import TelegramNotifier

__all__ = [
    "BaseNotificationStrategy",
    "ConsoleNotifier",
    "TelegramNotifier",
]
