# -*- coding: utf-8 -*-
"""Unit tests for BotPosition model lifecycle and PnL helpers."""

from __future__ import annotations

from collections.abc import Callable
from datetime import datetime, timezone
from decimal import Decimal
from uuid import uuid4

import pytest

from polymarket_copy_trading.models.bot_position import BotPosition, PositionStatus


def test_create_raises_when_shares_held_is_non_positive() -> None:
    with pytest.raises(ValueError, match="shares_held must be > 0"):
        BotPosition.create(
            ledger_id=uuid4(),
            tracked_wallet="0x2d27b6e21b3d4d7c9a43fdf58f12345678907706",
            asset="asset-1",
            shares_held=Decimal("0"),
        )


def test_create_initializes_open_state_and_default_close_tracking(
    bot_position_factory: Callable[..., BotPosition],
) -> None:
    position = bot_position_factory()

    assert position.status == PositionStatus.OPEN
    assert position.is_open is True
    assert position.is_closing_pending is False
    assert position.closed_at is None
    assert position.close_order_id is None
    assert position.close_transaction_hash is None
    assert position.close_requested_at is None
    assert position.close_attempts == 0


def test_with_closing_pending_sets_state_and_increments_attempts(
    bot_position_factory: Callable[..., BotPosition],
    now_utc: datetime,
) -> None:
    position = bot_position_factory()

    updated = position.with_closing_pending(
        close_order_id="order-123",
        close_transaction_hash="0xtxhash",
        close_requested_at=now_utc,
    )

    assert updated.status == PositionStatus.CLOSING_PENDING
    assert updated.is_open is False
    assert updated.is_closing_pending is True
    assert updated.closed_at is None
    assert updated.close_order_id == "order-123"
    assert updated.close_transaction_hash == "0xtxhash"
    assert updated.close_requested_at == now_utc
    assert updated.close_attempts == 1


def test_with_closing_pending_keeps_previous_metadata_when_not_overridden(
    bot_position_factory: Callable[..., BotPosition],
    now_utc: datetime,
) -> None:
    position = bot_position_factory().with_closing_pending(
        close_order_id="order-1",
        close_transaction_hash="0xtx1",
        close_requested_at=now_utc,
    )

    updated = position.with_closing_pending()

    assert updated.close_order_id == "order-1"
    assert updated.close_transaction_hash == "0xtx1"
    assert updated.close_requested_at is not None
    assert updated.close_attempts == 2


def test_with_closed_sets_closed_state_and_updates_close_values(
    bot_position_factory: Callable[..., BotPosition],
    now_utc: datetime,
) -> None:
    position = bot_position_factory(fees=Decimal("0.10"))

    updated = position.with_closed(
        closed_at=now_utc,
        close_proceeds_usdc=Decimal("15"),
        close_fees=Decimal("0.50"),
        close_order_id="order-close-1",
        close_transaction_hash="0xclosehash",
    )

    assert updated.status == PositionStatus.CLOSED
    assert updated.closed_at == now_utc
    assert updated.close_proceeds_usdc == Decimal("15")
    assert updated.fees == Decimal("0.60")
    assert updated.close_order_id == "order-close-1"
    assert updated.close_transaction_hash == "0xclosehash"


def test_with_closed_uses_existing_close_proceeds_when_not_provided(
    bot_position_factory: Callable[..., BotPosition],
    now_utc: datetime,
) -> None:
    position = bot_position_factory().with_closed(
        closed_at=now_utc,
        close_proceeds_usdc=Decimal("10"),
        close_fees=Decimal("0.25"),
    )

    updated = position.with_closed(
        closed_at=now_utc,
        close_proceeds_usdc=None,
        close_fees=Decimal("0.25"),
    )

    assert updated.close_proceeds_usdc == Decimal("10")
    assert updated.fees == Decimal("0.50")


def test_with_closed_preserves_existing_close_tracking_when_not_overridden(
    bot_position_factory: Callable[..., BotPosition],
    now_utc: datetime,
) -> None:
    position = bot_position_factory().with_closing_pending(
        close_order_id="order-a",
        close_transaction_hash="0xtx-a",
        close_requested_at=now_utc,
    )

    updated = position.with_closed(close_proceeds_usdc=Decimal("7"), close_fees=Decimal("0.1"))

    assert updated.close_order_id == "order-a"
    assert updated.close_transaction_hash == "0xtx-a"
    assert updated.close_requested_at == now_utc
    assert updated.close_attempts == 1


def test_with_close_proceeds_updated_adds_close_fees_and_sets_proceeds(
    bot_position_factory: Callable[..., BotPosition],
) -> None:
    position = bot_position_factory(fees=Decimal("0.20")).with_closed(
        close_proceeds_usdc=Decimal("5"),
        close_fees=Decimal("0.30"),
    )

    updated = position.with_close_proceeds_updated(
        close_proceeds_usdc=Decimal("6.5"),
        close_fees=Decimal("0.40"),
    )

    assert updated.close_proceeds_usdc == Decimal("6.5")
    assert updated.fees == Decimal("0.90")


def test_realized_pnl_is_none_for_open_position(
    bot_position_factory: Callable[..., BotPosition],
) -> None:
    position = bot_position_factory(entry_cost_usdc=Decimal("5"))
    assert position.realized_pnl_usdc() is None


def test_realized_pnl_is_none_when_closed_but_missing_cost_data(
    bot_position_factory: Callable[..., BotPosition],
) -> None:
    position = bot_position_factory(entry_cost_usdc=None).with_closed(
        close_proceeds_usdc=Decimal("8"),
    )
    assert position.realized_pnl_usdc() is None


def test_realized_pnl_is_computed_for_closed_position_with_cost_and_proceeds(
    bot_position_factory: Callable[..., BotPosition],
) -> None:
    position = bot_position_factory(entry_cost_usdc=Decimal("10")).with_closed(
        close_proceeds_usdc=Decimal("13.5"),
    )

    assert position.realized_pnl_usdc() == Decimal("3.5")


def test_net_pnl_is_none_for_open_position(
    bot_position_factory: Callable[..., BotPosition],
) -> None:
    position = bot_position_factory(entry_cost_usdc=Decimal("10"))
    assert position.net_pnl_usdc() is None


def test_net_pnl_is_none_when_realized_is_not_available(
    bot_position_factory: Callable[..., BotPosition],
) -> None:
    position = bot_position_factory(entry_cost_usdc=None).with_closed(
        close_proceeds_usdc=Decimal("11"),
        close_fees=Decimal("0.5"),
    )
    assert position.net_pnl_usdc() is None


def test_net_pnl_subtracts_all_fees_from_realized_pnl(
    bot_position_factory: Callable[..., BotPosition],
) -> None:
    # entry_cost=10, close_proceeds=13, fees=1 -> realized=3, net=2
    position = bot_position_factory(
        entry_cost_usdc=Decimal("10"),
        fees=Decimal("0.40"),
    ).with_closed(
        close_proceeds_usdc=Decimal("13"),
        close_fees=Decimal("0.60"),
    )

    assert position.realized_pnl_usdc() == Decimal("3")
    assert position.net_pnl_usdc() == Decimal("2")


def test_with_closed_without_closed_at_sets_current_utc_datetime(
    bot_position_factory: Callable[..., BotPosition],
) -> None:
    before = datetime.now(timezone.utc)
    updated = bot_position_factory().with_closed(
        close_proceeds_usdc=Decimal("4"),
        close_fees=Decimal("0"),
    )
    after = datetime.now(timezone.utc)

    assert updated.closed_at is not None
    assert before <= updated.closed_at <= after
