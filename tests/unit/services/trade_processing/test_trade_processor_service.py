# -*- coding: utf-8 -*-
"""Unit tests for TradeProcessorService orchestration."""

from __future__ import annotations

from collections.abc import Callable
from datetime import datetime, timezone
from decimal import Decimal
from types import SimpleNamespace
from typing import Any, cast
from unittest.mock import AsyncMock
from uuid import uuid4

from polymarket_copy_trading.queue.messages import QueueMessage
from polymarket_copy_trading.models.tracking_ledger import TrackingLedger
from polymarket_copy_trading.services.trade_processing.trade_processor import (
    TradeProcessorService,
)
from polymarket_copy_trading.services.tracking_trader.trade_dto import DataApiTradeDTO


def _trade() -> DataApiTradeDTO:
    """Build minimal trade DTO used by processor tests."""
    return DataApiTradeDTO(
        timestamp=123456,
        side="BUY",
        asset="asset-1",
        price=0.5,
        size=10.0,
        condition_id="cond-1",
        outcome="YES",
        transaction_hash="0xtx1",
    )


def _message(
    *,
    wallet: str | None = "0x2d27b6e21b3d4d7c9a43fdf58f12345678907706",
    is_snapshot: bool = False,
) -> QueueMessage[DataApiTradeDTO]:
    """Build queue message with metadata variations."""
    metadata: dict[str, object] = {}
    if wallet is not None:
        metadata["wallet"] = wallet
    metadata["is_snapshot"] = is_snapshot
    return QueueMessage[DataApiTradeDTO](
        id=uuid4(),
        payload=_trade(),
        created_at=datetime.now(timezone.utc),
        metadata=metadata,
    )


async def test_process_calls_post_tracking_when_wallet_and_not_snapshot(
    tracking_ledger_factory: Callable[..., TrackingLedger],
) -> None:
    ledger = tracking_ledger_factory(post_tracking_shares=Decimal("10"))
    post_engine = SimpleNamespace(apply_trade=AsyncMock(return_value=ledger))
    copy_engine = SimpleNamespace(evaluate_and_execute=AsyncMock())
    service = TradeProcessorService(
        post_tracking_engine=cast(Any, post_engine),
        copy_trading_engine=cast(Any, copy_engine),
    )
    message = _message(wallet="0xwallet", is_snapshot=False)

    await service.process(message)

    post_engine.apply_trade.assert_awaited_once_with("0xwallet", message.payload)


async def test_process_skips_post_tracking_when_snapshot_message() -> None:
    post_engine = SimpleNamespace(apply_trade=AsyncMock())
    copy_engine = SimpleNamespace(evaluate_and_execute=AsyncMock())
    service = TradeProcessorService(
        post_tracking_engine=cast(Any, post_engine),
        copy_trading_engine=cast(Any, copy_engine),
    )
    message = _message(wallet="0xwallet", is_snapshot=True)

    await service.process(message)

    post_engine.apply_trade.assert_not_called()
    copy_engine.evaluate_and_execute.assert_not_called()


async def test_process_skips_post_tracking_when_wallet_missing() -> None:
    post_engine = SimpleNamespace(apply_trade=AsyncMock())
    copy_engine = SimpleNamespace(evaluate_and_execute=AsyncMock())
    service = TradeProcessorService(
        post_tracking_engine=cast(Any, post_engine),
        copy_trading_engine=cast(Any, copy_engine),
    )
    message = _message(wallet=None, is_snapshot=False)

    await service.process(message)

    post_engine.apply_trade.assert_not_called()
    copy_engine.evaluate_and_execute.assert_not_called()


async def test_process_calls_copy_engine_with_ledger_after_post_tracking(
    tracking_ledger_factory: Callable[..., TrackingLedger],
) -> None:
    ledger = tracking_ledger_factory(post_tracking_shares=Decimal("25"))
    post_engine = SimpleNamespace(apply_trade=AsyncMock(return_value=ledger))
    copy_engine = SimpleNamespace(evaluate_and_execute=AsyncMock())
    service = TradeProcessorService(
        post_tracking_engine=cast(Any, post_engine),
        copy_trading_engine=cast(Any, copy_engine),
    )
    message = _message(wallet="0xwallet", is_snapshot=False)

    await service.process(message)

    copy_engine.evaluate_and_execute.assert_awaited_once_with(
        "0xwallet",
        message.payload,
        ledger,
    )


async def test_process_does_not_call_copy_engine_when_ledger_after_is_none() -> None:
    post_engine = SimpleNamespace(apply_trade=AsyncMock(return_value=None))
    copy_engine = SimpleNamespace(evaluate_and_execute=AsyncMock())
    service = TradeProcessorService(
        post_tracking_engine=cast(Any, post_engine),
        copy_trading_engine=cast(Any, copy_engine),
    )
    message = _message(wallet="0xwallet", is_snapshot=False)

    await service.process(message)

    copy_engine.evaluate_and_execute.assert_not_called()


async def test_process_does_not_call_copy_engine_when_copy_engine_is_none(
    tracking_ledger_factory: Callable[..., TrackingLedger],
) -> None:
    ledger = tracking_ledger_factory(post_tracking_shares=Decimal("5"))
    post_engine = SimpleNamespace(apply_trade=AsyncMock(return_value=ledger))
    service = TradeProcessorService(
        post_tracking_engine=cast(Any, post_engine),
        copy_trading_engine=None,
    )
    message = _message(wallet="0xwallet", is_snapshot=False)

    await service.process(message)

    post_engine.apply_trade.assert_awaited_once()


async def test_process_with_no_engines_completes_without_errors() -> None:
    service = TradeProcessorService(
        post_tracking_engine=None,
        copy_trading_engine=None,
    )
    message = _message(wallet="0xwallet", is_snapshot=False)

    await service.process(message)


async def test_process_handles_missing_metadata_as_empty_dict() -> None:
    post_engine = SimpleNamespace(apply_trade=AsyncMock())
    copy_engine = SimpleNamespace(evaluate_and_execute=AsyncMock())
    service = TradeProcessorService(
        post_tracking_engine=cast(Any, post_engine),
        copy_trading_engine=cast(Any, copy_engine),
    )
    message = QueueMessage[DataApiTradeDTO](
        id=uuid4(),
        payload=_trade(),
        created_at=datetime.now(timezone.utc),
        metadata=None,
    )

    await service.process(message)

    post_engine.apply_trade.assert_not_called()
    copy_engine.evaluate_and_execute.assert_not_called()
