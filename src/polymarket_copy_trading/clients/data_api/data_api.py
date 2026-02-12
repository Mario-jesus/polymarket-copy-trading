# -*- coding: utf-8 -*-
"""Polymarket Data API client (public endpoints)."""

from __future__ import annotations

import structlog
from typing import TYPE_CHECKING, Any, Callable, Dict, List, Literal, Optional, cast
from structlog.contextvars import bound_contextvars

from polymarket_copy_trading.clients.data_api.schema import PositionSchema, TradeSchema, ValueSchema
from polymarket_copy_trading.config import Settings
from polymarket_copy_trading.utils.validation import mask_address

if TYPE_CHECKING:
    from polymarket_copy_trading.clients.http import AsyncHttpClient

PositionSortBy = Literal[
    "CURRENT", "INITIAL", "TOKENS", "CASHPNL", "PERCENTPNL",
    "TITLE", "RESOLVING", "PRICE", "AVGPRICE",
]
PositionSortDirection = Literal["ASC", "DESC"]


class DataApiClient:
    """Client for Polymarket Data API (e.g. /trades, /positions)."""

    def __init__(
        self,
        http_client: "AsyncHttpClient",
        settings: Settings,
        *,
        get_logger: Callable[[str], Any] = structlog.get_logger,
        logger_name: Optional[str] = None,
    ) -> None:
        """Initialize the client.

        Args:
            http_client: Async HTTP client (e.g. AsyncHttpClient).
            settings: Application settings (uses settings.api.data_api_host).
            get_logger: Logger factory (injected) with default of structlog.get_logger.
            logger_name: Optional logger name (defaults to class name).
        """
        self._http = http_client
        self._settings = settings
        self._logger = get_logger(logger_name or self.__class__.__name__)

    def _base_url(self) -> str:
        return self._settings.api.data_api_host.rstrip("/")

    async def get_trades(
        self,
        user: str,
        *,
        limit: int = 20,
        offset: int = 0,
    ) -> List[TradeSchema]:
        """Fetch latest trades for a user (most recent first).

        Args:
            user: Wallet address (0x...).
            limit: Number of trades to fetch.
            offset: Pagination offset.

        Returns:
            List of trade items from the Data API (Trade schema).
        """
        user_masked = mask_address(user)
        with bound_contextvars(
            data_api_user_masked=user_masked,
            data_api_limit=limit,
            data_api_offset=offset,
        ):
            url = f"{self._base_url()}/trades"
            params: Dict[str, Any] = {
                "user": user,
                "limit": limit,
                "offset": offset,
            }
            data = await self._http.get(url, params=params)
            if not isinstance(data, list):
                self._logger.warning(
                    "data_api_get_trades_non_list",
                    data_api_response_type=type(data).__name__,
                )
                return []
            result: List[TradeSchema] = []
            for x in cast(list[Any], data):
                if isinstance(x, dict):
                    result.append(cast(TradeSchema, x))
            return result

    async def get_positions(
        self,
        user: str,
        *,
        market: Optional[List[str]] = None,
        event_id: Optional[List[int]] = None,
        size_threshold: float = 1.0,
        redeemable: bool = False,
        mergeable: bool = False,
        limit: int = 100,
        offset: int = 0,
        sort_by: PositionSortBy = "TOKENS",
        sort_direction: PositionSortDirection = "DESC",
        title: Optional[str] = None,
    ) -> list[PositionSchema]:
        """Get current positions for a user.

        API: GET /positions. Returns positions filtered by user and optional filters.
        market and eventId are mutually exclusive.

        Args:
            user: User address (0x..., required).
            market: Comma-separated condition IDs. Mutually exclusive with event_id.
            event_id: Comma-separated event IDs. Mutually exclusive with market.
            size_threshold: Minimum size (default 1, min 0).
            redeemable: Filter redeemable positions (default False).
            mergeable: Filter mergeable positions (default False).
            limit: Max results (default 100, 0-500).
            offset: Pagination offset (default 0, 0-10000).
            sort_by: CURRENT, INITIAL, TOKENS, CASHPNL, PERCENTPNL, TITLE,
                RESOLVING, PRICE, AVGPRICE (default TOKENS).
            sort_direction: ASC or DESC (default DESC).
            title: Filter by title substring (max 100 chars).

        Returns:
            List of position items from the Data API (Position schema).
        """
        if market is not None and event_id is not None:
            self._logger.warning(
                "data_api_get_positions_mutually_exclusive",
                message="market and event_id are mutually exclusive; ignoring event_id",
            )
            event_id = None
        # aiohttp/yarl only accept str, int, float in query params (no bool)
        params: Dict[str, Any] = {
            "user": user,
            "sizeThreshold": size_threshold,
            "redeemable": str(redeemable).lower(),
            "mergeable": str(mergeable).lower(),
            "limit": max(0, min(500, limit)),
            "offset": max(0, min(10000, offset)),
            "sortBy": sort_by,
            "sortDirection": sort_direction,
        }
        if market:
            params["market"] = ",".join(m.strip() for m in market)
        if event_id is not None and not market:
            params["eventId"] = ",".join(str(i) for i in event_id)
        if title is not None and len(title) <= 100:
            params["title"] = title

        user_masked = mask_address(user)
        with bound_contextvars(
            data_api_user_masked=user_masked,
            data_api_positions_limit=params["limit"],
            data_api_positions_offset=params["offset"],
        ):
            url = f"{self._base_url()}/positions"
            data = await self._http.get(url, params=params)
            if not isinstance(data, list):
                self._logger.warning(
                    "data_api_get_positions_non_list",
                    data_api_response_type=type(data).__name__,
                )
                return []
            result: List[PositionSchema] = []
            for x in cast(list[Any], data):
                if isinstance(x, dict):
                    result.append(cast(PositionSchema, x))
            return result

    async def get_positions_value(
        self,
        user: str,
        *,
        market: Optional[List[str]] = None,
    ) -> List[ValueSchema]:
        """Get value of a user's positions from the Data API (GET /value).

        Returns mark-to-market value of open positions. Does not include on-chain
        cash (USDC.e); for full account value use AccountValueService.

        API: GET /value

        Args:
            user: User address (0x..., required).
            market: Optional list of market ids (conditionIds) to filter by.

        Returns:
            List of Value items from the Data API (user, value).
        """
        params: Dict[str, Any] = {"user": user}
        if market:
            params["market"] = ",".join(m.strip() for m in market)

        user_masked = mask_address(user)
        with bound_contextvars(
            data_api_user_masked=user_masked,
        ):
            url = f"{self._base_url()}/value"
            data = await self._http.get(url, params=params)
            if not isinstance(data, list):
                self._logger.warning(
                    "data_api_get_positions_value_non_list",
                    data_api_response_type=type(data).__name__,
                )
                return []
            result: List[ValueSchema] = []
            for x in cast(list[Any], data):
                if isinstance(x, dict):
                    result.append(cast(ValueSchema, x))
            return result
