# -*- coding: utf-8 -*-
"""Unit tests for ClosePolicy."""

from __future__ import annotations

from collections.abc import Callable
from decimal import Decimal

import pytest

from polymarket_copy_trading.config.config import StrategySettings
from polymarket_copy_trading.models.tracking_ledger import TrackingLedger
from polymarket_copy_trading.services.strategy.close_policy import (
    ClosePolicy,
    ClosePolicyInput,
)


def _settings(close_total_threshold_pct: float = 80.0) -> StrategySettings:
    """Build StrategySettings with close threshold override."""
    return StrategySettings(close_total_threshold_pct=close_total_threshold_pct)


def _input(ledger: TrackingLedger, open_positions_count: int) -> ClosePolicyInput:
    """Build ClosePolicyInput."""
    return ClosePolicyInput(
        ledger=ledger,
        open_positions_count=open_positions_count,
    )


def test_returns_zero_when_no_open_positions(
    tracking_ledger_factory: Callable[..., TrackingLedger],
) -> None:
    policy = ClosePolicy()
    ledger = tracking_ledger_factory(
        post_tracking_shares=Decimal("50"),
        close_stage_ref_post_tracking_shares=Decimal("100"),
    )

    result = policy.positions_to_close(_input(ledger, 0), _settings(80.0))

    assert result.positions_to_close == 0
    assert "no open positions to close" in result.reason


@pytest.mark.parametrize(
    "ref_pt",
    [None, Decimal("0"), Decimal("-1")],
)
def test_returns_zero_when_ref_pt_is_missing_or_non_positive(
    ref_pt: Decimal | None,
    tracking_ledger_factory: Callable[..., TrackingLedger],
) -> None:
    policy = ClosePolicy()
    ledger = tracking_ledger_factory(
        post_tracking_shares=Decimal("50"),
        close_stage_ref_post_tracking_shares=ref_pt,
    )

    result = policy.positions_to_close(_input(ledger, 3), _settings(80.0))

    assert result.positions_to_close == 0
    assert "ref_pt not set or <= 0" in result.reason


@pytest.mark.parametrize(
    "pt_actual, ref_pt",
    [(Decimal("100"), Decimal("100")), (Decimal("120"), Decimal("100"))],
)
def test_returns_zero_when_no_close_stage_progress(
    pt_actual: Decimal,
    ref_pt: Decimal,
    tracking_ledger_factory: Callable[..., TrackingLedger],
) -> None:
    policy = ClosePolicy()
    ledger = tracking_ledger_factory(
        post_tracking_shares=pt_actual,
        close_stage_ref_post_tracking_shares=ref_pt,
    )

    result = policy.positions_to_close(_input(ledger, 4), _settings(80.0))

    assert result.positions_to_close == 0
    assert "no close stage progress" in result.reason


@pytest.mark.parametrize("threshold", [0.0])
def test_returns_zero_when_per_position_is_non_positive(
    threshold: float,
    tracking_ledger_factory: Callable[..., TrackingLedger],
) -> None:
    policy = ClosePolicy()
    ledger = tracking_ledger_factory(
        post_tracking_shares=Decimal("20"),
        close_stage_ref_post_tracking_shares=Decimal("100"),
    )

    result = policy.positions_to_close(_input(ledger, 2), _settings(threshold))

    assert result.positions_to_close == 0
    assert "per_position <= 0" in result.reason


def test_returns_zero_when_stage_close_is_below_per_position_threshold(
    tracking_ledger_factory: Callable[..., TrackingLedger],
) -> None:
    policy = ClosePolicy()
    # stage_pct_closed = 20%; per_position = 80/2 = 40% -> n = floor(20/40) = 0
    ledger = tracking_ledger_factory(
        post_tracking_shares=Decimal("80"),
        close_stage_ref_post_tracking_shares=Decimal("100"),
    )

    result = policy.positions_to_close(_input(ledger, 2), _settings(80.0))

    assert result.positions_to_close == 0
    assert "stage_pct_closed=20.00% < per_position=40.00%" in result.reason


def test_closes_exactly_one_position_when_stage_reaches_first_step(
    tracking_ledger_factory: Callable[..., TrackingLedger],
) -> None:
    policy = ClosePolicy()
    # stage_pct_closed = 40%; per_position = 80/2 = 40% -> n = floor(1) = 1
    ledger = tracking_ledger_factory(
        post_tracking_shares=Decimal("60"),
        close_stage_ref_post_tracking_shares=Decimal("100"),
    )

    result = policy.positions_to_close(_input(ledger, 2), _settings(80.0))

    assert result.positions_to_close == 1
    assert "close 1 positions" in result.reason


def test_closes_multiple_positions_using_floor_division(
    tracking_ledger_factory: Callable[..., TrackingLedger],
) -> None:
    policy = ClosePolicy()
    # open_positions=4 => per_position=80/4=20
    # stage_pct_closed=61 => floor(61/20)=3
    ledger = tracking_ledger_factory(
        post_tracking_shares=Decimal("39"),
        close_stage_ref_post_tracking_shares=Decimal("100"),
    )

    result = policy.positions_to_close(_input(ledger, 4), _settings(80.0))

    assert result.positions_to_close == 3
    assert "close 3 positions" in result.reason


def test_result_is_capped_by_open_positions_count(
    tracking_ledger_factory: Callable[..., TrackingLedger],
) -> None:
    policy = ClosePolicy()
    # stage_pct_closed=100, threshold=100, open_positions=2 -> per_position=50 -> floor(100/50)=2
    # still verifies cap behavior when upper bound is reached.
    ledger = tracking_ledger_factory(
        post_tracking_shares=Decimal("0"),
        close_stage_ref_post_tracking_shares=Decimal("100"),
    )

    result = policy.positions_to_close(_input(ledger, 2), _settings(100.0))

    assert result.positions_to_close == 2
    assert "close 2 positions" in result.reason


def test_handles_fractional_stage_and_threshold_with_expected_flooring(
    tracking_ledger_factory: Callable[..., TrackingLedger],
) -> None:
    policy = ClosePolicy()
    # open_positions=3 => per_position=80/3=26.666...
    # stage_pct_closed=79% => floor(79/26.666...) = 2
    ledger = tracking_ledger_factory(
        post_tracking_shares=Decimal("21"),
        close_stage_ref_post_tracking_shares=Decimal("100"),
    )

    result = policy.positions_to_close(_input(ledger, 3), _settings(80.0))

    assert result.positions_to_close == 2
    assert "close 2 positions" in result.reason


def test_closes_all_positions_at_or_above_total_threshold(
    tracking_ledger_factory: Callable[..., TrackingLedger],
) -> None:
    policy = ClosePolicy()
    # open_positions=5 => per_position=80/5=16
    # stage_pct_closed=80 => floor(80/16)=5
    ledger = tracking_ledger_factory(
        post_tracking_shares=Decimal("20"),
        close_stage_ref_post_tracking_shares=Decimal("100"),
    )

    result = policy.positions_to_close(_input(ledger, 5), _settings(80.0))

    assert result.positions_to_close == 5
    assert "close 5 positions" in result.reason


@pytest.mark.parametrize(
    ("open_positions_count", "pt_actual", "ref_pt", "threshold", "expected"),
    [
        # 25% closed, per_position=40 -> 0
        (2, Decimal("75"), Decimal("100"), 80.0, 0),
        # 50% closed, per_position=40 -> 1
        (2, Decimal("50"), Decimal("100"), 80.0, 1),
        # 75% closed, per_position=20 -> 3
        (4, Decimal("25"), Decimal("100"), 80.0, 3),
    ],
)
def test_table_driven_close_scenarios(
    open_positions_count: int,
    pt_actual: Decimal,
    ref_pt: Decimal,
    threshold: float,
    expected: int,
    tracking_ledger_factory: Callable[..., TrackingLedger],
) -> None:
    policy = ClosePolicy()
    ledger = tracking_ledger_factory(
        post_tracking_shares=pt_actual,
        close_stage_ref_post_tracking_shares=ref_pt,
    )

    result = policy.positions_to_close(
        _input(ledger, open_positions_count),
        _settings(threshold),
    )

    assert result.positions_to_close == expected


def test_negative_open_positions_is_treated_as_no_positions(
    tracking_ledger_factory: Callable[..., TrackingLedger],
) -> None:
    policy = ClosePolicy()
    ledger = tracking_ledger_factory(
        post_tracking_shares=Decimal("10"),
        close_stage_ref_post_tracking_shares=Decimal("100"),
    )

    result = policy.positions_to_close(_input(ledger, -1), _settings(80.0))

    assert result.positions_to_close == 0
    assert "no open positions to close" in result.reason
