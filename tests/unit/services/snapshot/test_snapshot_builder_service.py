# -*- coding: utf-8 -*-
"""Unit tests for SnapshotBuilderService."""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any, cast
from unittest.mock import AsyncMock

import pytest

from polymarket_copy_trading.clients.data_api.schema import PositionSchema
from polymarket_copy_trading.models.tracking_session import SessionStatus, TrackingSession
from polymarket_copy_trading.persistence.repositories.in_memory.tracking_repository import (
    InMemoryTrackingRepository,
)
from polymarket_copy_trading.persistence.repositories.in_memory.tracking_session_repository import (
    InMemoryTrackingSessionRepository,
)
from polymarket_copy_trading.services.snapshot.snapshot_builder import SnapshotBuilderService


def _builder(
    *,
    data_api: Any,
    tracking_repo: InMemoryTrackingRepository,
    session_repo: InMemoryTrackingSessionRepository,
) -> SnapshotBuilderService:
    """Build SnapshotBuilderService with injected fakes/repositories."""
    return SnapshotBuilderService(
        data_api=data_api,
        tracking_repository=tracking_repo,
        tracking_session_repository=session_repo,
    )


def _pos(asset: str | None, size: Any) -> PositionSchema:
    """Helper to build PositionSchema-like dict."""
    return cast(PositionSchema, {"asset": asset, "size": size})


@pytest.fixture
def tracking_repo() -> InMemoryTrackingRepository:
    return InMemoryTrackingRepository()


@pytest.fixture
def session_repo() -> InMemoryTrackingSessionRepository:
    return InMemoryTrackingSessionRepository()


async def test_build_snapshot_creates_session_and_persists_ledgers(
    tracking_repo: InMemoryTrackingRepository,
    session_repo: InMemoryTrackingSessionRepository,
) -> None:
    data_api: Any = SimpleNamespace(
        get_positions=AsyncMock(
            return_value=[
                _pos("asset-a", 2.5),
                _pos("asset-b", 3.0),
            ]
        )
    )
    builder = _builder(data_api=data_api, tracking_repo=tracking_repo, session_repo=session_repo)

    result = await builder.build_snapshot_t0(" 0xwallet ")

    assert result.success is True
    assert result.wallet == "0xwallet"
    assert len(result.ledgers_updated) == 2

    ledger_a = await tracking_repo.get("0xwallet", "asset-a")
    ledger_b = await tracking_repo.get("0xwallet", "asset-b")
    assert ledger_a is not None and str(ledger_a.snapshot_t0_shares) == "2.5"
    assert ledger_a is not None and str(ledger_a.post_tracking_shares) == "0"
    assert ledger_b is not None and str(ledger_b.snapshot_t0_shares) == "3.0"
    assert ledger_b is not None and str(ledger_b.post_tracking_shares) == "0"

    sessions = await session_repo.list_by_wallet("0xwallet")
    assert len(sessions) == 1
    assert sessions[0].snapshot_completed_at is not None
    assert sessions[0].snapshot_source == "positions"


async def test_build_snapshot_aggregates_same_asset_and_skips_invalid_positions(
    tracking_repo: InMemoryTrackingRepository,
    session_repo: InMemoryTrackingSessionRepository,
) -> None:
    data_api: Any = SimpleNamespace(
        get_positions=AsyncMock(
            return_value=[
                _pos("asset-a", 1.5),
                _pos("asset-a", 2),
                _pos(None, 3),  # invalid (no asset)
                _pos("asset-b", None),  # invalid (no size)
                _pos("asset-c", "bad"),  # invalid (non-float size)
            ]
        )
    )
    builder = _builder(data_api=data_api, tracking_repo=tracking_repo, session_repo=session_repo)

    result = await builder.build_snapshot_t0("0xwallet")

    assert result.success is True
    assert len(result.ledgers_updated) == 1
    ledger_a = await tracking_repo.get("0xwallet", "asset-a")
    assert ledger_a is not None
    assert str(ledger_a.snapshot_t0_shares) == "3.5"
    assert str(ledger_a.post_tracking_shares) == "0"


async def test_build_snapshot_paginates_until_chunk_shorter_than_limit(
    tracking_repo: InMemoryTrackingRepository,
    session_repo: InMemoryTrackingSessionRepository,
) -> None:
    first_chunk = [_pos("asset-a", 1)] * SnapshotBuilderService.DEFAULT_LIMIT
    second_chunk = [_pos("asset-b", 2)]
    data_api: Any = SimpleNamespace(
        get_positions=AsyncMock(side_effect=[first_chunk, second_chunk])
    )
    builder = _builder(data_api=data_api, tracking_repo=tracking_repo, session_repo=session_repo)

    result = await builder.build_snapshot_t0("0xwallet")

    assert result.success is True
    assert data_api.get_positions.await_count == 2
    # first page adds 100*1 to asset-a, second adds 1*2 to asset-b
    ledger_a = await tracking_repo.get("0xwallet", "asset-a")
    ledger_b = await tracking_repo.get("0xwallet", "asset-b")
    assert ledger_a is not None and str(ledger_a.snapshot_t0_shares) == "100.0"
    assert ledger_b is not None and str(ledger_b.snapshot_t0_shares) == "2.0"


async def test_build_snapshot_reuses_existing_active_session(
    tracking_repo: InMemoryTrackingRepository,
    session_repo: InMemoryTrackingSessionRepository,
) -> None:
    existing = TrackingSession.create("0xwallet")
    await session_repo.save(existing)

    data_api: Any = SimpleNamespace(get_positions=AsyncMock(return_value=[_pos("asset-a", 1)]))
    builder = _builder(data_api=data_api, tracking_repo=tracking_repo, session_repo=session_repo)

    result = await builder.build_snapshot_t0("0xwallet")

    assert result.success is True
    assert result.session_id == existing.id
    sessions = await session_repo.list_by_wallet("0xwallet")
    assert len(sessions) == 1
    assert sessions[0].id == existing.id


async def test_build_snapshot_marks_session_error_when_data_api_raises(
    tracking_repo: InMemoryTrackingRepository,
    session_repo: InMemoryTrackingSessionRepository,
) -> None:
    data_api: Any = SimpleNamespace(
        get_positions=AsyncMock(side_effect=RuntimeError("data api down"))
    )
    builder = _builder(data_api=data_api, tracking_repo=tracking_repo, session_repo=session_repo)

    result = await builder.build_snapshot_t0("0xwallet")

    assert result.success is False
    assert result.error == "data api down"
    assert result.session_id is not None

    sessions = await session_repo.list_by_wallet("0xwallet")
    assert len(sessions) == 1
    assert sessions[0].status == SessionStatus.ERROR
    assert sessions[0].ended_at is not None
