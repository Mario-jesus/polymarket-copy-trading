# -*- coding: utf-8 -*-
"""Unit tests for InMemoryBotPositionRepository."""

from __future__ import annotations

from collections.abc import Callable
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from uuid import uuid4

from polymarket_copy_trading.models.bot_position import BotPosition, PositionStatus
from polymarket_copy_trading.models.tracking_ledger import TrackingLedger
from polymarket_copy_trading.persistence.repositories.in_memory.bot_position_repository import (
    InMemoryBotPositionRepository,
)


async def test_save_and_get_roundtrip(
    bot_position_repo: InMemoryBotPositionRepository,
    bot_position_factory: Callable[..., BotPosition],
) -> None:
    position = bot_position_factory()

    await bot_position_repo.save(position)
    loaded = await bot_position_repo.get(position.id)

    assert loaded == position


async def test_get_returns_none_for_unknown_id(
    bot_position_repo: InMemoryBotPositionRepository,
) -> None:
    loaded = await bot_position_repo.get(uuid4())
    assert loaded is None


async def test_list_by_wallet_returns_fifo_order(
    bot_position_repo: InMemoryBotPositionRepository,
    bot_position_factory: Callable[..., BotPosition],
    wallet: str,
) -> None:
    t0 = datetime(2026, 2, 13, 10, 0, tzinfo=timezone.utc)
    newer = bot_position_factory(opened_at=t0 + timedelta(minutes=5))
    older = bot_position_factory(opened_at=t0)

    await bot_position_repo.save(newer)
    await bot_position_repo.save(older)

    listed = await bot_position_repo.list_by_wallet(wallet)

    assert [p.id for p in listed] == [older.id, newer.id]


async def test_list_open_by_wallet_filters_only_open_positions(
    bot_position_repo: InMemoryBotPositionRepository,
    bot_position_factory: Callable[..., BotPosition],
    wallet: str,
) -> None:
    open_position = bot_position_factory()
    closed_position = bot_position_factory().with_closed(
        close_proceeds_usdc=Decimal("12"),
        close_fees=Decimal("0.1"),
    )

    await bot_position_repo.save(open_position)
    await bot_position_repo.save(closed_position)

    listed = await bot_position_repo.list_open_by_wallet(wallet)

    assert len(listed) == 1
    assert listed[0].id == open_position.id
    assert listed[0].status == PositionStatus.OPEN


async def test_list_open_by_ledger_filters_ledger_and_only_open(
    bot_position_repo: InMemoryBotPositionRepository,
    bot_position_factory: Callable[..., BotPosition],
    tracking_ledger_factory: Callable[..., TrackingLedger],
) -> None:
    ledger_a = tracking_ledger_factory()
    ledger_b = tracking_ledger_factory(asset="another-asset")

    open_a = bot_position_factory(ledger=ledger_a)
    closed_a = bot_position_factory(ledger=ledger_a).with_closed(
        close_proceeds_usdc=Decimal("3"),
        close_fees=Decimal("0.1"),
    )
    open_b = bot_position_factory(ledger=ledger_b)

    await bot_position_repo.save(open_a)
    await bot_position_repo.save(closed_a)
    await bot_position_repo.save(open_b)

    listed = await bot_position_repo.list_open_by_ledger(ledger_a.id)

    assert len(listed) == 1
    assert listed[0].id == open_a.id


async def test_mark_closing_pending_returns_none_for_unknown_position(
    bot_position_repo: InMemoryBotPositionRepository,
) -> None:
    updated = await bot_position_repo.mark_closing_pending(uuid4())
    assert updated is None


async def test_mark_closing_pending_transitions_open_and_sets_tracking_fields(
    bot_position_repo: InMemoryBotPositionRepository,
    bot_position_factory: Callable[..., BotPosition],
    now_utc: datetime,
) -> None:
    position = bot_position_factory()
    await bot_position_repo.save(position)

    updated = await bot_position_repo.mark_closing_pending(
        position.id,
        close_order_id="order-1",
        close_transaction_hash="0xtx1",
        close_requested_at=now_utc,
    )

    assert updated is not None
    assert updated.status == PositionStatus.CLOSING_PENDING
    assert updated.close_order_id == "order-1"
    assert updated.close_transaction_hash == "0xtx1"
    assert updated.close_requested_at == now_utc
    assert updated.close_attempts == 1


async def test_mark_closing_pending_increments_attempts_when_already_pending(
    bot_position_repo: InMemoryBotPositionRepository,
    bot_position_factory: Callable[..., BotPosition],
    now_utc: datetime,
) -> None:
    position = bot_position_factory().with_closing_pending(
        close_order_id="order-1",
        close_transaction_hash="0xtx1",
        close_requested_at=now_utc,
    )
    await bot_position_repo.save(position)

    updated = await bot_position_repo.mark_closing_pending(
        position.id,
        close_order_id="order-2",
        close_transaction_hash="0xtx2",
        close_requested_at=now_utc + timedelta(minutes=1),
    )

    assert updated is not None
    assert updated.status == PositionStatus.CLOSING_PENDING
    assert updated.close_order_id == "order-2"
    assert updated.close_transaction_hash == "0xtx2"
    assert updated.close_attempts == 2


async def test_mark_closing_pending_returns_closed_position_unchanged(
    bot_position_repo: InMemoryBotPositionRepository,
    bot_position_factory: Callable[..., BotPosition],
) -> None:
    closed = bot_position_factory().with_closed(
        close_proceeds_usdc=Decimal("7"),
        close_fees=Decimal("0.1"),
    )
    await bot_position_repo.save(closed)

    updated = await bot_position_repo.mark_closing_pending(closed.id)

    assert updated == closed
    assert updated is not None
    assert updated.status == PositionStatus.CLOSED


async def test_confirm_closed_returns_none_for_unknown_position(
    bot_position_repo: InMemoryBotPositionRepository,
) -> None:
    updated = await bot_position_repo.confirm_closed(uuid4())
    assert updated is None


async def test_confirm_closed_returns_none_for_open_position(
    bot_position_repo: InMemoryBotPositionRepository,
    bot_position_factory: Callable[..., BotPosition],
) -> None:
    position = bot_position_factory()
    await bot_position_repo.save(position)

    updated = await bot_position_repo.confirm_closed(position.id)

    assert updated is None


async def test_confirm_closed_transitions_pending_to_closed_with_metadata(
    bot_position_repo: InMemoryBotPositionRepository,
    bot_position_factory: Callable[..., BotPosition],
    now_utc: datetime,
) -> None:
    pending = bot_position_factory().with_closing_pending(
        close_order_id="order-1",
        close_transaction_hash="0xtx1",
        close_requested_at=now_utc,
    )
    await bot_position_repo.save(pending)

    updated = await bot_position_repo.confirm_closed(
        pending.id,
        closed_at=now_utc + timedelta(minutes=2),
        close_proceeds_usdc=Decimal("9"),
        close_fees=Decimal("0.2"),
        close_order_id="order-2",
        close_transaction_hash="0xtx2",
    )

    assert updated is not None
    assert updated.status == PositionStatus.CLOSED
    assert updated.close_proceeds_usdc == Decimal("9")
    assert updated.fees == pending.fees + Decimal("0.2")
    assert updated.close_order_id == "order-2"
    assert updated.close_transaction_hash == "0xtx2"


async def test_confirm_closed_returns_already_closed_position_unchanged(
    bot_position_repo: InMemoryBotPositionRepository,
    bot_position_factory: Callable[..., BotPosition],
) -> None:
    closed = bot_position_factory().with_closed(
        close_proceeds_usdc=Decimal("6"),
        close_fees=Decimal("0.1"),
    )
    await bot_position_repo.save(closed)

    updated = await bot_position_repo.confirm_closed(closed.id)

    assert updated == closed
    assert updated is not None
    assert updated.status == PositionStatus.CLOSED


async def test_update_closed_pnl_returns_none_for_unknown_position(
    bot_position_repo: InMemoryBotPositionRepository,
) -> None:
    updated = await bot_position_repo.update_closed_pnl(
        uuid4(),
        close_proceeds_usdc=Decimal("10"),
        close_fees=Decimal("0.1"),
    )
    assert updated is None


async def test_update_closed_pnl_returns_none_for_open_position(
    bot_position_repo: InMemoryBotPositionRepository,
    bot_position_factory: Callable[..., BotPosition],
) -> None:
    position = bot_position_factory()
    await bot_position_repo.save(position)

    updated = await bot_position_repo.update_closed_pnl(
        position.id,
        close_proceeds_usdc=Decimal("10"),
        close_fees=Decimal("0.1"),
    )

    assert updated is None


async def test_update_closed_pnl_updates_closed_position_amounts_and_fees(
    bot_position_repo: InMemoryBotPositionRepository,
    bot_position_factory: Callable[..., BotPosition],
) -> None:
    position = bot_position_factory(fees=Decimal("0.2")).with_closed(
        close_proceeds_usdc=Decimal("8"),
        close_fees=Decimal("0.3"),
    )
    await bot_position_repo.save(position)

    updated = await bot_position_repo.update_closed_pnl(
        position.id,
        close_proceeds_usdc=Decimal("9.5"),
        close_fees=Decimal("0.4"),
    )

    assert updated is not None
    assert updated.status == PositionStatus.CLOSED
    assert updated.close_proceeds_usdc == Decimal("9.5")
    # 0.2 (open) + 0.3 (close in with_closed) + 0.4 (update)
    assert updated.fees == Decimal("0.9")
