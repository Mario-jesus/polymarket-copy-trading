# -*- coding: utf-8 -*-
"""Polymarket Data API client (public endpoints)."""

from __future__ import annotations

import structlog
from typing import TYPE_CHECKING, Any, cast
from structlog.contextvars import bound_contextvars

from polymarket_copy_trading.config import Settings
from polymarket_copy_trading.utils.validation import mask_address

if TYPE_CHECKING:
    from .http import AsyncHttpClient


class DataApiClient:
    """Client for Polymarket Data API (e.g. /trades, /positions)."""

    def __init__(self, http_client: "AsyncHttpClient", settings: Settings) -> None:
        """Initialize the client.

        Args:
            http_client: Async HTTP client (e.g. AsyncHttpClient).
            settings: Application settings (uses settings.api.data_api_host).
        """
        self._http = http_client
        self._settings = settings
        self._logger = structlog.get_logger(self.__class__.__name__)

    def _base_url(self) -> str:
        return self._settings.api.data_api_host.rstrip("/")

    async def get_trades(
        self,
        user: str,
        *,
        limit: int = 20,
        offset: int = 0,
    ) -> list[dict[str, Any]]:
        """Fetch latest trades for a user (most recent first).

        Args:
            user: Wallet address (0x...).
            limit: Number of trades to fetch.
            offset: Pagination offset.

        Returns:
            List of trade dicts from the Data API.
        """
        user_masked = mask_address(user)
        with bound_contextvars(
            data_api_user_masked=user_masked,
            data_api_limit=limit,
            data_api_offset=offset,
        ):
            url = f"{self._base_url()}/trades"
            params: dict[str, Any] = {
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
            result: list[dict[str, Any]] = []
            for x in cast(list[Any], data):
                if isinstance(x, dict):
                    result.append(cast(dict[str, Any], x))
            return result
