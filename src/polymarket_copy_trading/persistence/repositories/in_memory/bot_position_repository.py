# -*- coding: utf-8 -*-
"""In-memory bot position repository (keyed by position id)."""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Optional
from uuid import UUID

from polymarket_copy_trading.models.bot_position import BotPosition
from polymarket_copy_trading.persistence.repositories.interfaces.bot_position_repository import (
    IBotPositionRepository,
)


def _by_opened_at(position: BotPosition) -> str:
    """Sort key: opened_at (FIFO = oldest first)."""
    return position.opened_at.isoformat()


class InMemoryBotPositionRepository(IBotPositionRepository):
    """In-memory implementation of IBotPositionRepository."""

    def __init__(self) -> None:
        """Initialize an empty in-memory store."""
        self._store: dict[UUID, BotPosition] = {}

    async def get(self, position_id: UUID) -> Optional[BotPosition]:
        """Return the position by id, or None if missing."""
        return self._store.get(position_id)

    async def save(self, position: BotPosition) -> None:
        """Insert or update a position (by id)."""
        self._store[position.id] = position

    async def list_by_wallet(self, tracked_wallet: str) -> list[BotPosition]:
        """Return all positions for the given tracked wallet (any status), ordered by opened_at (FIFO)."""
        return sorted(
            (p for p in self._store.values() if p.tracked_wallet == tracked_wallet),
            key=_by_opened_at,
        )

    async def list_open_by_wallet(self, tracked_wallet: str) -> list[BotPosition]:
        """Return open positions for the given tracked wallet, ordered by opened_at (FIFO)."""
        return sorted(
            (p for p in self._store.values() if p.tracked_wallet == tracked_wallet and p.is_open),
            key=_by_opened_at,
        )

    async def list_open_by_ledger(self, ledger_id: UUID) -> list[BotPosition]:
        """Return open positions for the given ledger, ordered by opened_at (FIFO, oldest first)."""
        return sorted(
            (p for p in self._store.values() if p.ledger_id == ledger_id and p.is_open),
            key=_by_opened_at,
        )

    async def mark_closed(
        self,
        position_id: UUID,
        closed_at: Optional[datetime] = None,
        close_proceeds_usdc: Optional[Decimal] = None,
        close_fees: Optional[Decimal] = None,
    ) -> Optional[BotPosition]:
        """Load position by id, set status CLOSED with optional closed_at and PnL fields, save and return updated."""
        position = await self.get(position_id)
        if position is None or not position.is_open:
            return position
        updated = position.with_closed(
            closed_at=closed_at,
            close_proceeds_usdc=close_proceeds_usdc,
            close_fees=close_fees,
        )
        await self.save(updated)
        return updated

    async def update_closed_pnl(
        self,
        position_id: UUID,
        close_proceeds_usdc: Decimal,
        close_fees: Decimal,
    ) -> Optional[BotPosition]:
        """Update a CLOSED position with real close amounts."""
        position = await self.get(position_id)
        if position is None or position.is_open:
            return None
        updated = position.with_close_proceeds_updated(close_proceeds_usdc, close_fees)
        await self.save(updated)
        return updated
