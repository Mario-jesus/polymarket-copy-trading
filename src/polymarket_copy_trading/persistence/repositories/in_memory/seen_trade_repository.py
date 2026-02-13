# -*- coding: utf-8 -*-
"""In-memory seen trade repository (keyed by (wallet, trade_key))."""

from __future__ import annotations

from polymarket_copy_trading.models.seen_trade import SeenTrade
from polymarket_copy_trading.persistence.repositories.interfaces.seen_trade_repository import (
    ISeenTradeRepository,
)


def _key(wallet: str, trade_key: str) -> tuple[str, str]:
    """Normalize key for storage."""
    return (wallet.strip(), trade_key.strip())


class InMemorySeenTradeRepository(ISeenTradeRepository):
    """In-memory implementation of ISeenTradeRepository."""

    def __init__(self) -> None:
        """Initialize an empty in-memory store."""
        self._store: dict[tuple[str, str], SeenTrade] = {}

    async def contains(self, wallet: str, trade_key: str) -> bool:
        """Return True if (wallet, trade_key) has been seen."""
        return _key(wallet, trade_key) in self._store

    async def add(self, seen_trade: SeenTrade) -> None:
        """Record that a trade has been seen. Idempotent."""
        k = _key(seen_trade.wallet, seen_trade.trade_key)
        if k not in self._store:
            self._store[k] = seen_trade

    async def add_batch(self, seen_trades: list[SeenTrade]) -> None:
        """Record multiple trades in one pass."""
        for st in seen_trades:
            k = _key(st.wallet, st.trade_key)
            if k not in self._store:
                self._store[k] = st
