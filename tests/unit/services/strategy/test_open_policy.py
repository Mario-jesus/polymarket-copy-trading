# -*- coding: utf-8 -*-
"""Unit tests for OpenPolicy."""

from __future__ import annotations

from collections.abc import Callable
from decimal import Decimal

import pytest

from polymarket_copy_trading.config.config import StrategySettings
from polymarket_copy_trading.models.tracking_ledger import TrackingLedger
from polymarket_copy_trading.services.strategy.open_policy import OpenPolicy, OpenPolicyInput


def _settings(
    *,
    max_positions_per_ledger: int = 5,
    max_active_ledgers: int = 10,
    asset_min_position_percent: float = 0.0,
    asset_min_position_shares: float = 0.0,
) -> StrategySettings:
    """Build StrategySettings with relevant OpenPolicy overrides."""
    return StrategySettings(
        max_positions_per_ledger=max_positions_per_ledger,
        max_active_ledgers=max_active_ledgers,
        asset_min_position_percent=asset_min_position_percent,
        asset_min_position_shares=asset_min_position_shares,
    )


def _input(
    *,
    ledger: TrackingLedger,
    open_positions_count: int,
    active_ledgers_count: int,
    account_total_value_usdc: Decimal,
    post_tracking_value_usdc: Decimal,
) -> OpenPolicyInput:
    """Build OpenPolicyInput."""
    return OpenPolicyInput(
        ledger=ledger,
        open_positions_count=open_positions_count,
        active_ledgers_count=active_ledgers_count,
        account_total_value_usdc=account_total_value_usdc,
        post_tracking_value_usdc=post_tracking_value_usdc,
    )


def test_blocks_when_max_positions_per_ledger_reached(
    tracking_ledger_factory: Callable[..., TrackingLedger],
) -> None:
    policy = OpenPolicy()
    settings = _settings(max_positions_per_ledger=2, asset_min_position_shares=10.0)
    ledger = tracking_ledger_factory(post_tracking_shares=Decimal("100"))
    inp = _input(
        ledger=ledger,
        open_positions_count=2,
        active_ledgers_count=0,
        account_total_value_usdc=Decimal("1000"),
        post_tracking_value_usdc=Decimal("100"),
    )

    result = policy.should_open(inp, settings)

    assert result.should_open is False
    assert "max_positions_per_ledger reached" in result.reason


def test_blocks_new_ledger_when_max_active_ledgers_reached(
    tracking_ledger_factory: Callable[..., TrackingLedger],
) -> None:
    policy = OpenPolicy()
    settings = _settings(max_active_ledgers=3, asset_min_position_shares=10.0)
    ledger = tracking_ledger_factory(post_tracking_shares=Decimal("100"))
    inp = _input(
        ledger=ledger,
        open_positions_count=0,  # new ledger path
        active_ledgers_count=3,
        account_total_value_usdc=Decimal("1000"),
        post_tracking_value_usdc=Decimal("100"),
    )

    result = policy.should_open(inp, settings)

    assert result.should_open is False
    assert "max_active_ledgers reached" in result.reason


def test_does_not_apply_max_active_ledgers_when_ledger_already_active(
    tracking_ledger_factory: Callable[..., TrackingLedger],
) -> None:
    policy = OpenPolicy()
    settings = _settings(
        max_positions_per_ledger=5,
        max_active_ledgers=1,
        asset_min_position_shares=10.0,
    )
    ledger = tracking_ledger_factory(post_tracking_shares=Decimal("20"))
    inp = _input(
        ledger=ledger,
        open_positions_count=1,  # already active ledger
        active_ledgers_count=1,
        account_total_value_usdc=Decimal("1000"),
        post_tracking_value_usdc=Decimal("100"),
    )

    result = policy.should_open(inp, settings)

    assert result.should_open is True
    assert "shares threshold met" in result.reason


@pytest.mark.parametrize("post_tracking", [Decimal("0"), Decimal("-1")])
def test_blocks_when_post_tracking_is_non_positive(
    post_tracking: Decimal,
    tracking_ledger_factory: Callable[..., TrackingLedger],
) -> None:
    policy = OpenPolicy()
    settings = _settings(asset_min_position_shares=1.0)
    ledger = tracking_ledger_factory(post_tracking_shares=post_tracking)
    inp = _input(
        ledger=ledger,
        open_positions_count=0,
        active_ledgers_count=0,
        account_total_value_usdc=Decimal("1000"),
        post_tracking_value_usdc=Decimal("100"),
    )

    result = policy.should_open(inp, settings)

    assert result.should_open is False
    assert "post_tracking_shares <= 0" in result.reason


def test_opens_when_shares_threshold_is_met(
    tracking_ledger_factory: Callable[..., TrackingLedger],
) -> None:
    policy = OpenPolicy()
    settings = _settings(asset_min_position_shares=50.0, asset_min_position_percent=99.0)
    ledger = tracking_ledger_factory(post_tracking_shares=Decimal("50"))
    inp = _input(
        ledger=ledger,
        open_positions_count=0,
        active_ledgers_count=0,
        account_total_value_usdc=Decimal("1000"),
        post_tracking_value_usdc=Decimal("1"),  # percent intentionally not met
    )

    result = policy.should_open(inp, settings)

    assert result.should_open is True
    assert "shares threshold met" in result.reason


def test_opens_when_percent_threshold_is_met_for_first_position(
    tracking_ledger_factory: Callable[..., TrackingLedger],
) -> None:
    policy = OpenPolicy()
    settings = _settings(asset_min_position_shares=1000.0, asset_min_position_percent=10.0)
    ledger = tracking_ledger_factory(post_tracking_shares=Decimal("10"))
    inp = _input(
        ledger=ledger,
        open_positions_count=0,  # effective threshold = 1 * 10% = 10%
        active_ledgers_count=0,
        account_total_value_usdc=Decimal("1000"),
        post_tracking_value_usdc=Decimal("100"),  # 10%
    )

    result = policy.should_open(inp, settings)

    assert result.should_open is True
    assert "percent threshold met" in result.reason


def test_percent_threshold_scales_with_open_positions_count(
    tracking_ledger_factory: Callable[..., TrackingLedger],
) -> None:
    policy = OpenPolicy()
    settings = _settings(asset_min_position_shares=1000.0, asset_min_position_percent=10.0)
    ledger = tracking_ledger_factory(post_tracking_shares=Decimal("100"))
    inp = _input(
        ledger=ledger,
        open_positions_count=2,  # effective threshold = 30%
        active_ledgers_count=1,
        account_total_value_usdc=Decimal("1000"),
        post_tracking_value_usdc=Decimal("299"),  # 29.9% -> should not open
    )

    result = policy.should_open(inp, settings)

    assert result.should_open is False
    assert "thresholds not met" in result.reason
    assert "effective_pct=0.3000" in result.reason


def test_opens_when_percent_matches_scaled_effective_threshold(
    tracking_ledger_factory: Callable[..., TrackingLedger],
) -> None:
    policy = OpenPolicy()
    settings = _settings(asset_min_position_shares=1000.0, asset_min_position_percent=10.0)
    ledger = tracking_ledger_factory(post_tracking_shares=Decimal("100"))
    inp = _input(
        ledger=ledger,
        open_positions_count=2,  # effective threshold = 30%
        active_ledgers_count=1,
        account_total_value_usdc=Decimal("1000"),
        post_tracking_value_usdc=Decimal("300"),  # exactly 30%
    )

    result = policy.should_open(inp, settings)

    assert result.should_open is True
    assert "percent threshold met" in result.reason


@pytest.mark.parametrize(
    ("asset_min_position_percent", "account_total_value_usdc", "post_tracking_value_usdc"),
    [
        (0.0, Decimal("1000"), Decimal("100")),  # percent disabled
        (10.0, Decimal("0"), Decimal("100")),  # no account total value
    ],
)
def test_falls_back_to_shares_only_when_percent_is_disabled_or_no_account_value(
    asset_min_position_percent: float,
    account_total_value_usdc: Decimal,
    post_tracking_value_usdc: Decimal,
    tracking_ledger_factory: Callable[..., TrackingLedger],
) -> None:
    policy = OpenPolicy()
    settings = _settings(
        asset_min_position_shares=50.0,
        asset_min_position_percent=asset_min_position_percent,
    )
    ledger = tracking_ledger_factory(post_tracking_shares=Decimal("40"))  # below shares
    inp = _input(
        ledger=ledger,
        open_positions_count=0,
        active_ledgers_count=0,
        account_total_value_usdc=account_total_value_usdc,
        post_tracking_value_usdc=post_tracking_value_usdc,
    )

    result = policy.should_open(inp, settings)

    assert result.should_open is False
    assert "shares threshold not met" in result.reason
    assert "percent disabled or no account value" in result.reason


def test_shares_threshold_takes_precedence_over_percent(
    tracking_ledger_factory: Callable[..., TrackingLedger],
) -> None:
    policy = OpenPolicy()
    settings = _settings(asset_min_position_shares=20.0, asset_min_position_percent=90.0)
    ledger = tracking_ledger_factory(post_tracking_shares=Decimal("25"))  # shares met
    inp = _input(
        ledger=ledger,
        open_positions_count=0,
        active_ledgers_count=0,
        account_total_value_usdc=Decimal("1000"),
        post_tracking_value_usdc=Decimal("1"),  # percent not met
    )

    result = policy.should_open(inp, settings)

    assert result.should_open is True
    assert "shares threshold met" in result.reason


def test_thresholds_not_met_message_contains_both_shares_and_percent_values(
    tracking_ledger_factory: Callable[..., TrackingLedger],
) -> None:
    policy = OpenPolicy()
    settings = _settings(asset_min_position_shares=100.0, asset_min_position_percent=20.0)
    ledger = tracking_ledger_factory(post_tracking_shares=Decimal("10"))
    inp = _input(
        ledger=ledger,
        open_positions_count=1,  # effective threshold = 40%
        active_ledgers_count=0,
        account_total_value_usdc=Decimal("1000"),
        post_tracking_value_usdc=Decimal("150"),  # 15%
    )

    result = policy.should_open(inp, settings)

    assert result.should_open is False
    assert "thresholds not met" in result.reason
    assert "shares=10 < 100.0" in result.reason
    assert "open_pct=0.1500 < effective_pct=0.4000" in result.reason


@pytest.mark.parametrize(
    ("open_positions_count", "post_tracking_value_usdc", "expected_open"),
    [
        # effective pct = (k+1)*10%
        (0, Decimal("100"), True),  # 10%
        (1, Decimal("200"), True),  # 20%
        (2, Decimal("300"), True),  # 30%
        (3, Decimal("399"), False),  # 39.9% < 40%
    ],
)
def test_table_driven_effective_percent_threshold(
    open_positions_count: int,
    post_tracking_value_usdc: Decimal,
    expected_open: bool,
    tracking_ledger_factory: Callable[..., TrackingLedger],
) -> None:
    policy = OpenPolicy()
    settings = _settings(asset_min_position_shares=10000.0, asset_min_position_percent=10.0)
    ledger = tracking_ledger_factory(post_tracking_shares=Decimal("100"))
    inp = _input(
        ledger=ledger,
        open_positions_count=open_positions_count,
        active_ledgers_count=0,
        account_total_value_usdc=Decimal("1000"),
        post_tracking_value_usdc=post_tracking_value_usdc,
    )

    result = policy.should_open(inp, settings)

    assert result.should_open is expected_open
