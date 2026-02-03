# -*- coding: utf-8 -*-
"""Orchestrator: runs TradeTracker for multiple wallets until shutdown (signal or CancelledError)."""

from __future__ import annotations

import asyncio
import structlog

from polymarket_copy_trading.config import Settings
from polymarket_copy_trading.services.tracking import TradeTracker


class TrackingRunner:
    """Runs tracker.track() for each wallet in parallel until shutdown_event or CancelledError."""

    def __init__(self, tracker: TradeTracker, settings: Settings) -> None:
        """Initialize the runner.

        Args:
            tracker: Injected TradeTracker.
            settings: Application settings (uses settings.tracking for poll_seconds, limit, etc.).
        """
        self._tracker = tracker
        self._settings = settings
        self._logger = structlog.get_logger(self.__class__.__name__)

    async def run(
        self,
        wallets: list[str],
        shutdown_event: asyncio.Event,
    ) -> None:
        """Start one track task per wallet; wait for shutdown_event or CancelledError; cancel all tasks.

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
            tracking_gamma_lookup=tr.enable_gamma_lookup,
        )
        track_tasks = [
            asyncio.create_task(
                self._tracker.track(
                    wallet,
                    poll_seconds=tr.poll_seconds,
                    limit=tr.trades_limit,
                    enable_gamma_lookup=tr.enable_gamma_lookup,
                    emit_initial=False,
                ),
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
