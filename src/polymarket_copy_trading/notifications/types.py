# -*- coding: utf-8 -*-
"""Notification message types."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Protocol


@dataclass(frozen=True)
class NotificationMessage:
    """Message to be sent via one or more notification channels."""

    event_type: str
    message: str
    title: str | None = None
    payload: dict[str, Any] | None = None


class NotificationStyler(Protocol):
    """Render a message into a formatted string for delivery."""

    def render(self, message: NotificationMessage) -> str:
        """Return a formatted message for the given message."""
        ...
