# -*- coding: utf-8 -*-
"""OrderAnalysisWorker: listens to CopyTradeOrderPlacedEvent, polls get_trades, updates BotPosition."""

from __future__ import annotations

import asyncio
import structlog
import time
from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal
from typing import TYPE_CHECKING, Any, Callable, List, Literal, Optional
from uuid import UUID

from py_clob_client.clob_types import TradeParams  # type: ignore[import-untyped]

from polymarket_copy_trading.clients.clob_client.schema import TradeSchema
from polymarket_copy_trading.events.orders.copy_trade_events import (
    CopyTradeFailedEvent,
    CopyTradeOrderPlacedEvent,
)
from polymarket_copy_trading.exceptions import QueueFull, QueueShutdown
from polymarket_copy_trading.queue.base import IAsyncQueue
from polymarket_copy_trading.utils.validation import mask_address

if TYPE_CHECKING:
    from bubus import EventBus  # type: ignore[import-untyped]

    from polymarket_copy_trading.models.bot_position import BotPosition
    from polymarket_copy_trading.clients.clob_client import AsyncClobClient
    from polymarket_copy_trading.config import Settings
    from polymarket_copy_trading.persistence.repositories.interfaces.bot_position_repository import (
        IBotPositionRepository,
    )
    from polymarket_copy_trading.services.notifications import TradeConfirmedNotifier


@dataclass(slots=True)
class PendingOrder:
    """Order waiting for trade confirmation."""

    order_id: str
    position_id: UUID
    tracked_wallet: str
    asset: str
    is_open: bool
    transaction_hash: Optional[str] = None
    enqueued_at: float = field(default_factory=time.monotonic)


def _compute_fee_usdc(notional_usdc: Decimal, fee_rate_bps: int) -> Decimal:
    """Compute fee in USDC from notional and fee rate in basis points."""
    if fee_rate_bps <= 0:
        return Decimal("0")
    return (notional_usdc * Decimal(fee_rate_bps)) / Decimal("10000")


class OrderAnalysisWorker:
    """Listens to CopyTradeOrderPlacedEvent, enqueues, polls get_trades, updates BotPosition with real data."""

    def __init__(
        self,
        clob_client: "AsyncClobClient",
        bot_position_repository: "IBotPositionRepository",
        event_bus: Any,
        queue: IAsyncQueue[PendingOrder],
        settings: "Settings",
        trade_confirmed_notifier: "TradeConfirmedNotifier",
        *,
        get_logger: Callable[[str], Any] = structlog.get_logger,
        logger_name: Optional[str] = None,
    ) -> None:
        self._clob = clob_client
        self._position_repo = bot_position_repository
        self._event_bus: "EventBus" = event_bus
        self._queue = queue
        self._settings = settings
        self._trade_confirmed_notifier = trade_confirmed_notifier
        self._poll_interval = settings.order_analysis.poll_interval_sec
        self._max_attempts = settings.order_analysis.max_attempts
        self._logger = get_logger(logger_name or self.__class__.__name__)
        self._task: Optional[asyncio.Task[None]] = None

    async def start(self) -> None:
        """Subscribe to CopyTradeOrderPlacedEvent and start the worker loop."""
        self._event_bus.on(CopyTradeOrderPlacedEvent, self._on_order_placed)
        self._task = asyncio.create_task(self._worker_loop())
        self._logger.debug("order_analysis_worker_started")

    async def stop(self) -> None:
        """Unsubscribe, shutdown queue, cancel the worker task."""
        self._unsubscribe()
        self._queue.shutdown()
        if self._task is not None:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
            self._task = None
        await self._queue.join()
        self._logger.debug("order_analysis_worker_stopped")

    def _on_order_placed(self, event: CopyTradeOrderPlacedEvent) -> None:
        """Handle CopyTradeOrderPlacedEvent: enqueue for analysis."""
        if not event.success or not event.order_id:
            return
        try:
            pending = PendingOrder(
                order_id=event.order_id,
                position_id=event.position_id,
                tracked_wallet=event.tracked_wallet,
                asset=event.asset,
                is_open=event.is_open,
                transaction_hash=event.transaction_hash,
            )
            self._queue.put_nowait(pending)
        except QueueFull:
            self._logger.warning(
                "order_analysis_queue_full",
                order_id=event.order_id,
                position_id=str(event.position_id),
            )
            self._emit_failed(
                reason="queue_full",
                position_id=event.position_id,
                order_id=event.order_id,
                tracked_wallet=event.tracked_wallet,
                asset=event.asset,
                is_open=event.is_open,
                error_message="Order analysis queue is full",
                transaction_hash=event.transaction_hash,
                amount=event.amount,
                amount_kind=event.amount_kind,
            )
        except Exception as e:
            self._logger.exception(
                "order_analysis_enqueue_error",
                order_id=event.order_id,
                error=str(e),
            )

    def _emit_failed(
        self,
        reason: str,
        position_id: UUID,
        order_id: Optional[str],
        tracked_wallet: str,
        asset: str,
        is_open: bool,
        error_message: Optional[str] = None,
        transaction_hash: Optional[str] = None,
        amount: Optional[float] = None,
        amount_kind: Optional[Literal["usdc", "shares"]] = None,
        close_requested_at: Optional[datetime] = None,
        close_attempts: Optional[int] = None,
    ) -> None:
        """Emit CopyTradeFailedEvent for TradeFailedNotifier."""
        event = CopyTradeFailedEvent(
            reason=reason,
            position_id=position_id,
            order_id=order_id or "",
            tracked_wallet=tracked_wallet,
            asset=asset,
            is_open=is_open,
            error_message=error_message,
            transaction_hash=transaction_hash,
            amount=amount,
            amount_kind=amount_kind,
            close_requested_at=close_requested_at,
            close_attempts=close_attempts,
        )
        self._event_bus.dispatch(event)

    def _unsubscribe(self) -> None:
        """Remove our handler from the event bus."""
        key = CopyTradeOrderPlacedEvent.__name__
        handlers = getattr(self._event_bus, "handlers", {})
        if key in handlers:
            handlers[key] = [h for h in handlers[key] if h != self._on_order_placed]

    async def _worker_loop(self) -> None:
        """Process pending orders: poll get_trades until found, then update BotPosition."""
        pending: Optional[PendingOrder] = None
        while True:
            try:
                pending = await self._queue.get()
                await self._process_pending(pending)
                self._queue.task_done()
            except QueueShutdown:
                break
            except asyncio.CancelledError:
                break
            except Exception as e:
                order_id = pending.order_id if pending is not None else "?"
                position_id = str(pending.position_id) if pending is not None else "?"
                self._logger.exception(
                    "order_analysis_worker_error",
                    error=str(e),
                    position_id=position_id,
                    order_id=order_id,
                )
                try:
                    self._queue.task_done()
                except ValueError:
                    pass

    async def _process_pending(self, pending: PendingOrder) -> None:
        """Poll get_trades until trade found or max attempts, then update position."""
        for _ in range(1, self._max_attempts + 1):
            trade = await self._find_trade(pending)
            if trade is not None:
                updated = await self._apply_trade_to_position(pending, trade)
                if updated is not None:
                    self._trade_confirmed_notifier.notify(updated, trade, pending.is_open)
                return
            await asyncio.sleep(self._poll_interval)

        self._logger.warning(
            "order_analysis_trade_not_found",
            position_id=str(pending.position_id),
            order_id=pending.order_id,
            asset=pending.asset,
            attempts=self._max_attempts,
        )
        position = await self._position_repo.get(pending.position_id)
        self._emit_failed(
            reason="trade_not_found",
            position_id=pending.position_id,
            order_id=pending.order_id,
            tracked_wallet=pending.tracked_wallet,
            asset=pending.asset,
            is_open=pending.is_open,
            error_message=f"Trade not found after {self._max_attempts} attempts",
            transaction_hash=pending.transaction_hash,
            close_requested_at=position.close_requested_at if position is not None else None,
            close_attempts=position.close_attempts if position is not None else None,
        )

    def _trade_matches_pending(self, trade: TradeSchema, pending: PendingOrder) -> bool:
        """Check if trade matches pending order. Priority: maker_orders.order_id, taker_order_id, transaction_hash."""
        order_id = pending.order_id
        tx_hash = pending.transaction_hash

        maker_orders = trade.get("maker_orders") or []
        for mo in maker_orders:
            if mo.get("order_id") == order_id:
                return True

        if trade.get("taker_order_id") == order_id:
            return True

        if tx_hash and trade.get("transaction_hash") == tx_hash:
            return True

        return False

    async def _find_trade(self, pending: PendingOrder) -> Optional[TradeSchema]:
        """Fetch recent trades for asset and find the one matching pending order."""
        try:
            params = TradeParams(asset_id=pending.asset)
            trades: List[TradeSchema] = await self._clob.get_trades(params)
            for t in trades:
                if self._trade_matches_pending(t, pending):
                    return t
        except Exception as e:
            self._logger.exception(
                "order_analysis_get_trades_error",
                position_id=str(pending.position_id),
                order_id=pending.order_id,
                asset=pending.asset,
                transaction_hash=pending.transaction_hash,
                error=str(e),
            )
        return None

    async def _apply_trade_to_position(self, pending: PendingOrder, trade: TradeSchema) -> Optional["BotPosition"]:
        """Update BotPosition with trade data (costs, fees). Returns updated position or None."""
        position = await self._position_repo.get(pending.position_id)
        if position is None:
            self._logger.warning(
                "order_analysis_position_not_found",
                position_id=str(pending.position_id),
                order_id=pending.order_id,
                asset=pending.asset,
                transaction_hash=pending.transaction_hash,
            )
            self._emit_failed(
                reason="position_not_found",
                position_id=pending.position_id,
                order_id=pending.order_id,
                tracked_wallet=pending.tracked_wallet,
                asset=pending.asset,
                is_open=pending.is_open,
                error_message="Position not found in repository",
                transaction_hash=pending.transaction_hash,
            )
            return None

        try:
            size_str = trade.get("size", "0")
            price_str = trade.get("price", "0")
            fee_bps_str = trade.get("fee_rate_bps", "0")
            size = Decimal(str(size_str))
            price = Decimal(str(price_str))
            fee_bps = int(fee_bps_str) if fee_bps_str else 0
            notional = size * price
            fee_usdc = _compute_fee_usdc(notional, fee_bps)
        except (TypeError, ValueError) as e:
            self._logger.warning(
                "order_analysis_parse_trade_error",
                position_id=str(pending.position_id),
                trade_keys=list(trade.keys()),
                error=str(e),
            )
            self._emit_failed(
                reason="parse_trade_error",
                position_id=pending.position_id,
                order_id=pending.order_id,
                tracked_wallet=pending.tracked_wallet,
                asset=pending.asset,
                is_open=pending.is_open,
                error_message=str(e),
                transaction_hash=pending.transaction_hash,
                close_requested_at=position.close_requested_at,
                close_attempts=position.close_attempts,
            )
            return None

        updated: Optional["BotPosition"]
        if pending.is_open:
            updated = await self._update_open_position(position, notional, fee_usdc)
        else:
            updated = await self._update_closed_position(
                position,
                close_proceeds_usdc=notional,
                close_fee_usdc=fee_usdc,
                close_order_id=pending.order_id,
                close_transaction_hash=trade.get("transaction_hash"),
            )
            if updated is None:
                self._emit_failed(
                    reason="position_update_failed",
                    position_id=pending.position_id,
                    order_id=pending.order_id,
                    tracked_wallet=pending.tracked_wallet,
                    asset=pending.asset,
                    is_open=False,
                    error_message="confirm_closed returned None",
                    close_requested_at=position.close_requested_at,
                    close_attempts=position.close_attempts,
                )

        self._logger.info(
            "order_analysis_position_updated",
            position_id=str(pending.position_id),
            order_id=pending.order_id,
            is_open=pending.is_open,
            notional_usdc=float(notional),
            fee_usdc=float(fee_usdc),
            wallet_masked=mask_address(pending.tracked_wallet),
        )
        return updated

    async def _update_open_position(self, position: "BotPosition", entry_cost_usdc: Decimal, open_fee_usdc: Decimal) -> "BotPosition":
        """Update an OPEN position with real entry cost and fees."""
        from dataclasses import replace

        new_fees = position.fees + open_fee_usdc
        updated = replace(
            position,
            entry_cost_usdc=entry_cost_usdc,
            fees=new_fees,
        )
        await self._position_repo.save(updated)
        return updated

    async def _update_closed_position(
        self,
        position: "BotPosition",
        close_proceeds_usdc: Decimal,
        close_fee_usdc: Decimal,
        close_order_id: Optional[str],
        close_transaction_hash: Optional[str],
    ) -> Optional["BotPosition"]:
        """Confirm a CLOSING_PENDING position as CLOSED with real close proceeds and fees."""
        updated = await self._position_repo.confirm_closed(
            position.id,
            close_proceeds_usdc=close_proceeds_usdc,
            close_fees=close_fee_usdc,
            close_order_id=close_order_id,
            close_transaction_hash=close_transaction_hash,
        )
        if updated is None:
            self._logger.warning(
                "order_analysis_confirm_closed_failed",
                position_id=str(position.id),
                status=position.status.value,
            )
        return updated
