# -*- coding: utf-8 -*-
"""Service to compute total Polymarket account value (USDC.e cash + positions value)."""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from typing import TYPE_CHECKING, Any, Callable, Optional

import structlog

from polymarket_copy_trading.utils.validation import mask_address

if TYPE_CHECKING:
    from polymarket_copy_trading.clients.data_api import DataApiClient
    from polymarket_copy_trading.clients.rcp_client import RpcClient


@dataclass(frozen=True)
class AccountValueResult:
    """Total account value for a Polymarket wallet."""

    wallet: str
    cash_usdc: Decimal
    """On-chain USDC.e balance (collateral/cash)."""
    positions_value_usdc: Decimal
    """Mark-to-market value of open positions (from Data API /value)."""
    total_usdc: Decimal
    """cash_usdc + positions_value_usdc."""

    @property
    def total_float(self) -> float:
        """Total value as float for convenience."""
        return float(self.total_usdc)


class AccountValueService:
    """Computes total Polymarket wallet value: on-chain USDC.e + positions value from Data API."""

    def __init__(
        self,
        rpc_client: "RpcClient",
        data_api: "DataApiClient",
        *,
        get_logger: Callable[[str], Any] = structlog.get_logger,
        logger_name: Optional[str] = None,
    ) -> None:
        """Initialize the service.

        Args:
            rpc_client: For on-chain USDC.e balance (get_erc20_balance / get_usdc_e_balance).
            data_api: For positions value (get_positions_value).
            get_logger: Logger factory (injected).
            logger_name: Optional logger name (defaults to class name).
        """
        self._rpc = rpc_client
        self._data_api = data_api
        self._logger = get_logger(logger_name or self.__class__.__name__)

    async def get_total_account_value(
        self,
        wallet: str,
        *,
        market: Optional[list[str]] = None,
    ) -> AccountValueResult:
        """Get total value of a Polymarket wallet (cash + positions).

        Combines:
        - On-chain USDC.e balance (cash/collateral) via RpcClient
        - Positions value from Data API GET /value

        Args:
            wallet: Wallet address (0x...).
            market: Optional market filter for positions value (same as Data API).

        Returns:
            AccountValueResult with cash_usdc, positions_value_usdc, total_usdc.
        """
        wallet = wallet.strip()
        wallet_masked = mask_address(wallet)

        cash_usdc = await self._rpc.get_usdc_e_balance(wallet)
        value_items = await self._data_api.get_positions_value(wallet, market=market)

        positions_value = Decimal("0")
        for item in value_items:
            val = item.get("value")
            if val is not None:
                try:
                    positions_value += Decimal(str(val))
                except (TypeError, ValueError):
                    pass

        total_usdc = cash_usdc + positions_value

        self._logger.info(
            "account_value_computed",
            wallet_masked=wallet_masked,
            cash_usdc=float(cash_usdc),
            positions_value_usdc=float(positions_value),
            total_usdc=float(total_usdc),
        )

        return AccountValueResult(
            wallet=wallet,
            cash_usdc=cash_usdc,
            positions_value_usdc=positions_value,
            total_usdc=total_usdc,
        )
