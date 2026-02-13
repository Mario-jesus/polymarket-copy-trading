# -*- coding: utf-8 -*-
"""PnLService: pure computation of realized and net PnL from BotPosition.

No I/O, no side effects. Used by TradeConfirmedNotifier for position_closed notifications.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from typing import TYPE_CHECKING, Optional

if TYPE_CHECKING:
    from polymarket_copy_trading.models.bot_position import BotPosition


@dataclass(frozen=True)
class PnLResult:
    """Result of PnL computation for a closed position."""

    realized_pnl_usdc: Optional[Decimal]
    """Gross PnL (close_proceeds - entry_cost). None if OPEN or missing data."""

    net_pnl_usdc: Optional[Decimal]
    """Net PnL after fees. None if OPEN or missing data."""

    entry_cost_usdc: Optional[Decimal]
    """Total USDC cost to open (cost basis)."""

    close_proceeds_usdc: Optional[Decimal]
    """USDC received when closed."""

    total_fees_usdc: Decimal
    """Total fees in USDC (open + close)."""


class PnLService:
    """Sync, pure service for computing PnL from a BotPosition."""

    def compute(self, position: "BotPosition") -> PnLResult:
        """Compute PnL from position. No I/O, no side effects.

        For OPEN positions, realized_pnl_usdc and net_pnl_usdc are None.
        For CLOSED positions with full data, returns all fields.
        """
        realized = position.realized_pnl_usdc()
        net = position.net_pnl_usdc()
        return PnLResult(
            realized_pnl_usdc=realized,
            net_pnl_usdc=net,
            entry_cost_usdc=position.entry_cost_usdc,
            close_proceeds_usdc=position.close_proceeds_usdc,
            total_fees_usdc=position.fees,
        )
