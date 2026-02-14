"""Notification service and styler interface."""

from __future__ import annotations

import asyncio
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

import structlog

from polymarket_copy_trading.notifications.strategies import BaseNotificationStrategy
from polymarket_copy_trading.notifications.types import NotificationMessage


@dataclass
class NotificationService:
    """Dispatch notifications to all configured channels."""

    notifiers: list[BaseNotificationStrategy]
    queue_size: int = 1000
    get_logger: Callable[[str], Any] = field(default=structlog.get_logger)
    _queue: asyncio.Queue[NotificationMessage] | None = field(init=False, default=None)
    _worker_task: asyncio.Task[None] | None = field(init=False, default=None)
    _logger: Any = field(init=False)

    def __post_init__(self) -> None:
        self._logger = self.get_logger("NotificationService")

    async def initialize(self) -> None:
        """Initialize all notifiers."""
        notifiers_count = len(self.notifiers)
        self._logger.debug(
            "notification_init_started",
            notification_notifiers_count=notifiers_count,
        )
        for notifier in self.notifiers:
            await notifier.initialize()
        if not self.notifiers:
            self._queue = None
            self._worker_task = None
            self._logger.info("notification_init_no_notifiers")
            return
        self._queue = asyncio.Queue[NotificationMessage](maxsize=self.queue_size)
        self._worker_task = asyncio.create_task(self._worker_loop())
        self._logger.debug(
            "notification_init_complete",
            notification_queue_size=self.queue_size,
            notification_worker_started=True,
        )

    async def shutdown(self) -> None:
        """Shutdown all notifiers."""
        self._logger.debug("notification_shutdown_started")
        if self._queue is not None:
            self._queue.shutdown()
            await self._queue.join()
            self._logger.debug("notification_shutdown_queue_drained")
        if self._worker_task is not None:
            await self._worker_task
            self._worker_task = None
        self._queue = None

        for notifier in self.notifiers:
            await notifier.shutdown()
        self._logger.debug("notification_shutdown_complete")

    def notify(self, message: NotificationMessage) -> None:
        """Enqueue a notification (non-blocking for callers)."""
        queue = self._queue
        if queue is None:
            if not self.notifiers:
                return
            raise RuntimeError("NotificationService not initialized")
        try:
            queue.put_nowait(message)
        except asyncio.QueueFull:
            self._logger.warning(
                "notification_queue_full_dropped",
                notification_event_type=message.event_type,
            )

    async def _worker_loop(self) -> None:
        queue = self._queue
        if queue is None:
            return
        while True:
            try:
                msg = await queue.get()
            except asyncio.QueueShutDown:
                self._logger.debug("notification_worker_shutting_down")
                break
            try:
                await self._dispatch(msg)
            finally:
                queue.task_done()

    async def _dispatch(self, message: NotificationMessage) -> None:
        self._logger.debug(
            "notification_dispatch",
            notification_event_type=message.event_type,
            notification_notifiers_count=len(self.notifiers),
        )
        for notifier in self.notifiers:
            await notifier.send_notification(message)
