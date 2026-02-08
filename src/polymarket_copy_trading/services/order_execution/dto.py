# -*- coding: utf-8 -*-
"""Models for order execution."""
from __future__ import annotations

from typing import List, Optional, Dict, Any
from dataclasses import dataclass, field, asdict


@dataclass
class OrderExecutionResult[T]:
    """Result of a market order execution."""
    success: bool = False
    response: Optional[T] = None
    error: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "OrderExecutionResult[T]":
        return cls(**data)


@dataclass
class OrderResponse:
    """Response from the PostOrder API."""
    success: bool = False
    error_msg: Optional[str] = None
    order_id: Optional[str] = None
    transactions_hashes: List[str] = field(default_factory=list)
    status: Optional[str] = None
    taking_amount: Optional[str] = None
    making_amount: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "OrderResponse":
        return cls(**data)

    @classmethod
    def from_response(cls, response: Optional[Dict[str, Any]]) -> "OrderResponse":
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
