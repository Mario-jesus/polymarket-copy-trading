"""TradeConfirmedNotifier: builds and sends notifications when a trade is confirmed."""

from __future__ import annotations

from collections.abc import Callable
from datetime import datetime
from decimal import Decimal
from typing import TYPE_CHECKING, Any

import structlog

from polymarket_copy_trading.notifications.types import NotificationMessage

if TYPE_CHECKING:
    from polymarket_copy_trading.clients.clob_client.schema import TradeSchema
    from polymarket_copy_trading.models.bot_position import BotPosition
    from polymarket_copy_trading.notifications.notification_manager import (
        NotificationService,
    )
    from polymarket_copy_trading.services.pnl import PnLService


def _dec_to_str(v: Decimal | None) -> str | None:
    """Convert Decimal to string for payload."""
    if v is None:
        return None
    return str(v)


def _dt_to_str(v: datetime | None) -> str | None:
    """Convert datetime to ISO string for payload."""
    if v is None:
        return None
    return v.isoformat()


def _build_trade_payload(
    position: BotPosition,
    trade: TradeSchema,
    is_open: bool,
    pnl_result: Any | None = None,
) -> dict[str, Any]:
    """Build trade dict for EventNotificationStyler._render_trade."""
    side = "BUY" if is_open else "SELL"
    payload: dict[str, Any] = {
        "wallet": position.tracked_wallet,
        "asset": trade.get("asset_id") or position.asset,
        "side": side,
        "price": trade.get("price"),
        "size": trade.get("size") or str(position.shares_held),
        "transaction_hash": trade.get("transaction_hash"),
        "outcome": trade.get("outcome"),
        "condition_id": trade.get("condition_id") or trade.get("conditionId"),
        "position_id": str(position.id),
        "entry_cost_usdc": _dec_to_str(position.entry_cost_usdc),
        "close_order_id": position.close_order_id,
        "close_transaction_hash": position.close_transaction_hash,
        "close_requested_at": _dt_to_str(position.close_requested_at),
        "close_attempts": position.close_attempts,
    }
    if not is_open:
        payload["close_proceeds_usdc"] = _dec_to_str(position.close_proceeds_usdc)
        payload["fees_usdc"] = _dec_to_str(position.fees)
        if pnl_result is not None:
            payload["realized_pnl_usdc"] = _dec_to_str(pnl_result.realized_pnl_usdc)
            payload["net_pnl_usdc"] = _dec_to_str(pnl_result.net_pnl_usdc)
    return payload


class TradeConfirmedNotifier:
    """Builds NotificationMessage for position_opened/position_closed and sends via NotificationService."""

    def __init__(
        self,
        notification_service: NotificationService,
        pnl_service: PnLService,
        *,
        get_logger: Callable[[str], Any] = structlog.get_logger,
        logger_name: str | None = None,
    ) -> None:
        self._notification_service = notification_service
        self._pnl_service = pnl_service
        self._logger = get_logger(logger_name or self.__class__.__name__)

    def notify(
        self,
        position: BotPosition,
        trade: TradeSchema,
        is_open: bool,
    ) -> None:
        """Send notification for confirmed position open or close.

        For position_closed, includes PnL from PnLService.
        """
        event_type = "position_opened" if is_open else "position_closed"
        pnl_result = None
        if not is_open:
            pnl_result = self._pnl_service.compute(position)

        trade_payload = _build_trade_payload(position, trade, is_open, pnl_result)
        message = (
            "Position opened"
            if is_open
            else f"Position closed (PnL: {_dec_to_str(pnl_result.net_pnl_usdc) if pnl_result and pnl_result.net_pnl_usdc is not None else 'N/A'} USDC)"
        )

        notification = NotificationMessage(
            event_type=event_type,
            message=message,
            payload={"trade": trade_payload},
        )
        self._notification_service.notify(notification)
        self._logger.debug(
            "trade_confirmed_notified",
            event_type=event_type,
            position_id=str(position.id),
            asset=position.asset,
        )
