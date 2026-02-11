# -*- coding: utf-8 -*-
"""Snapshot t0 builder: fetches current positions from Data API and persists to tracking ledger."""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from decimal import Decimal
from typing import Any, Callable, Dict, List, Optional, Tuple

import structlog

from polymarket_copy_trading.clients.data_api import DataApiClient, PositionSchema
from polymarket_copy_trading.models.tracking_ledger import TrackingLedger
from polymarket_copy_trading.persistence.repositories.interfaces.tracking_repository import (
    ITrackingRepository,
)
from polymarket_copy_trading.utils.validation import mask_address


@dataclass(frozen=True)
class SnapshotResult:
    """Result of building snapshot t0 for a wallet."""

    wallet: str
    success: bool
    ledgers_updated: List[TrackingLedger]
    """Ledgers created or updated with snapshot_t0_shares; post_tracking_shares set to 0."""
    error: Optional[str] = None


def _parse_position(p: PositionSchema) -> Optional[Tuple[str, float]]:
    """Extract (asset, size) from a Data API position. None if invalid."""
    asset = p.get("asset")
    size_raw = p.get("size")
    if asset is None or size_raw is None:
        return None
    try:
        size_f = float(size_raw)
    except (TypeError, ValueError):
        return None
    return (str(asset).strip(), size_f)


class SnapshotBuilderService:
    """Builds snapshot t0 from Data API positions and persists to ITrackingRepository."""

    DEFAULT_LIMIT = 100
    MAX_PAGES = 200

    def __init__(
        self,
        data_api: DataApiClient,
        tracking_repository: ITrackingRepository,
        *,
        get_logger: Callable[[str], Any] = structlog.get_logger,
        logger_name: Optional[str] = None,
    ) -> None:
        """Initialize the snapshot builder.

        Args:
            data_api: Data API client (injected).
            tracking_repository: Tracking ledger repository (injected).
            get_logger: Logger factory (injected).
            logger_name: Optional logger name (defaults to class name).
        """
        self._data_api = data_api
        self._repo = tracking_repository
        self._logger = get_logger(logger_name or self.__class__.__name__)

    async def build_snapshot_t0(self, wallet: str) -> SnapshotResult:
        """Fetch current positions for wallet, one ledger per asset (positionId), persist snapshot t0.

        For each (wallet, asset) sets snapshot_t0_shares to the position size and
        post_tracking_shares to 0. Paginates get_positions until no more pages.

        Args:
            wallet: Tracked wallet address (0x...).

        Returns:
            SnapshotResult with success, ledgers_updated, and optional error.
        """
        wallet = wallet.strip()
        ledgers: List[TrackingLedger] = []
        # Aggregate by asset -> total size (sum if API returns duplicates)
        aggregated: Dict[str, float] = defaultdict(float)

        try:
            offset = 0
            limit = self.DEFAULT_LIMIT
            page_count = 0
            while page_count < self.MAX_PAGES:
                chunk = await self._data_api.get_positions(
                    user=wallet,
                    limit=limit,
                    offset=offset,
                )
                for p in chunk:
                    parsed = _parse_position(p)
                    if parsed is None:
                        continue
                    asset, size = parsed
                    aggregated[asset] += size
                if len(chunk) < limit:
                    break
                offset += limit
                page_count += 1

            for asset, total_size in aggregated.items():
                ledger = self._repo.get_or_create(wallet, asset)
                updated = ledger.with_snapshot_t0(Decimal(str(total_size))).with_post_tracking(
                    Decimal("0")
                )
                self._repo.save(updated)
                ledgers.append(updated)

            self._logger.info(
                "snapshot_t0_built",
                tracking_wallet_masked=mask_address(wallet),
                ledgers_count=len(ledgers),
            )
            return SnapshotResult(
                wallet=wallet,
                success=True,
                ledgers_updated=ledgers,
                error=None,
            )
        except Exception as e:  # pragma: no cover
            self._logger.exception(
                "snapshot_t0_build_error",
                tracking_wallet_masked=mask_address(wallet),
                error_type=type(e).__name__,
                error_message=str(e),
            )
            return SnapshotResult(
                wallet=wallet,
                success=False,
                ledgers_updated=ledgers,
                error=str(e),
            )
