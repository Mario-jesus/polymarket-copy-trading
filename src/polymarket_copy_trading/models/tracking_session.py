"""TrackingSession: domain entity for a formal t0 session.

Represents one "start of following" for a wallet. Captures when the session started,
when the snapshot t0 completed, and optional end/status for idempotency and auditing.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from enum import Enum
from uuid import UUID, uuid4


class SessionStatus(str, Enum):
    """Session lifecycle state."""

    RUNNING = "RUNNING"
    """Session active; tracking in progress."""
    STOPPED = "STOPPED"
    """Session ended gracefully."""
    ERROR = "ERROR"
    """Session failed (e.g. snapshot error)."""


@dataclass(frozen=True, slots=True)
class TrackingSession:
    """One tracking session for a wallet: from start through snapshot t0 and optional end.

    Identity: id (UUID). One session per wallet per "run" (or per explicit start).
    Supports idempotency: check if session exists before re-running snapshot.
    """

    id: UUID
    wallet: str
    """Tracked wallet address (0x...)."""
    started_at: datetime
    """When the session was started."""
    snapshot_completed_at: datetime | None = None
    """When the snapshot t0 finished successfully. None if not yet or failed."""
    snapshot_source: str | None = None
    """Source of snapshot: 'positions', 'trades', etc."""
    status: SessionStatus = SessionStatus.RUNNING
    ended_at: datetime | None = None
    """When the session ended (if status is STOPPED or ERROR)."""

    def with_snapshot_completed(
        self,
        completed_at: datetime,
        *,
        source: str | None = None,
    ) -> TrackingSession:
        """Return a copy with snapshot_completed_at set."""
        return TrackingSession(
            id=self.id,
            wallet=self.wallet,
            started_at=self.started_at,
            snapshot_completed_at=completed_at,
            snapshot_source=source or self.snapshot_source,
            status=self.status,
            ended_at=self.ended_at,
        )

    def with_ended(
        self,
        ended_at: datetime,
        *,
        status: SessionStatus = SessionStatus.STOPPED,
    ) -> TrackingSession:
        """Return a copy with ended_at and status set."""
        return TrackingSession(
            id=self.id,
            wallet=self.wallet,
            started_at=self.started_at,
            snapshot_completed_at=self.snapshot_completed_at,
            snapshot_source=self.snapshot_source,
            status=status,
            ended_at=ended_at,
        )

    def with_status(self, status: SessionStatus) -> TrackingSession:
        """Return a copy with updated status."""
        return TrackingSession(
            id=self.id,
            wallet=self.wallet,
            started_at=self.started_at,
            snapshot_completed_at=self.snapshot_completed_at,
            snapshot_source=self.snapshot_source,
            status=status,
            ended_at=self.ended_at,
        )

    @classmethod
    def create(
        cls,
        wallet: str,
        *,
        started_at: datetime | None = None,
        id: UUID | None = None,
    ) -> TrackingSession:
        """Create a new tracking session (status RUNNING)."""
        wallet = wallet.strip()
        if not wallet:
            raise ValueError("wallet must be non-empty")
        now = started_at or datetime.now(UTC)
        return cls(
            id=id or uuid4(),
            wallet=wallet,
            started_at=now,
            snapshot_completed_at=None,
            snapshot_source=None,
            status=SessionStatus.RUNNING,
            ended_at=None,
        )
