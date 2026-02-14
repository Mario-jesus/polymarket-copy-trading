# -*- coding: utf-8 -*-
"""Unit tests for OrderAnalysisWorker."""

from __future__ import annotations

from collections.abc import Callable
from datetime import datetime
from decimal import Decimal
from types import SimpleNamespace
from typing import Any, cast
from unittest.mock import AsyncMock, Mock
from uuid import uuid4

import pytest

from polymarket_copy_trading.clients.clob_client.schema import TradeSchema
from polymarket_copy_trading.events.orders.copy_trade_events import CopyTradeOrderPlacedEvent
from polymarket_copy_trading.exceptions import QueueFull
from polymarket_copy_trading.models.bot_position import PositionStatus
from polymarket_copy_trading.queue.in_memory_queue import InMemoryQueue
from polymarket_copy_trading.services.order_analysis.order_analysis_worker import (
    PendingOrder,
    OrderAnalysisWorker,
)


class _FakeEventBus:
    """Minimal event bus fake for unit tests."""

    def __init__(self) -> None:
        self.handlers: dict[str, list[Any]] = {}
        self.dispatched: list[Any] = []

    def on(self, event_type: type[Any], handler: Any) -> None:
        key = event_type.__name__
        self.handlers.setdefault(key, []).append(handler)

    def dispatch(self, event: Any) -> None:
        self.dispatched.append(event)


class _TestableOrderAnalysisWorker(OrderAnalysisWorker):
    """Test wrapper exposing selected protected methods as public helpers."""

    def trade_matches_pending(self, trade: TradeSchema, pending: PendingOrder) -> bool:
        return self._trade_matches_pending(trade, pending)

    def on_order_placed_public(self, event: CopyTradeOrderPlacedEvent) -> None:
        self._on_order_placed(event)

    async def apply_trade_to_position_public(
        self,
        pending: PendingOrder,
        trade: TradeSchema,
    ) -> Any:
        return await self._apply_trade_to_position(pending, trade)

    async def process_pending_public(self, pending: PendingOrder) -> None:
        await self._process_pending(pending)


def _settings(poll_interval: float = 0.001, max_attempts: int = 3) -> Any:
    """Build minimal settings object expected by OrderAnalysisWorker."""
    return SimpleNamespace(
        order_analysis=SimpleNamespace(
            poll_interval_sec=poll_interval,
            max_attempts=max_attempts,
        )
    )


def _worker(
    *,
    clob: Any,
    repo: Any,
    event_bus: _FakeEventBus,
    queue: Any | None = None,
    notifier: Any | None = None,
    settings: Any | None = None,
) -> _TestableOrderAnalysisWorker:
    """Build worker with injectable doubles."""
    resolved_queue = queue if queue is not None else InMemoryQueue[PendingOrder](maxsize=100)
    resolved_notifier = notifier if notifier is not None else Mock(notify=Mock())
    resolved_settings = settings if settings is not None else _settings()
    return _TestableOrderAnalysisWorker(
        clob_client=clob,
        bot_position_repository=repo,
        event_bus=event_bus,
        queue=resolved_queue,
        settings=resolved_settings,
        trade_confirmed_notifier=resolved_notifier,
    )


def _trade(
    *,
    order_id: str = "order-1",
    transaction_hash: str = "0xtx-1",
    size: str = "10",
    price: str = "0.5",
    fee_rate_bps: str = "100",
) -> TradeSchema:
    """Build minimal TradeSchema-like dict used by worker."""
    return cast(
        TradeSchema,
        {
            "id": "trade-1",
            "taker_order_id": order_id,
            "market": "market-1",
            "asset_id": "asset-1",
            "side": "SELL",
            "size": size,
            "fee_rate_bps": fee_rate_bps,
            "price": price,
            "status": "matched",
            "match_time": "t",
            "last_update": "t",
            "outcome": "YES",
            "bucket_index": 0,
            "owner": "owner",
            "maker_address": "maker",
            "maker_orders": [{"order_id": order_id}],
            "transaction_hash": transaction_hash,
            "trader_side": "TAKER",
        },
    )


def test_trade_matches_pending_by_maker_order(
    bot_position_repo: Any,
) -> None:
    worker = _worker(
        clob=Mock(),
        repo=bot_position_repo,
        event_bus=_FakeEventBus(),
    )
    pending = PendingOrder(
        order_id="order-1",
        position_id=uuid4(),
        tracked_wallet="0xwallet",
        asset="asset-1",
        is_open=False,
    )
    trade = _trade(order_id="order-1")
    assert worker.trade_matches_pending(trade, pending) is True


def test_trade_matches_pending_by_taker_order_id(
    bot_position_repo: Any,
) -> None:
    worker = _worker(
        clob=Mock(),
        repo=bot_position_repo,
        event_bus=_FakeEventBus(),
    )
    pending = PendingOrder(
        order_id="order-x",
        position_id=uuid4(),
        tracked_wallet="0xwallet",
        asset="asset-1",
        is_open=False,
    )
    trade = _trade(order_id="another")
    trade["maker_orders"] = []
    trade["taker_order_id"] = "order-x"
    assert worker.trade_matches_pending(trade, pending) is True


def test_trade_matches_pending_by_transaction_hash(
    bot_position_repo: Any,
) -> None:
    worker = _worker(
        clob=Mock(),
        repo=bot_position_repo,
        event_bus=_FakeEventBus(),
    )
    pending = PendingOrder(
        order_id="order-x",
        position_id=uuid4(),
        tracked_wallet="0xwallet",
        asset="asset-1",
        is_open=False,
        transaction_hash="0xtx-match",
    )
    trade = _trade(order_id="another", transaction_hash="0xtx-match")
    trade["maker_orders"] = []
    trade["taker_order_id"] = "order-y"
    assert worker.trade_matches_pending(trade, pending) is True


async def test_on_order_placed_enqueues_pending_order(
    bot_position_repo: Any,
) -> None:
    queue = InMemoryQueue[PendingOrder](maxsize=10)
    worker = _worker(
        clob=Mock(),
        repo=bot_position_repo,
        event_bus=_FakeEventBus(),
        queue=queue,
    )
    event = CopyTradeOrderPlacedEvent(
        order_id="order-1",
        position_id=uuid4(),
        tracked_wallet="0xwallet",
        asset="asset-1",
        is_open=False,
        amount=10.0,
        amount_kind="shares",
        success=True,
        transaction_hash="0xtx1",
    )

    worker.on_order_placed_public(event)
    queued = queue.get_nowait()

    assert queued.order_id == "order-1"
    assert queued.asset == "asset-1"


def test_on_order_placed_ignores_failed_event(
    bot_position_repo: Any,
) -> None:
    queue = Mock(put_nowait=Mock())
    worker = _worker(
        clob=Mock(),
        repo=bot_position_repo,
        event_bus=_FakeEventBus(),
        queue=queue,
    )
    event = CopyTradeOrderPlacedEvent(
        order_id="order-1",
        position_id=uuid4(),
        tracked_wallet="0xwallet",
        asset="asset-1",
        is_open=True,
        amount=10.0,
        amount_kind="usdc",
        success=False,
        transaction_hash="0xtx1",
    )

    worker.on_order_placed_public(event)

    queue.put_nowait.assert_not_called()


def test_on_order_placed_emits_failed_when_queue_full(
    bot_position_repo: Any,
) -> None:
    queue = Mock(put_nowait=Mock(side_effect=QueueFull()))
    bus = _FakeEventBus()
    worker = _worker(
        clob=Mock(),
        repo=bot_position_repo,
        event_bus=bus,
        queue=queue,
    )
    event = CopyTradeOrderPlacedEvent(
        order_id="order-1",
        position_id=uuid4(),
        tracked_wallet="0xwallet",
        asset="asset-1",
        is_open=False,
        amount=5.0,
        amount_kind="shares",
        success=True,
        transaction_hash="0xtx1",
    )

    worker.on_order_placed_public(event)

    assert len(bus.dispatched) == 1
    failed = bus.dispatched[0]
    assert failed.reason == "queue_full"
    assert failed.order_id == "order-1"


async def test_apply_trade_to_position_updates_open_position_and_notional(
    bot_position_repo: Any,
    bot_position_factory: Callable[..., Any],
) -> None:
    bus = _FakeEventBus()
    worker = _worker(clob=Mock(), repo=bot_position_repo, event_bus=bus)
    position = bot_position_factory(fees=Decimal("0"))
    await bot_position_repo.save(position)
    pending = PendingOrder(
        order_id="order-1",
        position_id=position.id,
        tracked_wallet=position.tracked_wallet,
        asset=position.asset,
        is_open=True,
        transaction_hash="0xtx1",
    )
    trade = _trade(size="10", price="0.5", fee_rate_bps="100")

    updated = await worker.apply_trade_to_position_public(pending, trade)

    assert updated is not None
    assert updated.entry_cost_usdc == Decimal("5.0")
    assert updated.fees == Decimal("0.05")


async def test_apply_trade_to_position_confirms_closed_when_pending(
    bot_position_repo: Any,
    bot_position_factory: Callable[..., Any],
    now_utc: datetime,
) -> None:
    bus = _FakeEventBus()
    worker = _worker(clob=Mock(), repo=bot_position_repo, event_bus=bus)
    position = bot_position_factory().with_closing_pending(
        close_order_id="order-1",
        close_transaction_hash="0xtx-old",
        close_requested_at=now_utc,
    )
    await bot_position_repo.save(position)
    pending = PendingOrder(
        order_id="order-1",
        position_id=position.id,
        tracked_wallet=position.tracked_wallet,
        asset=position.asset,
        is_open=False,
        transaction_hash="0xtx1",
    )
    trade = _trade(size="20", price="0.4", fee_rate_bps="50", transaction_hash="0xtx-final")

    updated = await worker.apply_trade_to_position_public(pending, trade)

    assert updated is not None
    assert updated.status == PositionStatus.CLOSED
    assert updated.close_proceeds_usdc == Decimal("8.0")
    assert updated.close_order_id == "order-1"
    assert updated.close_transaction_hash == "0xtx-final"


async def test_apply_trade_to_position_emits_failed_when_position_missing(
    bot_position_repo: Any,
) -> None:
    bus = _FakeEventBus()
    worker = _worker(clob=Mock(), repo=bot_position_repo, event_bus=bus)
    pending = PendingOrder(
        order_id="order-1",
        position_id=uuid4(),
        tracked_wallet="0xwallet",
        asset="asset-1",
        is_open=False,
        transaction_hash="0xtx1",
    )

    updated = await worker.apply_trade_to_position_public(pending, _trade())

    assert updated is None
    assert len(bus.dispatched) == 1
    assert bus.dispatched[0].reason == "position_not_found"


async def test_process_pending_emits_trade_not_found_after_max_attempts(
    bot_position_repo: Any,
    bot_position_factory: Callable[..., Any],
    now_utc: datetime,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    bus = _FakeEventBus()
    notifier = Mock(notify=Mock())
    worker = _worker(
        clob=Mock(),
        repo=bot_position_repo,
        event_bus=bus,
        notifier=notifier,
        settings=_settings(poll_interval=0.001, max_attempts=2),
    )
    position = bot_position_factory().with_closing_pending(
        close_order_id="order-1",
        close_requested_at=now_utc,
    )
    await bot_position_repo.save(position)
    pending = PendingOrder(
        order_id="order-1",
        position_id=position.id,
        tracked_wallet=position.tracked_wallet,
        asset=position.asset,
        is_open=False,
        transaction_hash="0xtx1",
    )

    worker._find_trade = AsyncMock(return_value=None)  # type: ignore[method-assign]
    monkeypatch.setattr(
        "polymarket_copy_trading.services.order_analysis.order_analysis_worker.asyncio.sleep",
        AsyncMock(return_value=None),
    )

    await worker.process_pending_public(pending)

    assert len(bus.dispatched) == 1
    failed = bus.dispatched[0]
    assert failed.reason == "trade_not_found"
    assert failed.close_requested_at == now_utc
    assert failed.close_attempts == 1
    notifier.notify.assert_not_called()
