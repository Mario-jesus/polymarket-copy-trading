# -*- coding: utf-8 -*-
"""Async queue interface (protocol)."""

from __future__ import annotations

from abc import ABC, abstractmethod


class IAsyncQueue[T](ABC):
    """Abstract interface for an async queue: put/get with optional non-blocking variants.

    Implementations must provide blocking and non-blocking put/get, task_done/join
    semantics, and shutdown. Use the exceptions from queue.exceptions (QueueFull,
    QueueEmpty, QueueShutdown) where specified.
    """

    @abstractmethod
    async def put(self, item: T) -> None:
        """Put item into the queue. Blocks if full until space is available.

        Args:
            item: The item to put into the queue.

        Raises:
            QueueShutdown: If the queue has been shut down (no more items can be put).
        """
        ...

    @abstractmethod
    def put_nowait(self, item: T) -> None:
        """Put item into the queue without blocking.

        Args:
            item: The item to put into the queue.

        Raises:
            QueueFull: If the queue has reached its maximum size.
            QueueShutdown: If the queue has been shut down (no more items can be put).
        """
        ...

    @abstractmethod
    async def get(self) -> T:
        """Remove and return an item. Blocks until an item is available.

        Returns:
            The next item from the queue.

        Raises:
            QueueShutdown: If the queue has been shut down and is empty, or was shut down
                with immediate=True. Signals consumers to exit gracefully.
        """
        ...

    @abstractmethod
    def get_nowait(self) -> T:
        """Remove and return an item without blocking.

        Returns:
            The next item from the queue.

        Raises:
            QueueEmpty: If the queue has no items (and is not shut down).
            QueueShutdown: If the queue has been shut down and is empty, or was shut down
                with immediate=True.
        """
        ...

    @abstractmethod
    def task_done(self) -> None:
        """Mark the last item retrieved by get() as processed.

        Must be called once per item after processing. Used by join() to know
        when all work is done.
        """
        ...

    @abstractmethod
    def shutdown(self, immediate: bool = False) -> None:
        """Shutdown the queue so no more items can be put and consumers can exit.

        Args:
            immediate: If True, shut down without waiting for in-flight items.
                If False, existing items may still be consumed until empty.
        """
        ...

    @abstractmethod
    async def join(self) -> None:
        """Wait until every item gotten from the queue has been marked with task_done().

        Blocks until the count of unfinished tasks drops to zero.
        """
        ...

    @abstractmethod
    def qsize(self) -> int:
        """Return the approximate number of items in the queue.

        Returns:
            The number of items currently in the queue.
        """
        ...

    @abstractmethod
    def empty(self) -> bool:
        """Return True if the queue is empty.

        Returns:
            True if there are no items in the queue, False otherwise.
        """
        ...

    @abstractmethod
    def full(self) -> bool:
        """Return True if the queue is full (has reached maxsize).

        Returns:
            True if the queue is at capacity, False otherwise.
        """
        ...
