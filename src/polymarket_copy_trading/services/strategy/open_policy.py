# -*- coding: utf-8 -*-
"""OpenPolicy: pure logic to decide if the bot should open a new position.

No I/O. Receives all inputs from the orquestador (ledger state, counts, settings).
Implements double threshold (shares + percent) and capacity limits.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from polymarket_copy_trading.config import StrategySettings
    from polymarket_copy_trading.models.tracking_ledger import TrackingLedger


@dataclass(frozen=True)
class OpenPolicyResult:
    """Result of OpenPolicy evaluation (decision + reason for logging)."""

    should_open: bool
    reason: str


@dataclass(frozen=True)
class OpenPolicyInput:
    """Input context for OpenPolicy.should_open (all data provided by orquestador)."""

    ledger: "TrackingLedger"
    """Ledger for (wallet, asset)."""
    open_positions_count: int
    """Number of open BotPositions for this ledger."""
    active_ledgers_count: int
    """Number of ledgers that have at least one open position (for max_active_ledgers)."""
    account_total_value_usdc: Decimal
    """Total account value (cash + positions). From AccountValueService."""
    post_tracking_value_usdc: Decimal
    """Mark-to-market value of post_tracking_shares for this asset."""


class OpenPolicy:
    """Pure policy: evaluates if the bot should open a new position.

    Uses double threshold (shares OR percent) and capacity limits.
    No I/O; all inputs must be provided by the orquestador.
    """

    def should_open(
        self,
        inp: OpenPolicyInput,
        settings: "StrategySettings",
    ) -> OpenPolicyResult:
        """Return OpenPolicyResult (decision + reason) for logging.

        Checks (in order):
        1. Capacity: open_positions_count < max_positions_per_ledger
        2. Capacity: if adding a new ledger, active_ledgers_count < max_active_ledgers
        3. Threshold: post_tracking_shares >= asset_min_position_shares OR
            open_pct >= effective_threshold_pct (derived by count)

        Args:
            inp: OpenPolicyInput with ledger, counts, and values.
            settings: StrategySettings (STRATEGY__*).

        Returns:
            OpenPolicyResult with should_open and reason for logging.
        """
        # 1. Max positions per ledger
        if inp.open_positions_count >= settings.max_positions_per_ledger:
            return OpenPolicyResult(
                should_open=False,
                reason=f"max_positions_per_ledger reached ({inp.open_positions_count} >= {settings.max_positions_per_ledger})",
            )

        # 2. Max active ledgers (only when adding a new asset)
        if inp.open_positions_count == 0:
            if inp.active_ledgers_count >= settings.max_active_ledgers:
                return OpenPolicyResult(
                    should_open=False,
                    reason=f"max_active_ledgers reached ({inp.active_ledgers_count} >= {settings.max_active_ledgers})",
                )

        # 3. At least some post-tracking to copy
        if inp.ledger.post_tracking_shares <= 0:
            return OpenPolicyResult(
                should_open=False,
                reason="post_tracking_shares <= 0 (nothing to copy)",
            )

        # 4. Double threshold: shares OR percent
        shares_ok = inp.ledger.post_tracking_shares >= Decimal(
            str(settings.asset_min_position_shares)
        )

        percent_ok = False
        effective_pct_val = 0.0
        open_pct_val = Decimal("0")
        if settings.asset_min_position_percent > 0 and inp.account_total_value_usdc > 0:
            open_pct_val = inp.post_tracking_value_usdc / inp.account_total_value_usdc
            effective_pct_val = (
                (inp.open_positions_count + 1)
                * settings.asset_min_position_percent
                / 100
            )
            percent_ok = open_pct_val >= Decimal(str(effective_pct_val))

        if shares_ok:
            return OpenPolicyResult(
                should_open=True,
                reason=f"shares threshold met (post_tracking_shares={inp.ledger.post_tracking_shares} >= {settings.asset_min_position_shares})",
            )
        if percent_ok:
            return OpenPolicyResult(
                should_open=True,
                reason=f"percent threshold met (open_pct={float(open_pct_val):.4f} >= effective_pct={effective_pct_val:.4f})",
            )
        if settings.asset_min_position_percent > 0 and inp.account_total_value_usdc > 0:
            reason = (
                f"thresholds not met (shares={inp.ledger.post_tracking_shares} < {settings.asset_min_position_shares}, "
                f"open_pct={float(open_pct_val):.4f} < effective_pct={effective_pct_val:.4f})"
            )
        else:
            reason = (
                f"shares threshold not met (post_tracking_shares={inp.ledger.post_tracking_shares} < "
                f"{settings.asset_min_position_shares}, percent disabled or no account value)"
            )
        return OpenPolicyResult(should_open=False, reason=reason)
