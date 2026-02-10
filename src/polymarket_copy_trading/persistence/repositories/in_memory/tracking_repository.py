# -*- coding: utf-8 -*-
"""In-memory tracking repository (keyed by wallet, condition_id, outcome)."""

from __future__ import annotations

from typing import Optional

from polymarket_copy_trading.models.tracking_ledger import TrackingLedger
from polymarket_copy_trading.persistence.repositories.interfaces.tracking_repository import (
    ITrackingRepository,
)


def _key(wallet: str, condition_id: str, outcome: str) -> tuple[str, str, str]:
    return (wallet, condition_id, outcome)


class InMemoryTrackingRepository(ITrackingRepository):
    """In-memory implementation of ITrackingRepository."""

    def __init__(self) -> None:
        """Initialize an empty in-memory store."""
        self._store: dict[tuple[str, str, str], TrackingLedger] = {}

    def get(
        self,
        tracked_wallet: str,
        condition_id: str,
        outcome: str,
    ) -> Optional[TrackingLedger]:
        """Return the ledger for (wallet, condition_id, outcome), or None if missing."""
        return self._store.get(_key(tracked_wallet, condition_id, outcome))

    def get_or_create(
        self,
        tracked_wallet: str,
        condition_id: str,
        outcome: str,
    ) -> TrackingLedger:
        """Return existing ledger or create one with snapshot_t0=0 and post_tracking=0."""
        k = _key(tracked_wallet, condition_id, outcome)
        if k in self._store:
            return self._store[k]
        ledger = TrackingLedger.create(
            tracked_wallet=tracked_wallet,
            condition_id=condition_id,
            outcome=outcome,
        )
        self._store[k] = ledger
        return ledger

    def save(self, ledger: TrackingLedger) -> None:
        """Upsert a ledger (by tracked_wallet, condition_id, outcome)."""
        k = _key(ledger.tracked_wallet, ledger.condition_id, ledger.outcome)
        self._store[k] = ledger

    def list_by_wallet(self, tracked_wallet: str) -> list[TrackingLedger]:
        """Return all ledgers for the given tracked wallet."""
        return [ledger for (w, _, _), ledger in self._store.items() if w == tracked_wallet]
