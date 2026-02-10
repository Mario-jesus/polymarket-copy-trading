# -*- coding: utf-8 -*-
"""In-memory bot position repository (keyed by position id)."""

from __future__ import annotations

from typing import Optional
from uuid import UUID

from polymarket_copy_trading.models.bot_position import BotPosition
from polymarket_copy_trading.persistence.repositories.interfaces.bot_position_repository import (
    IBotPositionRepository,
)


def _by_step_then_opened(position: BotPosition) -> tuple[int, str]:
    """Sort key: entry_step_level, then opened_at iso for stable order."""
    return (position.entry_step_level, position.opened_at.isoformat())


class InMemoryBotPositionRepository(IBotPositionRepository):
    """In-memory implementation of IBotPositionRepository."""

    def __init__(self) -> None:
        """Initialize an empty in-memory store."""
        self._store: dict[UUID, BotPosition] = {}

    def get(self, position_id: UUID) -> Optional[BotPosition]:
        """Return the position by id, or None if missing."""
        return self._store.get(position_id)

    def save(self, position: BotPosition) -> None:
        """Insert or update a position (by id)."""
        self._store[position.id] = position

    def list_by_wallet(self, tracked_wallet: str) -> list[BotPosition]:
        """Return all positions for the given tracked wallet (any status)."""
        return sorted(
            (p for p in self._store.values() if p.tracked_wallet == tracked_wallet),
            key=_by_step_then_opened,
        )

    def list_open_by_wallet(self, tracked_wallet: str) -> list[BotPosition]:
        """Return open positions for the given tracked wallet, ordered by entry_step_level."""
        return sorted(
            (p for p in self._store.values() if p.tracked_wallet == tracked_wallet and p.is_open),
            key=_by_step_then_opened,
        )

    def list_open_by_ledger(self, ledger_id: UUID) -> list[BotPosition]:
        """Return open positions for the given ledger (same market-outcome), ordered by entry_step_level."""
        return sorted(
            (p for p in self._store.values() if p.ledger_id == ledger_id and p.is_open),
            key=_by_step_then_opened,
        )
