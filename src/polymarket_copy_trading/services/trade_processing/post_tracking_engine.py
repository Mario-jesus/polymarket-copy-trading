"""Post-tracking engine: applies BUY/SELL rule to update ledger (snapshot_t0 and post_tracking_shares)."""

from __future__ import annotations

from collections.abc import Callable
from decimal import Decimal
from typing import Any

import structlog

from polymarket_copy_trading.models.tracking_ledger import TrackingLedger
from polymarket_copy_trading.persistence.repositories.interfaces.tracking_repository import (
    ITrackingRepository,
)
from polymarket_copy_trading.services.tracking_trader.trade_dto import DataApiTradeDTO
from polymarket_copy_trading.utils.validation import mask_address


class PostTrackingEngine:
    """Updates tracking ledger per trade: BUY increases post_tracking; SELL reduces post_tracking first, then snapshot_t0."""

    def __init__(
        self,
        tracking_repository: ITrackingRepository,
        *,
        get_logger: Callable[[str], Any] = structlog.get_logger,
        logger_name: str | None = None,
    ) -> None:
        """Initialize the engine.

        Args:
            tracking_repository: Ledger storage (injected).
            get_logger: Logger factory (injected).
            logger_name: Optional logger name (defaults to class name).
        """
        self._repo = tracking_repository
        self._logger = get_logger(logger_name or self.__class__.__name__)

    async def apply_trade(self, wallet: str, trade: DataApiTradeDTO) -> TrackingLedger | None:
        """Apply BUY/SELL rule to the ledger for this trade's (wallet, asset).

        BUY: add size to post_tracking_shares.
        SELL: subtract size from post_tracking_shares first; if that goes negative, set post_tracking to 0
        and reduce snapshot_t0_shares by the excess (clamped to 0).

        Args:
            wallet: Tracked wallet address.
            trade: Trade payload (asset, condition_id, outcome_index, outcome, side, size).

        Returns:
            Updated ledger if the trade was applied, None if skipped (missing/invalid fields).
        """
        asset = trade.asset and str(trade.asset).strip() or None
        side = trade.side
        if asset is None or side not in ("BUY", "SELL"):
            self._logger.debug(
                "post_tracking_skip_invalid",
                wallet_masked=mask_address(wallet),
                asset=asset,
                side=side,
            )
            return None
        size_raw = trade.size
        if size_raw is None or size_raw <= 0:
            self._logger.debug(
                "post_tracking_skip_no_size",
                wallet_masked=mask_address(wallet),
                asset=asset,
                size=size_raw,
            )
            return None
        size_d = Decimal(str(size_raw))

        if side == "BUY":
            await self._repo.get_or_create(wallet, asset)
            updated = await self._repo.add_post_tracking_delta(wallet, asset, size_d)
            self._logger.debug(
                "post_tracking_buy",
                wallet_masked=mask_address(wallet),
                asset=asset,
                size=float(size_d),
                post_tracking_after=float(updated.post_tracking_shares),
            )
            return updated

        # SELL: ensure ledger exists, then reduce post_tracking first; excess reduces snapshot_t0
        ledger = await self._repo.get_or_create(wallet, asset)
        new_pt = ledger.post_tracking_shares - size_d
        if new_pt >= 0:
            updated = ledger.with_post_tracking(new_pt)
            await self._repo.save(updated)
            self._logger.debug(
                "post_tracking_sell_from_pt",
                wallet_masked=mask_address(wallet),
                asset=asset,
                size=float(size_d),
                post_tracking_after=float(updated.post_tracking_shares),
            )
            return updated
        # new_pt < 0: set post_tracking to 0, reduce snapshot by |new_pt|
        excess = -new_pt
        new_snapshot = max(Decimal(0), ledger.snapshot_t0_shares - excess)
        updated = ledger.with_post_tracking(Decimal(0)).with_snapshot_t0(new_snapshot)
        await self._repo.save(updated)
        self._logger.debug(
            "post_tracking_sell_into_snapshot",
            wallet_masked=mask_address(wallet),
            asset=asset,
            size=float(size_d),
            snapshot_after=float(updated.snapshot_t0_shares),
        )
        return updated
