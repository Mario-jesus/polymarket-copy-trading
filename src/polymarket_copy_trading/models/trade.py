# -*- coding: utf-8 -*-
"""Trade-related models."""

from __future__ import annotations

from typing import Any
from dataclasses import dataclass


@dataclass(frozen=True)
class NormalizedTrade:
    """Normalized trade passed to the tracking callback."""

    timestamp: Any
    market_id: Any
    condition_id: str | None
    gamma_slug: str
    gamma_title: str
    event_id: Any
    outcome: Any
    side: Any
    price: Any
    size: Any
    transaction_hash: Any
