# -*- coding: utf-8 -*-
"""Repository interfaces (abstractions). Implementations live in in_memory/, sql/, etc."""

from polymarket_copy_trading.persistence.repositories.interfaces.bot_position_repository import (
    IBotPositionRepository,
)
from polymarket_copy_trading.persistence.repositories.interfaces.tracking_repository import (
    ITrackingRepository,
)

__all__ = ["ITrackingRepository", "IBotPositionRepository"]
