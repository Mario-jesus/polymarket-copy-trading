# -*- coding: utf-8 -*-
"""Unit tests for PostTrackingEngine."""

from __future__ import annotations

from collections.abc import Callable
from decimal import Decimal
from typing import Any
from unittest.mock import AsyncMock

import pytest

from polymarket_copy_trading.models.tracking_ledger import TrackingLedger
from polymarket_copy_trading.services.trade_processing.post_tracking_engine import (
    PostTrackingEngine,
)
from polymarket_copy_trading.services.tracking_trader.trade_dto import DataApiTradeDTO


def _trade(
    *,
    side: str | None,
    asset: str | None,
    size: float | None,
) -> DataApiTradeDTO:
    """Build a DataApiTradeDTO with only fields relevant for post-tracking."""
    return DataApiTradeDTO(
        timestamp=0,
        side=side,  # type: ignore[arg-type]
        asset=asset,
        size=size,
    )


def _engine(repo: Any) -> PostTrackingEngine:
    """Build PostTrackingEngine with injected repository double."""
    return PostTrackingEngine(tracking_repository=repo)


async def test_apply_trade_returns_none_when_asset_is_missing() -> None:
    repo = AsyncMock()
    engine = _engine(repo)

    result = await engine.apply_trade(
        wallet="0xwallet",
        trade=_trade(side="BUY", asset=None, size=10.0),
    )

    assert result is None
    repo.get_or_create.assert_not_called()


@pytest.mark.parametrize("side", [None, "HOLD"])
async def test_apply_trade_returns_none_when_side_is_invalid(side: str | None) -> None:
    repo = AsyncMock()
    engine = _engine(repo)

    result = await engine.apply_trade(
        wallet="0xwallet",
        trade=_trade(side=side, asset="asset-1", size=10.0),
    )

    assert result is None
    repo.get_or_create.assert_not_called()


@pytest.mark.parametrize("size", [None, 0.0, -1.0])
async def test_apply_trade_returns_none_when_size_is_non_positive(size: float | None) -> None:
    repo = AsyncMock()
    engine = _engine(repo)

    result = await engine.apply_trade(
        wallet="0xwallet",
        trade=_trade(side="BUY", asset="asset-1", size=size),
    )

    assert result is None
    repo.get_or_create.assert_not_called()


async def test_buy_creates_or_gets_ledger_and_adds_post_tracking_delta(
    tracking_ledger_factory: Callable[..., TrackingLedger],
) -> None:
    updated = tracking_ledger_factory(post_tracking_shares=Decimal("15"))
    repo = AsyncMock()
    repo.add_post_tracking_delta.return_value = updated
    engine = _engine(repo)

    result = await engine.apply_trade(
        wallet="0xwallet",
        trade=_trade(side="BUY", asset="asset-1", size=15.0),
    )

    repo.get_or_create.assert_awaited_once_with("0xwallet", "asset-1")
    repo.add_post_tracking_delta.assert_awaited_once_with(
        "0xwallet",
        "asset-1",
        Decimal("15.0"),
    )
    assert result == updated


async def test_sell_with_sufficient_post_tracking_reduces_post_tracking_only(
    tracking_ledger_factory: Callable[..., TrackingLedger],
) -> None:
    ledger = tracking_ledger_factory(
        snapshot_t0_shares=Decimal("100"),
        post_tracking_shares=Decimal("30"),
    )
    repo = AsyncMock()
    repo.get_or_create.return_value = ledger
    engine = _engine(repo)

    result = await engine.apply_trade(
        wallet="0xwallet",
        trade=_trade(side="SELL", asset="asset-1", size=10.0),
    )

    assert result is not None
    assert result.post_tracking_shares == Decimal("20")
    assert result.snapshot_t0_shares == Decimal("100")
    repo.save.assert_awaited_once()


async def test_sell_with_exact_post_tracking_sets_post_tracking_to_zero(
    tracking_ledger_factory: Callable[..., TrackingLedger],
) -> None:
    ledger = tracking_ledger_factory(
        snapshot_t0_shares=Decimal("50"),
        post_tracking_shares=Decimal("10"),
    )
    repo = AsyncMock()
    repo.get_or_create.return_value = ledger
    engine = _engine(repo)

    result = await engine.apply_trade(
        wallet="0xwallet",
        trade=_trade(side="SELL", asset="asset-1", size=10.0),
    )

    assert result is not None
    assert result.post_tracking_shares == Decimal("0")
    assert result.snapshot_t0_shares == Decimal("50")


async def test_sell_with_excess_reduces_snapshot_by_excess_and_zeros_post_tracking(
    tracking_ledger_factory: Callable[..., TrackingLedger],
) -> None:
    # post_tracking=10, sell=16 => excess=6, snapshot=20-6=14
    ledger = tracking_ledger_factory(
        snapshot_t0_shares=Decimal("20"),
        post_tracking_shares=Decimal("10"),
    )
    repo = AsyncMock()
    repo.get_or_create.return_value = ledger
    engine = _engine(repo)

    result = await engine.apply_trade(
        wallet="0xwallet",
        trade=_trade(side="SELL", asset="asset-1", size=16.0),
    )

    assert result is not None
    assert result.post_tracking_shares == Decimal("0")
    assert result.snapshot_t0_shares == Decimal("14")


async def test_sell_with_excess_clamps_snapshot_to_zero(
    tracking_ledger_factory: Callable[..., TrackingLedger],
) -> None:
    # post_tracking=5, sell=20 => excess=15, snapshot=max(0, 10-15)=0
    ledger = tracking_ledger_factory(
        snapshot_t0_shares=Decimal("10"),
        post_tracking_shares=Decimal("5"),
    )
    repo = AsyncMock()
    repo.get_or_create.return_value = ledger
    engine = _engine(repo)

    result = await engine.apply_trade(
        wallet="0xwallet",
        trade=_trade(side="SELL", asset="asset-1", size=20.0),
    )

    assert result is not None
    assert result.post_tracking_shares == Decimal("0")
    assert result.snapshot_t0_shares == Decimal("0")


async def test_apply_trade_strips_asset_before_repo_lookup(
    tracking_ledger_factory: Callable[..., TrackingLedger],
) -> None:
    ledger = tracking_ledger_factory(
        snapshot_t0_shares=Decimal("10"),
        post_tracking_shares=Decimal("3"),
    )
    repo = AsyncMock()
    repo.get_or_create.return_value = ledger
    engine = _engine(repo)

    await engine.apply_trade(
        wallet="0xwallet",
        trade=_trade(side="SELL", asset="  asset-1  ", size=1.0),
    )

    repo.get_or_create.assert_awaited_once_with("0xwallet", "asset-1")
