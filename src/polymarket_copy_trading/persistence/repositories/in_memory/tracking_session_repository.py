"""In-memory tracking session repository (keyed by session id)."""

from __future__ import annotations

from uuid import UUID

from polymarket_copy_trading.models.tracking_session import (
    SessionStatus,
    TrackingSession,
)
from polymarket_copy_trading.persistence.repositories.interfaces.tracking_session_repository import (
    ITrackingSessionRepository,
)


def _by_started_at_desc(session: TrackingSession) -> str:
    """Sort key: started_at descending (newest first)."""
    return session.started_at.isoformat()


class InMemoryTrackingSessionRepository(ITrackingSessionRepository):
    """In-memory implementation of ITrackingSessionRepository."""

    def __init__(self) -> None:
        """Initialize an empty in-memory store."""
        self._store: dict[UUID, TrackingSession] = {}

    async def get(self, session_id: UUID) -> TrackingSession | None:
        """Return the session by id, or None if missing."""
        return self._store.get(session_id)

    async def save(self, session: TrackingSession) -> None:
        """Insert or update a session (by id)."""
        self._store[session.id] = session

    async def get_active_for_wallet(self, wallet: str) -> TrackingSession | None:
        """Return the active (RUNNING) session for the wallet, or None."""
        wallet = wallet.strip()
        for s in self._store.values():
            if s.wallet == wallet and s.status == SessionStatus.RUNNING and s.ended_at is None:
                return s
        return None

    async def list_by_wallet(self, wallet: str) -> list[TrackingSession]:
        """Return all sessions for the wallet, ordered by started_at descending."""
        wallet = wallet.strip()
        sessions = [s for s in self._store.values() if s.wallet == wallet]
        return sorted(sessions, key=_by_started_at_desc, reverse=True)
