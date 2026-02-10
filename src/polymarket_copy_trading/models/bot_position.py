# -*- coding: utf-8 -*-
"""Bot position: a single open or closed position opened by the bot at a given step level.

Used to track which step (escalón) each position corresponds to for closing in order
or all at once. Linked to TrackingLedger for the same market-outcome.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from decimal import Decimal
from typing import Literal, Optional
from uuid import UUID, uuid4

PositionStatus = Literal["OPEN", "CLOSED"]


@dataclass(frozen=True, slots=True)
class BotPosition:
    """One position opened by the bot: fixed size, step level, and status.

    - entry_step_level: which threshold step this position was opened at (1, 2, 3, ...).
    - status: OPEN or CLOSED; when CLOSED, closed_at is set.
    - ledger_id: reference to TrackingLedger for the same (wallet, condition_id, outcome).
    """

    id: UUID
    ledger_id: UUID
    """Reference to TrackingLedger.id for the same market-outcome."""

    tracked_wallet: str
    condition_id: str
    outcome: str

    entry_step_level: int
    """Which step (1, 2, 3, ...) this position was opened at; used for closing order."""

    shares_held: Decimal
    entry_price: Optional[Decimal]
    status: PositionStatus

    opened_at: datetime
    closed_at: Optional[datetime]
    """None while OPEN; set when status becomes CLOSED."""

    def with_closed(self, closed_at: Optional[datetime] = None) -> BotPosition:
        """Return a copy with status CLOSED and closed_at set (default now)."""
        return BotPosition(
            id=self.id,
            ledger_id=self.ledger_id,
            tracked_wallet=self.tracked_wallet,
            condition_id=self.condition_id,
            outcome=self.outcome,
            entry_step_level=self.entry_step_level,
            shares_held=self.shares_held,
            entry_price=self.entry_price,
            status="CLOSED",
            opened_at=self.opened_at,
            closed_at=closed_at or datetime.now(timezone.utc),
        )

    @property
    def is_open(self) -> bool:
        return self.status == "OPEN"

    @classmethod
    def create(
        cls,
        ledger_id: UUID,
        tracked_wallet: str,
        condition_id: str,
        outcome: str,
        entry_step_level: int,
        shares_held: Decimal,
        entry_price: Optional[Decimal] = None,
        *,
        id: Optional[UUID] = None,
        opened_at: Optional[datetime] = None,
    ) -> BotPosition:
        """Create a new OPEN position (e.g. when bot opens at a step threshold)."""
        now = datetime.now(timezone.utc)
        return cls(
            id=id or uuid4(),
            ledger_id=ledger_id,
            tracked_wallet=tracked_wallet,
            condition_id=condition_id,
            outcome=outcome,
            entry_step_level=entry_step_level,
            shares_held=shares_held,
            entry_price=entry_price,
            status="OPEN",
            opened_at=opened_at or now,
            closed_at=None,
        )
