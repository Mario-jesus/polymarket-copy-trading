"""Queue-specific exceptions."""

from __future__ import annotations


class QueueError(Exception):
    """Base exception for queue operations."""


class QueueFull(QueueError):
    """Raised when putting an item into a queue that has reached its max size (non-blocking put)."""


class QueueEmpty(QueueError):
    """Raised when getting an item from an empty queue (non-blocking get)."""


class QueueShutdown(QueueError):
    """Raised when performing an operation on a queue that has been shut down."""
