# -*- coding: utf-8 -*-
"""Shared pytest fixtures for unit and integration tests."""

from __future__ import annotations

from collections.abc import Callable
from datetime import datetime, timezone
from decimal import Decimal
from typing import Any

import pytest
from bubus import EventBus  # type: ignore[import-untyped]

from polymarket_copy_trading.models.bot_position import BotPosition
from polymarket_copy_trading.models.tracking_ledger import TrackingLedger
from polymarket_copy_trading.persistence.repositories.in_memory.bot_position_repository import (
    InMemoryBotPositionRepository,
)
from polymarket_copy_trading.persistence.repositories.in_memory.tracking_repository import (
    InMemoryTrackingRepository,
)


@pytest.fixture
def wallet() -> str:
    """Default tracked wallet used by tests."""
    return "0x2d27b6e21b3d4d7c9a43fdf58f12345678907706"


@pytest.fixture
def asset() -> str:
    """Default asset/token id used by tests."""
    return "1234567890123456789012345678901234567890123456789012345678901234"


@pytest.fixture
def now_utc() -> datetime:
    """Stable UTC timestamp for deterministic assertions."""
    return datetime(2026, 2, 13, 12, 0, 0, tzinfo=timezone.utc)


@pytest.fixture
def D() -> Callable[[Any], Decimal]:
    """Decimal helper: D('1.23') -> Decimal('1.23')."""
    return lambda value: Decimal(str(value))


@pytest.fixture
def tracking_ledger_factory(
    wallet: str,
    asset: str,
    D: Callable[[Any], Decimal],
) -> Callable[..., TrackingLedger]:
    """Build TrackingLedger with sensible defaults and easy overrides."""

    def _build(**overrides: Any) -> TrackingLedger:
        return TrackingLedger.create(
            tracked_wallet=overrides.pop("tracked_wallet", wallet),
            asset=overrides.pop("asset", asset),
            snapshot_t0_shares=overrides.pop("snapshot_t0_shares", D("0")),
            post_tracking_shares=overrides.pop("post_tracking_shares", D("0")),
            close_stage_ref_post_tracking_shares=overrides.pop(
                "close_stage_ref_post_tracking_shares", None
            ),
            id=overrides.pop("id", None),
            created_at=overrides.pop("created_at", None),
            updated_at=overrides.pop("updated_at", None),
        )

    return _build


@pytest.fixture
def bot_position_factory(
    wallet: str,
    asset: str,
    D: Callable[[Any], Decimal],
    tracking_ledger_factory: Callable[..., TrackingLedger],
) -> Callable[..., BotPosition]:
    """Build OPEN BotPosition linked to a generated or provided ledger."""

    def _build(**overrides: Any) -> BotPosition:
        ledger = overrides.pop("ledger", None) or tracking_ledger_factory()
        return BotPosition.create(
            ledger_id=overrides.pop("ledger_id", ledger.id),
            tracked_wallet=overrides.pop("tracked_wallet", wallet),
            asset=overrides.pop("asset", asset),
            shares_held=overrides.pop("shares_held", D("10")),
            entry_price=overrides.pop("entry_price", D("0.5")),
            entry_cost_usdc=overrides.pop("entry_cost_usdc", D("5")),
            fees=overrides.pop("fees", D("0")),
            id=overrides.pop("id", None),
            opened_at=overrides.pop("opened_at", None),
        )

    return _build


@pytest.fixture
def tracking_repo() -> InMemoryTrackingRepository:
    """Fresh in-memory tracking repository per test."""
    return InMemoryTrackingRepository()


@pytest.fixture
def bot_position_repo() -> InMemoryBotPositionRepository:
    """Fresh in-memory bot position repository per test."""
    return InMemoryBotPositionRepository()


@pytest.fixture
def event_bus() -> EventBus:
    """Isolated event bus instance for tests."""
    return EventBus(
        name="PolymarketCopyTradingTests",
        max_history_size=200,
        wal_path=None,
    )
