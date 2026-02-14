"""Event-based notification styler with emoji separators (Telegram-style).

Each event type has a dedicated protected render method. Format adapted from
Polymarket copy-trading context (USDC, shares, condition_id, etc.).
"""

from __future__ import annotations

import re
from datetime import UTC, datetime
from typing import Any, cast

from polymarket_copy_trading.notifications.types import (
    NotificationMessage,
    NotificationStyler,
)


class EventNotificationStyler(NotificationStyler):
    """Render notifications by event_type. One protected method per type."""

    def render(self, message: NotificationMessage, *, parse_html: bool = False) -> str:
        """Dispatch to the appropriate renderer based on event_type.

        Args:
            message: Notification message to render.
            parse_html: If True, output includes HTML tags (e.g. <b>) for rich display.
                If False (default), output is plain text without HTML.
        """
        if message.event_type == "position_opened":
            result = self._render_position_opened(message)
        elif message.event_type == "position_closed":
            result = self._render_position_closed(message)
        elif message.event_type == "trade_failed":
            result = self._render_trade_failed(message)
        elif message.event_type == "system_started":
            result = self._render_system_started(message)
        elif message.event_type == "system_stopped":
            result = self._render_system_stopped(message)
        elif message.event_type == "trade_new":
            result = self._render_trade_new(message)
        else:
            result = self._render_generic(message)

        if not parse_html:
            result = self._strip_html(result)
        return result

    @staticmethod
    def _strip_html(text: str) -> str:
        """Remove HTML tags from text. Returns plain text."""
        return re.sub(r"<[^>]+>", "", text)

    def _render_position_opened(self, message: NotificationMessage) -> str:
        """Render position opened notification."""
        payload = message.payload or {}
        trade = self._extract_trade(payload)
        wallet = trade.get("wallet") or payload.get("wallet") or "N/A"
        asset = trade.get("asset") or "N/A"
        position_id = trade.get("position_id") or "N/A"
        tx_hash = trade.get("transaction_hash") or "N/A"
        amount_usdc = self._format_amount(trade.get("entry_cost_usdc"))
        shares = self._format_amount(trade.get("size"))
        price = self._format_amount(trade.get("price"))
        condition_id = trade.get("condition_id") or "N/A"
        outcome = trade.get("outcome") or "N/A"
        time_str = self._format_datetime_now()

        return (
            f"🟢 <b>Position Opened</b>\n\n"
            f"📊 <b>Trade Summary</b>\n"
            f"{'─' * 12}\n"
            f"🪙  <b>Asset:</b> {asset}\n"
            f"🔗 <b>Condition ID:</b> {condition_id}\n"
            f"📉 <b>Outcome:</b> {outcome}\n\n"
            f"👤 <b>Trader Info</b>\n"
            f"{'─' * 12}\n"
            f"🔗 <b>Wallet:</b> {wallet}\n\n"
            f"💰 <b>Trade Details</b>\n"
            f"{'─' * 12}\n"
            f"🔑 <b>Position ID:</b> {position_id}\n"
            f"🔗 <b>Transaction Hash:</b> {tx_hash}\n"
            f"📥 <b>Amount:</b> {amount_usdc} USDC\n"
            f"🪙  <b>Shares:</b> {shares}\n"
            f"💵 <b>Price:</b> {price} USDC\n\n"
            f"⏰ <b>Time:</b> {time_str}"
        )

    def _render_position_closed(self, message: NotificationMessage) -> str:
        """Render position closed notification with PnL."""
        payload = message.payload or {}
        trade = self._extract_trade(payload)
        wallet = trade.get("wallet") or payload.get("wallet") or "N/A"
        asset = trade.get("asset") or "N/A"
        position_id = trade.get("position_id") or "N/A"
        tx_hash = trade.get("transaction_hash") or "N/A"
        entry_usdc = self._format_amount(trade.get("entry_cost_usdc"))
        close_usdc = self._format_amount(trade.get("close_proceeds_usdc"))
        shares = self._format_amount(trade.get("size"))
        fees_usdc = self._format_amount(trade.get("fees_usdc"))
        realized_pnl = trade.get("realized_pnl_usdc")
        net_pnl = trade.get("net_pnl_usdc")
        close_order_id = trade.get("close_order_id") or "N/A"
        close_tx_hash = trade.get("close_transaction_hash") or tx_hash
        close_requested_at_raw = trade.get("close_requested_at")
        close_attempts = trade.get("close_attempts")
        condition_id = trade.get("condition_id") or "N/A"
        outcome = trade.get("outcome") or "N/A"
        time_str = self._format_datetime_now()

        pnl_indicator = self._pnl_indicator(net_pnl)
        realized_str = self._format_amount(realized_pnl)
        net_str = self._format_amount(net_pnl)

        return (
            f"🔴 <b>Position Closed</b>\n\n"
            f"📊 <b>Trade Summary</b>\n"
            f"{'─' * 12}\n"
            f"🪙 <b>Asset:</b> {asset}\n"
            f"🔗 <b>Condition ID:</b> {condition_id}\n"
            f"📉 <b>Outcome:</b> {outcome}\n\n"
            f"👤 <b>Trader Info</b>\n"
            f"{'─' * 12}\n"
            f"🔗 <b>Wallet:</b> {wallet}\n\n"
            f"💰 <b>Trade Details</b>\n"
            f"{'─' * 12}\n"
            f"🔑 <b>Position ID:</b> {position_id}\n"
            f"🔗 <b>Transaction Hash:</b> {tx_hash}\n"
            f"📥 <b>Entry:</b> {entry_usdc} USDC\n"
            f"📤 <b>Close Proceeds:</b> {close_usdc} USDC\n"
            f"🪙 <b>Shares:</b> {shares}\n"
            f"🧾 <b>Fees:</b> {fees_usdc} USDC\n\n"
            f"🧭 <b>Close Tracking</b>\n"
            f"{'─' * 12}\n"
            f"📋 <b>Close Order ID:</b> {close_order_id}\n"
            f"🔗 <b>Close Transaction Hash:</b> {close_tx_hash}\n"
            f"⏳ <b>Close Requested At:</b> {self._format_iso_or_value(close_requested_at_raw)}\n"
            f"🔁 <b>Close Attempts:</b> {close_attempts if close_attempts is not None else 'N/A'}\n\n"
            f"📈 <b>P&L</b>\n"
            f"{'─' * 12}\n"
            f"📊 <b>Realized:</b> {realized_str} USDC\n"
            f"{pnl_indicator} <b>Net:</b> {net_str} USDC\n\n"
            f"⏰ <b>Time:</b> {time_str}"
        )

    def _render_trade_failed(self, message: NotificationMessage) -> str:
        """Render trade failed notification."""
        payload = message.payload or {}
        wallet = payload.get("wallet") or "N/A"
        asset = payload.get("asset") or "N/A"
        reason = payload.get("reason") or "Unknown"
        is_open = payload.get("is_open", True)
        position_id = payload.get("position_id") or "N/A"
        order_id = payload.get("order_id") or "N/A"
        close_order_id = payload.get("close_order_id") or order_id
        error_msg = payload.get("error_message") or "N/A"
        tx_hash = payload.get("transaction_hash") or "N/A"
        close_tx_hash = payload.get("close_transaction_hash") or tx_hash
        close_requested_at_raw = payload.get("close_requested_at")
        close_attempts = payload.get("close_attempts")
        amount = payload.get("amount")
        amount_kind = payload.get("amount_kind", "")
        time_str = self._format_datetime_now()

        side_str = "BUY" if is_open else "SELL"
        amount_line = ""
        if amount is not None and amount_kind:
            amount_emoji = "📥" if is_open else "📤"
            amount_line = (
                f"{amount_emoji} <b>Amount:</b> {self._format_amount(amount)} {amount_kind}\n"
            )

        has_close_tracking = (
            not is_open
            or payload.get("close_order_id") is not None
            or payload.get("close_transaction_hash") is not None
            or payload.get("close_requested_at") is not None
            or payload.get("close_attempts") is not None
        )
        close_tracking_block = ""
        if has_close_tracking:
            close_tracking_block = (
                f"\n🧭 <b>Close Tracking</b>\n"
                f"{'─' * 12}\n"
                f"📋 <b>Close Order ID:</b> {close_order_id}\n"
                f"🔗 <b>Close Transaction Hash:</b> {close_tx_hash}\n"
                f"⏳ <b>Close Requested At:</b> {self._format_iso_or_value(close_requested_at_raw)}\n"
                f"🔁 <b>Close Attempts:</b> {close_attempts if close_attempts is not None else 'N/A'}\n"
            )

        return (
            f"❌ <b>Trade Failed</b>\n\n"
            f"📊 <b>Trade Summary</b>\n"
            f"{'─' * 12}\n"
            f"🪙 <b>Asset:</b> {asset}\n"
            f"📈 <b>Side:</b> {side_str}\n"
            f"📋 <b>Reason:</b> {reason}\n\n"
            f"👤 <b>Trader Info</b>\n"
            f"{'─' * 12}\n"
            f"🔗 <b>Wallet:</b> {wallet}\n\n"
            f"💰 <b>Failure Details</b>\n"
            f"{'─' * 12}\n"
            f"🔑 <b>Position ID:</b> {position_id}\n"
            f"📋 <b>Order ID:</b> {order_id}\n"
            f"🔗 <b>Transaction Hash:</b> {tx_hash}\n"
            f"{amount_line}"
            f"⚠️ <b>Error:</b> {error_msg}\n\n"
            f"{close_tracking_block}\n"
            f"⏰ <b>Time:</b> {time_str}"
        )

    def _render_system_started(self, message: NotificationMessage) -> str:
        """Render system started notification."""
        payload = message.payload or {}
        raw_wallet = payload.get("target_wallet")
        raw_wallets = payload.get("target_wallets")
        wallet_strs: list[str] = []
        if raw_wallet and isinstance(raw_wallet, str):
            wallet_strs = [raw_wallet]
        elif isinstance(raw_wallets, list):
            wallet_strs = [str(w) for w in cast(list[Any], raw_wallets)]
        wallets_str = ", ".join(wallet_strs) if wallet_strs else "N/A"
        time_str = self._format_datetime_now()

        return (
            f"▶️ <b>System Started</b>\n\n"
            f"🚀 <b>Status</b>\n"
            f"{'─' * 12}\n"
            f"{message.message}\n\n"
            f"👛 <b>Target Wallet:</b> {wallets_str}\n\n"
            f"⏰ <b>Time:</b> {time_str}"
        )

    def _render_system_stopped(self, message: NotificationMessage) -> str:
        """Render system stopped notification."""
        time_str = self._format_datetime_now()
        return (
            f"⏹️ <b>System Stopped</b>\n\n"
            f"🛑 <b>Status</b>\n"
            f"{'─' * 12}\n"
            f"{message.message}\n\n"
            f"⏰ <b>Time:</b> {time_str}"
        )

    def _render_trade_new(self, message: NotificationMessage) -> str:
        """Render trade_new (generic new trade). Falls back to position_opened style if trade present."""
        payload = message.payload or {}
        trade = self._extract_trade(payload)
        if trade and trade.get("position_id"):
            return self._render_position_opened(message)
        return self._render_generic(message)

    def _render_generic(self, message: NotificationMessage) -> str:
        """Render unknown event types using message and payload."""
        event_title = message.event_type.replace("_", " ").title()
        lines = [f"ℹ️ <b>{event_title}</b>\n", message.message]
        if message.payload:
            lines.append("")
            for key in sorted(message.payload.keys()):
                value = message.payload.get(key)
                if value is not None:
                    lines.append(f"<b>{key}:</b> {value}")
        return "\n".join(lines).strip()

    def _extract_trade(self, payload: dict[str, Any]) -> dict[str, Any]:
        """Extract trade dict from payload (payload.trade or empty)."""
        trade_raw = payload.get("trade")
        if isinstance(trade_raw, dict):
            return cast(dict[str, Any], trade_raw)
        return {}

    @staticmethod
    def _format_amount(value: Any) -> str:
        """Format amount with thousands separator and 4 decimal places."""
        if value is None:
            return "N/A"
        try:
            number = float(value)
        except (TypeError, ValueError):
            return str(value)
        return f"{number:,.4f}"

    @staticmethod
    def _pnl_indicator(value: Any) -> str:
        """Return emoji indicator for PnL (positive/negative/zero)."""
        if value is None:
            return "📊"
        try:
            n = float(value)
        except (TypeError, ValueError):
            return "📊"
        if n > 0:
            return "🟢"
        if n < 0:
            return "🔴"
        return "⚪"

    @staticmethod
    def _format_datetime_now() -> str:
        """Format current datetime for display."""
        return datetime.now(UTC).isoformat()

    @staticmethod
    def _format_timestamp(value: Any) -> str:
        """Format epoch seconds to readable datetime."""
        if value is None:
            return "N/A"
        try:
            ts = float(value)
        except (TypeError, ValueError):
            return str(value)
        try:
            return datetime.fromtimestamp(ts, tz=UTC).isoformat()
        except (OSError, OverflowError, ValueError):
            return str(value)

    @staticmethod
    def _format_iso_or_value(value: Any) -> str:
        """Format ISO datetime strings or return readable fallback."""
        if value is None:
            return "N/A"
        if isinstance(value, str):
            try:
                dt = datetime.fromisoformat(value)
                return dt.isoformat()
            except ValueError:
                return value
        return str(value)
