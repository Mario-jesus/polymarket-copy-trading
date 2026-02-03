# -*- coding: utf-8 -*-
"""Estrategia base de notificación."""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import TYPE_CHECKING

from polymarket_copy_trading.notifications.types import NotificationMessage

if TYPE_CHECKING:  # pragma: no cover
    from polymarket_copy_trading.config.config import Settings


class BaseNotificationStrategy(ABC):
    """Clase base abstracta para estrategias de notificación."""

    def __init__(self, settings: "Settings"):
        """
        Inicializa la estrategia base

        Args:
            settings: Configuración global (Settings).
        """
        self.settings = settings

    @property
    @abstractmethod
    def is_running(self) -> bool:
        """Indica si la estrategia está corriendo"""
        pass

    @abstractmethod
    async def initialize(self) -> None:
        """Inicializa la estrategia"""
        pass

    @abstractmethod
    async def shutdown(self) -> None:
        """Cierra la estrategia"""
        pass

    @abstractmethod
    async def send_notification(
        self,
        message: NotificationMessage,
    ) -> None:
        """
        Envía una notificación

        Args:
            message: Mensaje a enviar (NotificationMessage)
        """
        pass
