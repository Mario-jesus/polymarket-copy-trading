# -*- coding: utf-8 -*-
"""Abstract interface for tracking session storage (in-memory, DB, etc.)."""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Optional
from uuid import UUID

from polymarket_copy_trading.models.tracking_session import TrackingSession


class ITrackingSessionRepository(ABC):
    """Interface for persisting TrackingSession (formal t0 session per wallet)."""

    @abstractmethod
    async def get(self, session_id: UUID) -> Optional[TrackingSession]:
        """Return the session by id, or None if missing."""
        ...

    @abstractmethod
    async def save(self, session: TrackingSession) -> None:
        """Insert or update a session (by id)."""
        ...

    @abstractmethod
    async def get_active_for_wallet(self, wallet: str) -> Optional[TrackingSession]:
        """Return the active (RUNNING) session for the wallet, or None.

        Used for idempotency: avoid creating a new session if one is already running.
        """
        ...

    @abstractmethod
    async def list_by_wallet(self, wallet: str) -> list[TrackingSession]:
        """Return all sessions for the wallet, ordered by started_at descending (newest first)."""
        ...
