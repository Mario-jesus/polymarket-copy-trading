# -*- coding: utf-8 -*-
"""Abstract interface for bot position storage (in-memory, DB, etc.)."""

from __future__ import annotations

from abc import ABC, abstractmethod
from datetime import datetime
from decimal import Decimal
from typing import Optional
from uuid import UUID

from polymarket_copy_trading.models.bot_position import BotPosition


class IBotPositionRepository(ABC):
    """Interface for persisting BotPosition (open/closed positions of the bot)."""

    @abstractmethod
    def get(self, position_id: UUID) -> Optional[BotPosition]:
        """Return the position by id, or None if missing."""
        ...

    @abstractmethod
    def save(self, position: BotPosition) -> None:
        """Insert or update a position (by id)."""
        ...

    @abstractmethod
    def list_by_wallet(self, tracked_wallet: str) -> list[BotPosition]:
        """Return all positions for the given tracked wallet (any status)."""
        ...

    @abstractmethod
    def list_open_by_wallet(self, tracked_wallet: str) -> list[BotPosition]:
        """Return open positions for the given tracked wallet, ordered by opened_at (FIFO)."""
        ...

    @abstractmethod
    def list_open_by_ledger(self, ledger_id: UUID) -> list[BotPosition]:
        """Return open positions for the given ledger, ordered by opened_at (FIFO, oldest first)."""
        ...

    @abstractmethod
    def mark_closed(
        self,
        position_id: UUID,
        closed_at: datetime | None = None,
        close_proceeds_usdc: Decimal | None = None,
        close_fees: Decimal | None = None,
    ) -> Optional[BotPosition]:
        """Load position by id, set status CLOSED and closed_at (and optional PnL fields), save and return updated. None if not found."""
        ...
