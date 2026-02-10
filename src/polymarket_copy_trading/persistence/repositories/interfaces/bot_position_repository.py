# -*- coding: utf-8 -*-
"""Abstract interface for bot position storage (in-memory, DB, etc.)."""

from __future__ import annotations

from abc import ABC, abstractmethod
from datetime import datetime
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
        """Return open positions for the given tracked wallet, ordered by entry_step_level."""
        ...

    @abstractmethod
    def list_open_by_ledger(self, ledger_id: UUID) -> list[BotPosition]:
        """Return open positions for the given ledger (same market-outcome), ordered by entry_step_level."""
        ...

    def mark_closed(self, position_id: UUID, closed_at: datetime | None = None) -> Optional[BotPosition]:
        """Load position by id, set status CLOSED and closed_at, save and return updated. None if not found."""
        position = self.get(position_id)
        if position is None or not position.is_open:
            return position
        updated = position.with_closed(closed_at)
        self.save(updated)
        return updated
