# -*- coding: utf-8 -*-
"""Order execution events (bubus BaseEvent)."""

from __future__ import annotations

from typing import Any, Literal, Optional

from bubus import BaseEvent  # type: ignore[import-untyped]


class OrderPlacedEvent(BaseEvent[None]):
    """Emitted when a market order has been placed (buy or sell)."""

    token_id: str
    side: Literal["BUY", "SELL"]
    amount: float
    amount_kind: Literal["usdc", "shares"]
    success: bool
    order_id: Optional[str] = None
    error_msg: Optional[str] = None
    status: Optional[str] = None

    # Optional: raw response summary for handlers that need it
    response_summary: Optional[dict[str, Any]] = None
