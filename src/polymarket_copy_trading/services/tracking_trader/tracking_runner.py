"""Orchestrator: runs TradeTracker for multiple wallets until shutdown (signal or CancelledError)."""

from __future__ import annotations

import asyncio
from collections.abc import Callable
from typing import TYPE_CHECKING, Any

import structlog

from polymarket_copy_trading.config import Settings
from polymarket_copy_trading.services.tracking_trader import TradeTracker
from polymarket_copy_trading.utils.validation import mask_address

if TYPE_CHECKING:
    from polymarket_copy_trading.services.snapshot import SnapshotBuilderService


class TrackingRunner:
    """Runs tracker.track() for each wallet in parallel until shutdown_event or CancelledError."""

    def __init__(
        self,
        tracker: TradeTracker,
        settings: Settings,
        *,
        snapshot_builder: SnapshotBuilderService | None = None,
        get_logger: Callable[[str], Any] = structlog.get_logger,
        logger_name: str | None = None,
    ) -> None:
        """Initialize the runner.

        Args:
            tracker: Injected TradeTracker.
            settings: Application settings (uses settings.tracking for poll_seconds, limit, etc.).
            snapshot_builder: Optional; if set, build_snapshot_t0(wallet) is called before tracking each wallet.
            get_logger: Logger factory (injected) with default of structlog.get_logger.
            logger_name: Optional logger name (defaults to class name).
        """
        self._tracker = tracker
        self._settings = settings
        self._snapshot_builder = snapshot_builder
        self._logger = get_logger(logger_name or self.__class__.__name__)

    async def run(
        self,
        wallets: list[str],
        shutdown_event: asyncio.Event,
    ) -> None:
        """Start one track task per wallet; wait for shutdown_event or CancelledError; cancel all tasks.

        If snapshot_builder was injected, builds snapshot t0 for each wallet before starting track tasks.

        Args:
            wallets: List of 0x wallet addresses to track.
            shutdown_event: When set, stop all tasks and return.
        """
        tr = self._settings.tracking
        self._logger.info(
            "tracking_runner_started",
            tracking_wallets_count=len(wallets),
            tracking_poll_seconds=tr.poll_seconds,
            tracking_limit=tr.trades_limit,
        )
        if self._snapshot_builder is not None:
            for wallet in wallets:
                result = await self._snapshot_builder.build_snapshot_t0(wallet)
                if not result.success:
                    self._logger.warning(
                        "tracking_runner_snapshot_failed",
                        tracking_wallet_masked=mask_address(wallet),
                        error=result.error,
                    )
        track_tasks = [
            asyncio.create_task(
                self._tracker.track(wallet, poll_seconds=tr.poll_seconds, limit=tr.trades_limit),
            )
            for wallet in wallets
        ]

        try:
            await shutdown_event.wait()
        except asyncio.CancelledError:
            self._logger.info(
                "tracking_runner_shutdown_cancelled",
                message="Kernel or task cancelled; stopping system",
            )
            for t in track_tasks:
                t.cancel()
            for t in track_tasks:
                try:
                    await t
                except asyncio.CancelledError:
                    pass
            raise

        self._logger.info("tracking_runner_shutdown_started")
        for t in track_tasks:
            t.cancel()
        for t in track_tasks:
            try:
                await t
            except asyncio.CancelledError:
                pass
