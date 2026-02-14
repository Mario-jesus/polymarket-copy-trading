"""Snapshot t0 builder: fetches current positions from Data API and persists to tracking ledger."""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal
from typing import Any
from uuid import UUID

import structlog

from polymarket_copy_trading.clients.data_api import DataApiClient, PositionSchema
from polymarket_copy_trading.models.tracking_ledger import TrackingLedger
from polymarket_copy_trading.models.tracking_session import (
    SessionStatus,
    TrackingSession,
)
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
    ledgers_updated: list[TrackingLedger]
    """Ledgers created or updated with snapshot_t0_shares; post_tracking_shares set to 0."""
    error: str | None = None
    session_id: UUID | None = None
    """TrackingSession id for the session that ran this snapshot."""


def _parse_position(p: PositionSchema) -> tuple[str, float] | None:
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
        logger_name: str | None = None,
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
        ledgers: list[TrackingLedger] = []
        aggregated: dict[str, float] = defaultdict(float)

        self._logger.debug(
            "snapshot_t0_started",
            tracking_wallet_masked=mask_address(wallet),
        )

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
            raw_positions_total = 0
            invalid_positions = 0
            while page_count < self.MAX_PAGES:
                chunk = await self._data_api.get_positions(
                    user=wallet,
                    limit=limit,
                    offset=offset,
                )
                raw_positions_total += len(chunk)
                for p in chunk:
                    parsed = _parse_position(p)
                    if parsed is None:
                        invalid_positions += 1
                        continue
                    asset, size = parsed
                    aggregated[asset] += size
                self._logger.debug(
                    "snapshot_t0_page_fetched",
                    page=page_count + 1,
                    chunk_size=len(chunk),
                    offset=offset,
                    aggregated_assets_so_far=len(aggregated),
                )
                if len(chunk) < limit:
                    break
                offset += limit
                page_count += 1

            positions_added = len(aggregated)
            self._logger.info(
                "snapshot_t0_positions_aggregated",
                tracking_wallet_masked=mask_address(wallet),
                positions_added=positions_added,
                raw_positions_from_api=raw_positions_total,
                invalid_positions_skipped=invalid_positions,
                pages_fetched=page_count + 1,
            )

            for asset, total_size in aggregated.items():
                ledger = await self._repo.get_or_create(wallet, asset)
                updated = ledger.with_snapshot_t0(Decimal(str(total_size))).with_post_tracking(
                    Decimal("0")
                )
                await self._repo.save(updated)
                ledgers.append(updated)

            now = datetime.now(UTC)
            session = session.with_snapshot_completed(now, source="positions")
            await self._session_repo.save(session)

            self._logger.info(
                "snapshot_t0_built",
                tracking_wallet_masked=mask_address(wallet),
                positions_added=len(ledgers),
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
            now = datetime.now(UTC)
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
