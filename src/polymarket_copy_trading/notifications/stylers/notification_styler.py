# -*- coding: utf-8 -*-
"""Event-based notification styler with emoji separators (Telegram-style)."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, cast

from polymarket_copy_trading.notifications.types import NotificationMessage, NotificationStyler


_TRADE_EVENT_TYPES = frozenset({"trade_new", "position_opened", "position_closed"})


class EventNotificationStyler(NotificationStyler):
    """Render notifications by event_type with emojis, separators and formatted sections."""

    def render(self, message: NotificationMessage) -> str:
        """Dispatch to the appropriate renderer based on event_type."""
        if message.event_type in _TRADE_EVENT_TYPES:
            return self._render_trade(message)
        if message.event_type == "system_started":
            return self._render_system_started(message)
        if message.event_type == "system_stopped":
            return self._render_system_stopped(message)
        return self._render_generic(message)

    def _render_trade(self, message: NotificationMessage) -> str:
        """Render trade/position notifications."""
        payload: dict[str, Any] = message.payload.copy() if message.payload else {}
        trade_raw = payload.get("trade")
        if isinstance(trade_raw, dict):
            trade = cast(dict[str, Any], trade_raw)
        else:
            trade = {}

        wallet_value = payload.get("wallet")
        wallet = wallet_value if isinstance(wallet_value, str) else trade.get("wallet")
        emoji, title = self._title(message.event_type)
        is_snapshot = payload.get("isSnapshot", False)
        snapshot_tag = " 📸 Snapshot" if is_snapshot else ""

        summary_lines = [
            f"{emoji} <b>{title}{snapshot_tag}</b>\n",
            self._section(
                "📊 Trade Summary",
                [
                    ("👛 Wallet", wallet or "N/A"),
                    ("🆔 Market ID", trade.get("market_id") or "N/A"),
                    ("🔗 Condition ID", trade.get("condition_id") or "N/A"),
                    ("🏷️ Event Slug", trade.get("event_slug") or ""),
                    ("🧩 Market Slug", trade.get("slug") or ""),
                ],
            ),
            self._section(
                "💰 Trade Details",
                [
                    ("🕒 Timestamp", self._format_timestamp(trade.get("timestamp"))),
                    ("📈 Side", trade.get("side") or "N/A"),
                    ("📉 Outcome", trade.get("outcome") or "N/A"),
                    ("💵 Price", self._format_number(trade.get("price"))),
                    ("📦 Size", self._format_number(trade.get("size"))),
                    ("🔗 Transaction", trade.get("transaction_hash") or ""),
                    ("🪙 Asset", trade.get("asset") or ""),
                ],
            ),
        ]

        trader_name = trade.get("trader_name") or trade.get("trader_pseudonym")
        if trader_name:
            summary_lines.append(
                self._section("👤 Trader", [("🎭 Nickname", trader_name)])
            )

        title_text = trade.get("title")
        if title_text:
            summary_lines.append(
                self._section(
                    "📝 Market Title",
                    [("", title_text)],
                )
            )

        return "\n".join([line for line in summary_lines if line]).strip()

    def _render_system_started(self, message: NotificationMessage) -> str:
        """Render system started notification."""
        emoji, title = self._title(message.event_type)
        payload = message.payload or {}
        raw_wallet = payload.get("target_wallet")
        raw_wallets = payload.get("target_wallets")
        wallet_strs: list[str] = []
        if raw_wallet and isinstance(raw_wallet, str):
            wallet_strs = [raw_wallet]
        elif isinstance(raw_wallets, list):
            wallet_strs = [str(w) for w in cast(list[Any], raw_wallets)]
        lines = [f"{emoji} <b>{title}</b>\n", self._section("🚀 Status", [("", message.message)])]
        if wallet_strs:
            lines.append(self._section("👛 Wallets", [("", ", ".join(wallet_strs))]))
        return "\n".join([line for line in lines if line]).strip()

    def _render_system_stopped(self, message: NotificationMessage) -> str:
        """Render system stopped notification."""
        emoji, title = self._title(message.event_type)
        lines = [f"{emoji} <b>{title}</b>\n", self._section("🛑 Status", [("", message.message)])]
        return "\n".join([line for line in lines if line]).strip()

    def _render_generic(self, message: NotificationMessage) -> str:
        """Render unknown event types using message and payload."""
        emoji, title = self._title(message.event_type)
        lines = [f"{emoji} <b>{title}</b>", message.message]
        if message.payload:
            for key in sorted(message.payload.keys()):
                value = message.payload.get(key)
                if value is not None:
                    lines.append(f"<b>{key}:</b> {value}")
        return "\n".join(lines).strip()

    @staticmethod
    def _title(event_type: str) -> tuple[str, str]:
        """Get the emoji and title for the given event type."""
        mapping = {
            "position_opened": ("🟢", "Position Opened"),
            "position_closed": ("🔴", "Position Closed"),
            "trade_new": ("🆕", "New Trade"),
            "system_started": ("▶️", "System Started"),
            "system_stopped": ("⏹️", "System Stopped"),
        }
        return mapping.get(event_type, ("ℹ️", event_type.replace("_", " ").title()))

    def _section(self, header: str, rows: list[tuple[str, Any]]) -> str:
        """Format a section with a header and rows."""
        lines: list[str] = []
        content_lines: list[str] = []
        for label, value in rows:
            if not value:
                continue
            if label:
                content_lines.append(f"{self._format_label(label)} {value}")
            else:
                content_lines.append(str(value))
        if not content_lines:
            return ""
        lines.append(f"{self._format_heading(header)}\n{'─'*12}")
        lines.extend(content_lines)
        return "\n".join(lines) + "\n"

    @staticmethod
    def _format_number(value: Any) -> str:
        """Format a number with thousands separator and 4 decimal places."""
        if value is None:
            return "N/A"
        try:
            number = float(value)
        except (TypeError, ValueError):
            return str(value)
        return f"{number:,.4f}"

    @staticmethod
    def _format_timestamp(value: Any) -> str:
        """Format epoch seconds into ISO-8601 UTC when possible."""
        if value is None:
            return "N/A"
        try:
            ts = float(value)
        except (TypeError, ValueError):
            return str(value)
        try:
            return datetime.fromtimestamp(ts, tz=timezone.utc).isoformat()
        except (OSError, OverflowError, ValueError):
            return str(value)

    @staticmethod
    def _format_heading(text: str) -> str:
        """Format a section heading with bold text."""
        if not text:
            return ""
        emoji, _, remainder = text.partition(" ")
        if remainder:
            return f"{emoji} <b>{remainder}</b>"
        return f"<b>{text}</b>"

    @staticmethod
    def _format_label(label: str) -> str:
        """Format row labels with bold text."""
        if not label:
            return ""
        emoji, _, remainder = label.partition(" ")
        if remainder:
            return f"{emoji} <b>{remainder}:</b>"
        return f"<b>{label}:</b>"
