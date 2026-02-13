# -*- coding: utf-8 -*-
"""Snapshot t0 builder: fetches current positions from Data API and persists to tracking ledger."""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime, timezone
from decimal import Decimal
from typing import Any, Callable, Dict, List, Optional, Tuple
from uuid import UUID

import structlog

from polymarket_copy_trading.clients.data_api import DataApiClient, PositionSchema
from polymarket_copy_trading.models.tracking_ledger import TrackingLedger
from polymarket_copy_trading.models.tracking_session import SessionStatus, TrackingSession
from polymarket_copy_trading.persistence.repositories.interfaces.tracking_repository import (
    ITrackingRepository,
)
from polymarket_copy_trading.persistence.repositories.interfaces.tracking_session_repository import (
    ITrackingSessionRepository,
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
    session_id: Optional[UUID] = None
    """TrackingSession id for the session that ran this snapshot."""


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
        tracking_session_repository: ITrackingSessionRepository,
        *,
        get_logger: Callable[[str], Any] = structlog.get_logger,
        logger_name: Optional[str] = None,
    ) -> None:
        """Initialize the snapshot builder.

        Args:
            data_api: Data API client (injected).
            tracking_repository: Tracking ledger repository (injected).
            tracking_session_repository: Session repository for t0 lifecycle (injected).
            get_logger: Logger factory (injected).
            logger_name: Optional logger name (defaults to class name).
        """
        self._data_api = data_api
        self._repo = tracking_repository
        self._session_repo = tracking_session_repository
        self._logger = get_logger(logger_name or self.__class__.__name__)

    async def build_snapshot_t0(self, wallet: str) -> SnapshotResult:
        """Fetch current positions for wallet, one ledger per asset (positionId), persist snapshot t0.

        For each (wallet, asset) sets snapshot_t0_shares to the position size and
        post_tracking_shares to 0. Paginates get_positions until no more pages.

        Creates or reuses a TrackingSession; on success marks snapshot_completed_at,
        on error marks session status ERROR and ended_at.

        Args:
            wallet: Tracked wallet address (0x...).

        Returns:
            SnapshotResult with success, ledgers_updated, and optional error.
        """
        wallet = wallet.strip()
        ledgers: List[TrackingLedger] = []
        aggregated: Dict[str, float] = defaultdict(float)

        session = await self._session_repo.get_active_for_wallet(wallet)
        if session is None:
            session = TrackingSession.create(wallet)
            await self._session_repo.save(session)
        else:
            self._logger.info(
                "snapshot_reusing_session",
                session_id=str(session.id),
                tracking_wallet_masked=mask_address(wallet),
            )

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
                ledger = await self._repo.get_or_create(wallet, asset)
                updated = ledger.with_snapshot_t0(Decimal(str(total_size))).with_post_tracking(
                    Decimal("0")
                )
                await self._repo.save(updated)
                ledgers.append(updated)

            now = datetime.now(timezone.utc)
            session = session.with_snapshot_completed(now, source="positions")
            await self._session_repo.save(session)

            self._logger.info(
                "snapshot_t0_built",
                tracking_wallet_masked=mask_address(wallet),
                ledgers_count=len(ledgers),
                session_id=str(session.id),
            )
            return SnapshotResult(
                wallet=wallet,
                success=True,
                ledgers_updated=ledgers,
                error=None,
                session_id=session.id,
            )
        except Exception as e:  # pragma: no cover
            now = datetime.now(timezone.utc)
            session = session.with_ended(now, status=SessionStatus.ERROR)
            await self._session_repo.save(session)

            self._logger.exception(
                "snapshot_t0_build_error",
                tracking_wallet_masked=mask_address(wallet),
                session_id=str(session.id),
                error_type=type(e).__name__,
                error_message=str(e),
            )
            return SnapshotResult(
                wallet=wallet,
                success=False,
                ledgers_updated=ledgers,
                error=str(e),
                session_id=session.id,
            )
