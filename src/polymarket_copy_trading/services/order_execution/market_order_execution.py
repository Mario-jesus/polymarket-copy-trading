# -*- coding: utf-8 -*-
"""Order execution service."""

from __future__ import annotations

import math
import structlog
from typing import TYPE_CHECKING, Any, List, Literal, Optional, Callable

from py_clob_client.clob_types import MarketOrderArgs, OrderType  # type: ignore[import-untyped]
from py_clob_client.order_builder.constants import BUY, SELL  # type: ignore[import-untyped]
from py_clob_client.exceptions import PolyApiException  # type: ignore[import-untyped]

from polymarket_copy_trading.events.orders import OrderPlacedEvent
from polymarket_copy_trading.utils import mask_address
from polymarket_copy_trading.services.order_execution.dto import (
    OrderExecutionResult,
    OrderResponse,
)

if TYPE_CHECKING:
    from bubus import EventBus  # type: ignore[import-untyped]
    from polymarket_copy_trading.config import Settings
    from polymarket_copy_trading.clients import AsyncClobClient, DataApiClient


class MarketOrderExecutionService:
    """Market order execution service."""

    _event_bus: Optional["EventBus"]

    def __init__(
        self,
        settings: "Settings",
        clob_client: "AsyncClobClient",
        data_api: "DataApiClient",
        event_bus: Optional[Any] = None,
        *,
        get_logger: Callable[[str], Any] = structlog.get_logger,
        logger_name: Optional[str] = None,
    ) -> None:
        self._settings = settings
        self._client = clob_client
        self._data_api = data_api
        self._event_bus = event_bus
        self._logger = get_logger(logger_name or self.__class__.__name__)

    async def place_buy_usdc(
        self,
        token_id: str,
        amount: float,
        *,
        order_type: OrderType = OrderType.FOK, # type: ignore[arg-type]
        **kwargs: Any,
    ) -> "OrderExecutionResult[OrderResponse]":
        """Place a market BUY order for the given USDC amount.

        Args:
            token_id: CLOB token id (outcome token).
            amount: Amount in USDC to spend (e.g. 10.0 for $10).
            order_type: OrderType.FOK (fill-or-kill) or OrderType.FAK (fill-and-kill). Default FOK.
            **kwargs: Additional arguments for MarketOrderArgs.

        Returns:
            OrderExecutionResult object.
        """
        result = OrderExecutionResult[OrderResponse]()
        try:
            signed = await self._client.create_market_order(
                order_args=MarketOrderArgs(token_id=token_id.strip(), amount=float(amount), side=BUY, order_type=order_type, **kwargs)
            )
            resp = await self._client.post_order(signed, order_type)
            result.response = OrderResponse.from_response(resp)
            result.success = resp is not None and resp.get("success", False)

            self._logger.info(
                "place_buy_usdc_done",
                token_id=token_id,
                amount_usdc=amount,
                order_type=str(order_type),
                success=result.success,
                order_id=result.response.order_id,
                status=result.response.status,
            )
        except PolyApiException as e:
            error_msg = getattr(e, "error_msg", None)
            result.error = str(error_msg) if error_msg is not None else str(e)
            status_code = getattr(e, "status_code", None)
            self._logger.warning(
                "place_buy_usdc_failed",
                token_id=token_id,
                amount_usdc=amount,
                error_type=type(e).__name__,
                error_message=result.error,
                status_code=status_code,
            )
        except Exception as e:
            result.error = str(e)
            self._logger.exception(
                "place_buy_usdc_exception",
                token_id=token_id,
                amount_usdc=amount,
                error_type=type(e).__name__,
                error_message=str(e),
            )
        await self._dispatch_order_placed(token_id, "BUY", amount, "usdc", result)
        return result

    async def place_buy_shares(
        self,
        token_id: str,
        amount: float,
        *,
        order_type: OrderType = OrderType.FOK, # type: ignore[arg-type]
        **kwargs: Any,
    ) -> "OrderExecutionResult[OrderResponse]":
        """Place a market BUY order for the given number of shares.

        Fetches the current BUY price (best ask) via get_price, converts shares to USDC
        (rounded up to cents), then places a market buy with that USDC amount.

        Args:
            token_id: CLOB token id (outcome token).
            amount: Number of shares to buy.
            order_type: OrderType.FOK or OrderType.FAK. Default FOK.
            **kwargs: Additional arguments for MarketOrderArgs.

        Returns:
            OrderExecutionResult.
        """
        result = OrderExecutionResult[OrderResponse]()
        try:
            price_str = await self._client.get_price(token_id.strip(), "BUY")
            if not price_str:
                result.error = "No BUY price available for token (no liquidity or invalid token)"
                self._logger.warning(
                    "place_buy_shares_no_price",
                    token_id=token_id,
                    amount_shares=amount,
                )
                await self._dispatch_order_placed(token_id, "BUY", amount, "shares", result)
                return result
            price = float(price_str)
            if price <= 0:
                result.error = f"Invalid BUY price: {price_str}"
                await self._dispatch_order_placed(token_id, "BUY", amount, "shares", result)
                return result
            amount_usdc = self.__ceil_to_cents(price * amount)

            signed = await self._client.create_market_order(
                order_args=MarketOrderArgs(
                    token_id=token_id.strip(),
                    amount=amount_usdc,
                    side=BUY,
                    order_type=order_type,
                    **kwargs,
                )
            )
            resp = await self._client.post_order(signed, order_type)
            result.response = OrderResponse.from_response(resp)
            result.success = resp is not None and resp.get("success", False)

            self._logger.info(
                "place_buy_shares_done",
                token_id=token_id,
                amount_shares=amount,
                amount_usdc=amount_usdc,
                price=price,
                order_type=str(order_type),
                success=result.success,
                order_id=result.response.order_id,
                status=result.response.status,
            )
        except PolyApiException as e:
            error_msg = getattr(e, "error_msg", None)
            result.error = str(error_msg) if error_msg is not None else str(e)
            status_code = getattr(e, "status_code", None)
            self._logger.warning(
                "place_buy_shares_failed",
                token_id=token_id,
                amount_shares=amount,
                error_type=type(e).__name__,
                error_message=result.error,
                status_code=status_code,
            )
        except Exception as e:
            result.error = str(e)
            self._logger.exception(
                "place_buy_shares_exception",
                token_id=token_id,
                amount_shares=amount,
                error_type=type(e).__name__,
                error_message=str(e),
            )
        await self._dispatch_order_placed(token_id, "BUY", amount, "shares", result)
        return result

    async def place_buy_minimum(
        self,
        token_id: str,
        *,
        order_type: OrderType = OrderType.FOK,  # type: ignore[arg-type]
        **kwargs: Any,
    ) -> "OrderExecutionResult[OrderResponse]":
        """Place a market BUY for the configured minimum USDC amount (e.g. $1)."""
        minimum_amount = self._settings.order_execution.minimum_amount
        return await self.place_buy_usdc(
            token_id, minimum_amount, order_type=order_type, **kwargs
        )

    async def place_sell_usdc(
        self,
        token_id: str,
        amount: float,
        *,
        order_type: OrderType = OrderType.FOK, # type: ignore[arg-type]
        **kwargs: Any,
    ) -> "OrderExecutionResult[OrderResponse]":
        """Place a market SELL order to receive approximately the given USDC amount.

        Fetches the current SELL price (best bid) via get_price, converts USDC to shares
        (amount_usdc / price), then places a market sell for that many shares.

        Args:
            token_id: CLOB token id (outcome token).
            amount: Target USDC amount to receive from the sale (e.g. 10.0 for $10).
            order_type: OrderType.FOK or OrderType.FAK. Default FOK.
            **kwargs: Additional arguments for MarketOrderArgs.

        Returns:
            OrderExecutionResult.
        """
        result = OrderExecutionResult[OrderResponse]()
        try:
            price_str = await self._client.get_price(token_id.strip(), SELL)
            if not price_str:
                result.error = "No SELL price available for token (no liquidity or invalid token)"
                self._logger.warning(
                    "place_sell_usdc_no_price",
                    token_id=token_id,
                    amount_usdc=amount,
                )
                await self._dispatch_order_placed(token_id, "SELL", amount, "usdc", result)
                return result
            price = float(price_str)
            if price <= 0:
                result.error = f"Invalid SELL price: {price_str}"
                await self._dispatch_order_placed(token_id, "SELL", amount, "usdc", result)
                return result
            amount_shares = round(amount / price, 4)
            if amount_shares <= 0:
                result.error = f"Computed shares <= 0 (amount_usdc={amount}, price={price})"
                await self._dispatch_order_placed(token_id, "SELL", amount, "usdc", result)
                return result

            signed = await self._client.create_market_order(
                order_args=MarketOrderArgs(
                    token_id=token_id.strip(),
                    amount=amount_shares,
                    side=SELL,
                    order_type=order_type,
                    **kwargs,
                )
            )
            resp = await self._client.post_order(signed, order_type)
            result.response = OrderResponse.from_response(resp)
            result.success = resp is not None and resp.get("success", False)

            self._logger.info(
                "place_sell_usdc_done",
                token_id=token_id,
                amount_usdc=amount,
                amount_shares=amount_shares,
                price=price,
                order_type=str(order_type),
                success=result.success,
                order_id=result.response.order_id,
                status=result.response.status,
            )
        except PolyApiException as e:
            error_msg = getattr(e, "error_msg", None)
            result.error = str(error_msg) if error_msg is not None else str(e)
            status_code = getattr(e, "status_code", None)
            self._logger.warning(
                "place_sell_usdc_failed",
                token_id=token_id,
                amount_usdc=amount,
                error_type=type(e).__name__,
                error_message=result.error,
                status_code=status_code,
            )
        except Exception as e:
            result.error = str(e)
            self._logger.exception(
                "place_sell_usdc_exception",
                token_id=token_id,
                amount_usdc=amount,
                error_type=type(e).__name__,
                error_message=str(e),
            )
        await self._dispatch_order_placed(token_id, "SELL", amount, "usdc", result)
        return result

    async def place_sell_shares(
        self,
        token_id: str,
        amount: float,
        *,
        order_type: OrderType = OrderType.FOK, # type: ignore[arg-type]
        **kwargs: Any,
    ) -> "OrderExecutionResult[OrderResponse]":
        """Place a market SELL order for the given number of shares.

        Args:
            token_id: CLOB token id (outcome token).
            amount: Number of shares to sell.
            order_type: OrderType.FOK or OrderType.FAK. Default FOK.
            **kwargs: Additional arguments for MarketOrderArgs.

        Returns:
            OrderExecutionResult.
        """
        result = OrderExecutionResult[OrderResponse]()
        try:
            signed = await self._client.create_market_order(
                order_args=MarketOrderArgs(token_id=token_id.strip(), amount=float(amount), side=SELL, order_type=order_type, **kwargs)
            )
            resp = await self._client.post_order(signed, order_type)
            result.response = OrderResponse.from_response(resp)
            result.success = resp is not None and resp.get("success", False)

            self._logger.info(
                "place_sell_shares_done",
                token_id=token_id,
                amount_shares=amount,
                order_type=str(order_type),
                success=result.success,
                order_id=result.response.order_id,
                status=result.response.status,
            )
        except PolyApiException as e:
            error_msg = getattr(e, "error_msg", None)
            result.error = str(error_msg) if error_msg is not None else str(e)
            status_code = getattr(e, "status_code", None)
            self._logger.warning(
                "place_sell_shares_failed",
                token_id=token_id,
                amount_shares=amount,
                error_type=type(e).__name__,
                error_message=result.error,
                status_code=status_code,
            )
        except Exception as e:
            result.error = str(e)
            self._logger.exception(
                "place_sell_shares_exception",
                token_id=token_id,
                amount_shares=amount,
                error_type=type(e).__name__,
                error_message=str(e),
            )
        await self._dispatch_order_placed(token_id, "SELL", amount, "shares", result)
        return result

    async def close_full_position(
        self,
        token_id: str,
        *,
        order_type: OrderType = OrderType.FOK, # type: ignore[arg-type]
        **kwargs: Any,
    ) -> "OrderExecutionResult[OrderResponse]":
        """Close the full position for the given token by selling all shares.

        Fetches positions via Data API (get_positions), finds the position whose
        asset matches token_id, then places a market sell for position["size"] shares.
        Requires DataApiClient to be passed to the service constructor.

        Args:
            token_id: CLOB token id (outcome token / asset id).
            user: Wallet address to query positions for (0x...).
            order_type: OrderType.FOK or OrderType.FAK. Default FOK.
            **kwargs: Passed to place_sell_shares.

        Returns:
            OrderExecutionResult (or error if no data_api, no position, or size <= 0).
        """
        result = OrderExecutionResult[OrderResponse]()

        token_id = token_id.strip()
        user = self._settings.polymarket.funder

        try:
            positions = await self._data_api.get_positions(user=user)
            position = None
            for p in positions:
                asset = p.get("asset")
                if asset is None:
                    continue
                if str(asset).strip() == token_id:
                    position = p
                    break
            if position is None:
                result.error = f"No position found for token_id={token_id} and user={mask_address(user)}"
                self._logger.warning(
                    "close_full_position_not_found",
                    token_id=token_id,
                    user_masked=mask_address(user),
                )
                return result
            size = position.get("size")
            if size is None:
                result.error = f"Position has no 'size' for token_id={token_id}"
                return result
            try:
                size_f = float(size)
            except (TypeError, ValueError):
                result.error = f"Invalid position size: {size!r}"
                return result
            if size_f <= 0:
                result.error = f"Position size is not positive: {size_f}"
                return result

            return await self.place_sell_shares(
                token_id=token_id,
                amount=size_f,
                order_type=order_type,
                **kwargs,
            )
        except Exception as e:
            result.error = str(e)
            self._logger.exception(
                "close_full_position_exception",
                token_id=token_id,
                user_masked=mask_address(user),
                error_type=type(e).__name__,
                error_message=str(e),
            )
        return result

    async def close_all_positions(
        self,
        *,
        order_type: OrderType = OrderType.FOK, # type: ignore[arg-type]
        **kwargs: Any,
    ) -> "OrderExecutionResult[List[OrderResponse]]":
        """Close all positions for the given user.

        Fetches positions via Data API (get_positions), then sells all shares for each
        position (market sell per token). Requires DataApiClient to be passed to the
        service constructor.

        Args:
            user: Wallet address to query positions for (0x...).
            order_type: OrderType.FOK or OrderType.FAK. Default FOK.
            **kwargs: Passed to place_sell_shares for each position.

        Returns:
            OrderExecutionResult: success=True only if all positions were closed
            successfully (or there were no positions); error contains a summary if any failed.
        """
        result = OrderExecutionResult[List[OrderResponse]]()
        user = self._settings.polymarket.funder

        try:
            positions = await self._data_api.get_positions(user=user)
            to_close: list[tuple[str, float]] = []
            for p in positions:
                asset = p.get("asset")
                size = p.get("size")
                if asset is None or size is None:
                    continue
                try:
                    size_f = float(size)
                except (TypeError, ValueError):
                    continue
                if size_f <= 0:
                    continue
                to_close.append((str(asset).strip(), size_f))

            if not to_close:
                result.success = True
                self._logger.info(
                    "close_all_positions_done",
                    user_masked=mask_address(user),
                    closed_count=0,
                )
                return result

            errors: list[str] = []
            responses: List["OrderResponse"] = []
            closed = 0
            for token_id, size_f in to_close:
                single = await self.place_sell_shares(
                    token_id=token_id,
                    amount=size_f,
                    order_type=order_type,
                    **kwargs,
                )
                if single.success:
                    closed += 1
                    if single.response is not None:
                        responses.append(single.response)
                else:
                    errors.append(f"{mask_address(token_id)}: {single.error or 'unknown'}")

            result.success = len(errors) == 0
            result.response = responses
            if errors:
                result.error = "; ".join(errors)

            self._logger.info(
                "close_all_positions_done",
                user_masked=mask_address(user),
                closed_count=closed,
                total_count=len(to_close),
                failed_count=len(errors),
            )
        except Exception as e:
            result.error = str(e)
            self._logger.exception(
                "close_all_positions_exception",
                user_masked=mask_address(user),
                error_type=type(e).__name__,
                error_message=str(e),
            )
        return result

    @classmethod
    async def _dispatch_order_placed(
        cls,
        token_id: str,
        side: Literal["BUY", "SELL"],
        amount: float,
        amount_kind: Literal["usdc", "shares"],
        result: "OrderExecutionResult[OrderResponse]",
    ) -> None:
        """Emit OrderPlacedEvent on the event bus and wait until processing completes."""
        if cls._event_bus is None:
            return
        order_id = result.response.order_id if result.response else None
        status = result.response.status if result.response else None
        response_summary = result.response.to_dict() if result.response else None
        event = OrderPlacedEvent(
            token_id=token_id.strip(),
            side=side,
            amount=amount,
            amount_kind=amount_kind,
            success=result.success,
            order_id=order_id,
            error_msg=result.error,
            status=status,
            response_summary=response_summary,
        )
        dispatched = cls._event_bus.dispatch(event)
        await dispatched

    @staticmethod
    def __ceil_to_cents(value: float) -> float:
        """Round up to 2 decimal places (cents) to avoid underfill when converting shares to USDC."""
        return math.ceil(value * 100) / 100
