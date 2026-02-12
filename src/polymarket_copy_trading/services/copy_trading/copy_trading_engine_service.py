# -*- coding: utf-8 -*-
"""CopyTradingEngineService: orchestrates OpenPolicy, ClosePolicy and order execution.

After PostTrackingEngine updates the ledger, this service evaluates whether to open
or close positions and executes orders via MarketOrderExecutionService.
"""

from __future__ import annotations

import structlog
from datetime import datetime, timezone
from decimal import Decimal
from typing import TYPE_CHECKING, Any, Callable, Optional

from polymarket_copy_trading.models.bot_position import BotPosition
from polymarket_copy_trading.services.strategy import ClosePolicy, OpenPolicy
from polymarket_copy_trading.services.strategy.close_policy import ClosePolicyInput
from polymarket_copy_trading.services.strategy.open_policy import OpenPolicyInput
from polymarket_copy_trading.utils.validation import mask_address

if TYPE_CHECKING:
    from polymarket_copy_trading.clients.data_api import DataApiClient
    from polymarket_copy_trading.config import Settings
    from polymarket_copy_trading.models.tracking_ledger import TrackingLedger
    from polymarket_copy_trading.persistence.repositories.interfaces.bot_position_repository import (
        IBotPositionRepository,
    )
    from polymarket_copy_trading.persistence.repositories.interfaces.tracking_repository import (
        ITrackingRepository,
    )
    from polymarket_copy_trading.services.account_value import AccountValueService
    from polymarket_copy_trading.services.order_execution.market_order_execution import (
        MarketOrderExecutionService,
    )
    from polymarket_copy_trading.services.tracking_trader.trade_dto import DataApiTradeDTO


class CopyTradingEngineService:
    """Orchestrates open/close decisions and order execution based on ledger state."""

    def __init__(
        self,
        tracking_repository: "ITrackingRepository",
        bot_position_repository: "IBotPositionRepository",
        account_value_service: "AccountValueService",
        data_api: "DataApiClient",
        market_order_execution: "MarketOrderExecutionService",
        settings: "Settings",
        open_policy: Optional[OpenPolicy] = None,
        close_policy: Optional[ClosePolicy] = None,
        *,
        get_logger: Callable[[str], Any] = structlog.get_logger,
        logger_name: Optional[str] = None,
    ) -> None:
        """Initialize the copy trading engine.

        Args:
            tracking_repository: Ledger storage.
            bot_position_repository: Bot position storage.
            account_value_service: For tracked wallet account value (OpenPolicy % threshold).
            data_api: For trader positions (post_tracking_value_usdc via curPrice).
            market_order_execution: Order execution service.
            settings: Application settings (strategy, polymarket).
            open_policy: Optional; defaults to OpenPolicy().
            close_policy: Optional; defaults to ClosePolicy().
            get_logger: Logger factory.
            logger_name: Optional logger name.
        """
        self._tracking_repo = tracking_repository
        self._position_repo = bot_position_repository
        self._account_value = account_value_service
        self._data_api = data_api
        self._market_exec = market_order_execution
        self._settings = settings
        self._open_policy = open_policy or OpenPolicy()
        self._close_policy = close_policy or ClosePolicy()
        self._logger = get_logger(logger_name or self.__class__.__name__)

    async def evaluate_and_execute(
        self,
        wallet: str,
        trade: "DataApiTradeDTO",
        ledger: Optional["TrackingLedger"],
    ) -> None:
        """Evaluate open/close policies and execute orders based on the trade and ledger.

        Called after PostTrackingEngine has applied the trade. Ledger is the updated
        ledger (or None if the trade was skipped).

        Args:
            wallet: Tracked wallet address.
            trade: The trade that was processed (BUY or SELL).
            ledger: Updated ledger for (wallet, asset), or None if trade was skipped.
        """
        if ledger is None or not wallet:
            return
        side = trade.side
        if side not in ("BUY", "SELL"):
            return
        asset = trade.asset and str(trade.asset).strip()
        if not asset:
            return

        if side == "BUY":
            await self._handle_buy(wallet, trade, ledger, asset)
        else:
            await self._handle_sell(wallet, trade, ledger, asset)

    async def _handle_buy(
        self,
        wallet: str,
        trade: "DataApiTradeDTO",
        ledger: "TrackingLedger",
        asset: str,
    ) -> None:
        """Evaluate OpenPolicy and open a position if allowed."""
        strategy = self._settings.strategy
        open_positions = self._position_repo.list_open_by_ledger(ledger.id)
        open_positions_count = len(open_positions)
        active_ledgers_count = self._count_active_ledgers(wallet)

        try:
            account_result = await self._account_value.get_total_account_value(wallet)
            account_total_value_usdc = account_result.total_usdc
        except Exception as e:
            self._logger.warning(
                "copy_engine_account_value_failed",
                wallet_masked=mask_address(wallet),
                asset=asset,
                error=str(e),
            )
            account_total_value_usdc = Decimal("0")

        post_tracking_value_usdc = await self._get_post_tracking_value_usdc(
            wallet, asset, ledger.post_tracking_shares
        )

        inp = OpenPolicyInput(
            ledger=ledger,
            open_positions_count=open_positions_count,
            active_ledgers_count=active_ledgers_count,
            account_total_value_usdc=account_total_value_usdc,
            post_tracking_value_usdc=post_tracking_value_usdc,
        )
        result = self._open_policy.should_open(inp, strategy)

        if not result.should_open:
            self._logger.debug(
                "copy_engine_open_skipped",
                wallet_masked=mask_address(wallet),
                asset=asset,
                reason=result.reason,
            )
            return

        amount_usdc = float(strategy.fixed_position_amount_usdc)
        exec_result = await self._market_exec.place_buy_usdc(
            token_id=asset,
            amount=amount_usdc,
        )
        if not exec_result.success:
            self._logger.warning(
                "copy_engine_buy_failed",
                wallet_masked=mask_address(wallet),
                asset=asset,
                error=exec_result.error,
            )
            return

        price = trade.price if trade.price and trade.price > 0 else None
        shares_held = (
            Decimal(str(amount_usdc / price))
            if price is not None
            else Decimal(str(amount_usdc))
        )
        if shares_held <= 0:
            shares_held = Decimal(str(amount_usdc))

        position = BotPosition.create(
            ledger_id=ledger.id,
            tracked_wallet=wallet,
            asset=asset,
            shares_held=shares_held,
            entry_price=Decimal(str(price)) if price else None,
            entry_cost_usdc=Decimal(str(amount_usdc)),
        )
        self._position_repo.save(position)

        ref_pt = ledger.close_stage_ref_post_tracking_shares
        if ref_pt is None:
            self._tracking_repo.update_close_stage_ref(
                wallet, asset, ledger.post_tracking_shares
            )

        self._logger.info(
            "copy_engine_position_opened",
            wallet_masked=mask_address(wallet),
            asset=asset,
            position_id=str(position.id),
            shares_held=float(shares_held),
            amount_usdc=amount_usdc,
            reason=result.reason,
        )

    async def _handle_sell(
        self,
        wallet: str,
        trade: "DataApiTradeDTO",
        ledger: "TrackingLedger",
        asset: str,
    ) -> None:
        """Evaluate ClosePolicy and close positions if required."""
        open_positions = self._position_repo.list_open_by_ledger(ledger.id)
        open_positions_count = len(open_positions)
        if open_positions_count == 0:
            return

        inp = ClosePolicyInput(
            ledger=ledger,
            open_positions_count=open_positions_count,
        )
        result = self._close_policy.positions_to_close(
            inp, self._settings.strategy
        )

        if result.positions_to_close <= 0:
            self._logger.debug(
                "copy_engine_close_skipped",
                wallet_masked=mask_address(wallet),
                asset=asset,
                reason=result.reason,
            )
            return

        n = min(result.positions_to_close, open_positions_count)
        to_close = open_positions[:n]
        closed_at = datetime.now(timezone.utc)

        for position in to_close:
            exec_result = await self._market_exec.place_sell_shares(
                token_id=asset,
                amount=float(position.shares_held),
            )
            self._position_repo.mark_closed(
                position.id,
                closed_at=closed_at,
                close_proceeds_usdc=None,
                close_fees=None,
            )
            if exec_result.success:
                self._logger.info(
                    "copy_engine_position_closed",
                    wallet_masked=mask_address(wallet),
                    asset=asset,
                    position_id=str(position.id),
                    shares_sold=float(position.shares_held),
                    reason=result.reason,
                )
            else:
                self._logger.warning(
                    "copy_engine_sell_failed_but_marked_closed",
                    wallet_masked=mask_address(wallet),
                    asset=asset,
                    position_id=str(position.id),
                    error=exec_result.error,
                )

        self._tracking_repo.update_close_stage_ref(
            wallet, asset, ledger.post_tracking_shares
        )

    def _count_active_ledgers(self, wallet: str) -> int:
        """Count ledgers that have at least one open position."""
        open_positions = self._position_repo.list_open_by_wallet(wallet)
        ledger_ids = {p.ledger_id for p in open_positions}
        return len(ledger_ids)

    async def _get_post_tracking_value_usdc(
        self,
        wallet: str,
        asset: str,
        post_tracking_shares: Decimal,
    ) -> Decimal:
        """Compute mark-to-market value of post_tracking_shares for the asset."""
        if post_tracking_shares <= 0:
            return Decimal("0")
        try:
            positions = await self._data_api.get_positions(user=wallet)
            for p in positions:
                if str(p.get("asset", "")).strip() == asset:
                    cur_price = p.get("curPrice")
                    if cur_price is not None:
                        try:
                            price = float(cur_price)
                            if price > 0:
                                return post_tracking_shares * Decimal(str(price))
                        except (TypeError, ValueError):
                            pass
                    break
        except Exception as e:
            self._logger.debug(
                "copy_engine_post_tracking_value_failed",
                wallet_masked=mask_address(wallet),
                asset=asset,
                error=str(e),
            )
        return Decimal("0")
