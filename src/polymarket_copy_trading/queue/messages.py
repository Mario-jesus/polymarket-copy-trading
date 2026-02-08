# -*- coding: utf-8 -*-
"""DTOs for queue messages."""

from __future__ import annotations

import uuid
from typing import Any, Optional
from datetime import datetime, timezone
from dataclasses import dataclass, asdict


@dataclass(frozen=True)
class QueueMessage[T]:
    """Base message for all queue messages."""

    id: uuid.UUID
    payload: T
    created_at: datetime
    metadata: Optional[dict[str, Any]] = None

    @classmethod
    def create(cls, payload: T, metadata: Optional[dict[str, Any]] = None) -> QueueMessage[T]:
        """Create a new message with the given payload."""
        return cls(
            id=uuid.uuid4(),
            payload=payload,
            created_at=datetime.now(timezone.utc),
            metadata=metadata,
        )

    def to_dict(self) -> dict[str, Any]:
        """Convert the message to a dictionary."""
        return asdict(self)
