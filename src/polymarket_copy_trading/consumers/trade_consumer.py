# -*- coding: utf-8 -*-
"""Consumer that reads trade messages from the queue and processes them.

Uses _running (instance) for start/stop state only. No shutdown event in the loop:
queue.get() blocks until a message or queue.shutdown(), so an event cannot be
checked while blocked; stop is achieved via queue.shutdown() (QueueShutdown) or
task cancel (CancelledError).
"""

from __future__ import annotations

import asyncio
import structlog
from types import TracebackType
from typing import Any, Callable, Optional, Type

from polymarket_copy_trading.exceptions import QueueShutdown
from polymarket_copy_trading.queue import IAsyncQueue, QueueMessage
from polymarket_copy_trading.services.tracking_trader.trade_dto import DataApiTradeDTO
from polymarket_copy_trading.services.trade_processing import TradeProcessorService


class TradeConsumer:
    """Consumes trade messages from the queue and delegates to TradeProcessorService.

    Run either via consume() (e.g. main creates_task(consumer.consume())) or via
    start()/stop() / async with consumer. The loop exits on QueueShutdown (after
    queue.shutdown()) or CancelledError when the task is cancelled.
    """

    def __init__(
        self,
        queue: IAsyncQueue[QueueMessage[DataApiTradeDTO]],
        trade_processor: TradeProcessorService,
        *,
        get_logger: Callable[[str], Any] = structlog.get_logger,
        logger_name: Optional[str] = None,
    ) -> None:
        """Initialize the consumer.

        Args:
            queue: Async queue of trade messages (same as used by TradeTracker).
            trade_processor: Service that processes each message (log, notify, etc.).
            get_logger: Logger factory (injected).
            logger_name: Optional logger name (defaults to class name).
        """
        self._queue = queue
        self._processor = trade_processor
        self._logger = get_logger(logger_name or self.__class__.__name__)
        self._running = False
        self._lock = asyncio.Lock()
        self._worker_task: Optional[asyncio.Task[None]] = None

    async def __aenter__(self) -> TradeConsumer:
        await self.start()
        return self

    async def __aexit__(
        self,
        exc_type: Optional[Type[BaseException]],
        exc_value: Optional[BaseException],
        traceback: Optional[TracebackType],
    ) -> bool:
        await self.stop()
        return False

    async def start(self) -> None:
        """Start the consumer in a background task. Idempotent."""
        async with self._lock:
            if self._running:
                return
            self._running = True
            self._worker_task = asyncio.create_task(self._consume_loop())

    async def stop(self) -> None:
        """Stop the consumer: cancel the task and wait for it to finish. Idempotent."""
        async with self._lock:
            if not self._running:
                return
            self._running = False
            task = self._worker_task
            self._worker_task = None
        if task is not None:
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass

    async def _consume_loop(self) -> None:
        """Inner loop: get message, process, task_done. Exits on QueueShutdown or cancel."""
        self._logger.debug("trade_consumer_started")
        try:
            while True:
                message = await self._queue.get()
                try:
                    await self._processor.process(message)
                finally:
                    self._queue.task_done()
        except QueueShutdown:
            self._logger.info(
                "trade_consumer_stopped",
                reason="queue_shutdown",
            )
        except asyncio.CancelledError:
            self._logger.debug("trade_consumer_cancelled")
            raise
        finally:
            async with self._lock:
                self._running = False
                self._worker_task = None
