# -*- coding: utf-8 -*-
"""In-memory async queue implementation."""

from __future__ import annotations

import asyncio

from polymarket_copy_trading.queue.base import IAsyncQueue
from polymarket_copy_trading.exceptions import (
    QueueEmpty,
    QueueFull,
    QueueShutdown,
)


class InMemoryQueue[T](IAsyncQueue[T]):
    """In-memory implementation of AsyncQueue using asyncio.Queue."""

    def __init__(self, maxsize: int = 0) -> None:
        """Initialize the queue.

        Args:
            maxsize: Maximum number of items. 0 means unbounded.
        """
        self._queue: asyncio.Queue[T] = asyncio.Queue(maxsize=maxsize)

    def __len__(self) -> int:
        """Return the number of items in the queue."""
        return self._queue.qsize()

    async def put(self, item: T) -> None:
        """Put item into the queue. Blocks if full until space is available.

        Args:
            item: The item to put into the queue.

        Raises:
            QueueShutdown: If the queue has been shut down (no more items can be put).
        """
        try:
            await self._queue.put(item)
        except asyncio.QueueShutDown as e:
            raise QueueShutdown from e

    def put_nowait(self, item: T) -> None:
        """Put item into the queue without blocking.

        Args:
            item: The item to put into the queue.

        Raises:
            QueueFull: If the queue has reached its maximum size.
            QueueShutdown: If the queue has been shut down (no more items can be put).
        """
        try:
            self._queue.put_nowait(item)
        except asyncio.QueueShutDown as e:
            raise QueueShutdown from e
        except asyncio.QueueFull as e:
            raise QueueFull from e

    async def get(self) -> T:
        """Remove and return an item. Blocks until an item is available.

        Returns:
            The next item from the queue.

        Raises:
            QueueShutdown: If the queue has been shut down and is empty, or was shut down
                with immediate=True. Signals consumers to exit gracefully.
        """
        try:
            return await self._queue.get()
        except asyncio.QueueShutDown as e:
            raise QueueShutdown from e

    def get_nowait(self) -> T:
        """Remove and return an item without blocking.

        Returns:
            The next item from the queue.

        Raises:
            QueueEmpty: If the queue has no items (and is not shut down).
            QueueShutdown: If the queue has been shut down and is empty, or was shut down
                with immediate=True.
        """
        try:
            return self._queue.get_nowait()
        except asyncio.QueueShutDown as e:
            raise QueueShutdown from e
        except asyncio.QueueEmpty as e:
            raise QueueEmpty from e

    def task_done(self) -> None:
        """Mark the last item retrieved by get() as processed.

        Must be called once per item after processing. Used by join() to know
        when all work is done.
        """
        self._queue.task_done()

    def qsize(self) -> int:
        """Return the approximate number of items in the queue.

        Returns:
            The number of items currently in the queue.
        """
        return self._queue.qsize()

    def empty(self) -> bool:
        """Return True if the queue is empty.

        Returns:
            True if there are no items in the queue, False otherwise.
        """
        return self._queue.empty()

    def full(self) -> bool:
        """Return True if the queue is full (has reached maxsize).

        Returns:
            True if the queue is at capacity, False otherwise. Always False when maxsize is 0.
        """
        return self._queue.full()

    def shutdown(self, immediate: bool = False) -> None:
        """Shutdown the queue so no more items can be put and consumers can exit.

        Args:
            immediate: If True, shut down without waiting for in-flight items to be processed.
                If False, existing items may still be consumed until the queue is empty.
        """
        self._queue.shutdown(immediate)

    async def join(self) -> None:
        """Wait until every item gotten from the queue has been marked with task_done().

        Blocks until the count of unfinished tasks drops to zero.
        """
        await self._queue.join()
