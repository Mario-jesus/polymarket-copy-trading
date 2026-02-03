# -*- coding: utf-8 -*-
"""Notification service and styler interface."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from typing import List

from polymarket_copy_trading.notifications.strategies import BaseNotificationStrategy
from polymarket_copy_trading.notifications.types import NotificationMessage


@dataclass
class NotificationService:
    """Dispatch notifications to all configured channels."""

    notifiers: List[BaseNotificationStrategy]
    queue_size: int = 1000
    _queue: asyncio.Queue[NotificationMessage] | None = field(init=False, default=None)
    _worker_task: asyncio.Task[None] | None = field(init=False, default=None)

    async def initialize(self) -> None:
        """Initialize all notifiers."""
        for notifier in self.notifiers:
            await notifier.initialize()
        if not self.notifiers:
            self._queue = None
            self._worker_task = None
            return
        self._queue = asyncio.Queue[NotificationMessage](maxsize=self.queue_size)
        self._worker_task = asyncio.create_task(self._worker_loop())

    async def shutdown(self) -> None:
        """Shutdown all notifiers."""
        if self._queue is not None:
            self._queue.shutdown()
            await self._queue.join()
        if self._worker_task is not None:
            await self._worker_task
            self._worker_task = None
        self._queue = None

        for notifier in self.notifiers:
            await notifier.shutdown()

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
            # Log? For now, just drop silently
            pass

    async def _worker_loop(self) -> None:
        queue = self._queue
        if queue is None:
            return
        while True:
            try:
                msg = await queue.get()
            except asyncio.QueueShutDown:
                break
            try:
                await self._dispatch(msg)
            finally:
                queue.task_done()

    async def _dispatch(self, message: NotificationMessage) -> None:
        for notifier in self.notifiers:
            await notifier.send_notification(message)
