# -*- coding: utf-8 -*-
"""Polymarket Gamma API client (markets by condition_id)."""

from __future__ import annotations

import structlog
from typing import TYPE_CHECKING, Any, Callable, Dict, List, Optional, cast
from structlog.contextvars import bound_contextvars

from polymarket_copy_trading.config import Settings

if TYPE_CHECKING:
    from .http import AsyncHttpClient


class GammaApiClient:
    """Client for Polymarket Gamma API (e.g. /markets by condition_ids)."""

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
            settings: Application settings (uses settings.api.gamma_host,
                settings.tracking.gamma_batch_size).
            get_logger: Logger factory (injected) with default of structlog.get_logger.
            logger_name: Optional logger name (defaults to class name).
        """
        self._http = http_client
        self._settings = settings
        self._logger = get_logger(logger_name or self.__class__.__name__)

    def _base_url(self) -> str:
        return self._settings.api.gamma_host.rstrip("/")

    async def get_markets_by_condition_ids(
        self,
        condition_ids: List[str],
    ) -> Dict[str, Dict[str, Any]]:
        """Resolve condition_ids to market info (market_id, slug, title).

        Batches requests using settings.tracking.gamma_batch_size.
        Tries params condition_ids first, then condition_ids[] if the
        response is empty.

        Args:
            condition_ids: List of 0x condition IDs (66 chars).

        Returns:
            Dict mapping condition_id -> {market_id, slug, title}.
        """
        uniq: list[str] = []
        seen: set[str] = set()
        for cid in condition_ids:
            if self.__is_condition_id(cid) and cid not in seen:
                seen.add(cid)
                uniq.append(cid)

        if not uniq:
            return {}

        batch_size = max(1, self._settings.tracking.gamma_batch_size)
        out: Dict[str, Dict[str, Any]] = {}

        for i in range(0, len(uniq), batch_size):
            batch = uniq[i : i + batch_size]
            batch_index = i // batch_size
            with bound_contextvars(
                gamma_api_batch_index=batch_index,
                gamma_api_batch_size=len(batch),
                gamma_api_condition_ids_count=len(uniq),
            ):
                try:
                    self._logger.debug("gamma_api_batch_request")
                    arr = await self._fetch_one_batch(batch)
                except Exception as e:
                    self._logger.exception(
                        "gamma_api_batch_failed",
                        error_type=type(e).__name__,
                        error_message=str(e),
                    )
                    arr = []

            for m in self.__as_list_of_dicts(arr):
                cid = m.get("condition_id") or m.get("conditionId")
                if not cid or not self.__is_condition_id(cid):
                    continue
                out[str(cid)] = {
                    "market_id": m.get("id"),
                    "slug": m.get("slug") or "",
                    "title": m.get("title") or m.get("question") or "",
                }

        return out

    async def _fetch_one_batch(self, condition_ids: List[str]) -> List[Dict[str, Any]]:
        url = f"{self._base_url()}/markets"
        params: Dict[str, Any] = {
            "condition_ids": condition_ids,
            "limit": max(1, len(condition_ids)),
            "offset": 0,
        }
        data = await self._http.get(url, params=params)
        arr = self.__as_list_of_dicts(data)
        if arr:
            return arr
        self._logger.debug(
            "gamma_api_batch_empty",
            gamma_api_fallback_params="condition_ids[]",
        )
        params2: Dict[str, Any] = {
            "condition_ids[]": condition_ids,
            "limit": max(1, len(condition_ids)),
            "offset": 0,
        }
        data2 = await self._http.get(url, params=params2)
        return self.__as_list_of_dicts(data2)

    @staticmethod
    def __is_condition_id(x: Any) -> bool:
        if not isinstance(x, str):
            return False
        s = x.strip()
        return s.startswith("0x") and len(s) == 66

    @staticmethod
    def __as_list_of_dicts(x: Any) -> List[Dict[str, Any]]:
        if not isinstance(x, list):
            return []
        result: List[Dict[str, Any]] = []
        for v in cast(List[Any], x):
            if isinstance(v, dict):
                result.append(cast(Dict[str, Any], v))
        return result
