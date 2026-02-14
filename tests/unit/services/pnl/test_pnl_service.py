# -*- coding: utf-8 -*-
"""Unit tests for PnLService."""

from __future__ import annotations

from collections.abc import Callable
from decimal import Decimal

from polymarket_copy_trading.models.bot_position import BotPosition
from polymarket_copy_trading.services.pnl.pnl_service import PnLService


def test_compute_for_open_position_returns_none_for_realized_and_net(
    bot_position_factory: Callable[..., BotPosition],
) -> None:
    service = PnLService()
    position = bot_position_factory(
        entry_cost_usdc=Decimal("10"),
        fees=Decimal("0.25"),
    )

    result = service.compute(position)

    assert result.realized_pnl_usdc is None
    assert result.net_pnl_usdc is None
    assert result.entry_cost_usdc == Decimal("10")
    assert result.close_proceeds_usdc is None
    assert result.total_fees_usdc == Decimal("0.25")


def test_compute_for_closed_position_with_full_data_returns_expected_values(
    bot_position_factory: Callable[..., BotPosition],
) -> None:
    service = PnLService()
    # entry=10, close=13, fees=1 -> realized=3, net=2
    position = bot_position_factory(
        entry_cost_usdc=Decimal("10"),
        fees=Decimal("0.4"),
    ).with_closed(
        close_proceeds_usdc=Decimal("13"),
        close_fees=Decimal("0.6"),
    )

    result = service.compute(position)

    assert result.realized_pnl_usdc == Decimal("3")
    assert result.net_pnl_usdc == Decimal("2")
    assert result.entry_cost_usdc == Decimal("10")
    assert result.close_proceeds_usdc == Decimal("13")
    assert result.total_fees_usdc == Decimal("1.0")


def test_compute_for_closed_position_missing_entry_cost_returns_none_pnl(
    bot_position_factory: Callable[..., BotPosition],
) -> None:
    service = PnLService()
    position = bot_position_factory(
        entry_cost_usdc=None,
        fees=Decimal("0.2"),
    ).with_closed(
        close_proceeds_usdc=Decimal("7"),
        close_fees=Decimal("0.3"),
    )

    result = service.compute(position)

    assert result.realized_pnl_usdc is None
    assert result.net_pnl_usdc is None
    assert result.entry_cost_usdc is None
    assert result.close_proceeds_usdc == Decimal("7")
    assert result.total_fees_usdc == Decimal("0.5")


def test_compute_for_closed_position_missing_close_proceeds_returns_none_pnl(
    bot_position_factory: Callable[..., BotPosition],
) -> None:
    service = PnLService()
    position = bot_position_factory(
        entry_cost_usdc=Decimal("8"),
        fees=Decimal("0.1"),
    ).with_closed(
        close_proceeds_usdc=None,
        close_fees=Decimal("0.2"),
    )

    result = service.compute(position)

    assert result.realized_pnl_usdc is None
    assert result.net_pnl_usdc is None
    assert result.entry_cost_usdc == Decimal("8")
    assert result.close_proceeds_usdc is None
    assert result.total_fees_usdc == Decimal("0.3")


def test_compute_handles_negative_realized_and_negative_net_pnl(
    bot_position_factory: Callable[..., BotPosition],
) -> None:
    service = PnLService()
    # entry=10, close=8, fees=1.5 -> realized=-2, net=-3.5
    position = bot_position_factory(
        entry_cost_usdc=Decimal("10"),
        fees=Decimal("1.0"),
    ).with_closed(
        close_proceeds_usdc=Decimal("8"),
        close_fees=Decimal("0.5"),
    )

    result = service.compute(position)

    assert result.realized_pnl_usdc == Decimal("-2")
    assert result.net_pnl_usdc == Decimal("-3.5")
    assert result.total_fees_usdc == Decimal("1.5")
