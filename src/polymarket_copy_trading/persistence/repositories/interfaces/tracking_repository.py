# -*- coding: utf-8 -*-
"""Abstract interface for tracking ledger storage (in-memory, DB, etc.)."""

from __future__ import annotations

from abc import ABC, abstractmethod
from decimal import Decimal
from typing import Optional

from polymarket_copy_trading.models.tracking_ledger import TrackingLedger


class ITrackingRepository(ABC):
    """Interface for persisting TrackingLedger by (tracked_wallet, condition_id, outcome)."""

    @abstractmethod
    def get(
        self,
        tracked_wallet: str,
        condition_id: str,
        outcome: str,
    ) -> Optional[TrackingLedger]:
        """Return the ledger for (wallet, condition_id, outcome), or None if missing."""
        ...

    @abstractmethod
    def get_or_create(
        self,
        tracked_wallet: str,
        condition_id: str,
        outcome: str,
    ) -> TrackingLedger:
        """Return existing ledger or create one with snapshot_t0=0 and post_tracking=0."""
        ...

    @abstractmethod
    def save(self, ledger: TrackingLedger) -> None:
        """Upsert a ledger (by tracked_wallet, condition_id, outcome)."""
        ...

    @abstractmethod
    def list_by_wallet(self, tracked_wallet: str) -> list[TrackingLedger]:
        """Return all ledgers for the given tracked wallet."""
        ...

    # -------------------------------------------------------------------------
    # Convenience: update snapshot_t0 or post_tracking then save (ledger is immutable)
    # -------------------------------------------------------------------------

    def update_snapshot_t0(
        self,
        tracked_wallet: str,
        condition_id: str,
        outcome: str,
        new_snapshot: Decimal,
    ) -> TrackingLedger:
        """Get-or-create ledger, set snapshot_t0_shares to new_snapshot, save and return updated."""
        ledger = self.get_or_create(tracked_wallet, condition_id, outcome)
        updated = ledger.with_snapshot_t0(new_snapshot)
        self.save(updated)
        return updated

    def update_post_tracking(
        self,
        tracked_wallet: str,
        condition_id: str,
        outcome: str,
        new_post_tracking: Decimal,
    ) -> TrackingLedger:
        """Get-or-create ledger, set post_tracking_shares to new_post_tracking, save and return updated."""
        ledger = self.get_or_create(tracked_wallet, condition_id, outcome)
        updated = ledger.with_post_tracking(new_post_tracking)
        self.save(updated)
        return updated

    def add_post_tracking_delta(
        self,
        tracked_wallet: str,
        condition_id: str,
        outcome: str,
        delta: Decimal,
    ) -> TrackingLedger:
        """Get-or-create ledger, add delta to post_tracking_shares (e.g. +size BUY, -size SELL), save and return."""
        ledger = self.get_or_create(tracked_wallet, condition_id, outcome)
        updated = ledger.add_post_tracking_delta(delta)
        self.save(updated)
        return updated
