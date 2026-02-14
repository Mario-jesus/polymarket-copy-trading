# -*- coding: utf-8 -*-
"""Unit tests for CopyTradingEngineService orchestration."""

from __future__ import annotations

from collections.abc import Callable
from decimal import Decimal
from types import SimpleNamespace
from typing import Any
from unittest.mock import AsyncMock, Mock

from polymarket_copy_trading.config.config import StrategySettings
from polymarket_copy_trading.models.bot_position import BotPosition
from polymarket_copy_trading.models.tracking_ledger import TrackingLedger
from polymarket_copy_trading.services.copy_trading.copy_trading_engine_service import (
    CopyTradingEngineService,
)
from polymarket_copy_trading.services.order_execution.dto import (
    OrderExecutionResult,
    OrderResponse,
)
from polymarket_copy_trading.services.strategy.close_policy import ClosePolicyResult
from polymarket_copy_trading.services.strategy.open_policy import OpenPolicyResult
from polymarket_copy_trading.services.tracking_trader.trade_dto import DataApiTradeDTO


class _FakeEventBus:
    """Minimal event bus fake for asserting dispatched events."""

    def __init__(self) -> None:
        self.dispatched: list[Any] = []

    def dispatch(self, event: Any) -> None:
        self.dispatched.append(event)


def _settings(
    *,
    fixed_position_amount_usdc: float = 10.0,
    max_positions_per_ledger: int = 5,
    max_active_ledgers: int = 10,
    asset_min_position_percent: float = 0.0,
    asset_min_position_shares: float = 0.0,
    close_total_threshold_pct: float = 80.0,
) -> Any:
    """Build minimal settings object expected by the service."""
    return SimpleNamespace(
        strategy=StrategySettings(
            fixed_position_amount_usdc=fixed_position_amount_usdc,
            max_positions_per_ledger=max_positions_per_ledger,
            max_active_ledgers=max_active_ledgers,
            asset_min_position_percent=asset_min_position_percent,
            asset_min_position_shares=asset_min_position_shares,
            close_total_threshold_pct=close_total_threshold_pct,
        )
    )


def _trade(
    *,
    side: str = "BUY",
    asset: str = "asset-1",
    price: float | None = 0.5,
    size: float | None = 10.0,
) -> DataApiTradeDTO:
    """Build trade DTO for evaluate_and_execute tests."""
    return DataApiTradeDTO(
        timestamp=0,
        side=side,  # type: ignore[arg-type]
        asset=asset,
        price=price,
        size=size,
    )


def _exec_result(
    *,
    success: bool,
    order_id: str | None = "order-1",
    tx_hashes: list[str] | None = None,
    error: str | None = None,
) -> OrderExecutionResult[OrderResponse]:
    """Build order execution result used by market execution mocks."""
    response = OrderResponse(
        success=success,
        order_id=order_id,
        transactions_hashes=tx_hashes or [],
    )
    return OrderExecutionResult(
        success=success,
        response=response,
        error=error,
    )


def _engine(
    *,
    tracking_repo: Any,
    position_repo: Any,
    account_value_service: Any,
    data_api: Any,
    market_exec: Any,
    settings: Any,
    event_bus: Any,
    open_policy: Any,
    close_policy: Any,
) -> CopyTradingEngineService:
    """Create service with injected doubles."""
    return CopyTradingEngineService(
        tracking_repository=tracking_repo,
        bot_position_repository=position_repo,
        account_value_service=account_value_service,
        data_api=data_api,
        market_order_execution=market_exec,
        settings=settings,
        event_bus=event_bus,
        open_policy=open_policy,
        close_policy=close_policy,
    )


def _deps() -> dict[str, Any]:
    """Create async-capable dependency mocks used by tests."""
    tracking_repo = SimpleNamespace(update_close_stage_ref=AsyncMock())
    position_repo = SimpleNamespace(
        list_open_by_ledger=AsyncMock(return_value=[]),
        list_open_by_wallet=AsyncMock(return_value=[]),
        save=AsyncMock(),
        mark_closing_pending=AsyncMock(),
    )
    account_value_service = SimpleNamespace(
        get_total_account_value=AsyncMock(return_value=SimpleNamespace(total_usdc=Decimal("1000")))
    )
    data_api = SimpleNamespace(get_positions=AsyncMock(return_value=[]))
    market_exec = SimpleNamespace(
        place_buy_usdc=AsyncMock(),
        place_sell_shares=AsyncMock(),
    )
    open_policy = Mock()
    close_policy = Mock()
    event_bus = _FakeEventBus()
    return {
        "tracking_repo": tracking_repo,
        "position_repo": position_repo,
        "account_value_service": account_value_service,
        "data_api": data_api,
        "market_exec": market_exec,
        "open_policy": open_policy,
        "close_policy": close_policy,
        "event_bus": event_bus,
    }


async def test_evaluate_and_execute_returns_early_when_ledger_is_none() -> None:
    deps = _deps()
    service = _engine(settings=_settings(), **deps)

    await service.evaluate_and_execute("0xwallet", _trade(side="BUY"), ledger=None)

    deps["position_repo"].list_open_by_ledger.assert_not_called()
    deps["market_exec"].place_buy_usdc.assert_not_called()


async def test_evaluate_and_execute_returns_early_for_invalid_side(
    tracking_ledger_factory: Callable[..., TrackingLedger],
) -> None:
    deps = _deps()
    service = _engine(settings=_settings(), **deps)
    ledger = tracking_ledger_factory(post_tracking_shares=Decimal("10"))

    await service.evaluate_and_execute("0xwallet", _trade(side="HOLD"), ledger=ledger)

    deps["market_exec"].place_buy_usdc.assert_not_called()
    deps["market_exec"].place_sell_shares.assert_not_called()


async def test_buy_skips_when_open_policy_denies(
    tracking_ledger_factory: Callable[..., TrackingLedger],
) -> None:
    deps = _deps()
    deps["open_policy"].should_open.return_value = OpenPolicyResult(
        should_open=False,
        reason="denied",
    )
    service = _engine(settings=_settings(), **deps)
    ledger = tracking_ledger_factory(post_tracking_shares=Decimal("10"))

    await service.evaluate_and_execute("0xwallet", _trade(side="BUY"), ledger=ledger)

    deps["market_exec"].place_buy_usdc.assert_not_called()
    deps["position_repo"].save.assert_not_called()


async def test_buy_emits_failed_event_when_order_placement_fails(
    tracking_ledger_factory: Callable[..., TrackingLedger],
) -> None:
    deps = _deps()
    deps["open_policy"].should_open.return_value = OpenPolicyResult(
        should_open=True,
        reason="ok",
    )
    deps["market_exec"].place_buy_usdc.return_value = _exec_result(
        success=False,
        order_id="order-fail",
        error="boom",
    )
    service = _engine(settings=_settings(fixed_position_amount_usdc=12.0), **deps)
    ledger = tracking_ledger_factory(post_tracking_shares=Decimal("10"))

    await service.evaluate_and_execute("0xwallet", _trade(side="BUY"), ledger=ledger)

    deps["position_repo"].save.assert_not_called()
    assert len(deps["event_bus"].dispatched) == 1
    event = deps["event_bus"].dispatched[0]
    assert event.reason == "order_placement_failed"
    assert event.is_open is True


async def test_buy_success_saves_position_emits_order_and_sets_ref_when_missing(
    tracking_ledger_factory: Callable[..., TrackingLedger],
) -> None:
    deps = _deps()
    deps["open_policy"].should_open.return_value = OpenPolicyResult(
        should_open=True,
        reason="ok",
    )
    deps["market_exec"].place_buy_usdc.return_value = _exec_result(
        success=True,
        order_id="order-1",
        tx_hashes=["0xtx1"],
    )
    service = _engine(settings=_settings(fixed_position_amount_usdc=10.0), **deps)
    ledger = tracking_ledger_factory(
        post_tracking_shares=Decimal("20"),
        close_stage_ref_post_tracking_shares=None,
    )

    await service.evaluate_and_execute("0xwallet", _trade(side="BUY", price=0.5), ledger=ledger)

    deps["position_repo"].save.assert_called_once()
    saved_position = deps["position_repo"].save.call_args.args[0]
    assert isinstance(saved_position, BotPosition)
    assert saved_position.status.value == "OPEN"
    deps["tracking_repo"].update_close_stage_ref.assert_awaited_once_with(
        "0xwallet", "asset-1", Decimal("20")
    )
    assert len(deps["event_bus"].dispatched) == 1
    assert deps["event_bus"].dispatched[0].order_id == "order-1"


async def test_buy_success_does_not_update_ref_when_already_set(
    tracking_ledger_factory: Callable[..., TrackingLedger],
) -> None:
    deps = _deps()
    deps["open_policy"].should_open.return_value = OpenPolicyResult(
        should_open=True,
        reason="ok",
    )
    deps["market_exec"].place_buy_usdc.return_value = _exec_result(success=True, order_id="order-1")
    service = _engine(settings=_settings(), **deps)
    ledger = tracking_ledger_factory(
        post_tracking_shares=Decimal("20"),
        close_stage_ref_post_tracking_shares=Decimal("15"),
    )

    await service.evaluate_and_execute("0xwallet", _trade(side="BUY", price=1.0), ledger=ledger)

    deps["tracking_repo"].update_close_stage_ref.assert_not_called()


async def test_sell_returns_when_no_open_positions(
    tracking_ledger_factory: Callable[..., TrackingLedger],
) -> None:
    deps = _deps()
    deps["position_repo"].list_open_by_ledger.return_value = []
    service = _engine(settings=_settings(), **deps)
    ledger = tracking_ledger_factory(post_tracking_shares=Decimal("10"))

    await service.evaluate_and_execute("0xwallet", _trade(side="SELL"), ledger=ledger)

    deps["market_exec"].place_sell_shares.assert_not_called()


async def test_sell_skips_when_close_policy_returns_zero(
    tracking_ledger_factory: Callable[..., TrackingLedger],
    bot_position_factory: Callable[..., BotPosition],
) -> None:
    deps = _deps()
    deps["position_repo"].list_open_by_ledger.return_value = [bot_position_factory()]
    deps["close_policy"].positions_to_close.return_value = ClosePolicyResult(
        positions_to_close=0,
        reason="skip",
    )
    service = _engine(settings=_settings(), **deps)
    ledger = tracking_ledger_factory(post_tracking_shares=Decimal("10"))

    await service.evaluate_and_execute("0xwallet", _trade(side="SELL"), ledger=ledger)

    deps["market_exec"].place_sell_shares.assert_not_called()


async def test_sell_emits_failed_when_order_placement_fails(
    tracking_ledger_factory: Callable[..., TrackingLedger],
    bot_position_factory: Callable[..., BotPosition],
) -> None:
    deps = _deps()
    open_position = bot_position_factory(shares_held=Decimal("7"))
    deps["position_repo"].list_open_by_ledger.return_value = [open_position]
    deps["close_policy"].positions_to_close.return_value = ClosePolicyResult(
        positions_to_close=1,
        reason="close one",
    )
    deps["market_exec"].place_sell_shares.return_value = _exec_result(
        success=False,
        order_id="order-sell-fail",
        error="sell failed",
    )
    service = _engine(settings=_settings(), **deps)
    ledger = tracking_ledger_factory(post_tracking_shares=Decimal("10"))

    await service.evaluate_and_execute("0xwallet", _trade(side="SELL"), ledger=ledger)

    deps["position_repo"].mark_closing_pending.assert_not_called()
    deps["tracking_repo"].update_close_stage_ref.assert_not_called()
    assert len(deps["event_bus"].dispatched) == 1
    failed = deps["event_bus"].dispatched[0]
    assert failed.reason == "order_placement_failed"
    assert failed.is_open is False


async def test_sell_success_marks_pending_emits_order_and_updates_ref(
    tracking_ledger_factory: Callable[..., TrackingLedger],
    bot_position_factory: Callable[..., BotPosition],
) -> None:
    deps = _deps()
    open_position = bot_position_factory(shares_held=Decimal("4"))
    deps["position_repo"].list_open_by_ledger.return_value = [open_position]
    deps["close_policy"].positions_to_close.return_value = ClosePolicyResult(
        positions_to_close=1,
        reason="close one",
    )
    deps["market_exec"].place_sell_shares.return_value = _exec_result(
        success=True,
        order_id="order-sell-1",
        tx_hashes=["0xselltx"],
    )
    deps["position_repo"].mark_closing_pending.return_value = open_position.with_closing_pending(
        close_order_id="order-sell-1",
        close_transaction_hash="0xselltx",
    )
    service = _engine(settings=_settings(), **deps)
    ledger = tracking_ledger_factory(post_tracking_shares=Decimal("11"))

    await service.evaluate_and_execute("0xwallet", _trade(side="SELL"), ledger=ledger)

    deps["position_repo"].mark_closing_pending.assert_awaited_once()
    deps["tracking_repo"].update_close_stage_ref.assert_awaited_once_with(
        "0xwallet", "asset-1", Decimal("11")
    )
    assert len(deps["event_bus"].dispatched) == 1
    placed = deps["event_bus"].dispatched[0]
    assert placed.order_id == "order-sell-1"
    assert placed.is_open is False


async def test_sell_emits_position_not_found_when_mark_pending_returns_none(
    tracking_ledger_factory: Callable[..., TrackingLedger],
    bot_position_factory: Callable[..., BotPosition],
) -> None:
    deps = _deps()
    open_position = bot_position_factory(shares_held=Decimal("4"))
    deps["position_repo"].list_open_by_ledger.return_value = [open_position]
    deps["close_policy"].positions_to_close.return_value = ClosePolicyResult(
        positions_to_close=1,
        reason="close one",
    )
    deps["market_exec"].place_sell_shares.return_value = _exec_result(
        success=True,
        order_id="order-sell-1",
        tx_hashes=["0xselltx"],
    )
    deps["position_repo"].mark_closing_pending.return_value = None
    service = _engine(settings=_settings(), **deps)
    ledger = tracking_ledger_factory(post_tracking_shares=Decimal("11"))

    await service.evaluate_and_execute("0xwallet", _trade(side="SELL"), ledger=ledger)

    deps["tracking_repo"].update_close_stage_ref.assert_not_called()
    assert len(deps["event_bus"].dispatched) == 1
    failed = deps["event_bus"].dispatched[0]
    assert failed.reason == "position_not_found"
