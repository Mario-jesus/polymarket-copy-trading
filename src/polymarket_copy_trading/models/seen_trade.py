"""SeenTrade: domain entity for persistent trade deduplication.

Identity is (wallet, trade_key). Used to avoid reprocessing trades on restart.
trade_key comes from utils.dedupe.trade_key() (e.g. tx:{transactionHash}).
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime


@dataclass(frozen=True, slots=True)
class SeenTrade:
    """Record that a trade has been seen (for deduplication).

    Identity: (wallet, trade_key). seen_at supports retention policies.
    """

    wallet: str
    """Tracked wallet address (0x...)."""
    trade_key: str
    """Stable key from utils.dedupe.trade_key() (e.g. tx:0x..., id:123, cmp:...)."""
    seen_at: datetime
    """When the trade was first seen (for retention/audit)."""

    @classmethod
    def create(
        cls,
        wallet: str,
        trade_key: str,
        *,
        seen_at: datetime | None = None,
    ) -> SeenTrade:
        """Create a new SeenTrade record."""
        wallet = wallet.strip()
        trade_key = trade_key.strip()
        if not wallet or not trade_key:
            raise ValueError("wallet and trade_key must be non-empty")
        return cls(
            wallet=wallet,
            trade_key=trade_key,
            seen_at=seen_at or datetime.now(UTC),
        )
