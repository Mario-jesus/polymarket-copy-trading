"""DTOs for queue messages."""

from __future__ import annotations

import uuid
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from typing import Any


@dataclass(frozen=True, slots=True)
class QueueMessage[T]:
    """Base message for all queue messages."""

    id: uuid.UUID
    payload: T
    created_at: datetime
    metadata: dict[str, Any] | None = None

    @classmethod
    def create(cls, payload: T, metadata: dict[str, Any] | None = None) -> QueueMessage[T]:
        """Create a new message with the given payload."""
        return cls(
            id=uuid.uuid4(),
            payload=payload,
            created_at=datetime.now(UTC),
            metadata=metadata,
        )

    def to_dict(self) -> dict[str, Any]:
        """Convert the message to a dictionary."""
        return asdict(self)
