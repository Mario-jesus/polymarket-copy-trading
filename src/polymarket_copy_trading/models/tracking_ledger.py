# -*- coding: utf-8 -*-
"""Tracking ledger: snapshot t0 and post-tracking shares per (wallet, condition_id, outcome).

Used by the copy-trading logic to classify trader operations (open vs close)
and to evaluate open/close thresholds. See docs on Prediction Markets Copy Trading.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from decimal import Decimal
from uuid import UUID, uuid4


@dataclass(frozen=True, slots=True)
class TrackingLedger:
    """Per (tracked_wallet, condition_id, outcome): snapshot at t0 and post-tracking shares.

    - snapshot_t0_shares: shares the trader had at follow start (reference only; not copied).
    - post_tracking_shares: shares bought/sold after t0; starts at 0, increases on BUY, decreases on SELL.
    """

    id: UUID
    tracked_wallet: str
    condition_id: str
    outcome: str

    snapshot_t0_shares: Decimal
    """Shares the trader had at t0. Never used to open/close bot; only to classify trades."""

    post_tracking_shares: Decimal
    """Current post-tracking balance (increases on BUY, decreases on SELL after t0)."""

    created_at: datetime
    updated_at: datetime

    def with_snapshot_t0(self, new_snapshot: Decimal) -> TrackingLedger:
        """Return a copy with updated snapshot_t0_shares (e.g. when setting t0 or reducing on SELL)."""
        return TrackingLedger(
            id=self.id,
            tracked_wallet=self.tracked_wallet,
            condition_id=self.condition_id,
            outcome=self.outcome,
            snapshot_t0_shares=new_snapshot,
            post_tracking_shares=self.post_tracking_shares,
            created_at=self.created_at,
            updated_at=datetime.now(timezone.utc),
        )

    def with_post_tracking(self, new_post_tracking: Decimal) -> TrackingLedger:
        """Return a copy with updated post_tracking_shares."""
        return TrackingLedger(
            id=self.id,
            tracked_wallet=self.tracked_wallet,
            condition_id=self.condition_id,
            outcome=self.outcome,
            snapshot_t0_shares=self.snapshot_t0_shares,
            post_tracking_shares=new_post_tracking,
            created_at=self.created_at,
            updated_at=datetime.now(timezone.utc),
        )

    def add_post_tracking_delta(self, delta: Decimal) -> TrackingLedger:
        """Return a copy with post_tracking_shares = current + delta (e.g. +size on BUY, -size on SELL)."""
        return self.with_post_tracking(self.post_tracking_shares + delta)

    @classmethod
    def create(
        cls,
        tracked_wallet: str,
        condition_id: str,
        outcome: str,
        snapshot_t0_shares: Decimal = Decimal("0"),
        post_tracking_shares: Decimal = Decimal("0"),
        *,
        id: UUID | None = None,
        created_at: datetime | None = None,
        updated_at: datetime | None = None,
    ) -> TrackingLedger:
        """Create a new ledger entry (e.g. for a new market-outcome or at t0)."""
        now = datetime.now(timezone.utc)
        return cls(
            id=id or uuid4(),
            tracked_wallet=tracked_wallet,
            condition_id=condition_id,
            outcome=outcome,
            snapshot_t0_shares=snapshot_t0_shares,
            post_tracking_shares=post_tracking_shares,
            created_at=created_at or now,
            updated_at=updated_at or now,
        )
