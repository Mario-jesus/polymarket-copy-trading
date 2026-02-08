# -*- coding: utf-8 -*-
"""Base notification strategy."""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import TYPE_CHECKING

from polymarket_copy_trading.notifications.types import NotificationMessage

if TYPE_CHECKING:  # pragma: no cover
    from polymarket_copy_trading.config.config import Settings


class BaseNotificationStrategy(ABC):
    """Abstract base class for notification strategies."""

    def __init__(self, settings: "Settings"):
        """
        Initialize the base strategy.

        Args:
            settings: Global configuration (Settings).
        """
        self.settings = settings

    @property
    @abstractmethod
    def is_running(self) -> bool:
        """Indicates whether the strategy is running."""
        pass

    @abstractmethod
    async def initialize(self) -> None:
        """Initializes the strategy."""
        pass

    @abstractmethod
    async def shutdown(self) -> None:
        """Shuts down the strategy."""
        pass

    @abstractmethod
    async def send_notification(
        self,
        message: NotificationMessage,
    ) -> None:
        """
        Sends a notification.

        Args:
            message: Notification message to send (NotificationMessage).
        """
        pass
