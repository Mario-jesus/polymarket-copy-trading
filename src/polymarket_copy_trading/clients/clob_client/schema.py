"""Schema for Polymarket CLOB (py_clob_client)."""

from __future__ import annotations

from typing import Literal, TypedDict

Side = Literal["BUY", "SELL"]


class TradeSchema(TypedDict):
    """Trade schema."""

    id: str
    taker_order_id: str
    market: str
    asset_id: str
    side: Side
    size: str
    fee_rate_bps: str
    price: str
    status: str
    match_time: str
    last_update: str
    outcome: str
    bucket_index: int
    owner: str
    maker_address: str
    maker_orders: list[MakerOrderSchema]
    transaction_hash: str
    trader_side: Literal["TAKER", "MAKER"]


class MakerOrderSchema(TypedDict):
    """Maker order schema."""

    order_id: str
    owner: str
    maker_address: str
    matched_amount: str
    price: str
    fee_rate_bps: str
    asset_id: str
    outcome: str
    side: Side
