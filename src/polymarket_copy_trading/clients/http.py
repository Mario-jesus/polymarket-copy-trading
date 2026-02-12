# -*- coding: utf-8 -*-
"""Async HTTP client with retries and rate-limit handling."""

from __future__ import annotations

import asyncio
import random
import uuid
import aiohttp
import structlog
from typing import Any, Callable, Dict, Optional
from structlog.contextvars import bound_contextvars

from polymarket_copy_trading.config import Settings
from polymarket_copy_trading.exceptions import PolymarketAPIError


class AsyncHttpClient:
    """Async HTTP client for Polymarket APIs with retries and 429 handling.

    Injects Settings and optionally an aiohttp.ClientSession. If no session
    is provided, one is created and must be closed via aclose() or used
    as an async context manager.
    """

    def __init__(
        self,
        settings: Settings,
        *,
        session: Optional[aiohttp.ClientSession] = None,
        get_logger: Callable[[str], Any] = structlog.get_logger,
        logger_name: Optional[str] = None,
    ) -> None:
        """Initialize the client.

        Args:
            settings: Configuration (timeout, max_retries, etc.).
            session: Optional shared aiohttp session. If None, the client
                creates and owns a session (call aclose() when done).
            get_logger: Logger factory (injected) with default of structlog.get_logger.
            logger_name: Optional logger name (defaults to class name).
        """
        self._settings = settings
        self._session = session
        self._owns_session = session is None
        self._logger = get_logger(logger_name or self.__class__.__name__)

    async def _get_session(self) -> aiohttp.ClientSession:
        if self._session is None or self._session.closed:
            timeout = aiohttp.ClientTimeout(total=self._settings.api.timeout_seconds)
            self._session = aiohttp.ClientSession(timeout=timeout)
        return self._session

    async def aclose(self) -> None:
        """Close the session if this client owns it."""
        if self._owns_session and self._session is not None and not self._session.closed:
            await self._session.close()
            self._session = None

    async def __aenter__(self) -> AsyncHttpClient:
        return self

    async def __aexit__(self, *args: Any) -> None:
        await self.aclose()

    def _backoff_delay(self, attempt: int) -> float:
        """Exponential backoff with jitter, capped at 4 seconds."""
        base = min(4.0, 0.25 * (2**attempt))
        return base + random.uniform(0.0, 0.15)

    async def get(
        self,
        url: str,
        *,
        params: Optional[Dict[str, Any]] = None,
    ) -> Any:
        """Perform a GET request and return JSON. Retries on failure and on 429.

        Args:
            url: Full URL to request.
            params: Optional query parameters.

        Returns:
            Parsed JSON response (dict or list).

        Raises:
            RateLimitError: If 429 is returned and retries are exhausted.
            PolymarketAPIError: If the request fails after all retries.
        """
        params = params or {}
        request_id = uuid.uuid4().hex[:12]
        max_retries = self._settings.api.max_retries
        last_error: Optional[Exception] = None

        with bound_contextvars(
            http_url=url,
            http_request_id=request_id,
            http_max_retries=max_retries,
        ):
            for attempt in range(max_retries):
                with bound_contextvars(http_attempt=attempt + 1):
                    try:
                        session = await self._get_session()
                        async with session.get(url, params=params) as response:
                            if response.status == 429:
                                retry_after: Optional[float] = None
                                header = response.headers.get("Retry-After")
                                if header:
                                    try:
                                        retry_after = float(header)
                                    except ValueError:
                                        pass
                                self._logger.warning(
                                    "http_get_rate_limited",
                                    http_status_code=429,
                                    http_retry_after_seconds=retry_after,
                                )
                                if retry_after is not None and retry_after > 0:
                                    await asyncio.sleep(retry_after)
                                else:
                                    await asyncio.sleep(self._backoff_delay(attempt))
                                continue

                            response.raise_for_status()
                            return await response.json()
                    except aiohttp.ClientResponseError as e:
                        last_error = e
                        self._logger.debug(
                            "http_get_retry",
                            error_type=type(e).__name__,
                            error_message=str(e),
                            http_status_code=getattr(e, "status", None),
                        )
                        await asyncio.sleep(self._backoff_delay(attempt))
                    except (aiohttp.ClientError, asyncio.TimeoutError) as e:
                        last_error = e
                        self._logger.debug(
                            "http_get_retry",
                            error_type=type(e).__name__,
                            error_message=str(e),
                        )
                        await asyncio.sleep(self._backoff_delay(attempt))

            status_code = (
                getattr(last_error, "status", None)
                if isinstance(last_error, aiohttp.ClientResponseError)
                else None
            )
            self._logger.exception(
                "http_get_failed",
                http_status_code=status_code,
                http_attempts=max_retries,
                error_type=type(last_error).__name__ if last_error else None,
                error_message=str(last_error) if last_error else None,
            )
            if isinstance(last_error, aiohttp.ClientResponseError):
                raise PolymarketAPIError(
                    f"GET failed after {max_retries} retries: {url}",
                    url=url,
                    status_code=getattr(last_error, "status", None),
                    cause=last_error,
                ) from last_error
            raise PolymarketAPIError(
                f"GET failed after {max_retries} retries: {url}",
                url=url,
                cause=last_error,
            ) from last_error

    async def post(
        self,
        url: str,
        *,
        json: Optional[Dict[str, Any]] = None,
    ) -> Any:
        """Perform a POST request with JSON body and return JSON. Retries on failure.

        Args:
            url: Full URL to request.
            json: Optional JSON-serializable body.

        Returns:
            Parsed JSON response (dict or list).

        Raises:
            PolymarketAPIError: If the request fails after all retries.
        """
        payload = json or {}
        request_id = uuid.uuid4().hex[:12]
        max_retries = self._settings.api.max_retries
        last_error: Optional[Exception] = None

        with bound_contextvars(
            http_url=url,
            http_request_id=request_id,
            http_max_retries=max_retries,
        ):
            for attempt in range(max_retries):
                with bound_contextvars(http_attempt=attempt + 1):
                    try:
                        session = await self._get_session()
                        async with session.post(url, json=payload) as response:
                            response.raise_for_status()
                            return await response.json()
                    except aiohttp.ClientResponseError as e:
                        last_error = e
                        self._logger.debug(
                            "http_post_retry",
                            error_type=type(e).__name__,
                            error_message=str(e),
                            http_status_code=getattr(e, "status", None),
                        )
                        await asyncio.sleep(self._backoff_delay(attempt))
                    except (aiohttp.ClientError, asyncio.TimeoutError) as e:
                        last_error = e
                        self._logger.debug(
                            "http_post_retry",
                            error_type=type(e).__name__,
                            error_message=str(e),
                        )
                        await asyncio.sleep(self._backoff_delay(attempt))

            status_code = (
                getattr(last_error, "status", None)
                if isinstance(last_error, aiohttp.ClientResponseError)
                else None
            )
            self._logger.exception(
                "http_post_failed",
                http_status_code=status_code,
                http_attempts=max_retries,
                error_type=type(last_error).__name__ if last_error else None,
                error_message=str(last_error) if last_error else None,
            )
            if isinstance(last_error, aiohttp.ClientResponseError):
                raise PolymarketAPIError(
                    f"POST failed after {max_retries} retries: {url}",
                    url=url,
                    status_code=getattr(last_error, "status", None),
                    cause=last_error,
                ) from last_error
            raise PolymarketAPIError(
                f"POST failed after {max_retries} retries: {url}",
                url=url,
                cause=last_error,
            ) from last_error
