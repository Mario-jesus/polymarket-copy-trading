"""Polygon RPC client for on-chain reads (eth_call, ERC-20 balances)."""

from __future__ import annotations

from collections.abc import Callable
from decimal import Decimal, getcontext
from typing import TYPE_CHECKING, Any, cast

import structlog

from polymarket_copy_trading.utils.validation import mask_address

if TYPE_CHECKING:
    from polymarket_copy_trading.clients.http import AsyncHttpClient
    from polymarket_copy_trading.config import Settings

# Set decimal precision to 18
getcontext().prec = 18

# ERC-20 selectors (bytes4(keccak256(...)))
SELECTOR_DECIMALS = "0x313ce567"
SELECTOR_BALANCE_OF = "0x70a08231"


def _normalize_address(addr: str) -> str:
    """Return lowercase hex address without 0x prefix (for calldata)."""
    s = (addr or "").strip().lower()
    if s.startswith("0x"):
        s = s[2:]
    return s


class RpcClient:
    """Client for Polygon JSON-RPC (eth_call). Used for on-chain balance reads (e.g. USDC.e)."""

    def __init__(
        self,
        http_client: AsyncHttpClient,
        settings: Settings,
        *,
        get_logger: Callable[[str], Any] = structlog.get_logger,
        logger_name: str | None = None,
    ) -> None:
        """Initialize the RPC client.

        Args:
            http_client: HTTP client for POST requests (JSON-RPC).
            settings: Configuration (uses settings.api.polygon_rpc_url, polygon_usdc_e_address).
            get_logger: Logger factory (injected).
            logger_name: Optional logger name (defaults to class name).
        """
        self._http = http_client
        self._settings = settings
        self._logger = get_logger(logger_name or self.__class__.__name__)

    def _rpc_url(self) -> str:
        return self._settings.api.polygon_rpc_url.rstrip("/")

    async def eth_call(self, to: str, data: str, block: str = "latest") -> str:
        """Perform eth_call (read-only contract call).

        Args:
            to: Contract address (0x...).
            data: Hex-encoded calldata (with 0x prefix).
            block: Block tag (default "latest").

        Returns:
            Hex-encoded result (e.g. "0x...").

        Raises:
            PolymarketAPIError: If the RPC request fails.
            ValueError: If the RPC response contains an error.
        """
        to_norm = to.strip()
        if not to_norm.startswith("0x"):
            to_norm = "0x" + to_norm
        payload = {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "eth_call",
            "params": [{"to": to_norm, "data": data}, block],
        }
        response = await self._http.post(self._rpc_url(), json=payload)
        if not isinstance(response, dict):
            raise ValueError(f"Unexpected RPC response type: {type(response)}")
        resp_dict = cast(dict[str, Any], response)
        if "error" in resp_dict:
            err = resp_dict["error"]
            if isinstance(err, dict):
                err_d = cast(dict[str, Any], err)
                msg = str(err_d.get("message", err_d))
            else:
                msg = str(err)
            raise ValueError(f"RPC error: {msg}")
        result = resp_dict.get("result")
        return str(result) if result is not None else "0x0"

    async def get_erc20_decimals(self, token_address: str) -> int:
        """Get decimals of an ERC-20 token.

        Args:
            token_address: Token contract address (0x...).

        Returns:
            Number of decimals (e.g. 6 for USDC).
        """
        raw = await self.eth_call(token_address, SELECTOR_DECIMALS)
        return int(raw, 16)

    async def get_erc20_balance_raw(self, token_address: str, owner_address: str) -> int:
        """Get raw (unscaled) ERC-20 balance of owner.

        Args:
            token_address: Token contract address (0x...).
            owner_address: Wallet address (0x...).

        Returns:
            Balance in smallest units (e.g. 6 decimals for USDC).
        """
        owner_hex = _normalize_address(owner_address)
        if len(owner_hex) != 40:
            raise ValueError(f"Invalid address length: {owner_address!r}")
        # balanceOf(address): selector + uint256 (padded address, 32 bytes)
        data = SELECTOR_BALANCE_OF + "0" * 24 + owner_hex
        raw = await self.eth_call(token_address, data)
        return int(raw, 16)

    async def get_erc20_balance(
        self,
        token_address: str,
        owner_address: str,
        *,
        decimals: int | None = None,
    ) -> Decimal:
        """Get human-readable ERC-20 balance of owner.

        Args:
            token_address: Token contract address (0x...).
            owner_address: Wallet address (0x...).
            decimals: If provided, use this; otherwise fetch from contract.

        Returns:
            Balance as Decimal (e.g. 39.972491 for USDC.e).
        """
        if decimals is None:
            decimals = await self.get_erc20_decimals(token_address)
        raw = await self.get_erc20_balance_raw(token_address, owner_address)
        return Decimal(raw) / (10**decimals)

    async def get_usdc_e_balance(self, owner_address: str) -> Decimal:
        """Get USDC.e (bridged) balance on Polygon.

        Uses the configured USDC.e contract address (API__POLYGON_USDC_E_ADDRESS).

        Args:
            owner_address: Wallet address (0x...).

        Returns:
            Balance in USDC (e.g. 39.972491).
        """
        token = self._settings.api.polygon_usdc_e_address
        balance = await self.get_erc20_balance(token, owner_address)
        self._logger.debug(
            "rpc_usdc_e_balance",
            owner_masked=mask_address(owner_address),
            balance_usdc=float(balance),
        )
        return balance
