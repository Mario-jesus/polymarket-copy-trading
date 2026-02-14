"""Abstract interface for tracking ledger storage (in-memory, DB, etc.)."""

from __future__ import annotations

from abc import ABC, abstractmethod
from decimal import Decimal

from polymarket_copy_trading.models.tracking_ledger import TrackingLedger


class ITrackingRepository(ABC):
    """Interface for persisting TrackingLedger by (tracked_wallet, asset)."""

    @abstractmethod
    async def get(
        self,
        tracked_wallet: str,
        asset: str,
    ) -> TrackingLedger | None:
        """Return the ledger for (wallet, asset), or None if missing."""
        ...

    @abstractmethod
    async def get_or_create(
        self,
        tracked_wallet: str,
        asset: str,
    ) -> TrackingLedger:
        """Return existing ledger or create one with snapshot_t0=0 and post_tracking=0."""
        ...

    @abstractmethod
    async def save(self, ledger: TrackingLedger) -> None:
        """Upsert a ledger (by tracked_wallet, asset)."""
        ...

    @abstractmethod
    async def list_by_wallet(self, tracked_wallet: str) -> list[TrackingLedger]:
        """Return all ledgers for the given tracked wallet."""
        ...

    # -------------------------------------------------------------------------
    # Convenience: update snapshot_t0 or post_tracking then save (ledger is immutable)
    # -------------------------------------------------------------------------

    async def update_snapshot_t0(
        self,
        tracked_wallet: str,
        asset: str,
        new_snapshot: Decimal,
    ) -> TrackingLedger:
        """Get-or-create ledger, set snapshot_t0_shares to new_snapshot, save and return updated."""
        ledger = await self.get_or_create(tracked_wallet, asset)
        updated = ledger.with_snapshot_t0(new_snapshot)
        await self.save(updated)
        return updated

    async def update_post_tracking(
        self,
        tracked_wallet: str,
        asset: str,
        new_post_tracking: Decimal,
    ) -> TrackingLedger:
        """Get-or-create ledger, set post_tracking_shares to new_post_tracking, save and return updated."""
        ledger = await self.get_or_create(tracked_wallet, asset)
        updated = ledger.with_post_tracking(new_post_tracking)
        await self.save(updated)
        return updated

    async def add_post_tracking_delta(
        self,
        tracked_wallet: str,
        asset: str,
        delta: Decimal,
    ) -> TrackingLedger:
        """Get-or-create ledger, add delta to post_tracking_shares (e.g. +size BUY, -size SELL), save and return."""
        ledger = await self.get_or_create(tracked_wallet, asset)
        updated = ledger.add_post_tracking_delta(delta)
        await self.save(updated)
        return updated

    async def update_close_stage_ref(
        self,
        tracked_wallet: str,
        asset: str,
        new_ref: Decimal | None,
    ) -> TrackingLedger:
        """Get ledger, set close_stage_ref_post_tracking_shares (ref_pt) to new_ref, save and return. Ledger must exist."""
        ledger = await self.get(tracked_wallet, asset)
        if ledger is None:
            raise ValueError(f"No ledger for ({tracked_wallet!r}, {asset!r})")
        updated = ledger.with_close_stage_ref(new_ref)
        await self.save(updated)
        return updated
