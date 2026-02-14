"""Abstract interface for seen trade storage (in-memory, DB, etc.)."""

from __future__ import annotations

from abc import ABC, abstractmethod

from polymarket_copy_trading.models.seen_trade import SeenTrade


class ISeenTradeRepository(ABC):
    """Interface for persisting SeenTrade (deduplication of processed trades)."""

    @abstractmethod
    async def contains(self, wallet: str, trade_key: str) -> bool:
        """Return True if (wallet, trade_key) has been seen."""
        ...

    @abstractmethod
    async def add(self, seen_trade: SeenTrade) -> None:
        """Record that a trade has been seen. Idempotent (re-adding same key is no-op)."""
        ...

    async def add_batch(self, seen_trades: list[SeenTrade]) -> None:
        """Record multiple trades. Default impl calls add() for each."""
        for st in seen_trades:
            await self.add(st)
