"""Notification subsystem."""

from polymarket_copy_trading.notifications.notification_manager import (
    NotificationService,
)
from polymarket_copy_trading.notifications.strategies import (
    BaseNotificationStrategy,
    ConsoleNotifier,
    TelegramNotifier,
)
from polymarket_copy_trading.notifications.types import (
    NotificationMessage,
    NotificationStyler,
)

__all__ = [
    "BaseNotificationStrategy",
    "ConsoleNotifier",
    "TelegramNotifier",
    "NotificationMessage",
    "NotificationService",
    "NotificationStyler",
]
