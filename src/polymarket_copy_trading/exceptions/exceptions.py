"""Custom exceptions for Polymarket API and tracking."""

from __future__ import annotations


class PolymarketError(Exception):
    """Base exception for Polymarket-related errors."""

    pass


class MissingRequiredConfigError(PolymarketError):
    """Raised when a required configuration value is missing."""

    pass


class PolymarketAPIError(PolymarketError):
    """Raised when a Polymarket API request fails after retries."""

    def __init__(
        self,
        message: str,
        *,
        url: str | None = None,
        status_code: int | None = None,
        cause: Exception | None = None,
    ) -> None:
        super().__init__(message)
        self.url = url
        self.status_code = status_code
        self.cause = cause


class RateLimitError(PolymarketAPIError):
    """Raised when the API returns HTTP 429 (Too Many Requests)."""

    def __init__(
        self,
        message: str = "Rate limit exceeded (429)",
        *,
        url: str | None = None,
        retry_after: float | None = None,
    ) -> None:
        super().__init__(message, url=url, status_code=429)
        self.retry_after = retry_after
