# -*- coding: utf-8 -*-
"""Notification message types."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Protocol, Optional


@dataclass(frozen=True)
class NotificationMessage:
    """Message to be sent via one or more notification channels."""

    event_type: str
    message: str
    title: Optional[str] = None
    payload: Optional[dict[str, Any]] = None


class NotificationStyler(Protocol):
    """Render a message into a formatted string for delivery."""

    def render(self, message: NotificationMessage, *, parse_html: bool = False) -> str:
        """Return a formatted message for the given message.

        Args:
            message: Notification message to render.
            parse_html: If True, output includes HTML. If False (default), plain text.
        """
        ...
