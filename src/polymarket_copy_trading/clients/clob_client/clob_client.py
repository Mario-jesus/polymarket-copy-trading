# -*- coding: utf-8 -*-
"""Async facade for Polymarket CLOB (py_clob_client) with asyncio.to_thread.

Centralizes ClobClient construction from settings and runs all sync methods
in a thread pool so callers can use async/await without blocking the event loop.

API alignment: https://pypi.org/project/py-clob-client and project docs.
- Read-only (Level 0): get_ok, get_server_time, get_midpoint, get_price, get_order_book(s), get_simplified_markets.
- Trading (auth): set_api_creds, create_or_derive_api_creds, create_market_order, create_order, post_order,
    get_orders, cancel, cancel_all, get_balance_allowance, get_last_trade_price, get_trades.
"""

from __future__ import annotations

import asyncio
import structlog
from typing import TYPE_CHECKING, Any, Callable, Dict, List, Literal, Optional, cast

from py_clob_client.clob_types import SignedOrder, OrderBookSummary, OrderType # type: ignore[import-untyped]

from polymarket_copy_trading.config import Settings
from polymarket_copy_trading.clients.clob_client.schema import TradeSchema

if TYPE_CHECKING:
    from py_clob_client.client import ClobClient  # type: ignore[import-untyped]
    from py_clob_client.clob_types import ( # type: ignore [import-untyped]
        ApiCreds,
        OpenOrderParams,
        BookParams,
        MarketOrderArgs,
        PartialCreateOrderOptions,
        OrderArgs,
        TradeParams,
        BalanceAllowanceParams,
    )


def _build_sync_client(settings: Settings) -> "ClobClient":
    """Build a sync ClobClient from settings.

    Args:
        settings: Application settings.
    
    Raises:
        MissingRequiredConfigError: If POLYMARKET__PRIVATE_KEY, POLYMARKET__FUNDER, POLYMARKET__API_KEY, POLYMARKET__API_SECRET, or POLYMARKET__API_PASSPHRASE is not set.
    """
    from py_clob_client.client import ClobClient, ApiCreds # type: ignore[import-untyped]

    pm = settings.polymarket
    HOST = pm.clob_host
    CHAIN_ID = pm.chain_id
    SIGNATURE_TYPE = pm.signature_type
    PRIVATE_KEY = pm.private_key
    API_KEY = pm.api_key
    API_SECRET = pm.api_secret
    API_PASSPHRASE = pm.api_passphrase
    FUNDER = pm.funder

    return ClobClient(
        host=HOST,
        chain_id=CHAIN_ID,
        key=PRIVATE_KEY,
        creds=ApiCreds(
            api_key=API_KEY,
            api_secret=API_SECRET,
            api_passphrase=API_PASSPHRASE
        ),
        signature_type=SIGNATURE_TYPE,
        funder=FUNDER,
    )


class AsyncClobClient:
    """Async wrapper around py_clob_client.ClobClient. All methods run via asyncio.to_thread."""

    def __init__(
        self,
        settings: Settings,
        *,
        sync_client: Optional["ClobClient"] = None,
        get_logger: Callable[[str], Any] = structlog.get_logger,
        logger_name: Optional[str] = None,
    ) -> None:
        """Initialize from settings or an existing sync ClobClient.

        Args:
            settings: Application settings (used if sync_client is None).
            sync_client: Optional pre-built ClobClient (e.g. from notebooks). If None, builds from settings.
            get_logger: Logger factory (injected) with default of structlog.get_logger.
            logger_name: Optional logger name (defaults to class name).
        """
        self._settings = settings
        if sync_client is not None:
            self._client = sync_client
        else:
            self._client = _build_sync_client(settings)
        self._logger = get_logger(logger_name or self.__class__.__name__)

    @property
    def sync_client(self) -> "ClobClient":
        """Access the underlying sync ClobClient for advanced or one-off calls."""
        return self._client

    async def _run[T](self, fn: Callable[..., T], *args: Any, **kwargs: Any) -> T:
        """Run a sync call in a thread. Use for any py_clob_client method."""
        return await asyncio.to_thread(fn, *args, **kwargs)

    async def run_sync(self, method_name: str, *args: Any, **kwargs: Any) -> Any:
        """Run an arbitrary sync method of the underlying ClobClient in a thread.

        Example: await clob.run_sync(\"cancel_order\", order_id)
        """
        fn = getattr(self._client, method_name)
        return await self._run(fn, *args, **kwargs)

    # --- Credentials (run in thread in case of I/O) ---

    async def create_or_derive_api_creds(self) -> "ApiCreds":
        """Create or derive API credentials. Returns ApiCreds."""
        return await self._run(self._client.create_or_derive_api_creds)

    def set_api_creds(self, creds: "ApiCreds") -> None:
        """Set API credentials on the client (sync; no I/O in typical usage)."""
        self._client.set_api_creds(creds)

    async def ensure_api_creds(self) -> None:
        """Ensure API creds are set; create/derive and set if needed. Safe to call multiple times."""
        creds = await self.create_or_derive_api_creds()
        self.set_api_creds(creds)

    # --- Orders ---

    async def get_orders(self, params: Optional["OpenOrderParams"] = None) -> List[Any]:
        """Fetch orders. Pass OpenOrderParams() for open orders (doc: get_orders(OpenOrderParams()))."""
        if params is None:
            return cast(List[Any], await self._run(self._client.get_orders))
        return cast(List[Any], await self._run(self._client.get_orders, params))

    async def get_order_book(self, token_id: str) -> "OrderBookSummary":
        """Get order book for a token id (read-only)."""
        return await self._run(cast(Callable[[str], OrderBookSummary], self._client.get_order_book), str(token_id).strip())

    async def get_order_books(self, params_list: List["BookParams"]) -> List["OrderBookSummary"]:
        """Get multiple order books (e.g. [BookParams(token_id=...)]). Read-only."""
        return await self._run(self._client.get_order_books, params_list)

    async def get_midpoint(self, token_id: str) -> Optional[str]:
        """Get midpoint price for token (read-only)."""
        midpoint = await self._run(cast(Callable[[str], Any], self._client.get_midpoint), str(token_id).strip())
        if isinstance(midpoint, dict):
            return cast(Dict[str, Any], midpoint).get("mid", None)
        return None

    async def get_price(self, token_id: str, side: Literal["BUY", "SELL"] = "BUY") -> Optional[str]:
        """Get price for token and side (read-only). side: 'BUY' or 'SELL'."""
        response = await self._run(cast(Callable[[str, Literal["BUY", "SELL"]], Any], self._client.get_price), str(token_id).strip(), side)
        if isinstance(response, dict):
            return cast(Dict[str, Any], response).get("price", None)
        return None

    async def create_market_order(self, order_args: MarketOrderArgs, options: Optional["PartialCreateOrderOptions"] = None) -> "SignedOrder":
        """Create a signed market order (MarketOrderArgs). Returns signed order."""
        return await self._run(self._client.create_market_order, order_args, options)

    async def create_order(self, order_args: OrderArgs, options: Optional["PartialCreateOrderOptions"] = None) -> "SignedOrder":
        """Create a signed limit order (OrderArgs). Returns signed order."""
        return await self._run(self._client.create_order, order_args, options)

    async def post_order(self, signed_order: "SignedOrder", order_type: OrderType, post_only: bool = False) -> Optional[Dict[str, Any]]:
        """Post a signed order (e.g. OrderType.FOK, OrderType.FAK, OrderType.GTC)."""
        response = await self._run(cast(Callable[[SignedOrder, OrderType, bool], Any], self._client.post_order), signed_order, order_type, post_only)
        if isinstance(response, dict):
            return cast(Dict[str, Any], response)
        return None

    async def cancel(self, order_id: str) -> Optional[Dict[str, Any]]:
        """Cancel a single order by id."""
        response = await self._run(cast(Callable[[str], Any], self._client.cancel), order_id)
        if isinstance(response, dict):
            return cast(Dict[str, Any], response)
        return None

    async def cancel_all(self) -> Optional[Dict[str, Any]]:
        """Cancel all open orders."""
        response = await self._run(self._client.cancel_all)
        if isinstance(response, dict):
            return cast(Dict[str, Any], response)
        return None

    # --- Read-only (no auth): health and markets ---

    async def get_ok(self) -> str:
        """Health check (read-only, no auth). Returns "OK" if successful."""
        return await self._run(self._client.get_ok)

    async def get_server_time(self) -> int:
        """Server time (read-only, no auth)."""
        server_time = await self._run(self._client.get_server_time)
        return int(server_time)

    async def get_simplified_markets(self) -> Optional[Dict[str, Any]]:
        """Get simplified markets (read-only). Returns dict with 'data' key."""
        response = await self._run(self._client.get_simplified_markets)
        if isinstance(response, dict):
            return cast(Dict[str, Any], response)
        return None

    async def get_fee_rate_bps(self, token_id: str) -> int:
        """Get the fee rate in basis points for a token."""
        response = await self._run(self._client.get_fee_rate_bps, str(token_id).strip())
        return int(response or 0)

    # --- User trades (requires auth) ---

    async def get_last_trade_price(self, token_id: str) -> Optional[Dict[str, Any]]:
        """Get last trade price for token (requires auth)."""
        response = await self._run(self._client.get_last_trade_price, str(token_id).strip()) # type: ignore [arg-type]
        if isinstance(response, dict):
            return cast(Dict[str, Any], response)
        return None

    async def get_trades(self, params: Optional["TradeParams"] = None) -> List["TradeSchema"]:
        """Get user trades (requires auth)."""
        response = cast(Any, await self._run(self._client.get_trades, params))
        if isinstance(response, list) and len(cast(List[Any], response)) > 0 and isinstance(response[0], dict):
            return cast(List[TradeSchema], response)
        return []

    # --- Balance / allowance (requires auth) ---

    async def get_balance_allowance(self, params: "BalanceAllowanceParams") -> Any:
        """Get balance/allowance (e.g. BalanceAllowanceParams with asset_type=AssetType.COLLATERAL)."""
        return await self._run(self._client.get_balance_allowance, params)
