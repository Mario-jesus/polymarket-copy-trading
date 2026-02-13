# -*- coding: utf-8 -*-
"""In-memory tracking repository (keyed by tracked_wallet, asset)."""

from __future__ import annotations

from typing import Optional

from polymarket_copy_trading.models.tracking_ledger import TrackingLedger
from polymarket_copy_trading.persistence.repositories.interfaces.tracking_repository import (
    ITrackingRepository,
)


def _key(wallet: str, asset: str) -> tuple[str, str]:
    return (wallet.strip(), asset.strip())


class InMemoryTrackingRepository(ITrackingRepository):
    """In-memory implementation of ITrackingRepository."""

    def __init__(self) -> None:
        """Initialize an empty in-memory store."""
        self._store: dict[tuple[str, str], TrackingLedger] = {}

    async def get(
        self,
        tracked_wallet: str,
        asset: str,
    ) -> Optional[TrackingLedger]:
        """Return the ledger for (wallet, asset), or None if missing."""
        return self._store.get(_key(tracked_wallet, asset))

    async def get_or_create(
        self,
        tracked_wallet: str,
        asset: str,
    ) -> TrackingLedger:
        """Return existing ledger or create one with snapshot_t0=0 and post_tracking=0."""
        k = _key(tracked_wallet, asset)
        if k in self._store:
            return self._store[k]
        ledger = TrackingLedger.create(
            tracked_wallet=tracked_wallet,
            asset=asset,
        )
        self._store[k] = ledger
        return ledger

    async def save(self, ledger: TrackingLedger) -> None:
        """Upsert a ledger (by tracked_wallet, asset)."""
        k = _key(ledger.tracked_wallet, ledger.asset)
        self._store[k] = ledger

    async def list_by_wallet(self, tracked_wallet: str) -> list[TrackingLedger]:
        """Return all ledgers for the given tracked wallet."""
        return [ledger for (w, _), ledger in self._store.items() if w == tracked_wallet.strip()]
