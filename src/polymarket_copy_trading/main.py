# -*- coding: utf-8 -*-
"""
Entry point for the copy-trading application.

Orchestrates: logging, settings, container, trade consumer, tracking runner, shutdown (SIGINT or CancelledError).
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
    target_wallets = settings.tracking.target_wallets
    if not target_wallets:
        logger.error(
            "main_missing_target_wallets",
            message="TRACKING__TARGET_WALLETS is not set (comma-separated list)",
        )
        raise MissingRequiredConfigError("TRACKING__TARGET_WALLETS")

    container = Container()
    runner = container.tracking_runner()
    consumer = container.trade_consumer()
    trade_queue = container.trade_queue()
    notification_service = container.notification_service()
    await notification_service.initialize()
    shutdown_event = asyncio.Event()
    _setup_sigint(shutdown_event)

    logger.info(
        "main_tracking_started",
        target_wallets=[mask_address(w) for w in target_wallets],
    )
    notification_service.notify(
        NotificationMessage(
            event_type="system_started",
            message="Copy trading system started",
            payload={"target_wallets": [mask_address(w) for w in target_wallets]},
        )
    )

    await consumer.start()
    try:
        try:
            await runner.run(target_wallets, shutdown_event)
        except asyncio.CancelledError:
            await _do_shutdown(logger)
            raise

        await _do_shutdown(logger)
    finally:
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
