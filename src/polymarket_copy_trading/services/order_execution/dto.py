"""Models for order execution."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any


@dataclass
class OrderExecutionResult[T]:
    """Result of a market order execution."""

    success: bool = False
    response: T | None = None
    error: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> OrderExecutionResult[T]:
        return cls(**data)


@dataclass
class OrderResponse:
    """Response from the PostOrder API."""

    success: bool = False
    error_msg: str | None = None
    order_id: str | None = None
    transactions_hashes: list[str] = field(default_factory=list)
    status: str | None = None
    taking_amount: str | None = None
    making_amount: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> OrderResponse:
        return cls(**data)

    @classmethod
    def from_response(cls, response: dict[str, Any] | None) -> OrderResponse:
        if response is None:
            return cls()

        return cls(
            success=response.get("success", False),
            error_msg=response.get("errorMsg", None),
            order_id=response.get("orderID", None),
            transactions_hashes=response.get("transactionsHashes", []),
            status=response.get("status", None),
            taking_amount=response.get("takingAmount", None),
            making_amount=response.get("makingAmount", None),
        )
