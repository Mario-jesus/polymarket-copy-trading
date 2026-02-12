# -*- coding: utf-8 -*-
"""Repository interfaces (abstractions). Implementations live in in_memory/, sql/, etc."""

from polymarket_copy_trading.persistence.repositories.interfaces.bot_position_repository import (
    IBotPositionRepository,
)
from polymarket_copy_trading.persistence.repositories.interfaces.seen_trade_repository import (
    ISeenTradeRepository,
)
from polymarket_copy_trading.persistence.repositories.interfaces.tracking_repository import (
    ITrackingRepository,
)
from polymarket_copy_trading.persistence.repositories.interfaces.tracking_session_repository import (
    ITrackingSessionRepository,
)

__all__ = [
    "ISeenTradeRepository",
    "ITrackingRepository",
    "ITrackingSessionRepository",
    "IBotPositionRepository",
]
