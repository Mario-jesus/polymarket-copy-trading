# -*- coding: utf-8 -*-
"""In-memory cache for Gamma API market lookups (condition_id -> market info)."""

from __future__ import annotations

import structlog
from typing import Any, Callable, Dict, List, Optional
from cachetools import LRUCache
from structlog.contextvars import bound_contextvars

from polymarket_copy_trading.clients.gamma_api import GammaApiClient


class GammaCache:
    """Cache for condition_id -> {market_id, slug, title}. Resolves only missing IDs.

    Uses cachetools.LRUCache so memory stays bounded when tracking many markets.
    """

    def __init__(
        self,
        gamma_client: GammaApiClient,
        *,
        maxsize: int = 2048,
        get_logger: Callable[[str], Any] = structlog.get_logger,
        logger_name: Optional[str] = None,
    ) -> None:
        """Initialize the cache.

        Args:
            gamma_client: Gamma API client (injected).
            maxsize: Maximum number of condition_ids to keep (LRU eviction).
            get_logger: Logger factory (injected) with default of structlog.get_logger.
            logger_name: Optional logger name (defaults to class name).
        """
        self._client = gamma_client
        self._cache: LRUCache[str, Dict[str, Any]] = LRUCache(maxsize=max(1, maxsize))
        self._logger = get_logger(logger_name or self.__class__.__name__)

    async def resolve(self, condition_ids: List[str]) -> None:
        """Fetch and cache market info for condition_ids that are not yet cached.

        Args:
            condition_ids: List of 0x condition IDs (66 chars).
        """
        missing = [cid for cid in condition_ids if cid not in self._cache]
        if not missing:
            return
        with bound_contextvars(
            gamma_cache_requested_count=len(condition_ids),
            gamma_cache_missing_count=len(missing),
        ):
            result = await self._client.get_markets_by_condition_ids(missing)
            for cid, info in result.items():
                self._cache[cid] = info
            self._logger.debug(
                "gamma_cache_resolve",
                gamma_cache_resolved_count=len(result),
            )

    def get(self, condition_id: str) -> Dict[str, Any]:
        """Return cached market info for a condition_id, or empty dict.

        Args:
            condition_id: 0x condition ID.

        Returns:
            Dict with keys market_id, slug, title (or {} if not cached).
        """
        return dict(self._cache.get(condition_id, {}))
