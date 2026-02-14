# -*- coding: utf-8 -*-
"""TradeFailedNotifier: listens to CopyTradeFailedEvent and sends notifications."""

from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING, Any, Callable, Optional

import structlog

from polymarket_copy_trading.events.orders.copy_trade_events import CopyTradeFailedEvent
from polymarket_copy_trading.notifications.types import NotificationMessage

if TYPE_CHECKING:
    from bubus import EventBus  # type: ignore[import-untyped]

    from polymarket_copy_trading.notifications.notification_manager import NotificationService


_REASON_LABELS = {
    "order_placement_failed": "Order placement failed",
    "trade_not_found": "Trade not found in API",
    "position_not_found": "Position not found",
    "position_update_failed": "Position update failed",
    "queue_full": "Order analysis queue full",
    "parse_trade_error": "Parse trade error",
    "get_trades_error": "Get trades API error",
}


def _dt_to_str(v: Optional[datetime]) -> Optional[str]:
    """Convert datetime to ISO string for payload."""
    if v is None:
        return None
    return v.isoformat()


class TradeFailedNotifier:
    """Subscribes to CopyTradeFailedEvent and sends notifications via NotificationService."""

    def __init__(
        self,
        notification_service: "NotificationService",
        event_bus: Any,
        *,
        get_logger: Callable[[str], Any] = structlog.get_logger,
        logger_name: Optional[str] = None,
    ) -> None:
        self._notification_service = notification_service
        self._event_bus: "EventBus" = event_bus
        self._logger = get_logger(logger_name or self.__class__.__name__)

    def start(self) -> None:
        """Subscribe to CopyTradeFailedEvent."""
        self._event_bus.on(CopyTradeFailedEvent, self._on_failed)
        self._logger.debug("trade_failed_notifier_started")

    def stop(self) -> None:
        """Unsubscribe from CopyTradeFailedEvent."""
        key = CopyTradeFailedEvent.__name__
        handlers = getattr(self._event_bus, "handlers", {})
        if key in handlers:
            handlers[key] = [h for h in handlers[key] if h != self._on_failed]
        self._logger.debug("trade_failed_notifier_stopped")

    def _on_failed(self, event: CopyTradeFailedEvent) -> None:
        """Handle CopyTradeFailedEvent: build and send notification."""
        label = _REASON_LABELS.get(event.reason, event.reason.replace("_", " ").title())
        message = f"Copy trade failed: {label}"
        if event.error_message:
            message += f" — {event.error_message}"

        payload: dict[str, Any] = {
            "reason": event.reason,
            "wallet": event.tracked_wallet,
            "asset": event.asset,
            "is_open": event.is_open,
        }
        if event.position_id is not None:
            payload["position_id"] = str(event.position_id)
        if event.order_id:
            payload["order_id"] = event.order_id
            payload["close_order_id"] = event.order_id
        if event.error_message:
            payload["error_message"] = event.error_message
        if event.transaction_hash:
            payload["transaction_hash"] = event.transaction_hash
            payload["close_transaction_hash"] = event.transaction_hash
        if event.amount is not None:
            payload["amount"] = event.amount
        if event.amount_kind:
            payload["amount_kind"] = event.amount_kind
        if event.close_requested_at is not None:
            payload["close_requested_at"] = _dt_to_str(event.close_requested_at)
        if event.close_attempts is not None:
            payload["close_attempts"] = event.close_attempts

        notification = NotificationMessage(
            event_type="trade_failed",
            message=message,
            payload=payload,
        )
        self._notification_service.notify(notification)
        self._logger.debug(
            "trade_failed_notified",
            reason=event.reason,
            position_id=str(event.position_id) if event.position_id else None,
            order_id=event.order_id,
            asset=event.asset,
        )
