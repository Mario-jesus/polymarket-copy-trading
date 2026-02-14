"""Data API response types (OpenAPI schema alignment)."""

from __future__ import annotations

from typing import Literal, TypedDict


class TradeSchema(TypedDict, total=False):
    """GET /trades item (Trade schema). Keys match API response (camelCase)."""

    proxyWallet: str
    side: Literal["BUY", "SELL"]
    asset: str
    conditionId: str
    size: float
    price: float
    timestamp: int
    title: str
    slug: str
    icon: str
    eventSlug: str
    outcome: str
    outcomeIndex: int
    name: str
    pseudonym: str
    bio: str
    profileImage: str
    profileImageOptimized: str
    transactionHash: str


class PositionSchema(TypedDict, total=False):
    """GET /positions item (Position schema). Keys match API response (camelCase)."""

    proxyWallet: str
    asset: str
    conditionId: str
    size: float
    avgPrice: float
    initialValue: float
    currentValue: float
    cashPnl: float
    percentPnl: float
    totalBought: float
    realizedPnl: float
    percentRealizedPnl: float
    curPrice: float
    redeemable: bool
    mergeable: bool
    title: str
    slug: str
    icon: str
    eventSlug: str
    outcome: str
    outcomeIndex: int
    oppositeOutcome: str
    oppositeAsset: str
    endDate: str
    negativeRisk: bool


class ValueSchema(TypedDict, total=False):
    """GET /value item (Value schema). Keys match API response (camelCase)."""

    user: str
    value: float
