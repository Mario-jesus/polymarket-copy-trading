# -*- coding: utf-8 -*-
"""Trade tracking service (polling)."""

from __future__ import annotations

import asyncio
import structlog
from collections.abc import Awaitable, Callable
from typing import Any, Optional

from polymarket_copy_trading.clients.data_api import DataApiClient
from polymarket_copy_trading.clients.gamma_cache import GammaCache
from polymarket_copy_trading.config import Settings
from polymarket_copy_trading.models.trade import NormalizedTrade
from polymarket_copy_trading.notifications.notification_manager import NotificationService
from polymarket_copy_trading.notifications.types import NotificationMessage
from polymarket_copy_trading.utils.dedupe import trade_key
from polymarket_copy_trading.utils.validation import is_condition_id, is_hex_address, mask_address

OnNewTrade = Callable[[NormalizedTrade], None] | Callable[[NormalizedTrade], Awaitable[None]]


def _default_on_new_trade(trade: NormalizedTrade) -> None:
    """Default callback: no-op; new trades are logged by the service with tracking_new_trade."""
    pass


class TradeTracker:
    """Tracks a wallet's new Polymarket trades via polling (Data API + Gamma cache)."""

    def __init__(
        self,
        data_api: DataApiClient,
        gamma_cache: GammaCache,
        settings: Settings,
        notification_service: Optional[NotificationService] = None,
        *,
        get_logger: Callable[[str], Any] = structlog.get_logger,
        logger_name: Optional[str] = None,
    ) -> None:
        """Initialize the tracker.

        Args:
            data_api: Data API client (injected).
            gamma_cache: Gamma cache for condition_id -> market info (injected).
            settings: Application settings (uses settings.tracking).
            notification_service: Optional notification service (injected).
            get_logger: Logger factory (injected) with default of structlog.get_logger.
            logger_name: Optional logger name (defaults to class name).
        """
        self._data_api = data_api
        self._gamma_cache = gamma_cache
        self._settings = settings
        self._notification_service = notification_service
        self._logger = get_logger(logger_name or self.__class__.__name__)

    async def track(
        self,
        wallet: str,
        *,
        poll_seconds: Optional[float] = None,
        limit: Optional[int] = None,
        enable_gamma_lookup: Optional[bool] = None,
        emit_initial: bool = False,
        on_new_trade: Optional[OnNewTrade] = None,
    ) -> None:
        """Poll for new trades and invoke callback for each new one.

        First poll establishes a baseline (seen_keys). Subsequent polls
        emit only trades whose key was not seen before. Stop with Ctrl+C.

        Args:
            wallet: 0x wallet address (42 chars).
            poll_seconds: Polling interval; default from settings.tracking.poll_seconds.
            limit: Trades per poll; default from settings.tracking.trades_limit.
            enable_gamma_lookup: Resolve condition_id to market_id/title; default from settings.
            emit_initial: If True, emit all baseline trades at start (oldest first).
            on_new_trade: Callback for each new trade (sync or async). Default prints one line.
        """
        if not is_hex_address(wallet):
            raise ValueError("wallet must be a valid 0x wallet address (42 chars)")

        tr = self._settings.tracking
        poll_seconds = poll_seconds if poll_seconds is not None else tr.poll_seconds
        limit = limit if limit is not None else tr.trades_limit
        enable_gamma_lookup = (
            enable_gamma_lookup if enable_gamma_lookup is not None else tr.enable_gamma_lookup
        )
        if poll_seconds <= 0:
            poll_seconds = 1.0
        if limit <= 0:
            limit = 10

        if on_new_trade is None:
            on_new_trade = _default_on_new_trade

        seen_keys: set[str] = set()

        # Baseline fetch
        latest = await self._data_api.get_trades(wallet, limit=limit, offset=0)
        if enable_gamma_lookup and latest:
            cids: list[str] = [
                cid
                for t in latest
                if (cid := t.get("conditionId")) is not None and is_condition_id(cid)
            ]
            if cids:
                await self._gamma_cache.resolve(cids)
        for t in latest:
            seen_keys.add(trade_key(t))

        if emit_initial:
            for t in reversed(latest):
                norm = self._normalize(t)
                self._emit_notification(wallet, t, norm, is_snapshot=True)
                if asyncio.iscoroutinefunction(on_new_trade):
                    await on_new_trade(norm)  # type: ignore[misc]
                else:
                    on_new_trade(norm)  # type: ignore[misc]

        wallet_masked = mask_address(wallet)
        self._logger.info(
            "tracking_started",
            tracking_wallet_masked=wallet_masked,
            tracking_poll_seconds=poll_seconds,
            tracking_limit=limit,
            tracking_gamma_lookup=enable_gamma_lookup,
        )
        self._logger.info(
            "tracking_waiting_for_trades",
            tracking_wallet_masked=wallet_masked,
        )

        try:
            while True:
                await asyncio.sleep(poll_seconds)
                newest = await self._data_api.get_trades(wallet, limit=limit, offset=0)
                if enable_gamma_lookup and newest:
                    cids_loop: list[str] = [
                        cid
                        for t in newest
                        if (cid := t.get("conditionId")) is not None and is_condition_id(cid)
                    ]
                    if cids_loop:
                        await self._gamma_cache.resolve(cids_loop)
                new_items = [t for t in newest if trade_key(t) not in seen_keys]
                if new_items:
                    for t in reversed(new_items):
                        k = trade_key(t)
                        seen_keys.add(k)
                        norm = self._normalize(t)
                        self._logger.info(
                            "tracking_new_trade",
                            tracking_wallet_masked=wallet_masked,
                            **self.__trade_log_context(norm),
                        )
                        self._emit_notification(wallet, t, norm, is_snapshot=False)
                        if asyncio.iscoroutinefunction(on_new_trade):
                            await on_new_trade(norm)  # type: ignore[misc]
                        else:
                            on_new_trade(norm)  # type: ignore[misc]
                    if len(seen_keys) > 5000:
                        seen_keys.clear()
                        seen_keys.update(trade_key(t) for t in newest)
        except asyncio.CancelledError:
            self._logger.info(
                "tracking_stopped",
                tracking_wallet_masked=wallet_masked,
                tracking_stop_reason="cancelled",
            )
            raise
        except KeyboardInterrupt:
            self._logger.info(
                "tracking_stopped",
                tracking_wallet_masked=wallet_masked,
                tracking_stop_reason="keyboard_interrupt",
            )

    def _normalize(self, t: dict[str, Any]) -> NormalizedTrade:
        """Build NormalizedTrade from raw trade dict and gamma cache."""
        cid = t.get("conditionId")
        g = self._gamma_cache.get(cid) if cid and is_condition_id(cid) else {}
        return NormalizedTrade(
            timestamp=t.get("timestamp"),
            market_id=g.get("market_id"),
            condition_id=cid,
            gamma_slug=g.get("slug", ""),
            gamma_title=g.get("title", ""),
            event_id=t.get("eventId"),
            outcome=t.get("outcome"),
            side=t.get("side") or t.get("type"),
            price=t.get("price"),
            size=t.get("size"),
            transaction_hash=t.get("transactionHash"),
        )

    @staticmethod
    def __trade_log_context(trade: NormalizedTrade) -> dict[str, Any]:
        """Build structured context for tracking_new_trade (snake_case, no PII)."""
        return {
            "trade_timestamp": trade.timestamp,
            "trade_market_id": trade.market_id,
            "trade_condition_id": trade.condition_id,
            "trade_outcome": trade.outcome,
            "trade_side": trade.side,
            "trade_price": trade.price,
            "trade_size": trade.size,
            "trade_gamma_title": (trade.gamma_title or trade.gamma_slug or "").strip() or None,
            "trade_transaction_hash": trade.transaction_hash,
        }

    def _emit_notification(
        self,
        wallet: str,
        raw_trade: dict[str, Any],
        trade: NormalizedTrade,
        *,
        is_snapshot: bool = False,
    ) -> None:
        """Send notification through NotificationService if available."""
        if not self._notification_service:
            return

        title = (
            (trade.gamma_title or trade.gamma_slug or "").strip()
            or raw_trade.get("title")
            or ""
        )
        slug = trade.gamma_slug or raw_trade.get("slug") or ""
        trade_payload: dict[str, Any] = {
            "wallet": wallet,
            "proxy_wallet": raw_trade.get("proxyWallet"),
            "timestamp": trade.timestamp,
            "market_id": trade.market_id,
            "condition_id": trade.condition_id,
            "asset": raw_trade.get("asset"),
            "outcome": trade.outcome,
            "outcome_index": raw_trade.get("outcomeIndex"),
            "side": trade.side,
            "price": trade.price,
            "size": trade.size,
            "title": title,
            "slug": slug,
            "icon": raw_trade.get("icon"),
            "event_slug": raw_trade.get("eventSlug"),
            "transaction_hash": trade.transaction_hash,
            "trader_name": raw_trade.get("name"),
            "trader_pseudonym": raw_trade.get("pseudonym"),
            "trader_profile_image": raw_trade.get("profileImageOptimized") or raw_trade.get("profileImage"),
        }
        message = NotificationMessage(
            event_type="trade_new",
            message=f"New trade for {mask_address(wallet)}",
            payload={
                "wallet": wallet,
                "trade": trade_payload,
                "isSnapshot": is_snapshot,
            },
        )
        self._notification_service.notify(message)
