# -*- coding: utf-8 -*-
"""Copy-trade specific events (emitted by CopyTradingEngineService and OrderAnalysisWorker)."""

from __future__ import annotations

from typing import Literal, Optional
from uuid import UUID

from bubus import BaseEvent  # type: ignore[import-untyped]


class CopyTradeFailedEvent(BaseEvent[None]):
    """Emitted when a copy trade fails (order placement, trade confirmation, or position update).

    Handled by TradeFailedNotifier to send notifications.
    """

    reason: str
    """One of: order_placement_failed, trade_not_found, position_not_found,
    position_update_failed, queue_full, parse_trade_error, get_trades_error."""

    position_id: Optional[UUID] = None
    order_id: Optional[str] = None
    tracked_wallet: str
    asset: str
    is_open: bool
    error_message: Optional[str] = None
    transaction_hash: Optional[str] = None
    amount: Optional[float] = None
    amount_kind: Optional[Literal["usdc", "shares"]] = None


class CopyTradeOrderPlacedEvent(BaseEvent[None]):
    """Emitted when the copy-trading engine places an order (open or close position).

    Carries full context for OrderAnalysisWorker to reconcile with get_trades.
    """

    order_id: str
    """Order id from post_order response (taker_order_id in trade)."""

    position_id: UUID
    tracked_wallet: str
    asset: str
    is_open: bool
    """True if opening a position, False if closing."""

    amount: float
    amount_kind: Literal["usdc", "shares"]
    success: bool

    transaction_hash: Optional[str] = None
    """First transaction hash from post_order response. Used as fallback to match trade."""
