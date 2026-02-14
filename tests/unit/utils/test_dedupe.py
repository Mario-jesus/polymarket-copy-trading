# -*- coding: utf-8 -*-
"""Unit tests for dedupe helpers."""

from __future__ import annotations

from typing import Any

from polymarket_copy_trading.utils.dedupe import trade_key


def test_trade_key_prefers_transaction_hash_field() -> None:
    trade = {"transactionHash": "0xabc", "id": "123"}
    assert trade_key(trade) == "tx:0xabc"


def test_trade_key_uses_txhash_when_transaction_hash_missing() -> None:
    trade = {"txHash": "0xdef", "id": "123"}
    assert trade_key(trade) == "tx:0xdef"


def test_trade_key_uses_hash_when_other_hash_fields_missing() -> None:
    trade = {"hash": "0xghi", "id": "123"}
    assert trade_key(trade) == "tx:0xghi"


def test_trade_key_uses_id_when_no_hashes_present() -> None:
    trade = {"id": "trade-1", "timestamp": 123}
    assert trade_key(trade) == "id:trade-1"


def test_trade_key_uses_id_when_id_is_non_string() -> None:
    trade = {"id": 42}
    assert trade_key(trade) == "id:42"


def test_trade_key_falls_back_to_composite_with_condition_id() -> None:
    trade = {
        "timestamp": 1000,
        "conditionId": "cond-1",
        "outcome": "YES",
        "price": 0.45,
        "size": 12,
    }
    assert trade_key(trade) == "cmp:1000|cond-1|YES|0.45|12"


def test_trade_key_falls_back_to_market_when_condition_id_missing() -> None:
    trade = {
        "timestamp": 1000,
        "market": "market-1",
        "outcome": "NO",
        "price": 0.7,
        "size": 4,
    }
    assert trade_key(trade) == "cmp:1000|market-1|NO|0.7|4"


def test_trade_key_fallback_uses_empty_tokens_for_missing_fields() -> None:
    trade: dict[str, Any] = {}
    assert trade_key(trade) == "cmp:||||"


def test_trade_key_treats_empty_transaction_hash_as_missing() -> None:
    trade = {
        "transactionHash": "",
        "id": "trade-99",
    }
    assert trade_key(trade) == "id:trade-99"


def test_trade_key_treats_none_id_as_missing_and_uses_composite() -> None:
    trade = {
        "id": None,
        "timestamp": 10,
        "conditionId": "cond-a",
        "outcome": "YES",
        "price": 1,
        "size": 2,
    }
    assert trade_key(trade) == "cmp:10|cond-a|YES|1|2"
