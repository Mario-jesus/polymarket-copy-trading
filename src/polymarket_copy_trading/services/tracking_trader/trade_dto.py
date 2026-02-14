"""Trade-related DTOs: Data API (GET /trades) and Gamma cache (market_id, slug, title).

Data from the Polymarket Data API and from the Gamma cache are kept in separate
DTOs. TrackingTradeDTO composes them without mixing fields.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from time import time
from typing import Any, Literal

TradeSide = Literal["BUY", "SELL"]


# ---------------------------------------------------------------------------
# Data API (GET /trades) – fields from the Trade response only
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class DataApiTradeDTO:
    """Payload from Polymarket Data API GET /trades (Trade schema).

    All fields come from the API response; none from Gamma. OpenAPI does not
    declare required fields, so all are Optional except timestamp (default 0).
    """

    timestamp: int = 0
    """Unix timestamp (seconds). Default 0 if missing."""

    condition_id: str | None = None
    outcome: str | None = None
    side: TradeSide | None = None
    price: float | None = None
    size: float | None = None
    transaction_hash: str | None = None
    proxy_wallet: str | None = None
    asset: str | None = None
    icon: str | None = None
    event_slug: str | None = None
    event_id: str | None = None
    outcome_index: int | None = None
    name: str | None = None
    pseudonym: str | None = None
    bio: str | None = None
    profile_image: str | None = None
    profile_image_optimized: str | None = None
    """Data API also returns title and slug per trade; we keep them here as API source."""
    title: str | None = None
    slug: str | None = None

    def to_dict(self) -> dict[str, Any]:
        """Snake_case dict; do not mix with Gamma fields."""
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> DataApiTradeDTO:
        """Build from dict with all fields."""
        return cls(**data)

    @classmethod
    def from_response(cls, response: dict[str, Any]) -> DataApiTradeDTO:
        """Build from raw GET /trades item (camelCase)."""
        ts = response.get("timestamp")
        price_val = response.get("price")
        size_val = response.get("size")
        oi = response.get("outcomeIndex")
        return cls(
            timestamp=int(ts) if ts is not None else int(time()),
            condition_id=response.get("conditionId"),
            outcome=response.get("outcome"),
            side=response.get("side"),
            price=float(price_val) if price_val is not None else None,
            size=float(size_val) if size_val is not None else None,
            transaction_hash=response.get("transactionHash"),
            proxy_wallet=response.get("proxyWallet"),
            asset=str(response.get("asset")) if response.get("asset") is not None else None,
            icon=response.get("icon"),
            event_slug=response.get("eventSlug"),
            event_id=response.get("eventId"),
            outcome_index=int(oi) if oi is not None else None,
            name=response.get("name"),
            pseudonym=response.get("pseudonym"),
            bio=response.get("bio"),
            profile_image=response.get("profileImage"),
            profile_image_optimized=response.get("profileImageOptimized"),
            title=response.get("title"),
            slug=response.get("slug"),
        )
