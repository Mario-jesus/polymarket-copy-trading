# -*- coding: utf-8 -*-
"""
Entry point for the copy-trading application.

Orchestrates: logging, settings, container, trade consumer, snapshot t0, tracker, shutdown (SIGINT or CancelledError).
Trades flow: tracker -> queue -> consumer -> TradeProcessorService (log + optional notifications).

Run with: python -m polymarket_copy_trading.main

Notebook usage:
    from polymarket_copy_trading.main import run
    await run()  # Interrupt kernel to stop; system will shut down on CancelledError.
"""
from __future__ import annotations

import asyncio
import signal
import structlog
from datetime import datetime, timezone
from typing import Any

from polymarket_copy_trading.DI import Container
from polymarket_copy_trading.config import get_settings
from polymarket_copy_trading.exceptions import MissingRequiredConfigError
from polymarket_copy_trading.logging.config import configure_logging
from polymarket_copy_trading.notifications.types import NotificationMessage
from polymarket_copy_trading.utils import mask_address


def _setup_sigint(shutdown_event: asyncio.Event) -> None:
    try:
        loop = asyncio.get_running_loop()
        loop.add_signal_handler(
            signal.SIGINT,
            lambda: shutdown_event.set(),
        )
    except NotImplementedError:
        pass  # Windows has no add_signal_handler


async def _do_shutdown(logger: Any) -> None:
    """Clean shutdown. Safe to call on normal shutdown or CancelledError."""
    logger.info("main_shutdown_complete")


async def run() -> None:
    configure_logging()
    logger = structlog.get_logger("main")
    settings = get_settings()
    target_wallet = settings.tracking.target_wallet.strip()
    if not target_wallet:
        logger.error(
            "main_missing_target_wallet",
            message="TRACKING__TARGET_WALLET is not set",
        )
        raise MissingRequiredConfigError("TRACKING__TARGET_WALLET")

    container = Container()
    snapshot_builder = container.snapshot_builder_service()
    tracking_session_repo = container.tracking_session_repository()
    tracker = container.trade_tracker()
    consumer = container.trade_consumer()
    trade_queue = container.trade_queue()
    notification_service = container.notification_service()
    await notification_service.initialize()
    shutdown_event = asyncio.Event()
    _setup_sigint(shutdown_event)

    tr = settings.tracking
    result = await snapshot_builder.build_snapshot_t0(target_wallet)
    if not result.success:
        logger.warning(
            "main_snapshot_failed",
            wallet_masked=mask_address(target_wallet),
            error=result.error,
        )

    logger.info(
        "main_tracking_started",
        target_wallet=mask_address(target_wallet),
        poll_seconds=tr.poll_seconds,
        trades_limit=tr.trades_limit,
    )
    notification_service.notify(
        NotificationMessage(
            event_type="system_started",
            message="Copy trading system started",
            payload={"target_wallet": mask_address(target_wallet)},
        )
    )

    track_task = asyncio.create_task(
        tracker.track(
            target_wallet,
            poll_seconds=tr.poll_seconds,
            limit=tr.trades_limit,
        )
    )

    await consumer.start()
    try:
        try:
            await shutdown_event.wait()
        except asyncio.CancelledError:
            await _do_shutdown(logger)
            raise

        await _do_shutdown(logger)
    finally:
        active = tracking_session_repo.get_active_for_wallet(target_wallet)
        if active is not None:
            tracking_session_repo.save(
                active.with_ended(datetime.now(timezone.utc))
            )
        track_task.cancel()
        try:
            await track_task
        except asyncio.CancelledError:
            pass
        trade_queue.shutdown()
        await trade_queue.join()
        await consumer.stop()

        notification_service.notify(
            NotificationMessage(
                event_type="system_stopped",
                message="Copy trading system stopped",
                payload={},
            )
        )
        await notification_service.shutdown()


def main() -> None:
    asyncio.run(run())


__all__ = ["run", "main"]

if __name__ == "__main__":
    main()
