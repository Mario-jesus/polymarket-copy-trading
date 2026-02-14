"""ClosePolicy: pure logic to decide how many positions the bot should close.

No I/O. Receives all inputs from the orquestador (ledger state, open positions count, settings).
Implements progressive close: stage_pct_closed from ref_pt, per_position divisor, n = floor(stage_pct_closed / per_position).
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from decimal import Decimal
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from polymarket_copy_trading.config import StrategySettings
    from polymarket_copy_trading.models.tracking_ledger import TrackingLedger


@dataclass(frozen=True)
class ClosePolicyResult:
    """Result of ClosePolicy evaluation (number of positions to close + reason for logging)."""

    positions_to_close: int
    reason: str


@dataclass(frozen=True)
class ClosePolicyInput:
    """Input context for ClosePolicy.positions_to_close (all data provided by orquestador)."""

    ledger: TrackingLedger
    """Ledger for (wallet, asset); must have post_tracking_shares and close_stage_ref_post_tracking_shares."""
    open_positions_count: int
    """Number of open BotPositions for this ledger (used for per_position divisor and cap)."""


class ClosePolicy:
    """Pure policy: evaluates how many positions the bot should close on a SELL.

    Uses stage_pct_closed = (ref_pt - pt_actual) / ref_pt * 100,
    per_position = close_total_threshold_pct / open_positions_count,
    n = floor(stage_pct_closed / per_position).
    No I/O; all inputs must be provided by the orquestador.
    """

    def positions_to_close(
        self,
        inp: ClosePolicyInput,
        settings: StrategySettings,
    ) -> ClosePolicyResult:
        """Return ClosePolicyResult (positions_to_close + reason) for logging.

        Logic:
        - ref_pt = ledger.close_stage_ref_post_tracking_shares
        - stage_pct_closed = (ref_pt - pt_actual) / ref_pt * 100
        - per_position = close_total_threshold_pct / open_positions_count
        - n = floor(stage_pct_closed / per_position), capped by open_positions_count

        Args:
            inp: ClosePolicyInput with ledger and open_positions_count.
            settings: StrategySettings (STRATEGY__*).

        Returns:
            ClosePolicyResult with positions_to_close (0 or more) and reason for logging.
        """
        # 1. No open positions: nothing to close
        if inp.open_positions_count <= 0:
            return ClosePolicyResult(
                positions_to_close=0,
                reason="no open positions to close",
            )

        # 2. No ref_pt: cannot compute stage_pct_closed (orquestador must set ref_pt at stage start)
        ref_pt = inp.ledger.close_stage_ref_post_tracking_shares
        if ref_pt is None or ref_pt <= 0:
            return ClosePolicyResult(
                positions_to_close=0,
                reason=f"ref_pt not set or <= 0 (close_stage_ref_post_tracking_shares={ref_pt})",
            )

        pt_actual = inp.ledger.post_tracking_shares

        # 3. Trader bought (pt_actual > ref_pt): stage_pct_closed would be negative
        if pt_actual >= ref_pt:
            return ClosePolicyResult(
                positions_to_close=0,
                reason=f"no close stage progress (pt_actual={pt_actual} >= ref_pt={ref_pt})",
            )

        # 4. stage_pct_closed = (ref_pt - pt_actual) / ref_pt * 100
        stage_pct_closed = float((ref_pt - pt_actual) / ref_pt * Decimal("100"))

        # 5. per_position = close_total_threshold_pct / open_positions_count
        per_position = settings.close_total_threshold_pct / inp.open_positions_count
        if per_position <= 0:
            return ClosePolicyResult(
                positions_to_close=0,
                reason="per_position <= 0 (close_total_threshold_pct or open_positions_count invalid)",
            )

        # 6. n = floor(stage_pct_closed / per_position), capped by open_positions_count
        n = int(math.floor(stage_pct_closed / per_position))
        n = max(0, min(n, inp.open_positions_count))

        if n == 0:
            return ClosePolicyResult(
                positions_to_close=0,
                reason=(
                    f"stage_pct_closed={stage_pct_closed:.2f}% < per_position={per_position:.2f}% "
                    f"(threshold {settings.close_total_threshold_pct}% / {inp.open_positions_count} positions)"
                ),
            )

        return ClosePolicyResult(
            positions_to_close=n,
            reason=(
                f"close {n} positions: stage_pct_closed={stage_pct_closed:.2f}%, "
                f"per_position={per_position:.2f}%, n=floor({stage_pct_closed:.2f}/{per_position:.2f})={n}"
            ),
        )
