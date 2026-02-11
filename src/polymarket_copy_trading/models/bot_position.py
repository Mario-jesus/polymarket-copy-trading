# -*- coding: utf-8 -*-
"""Bot position: a single open or closed position opened by the bot.

Used to track positions for closing in FIFO order (oldest opened_at first).
Linked to TrackingLedger for the same (wallet, asset).
Fields for entry_cost_usdc, close_proceeds_usdc and fees support PnL and net PnL later.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from decimal import Decimal
from enum import Enum
from typing import Optional
from uuid import UUID, uuid4


class PositionStatus(str, Enum):
    """Position lifecycle state."""

    OPEN = "OPEN"
    CLOSED = "CLOSED"


@dataclass(frozen=True, slots=True)
class BotPosition:
    """One position opened by the bot: fixed size and status.

    Identity / execution: ledger_id + asset (asset = token_id for CLOB).
    Denormalized tracked_wallet for list_by_wallet queries; must match ledger.tracked_wallet.
    Close order: FIFO by opened_at (oldest first).
    PnL: entry_cost_usdc (cost basis), close_proceeds_usdc (when closed), fees (open + close).
    """

    id: UUID
    ledger_id: UUID
    """Reference to TrackingLedger.id for the same (wallet, asset)."""

    tracked_wallet: str
    asset: str
    """PositionId / token_id; for CLOB execution and reconciliation."""

    shares_held: Decimal
    entry_price: Optional[Decimal]
    status: PositionStatus

    opened_at: datetime
    closed_at: Optional[datetime]
    """None while OPEN; set when status is CLOSED."""

    # PnL / cost basis (for realized and net PnL later)
    entry_cost_usdc: Optional[Decimal] = None
    """Total USDC cost to open (shares cost + open fees). Cost basis."""
    close_proceeds_usdc: Optional[Decimal] = None
    """USDC received when closed (after fees). Set when status is CLOSED."""
    fees: Decimal = Decimal("0")
    """Total fees in USDC (open + close). For reporting and net PnL."""

    def with_closed(
        self,
        closed_at: Optional[datetime] = None,
        close_proceeds_usdc: Optional[Decimal] = None,
        close_fees: Optional[Decimal] = None,
    ) -> BotPosition:
        """Return a copy with status CLOSED, closed_at set, and optional close amounts."""
        now = closed_at or datetime.now(timezone.utc)
        new_fees = self.fees + (close_fees or Decimal("0"))
        return BotPosition(
            id=self.id,
            ledger_id=self.ledger_id,
            tracked_wallet=self.tracked_wallet,
            asset=self.asset,
            shares_held=self.shares_held,
            entry_price=self.entry_price,
            status=PositionStatus.CLOSED,
            opened_at=self.opened_at,
            closed_at=now,
            entry_cost_usdc=self.entry_cost_usdc,
            close_proceeds_usdc=close_proceeds_usdc if close_proceeds_usdc is not None else self.close_proceeds_usdc,
            fees=new_fees,
        )

    @property
    def is_open(self) -> bool:
        return self.status == PositionStatus.OPEN

    def realized_pnl_usdc(self) -> Optional[Decimal]:
        """Realized PnL in USDC when closed. None if OPEN or missing cost/proceeds."""
        if self.status != PositionStatus.CLOSED:
            return None
        if self.entry_cost_usdc is None or self.close_proceeds_usdc is None:
            return None
        return self.close_proceeds_usdc - self.entry_cost_usdc

    def net_pnl_usdc(self) -> Optional[Decimal]:
        """Net PnL in USDC (after fees) when closed. None if OPEN or missing data."""
        pnl = self.realized_pnl_usdc()
        if pnl is None:
            return None
        return pnl - self.fees

    @classmethod
    def create(
        cls,
        ledger_id: UUID,
        tracked_wallet: str,
        asset: str,
        shares_held: Decimal = Decimal("0"),
        entry_price: Optional[Decimal] = None,
        entry_cost_usdc: Optional[Decimal] = None,
        fees: Optional[Decimal] = None,
        *,
        id: Optional[UUID] = None,
        opened_at: Optional[datetime] = None,
    ) -> BotPosition:
        """Create a new OPEN position (e.g. when bot opens at a threshold).

        Raises:
            ValueError: If shares_held <= 0.
        """
        if shares_held <= 0:
            raise ValueError("shares_held must be > 0 when opening a position")
        now = datetime.now(timezone.utc)
        return cls(
            id=id or uuid4(),
            ledger_id=ledger_id,
            tracked_wallet=tracked_wallet,
            asset=asset.strip(),
            shares_held=shares_held,
            entry_price=entry_price,
            status=PositionStatus.OPEN,
            opened_at=opened_at or now,
            closed_at=None,
            entry_cost_usdc=entry_cost_usdc,
            close_proceeds_usdc=None,
            fees=fees if fees is not None else Decimal("0"),
        )
