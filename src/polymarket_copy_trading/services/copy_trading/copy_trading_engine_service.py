# -*- coding: utf-8 -*-
"""CopyTradingEngineService: orchestrates OpenPolicy, ClosePolicy and order execution.

After PostTrackingEngine updates the ledger, this service evaluates whether to open
or close positions and executes orders via MarketOrderExecutionService.
"""

from __future__ import annotations

import structlog
from datetime import datetime, timezone
from decimal import Decimal
from typing import TYPE_CHECKING, Any, Callable, Optional, Literal

from polymarket_copy_trading.events.orders.copy_trade_events import (
    CopyTradeFailedEvent,
    CopyTradeOrderPlacedEvent,
)
from polymarket_copy_trading.models.bot_position import BotPosition
from polymarket_copy_trading.services.strategy import ClosePolicy, OpenPolicy
from polymarket_copy_trading.services.strategy.close_policy import ClosePolicyInput
from polymarket_copy_trading.services.strategy.open_policy import OpenPolicyInput
from polymarket_copy_trading.utils.validation import mask_address

if TYPE_CHECKING:
    from uuid import UUID

    from bubus import EventBus  # type: ignore[import-untyped]

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

    _event_bus: Optional["EventBus"] = None

    def __init__(
        self,
        tracking_repository: "ITrackingRepository",
        bot_position_repository: "IBotPositionRepository",
        account_value_service: "AccountValueService",
        data_api: "DataApiClient",
        market_order_execution: "MarketOrderExecutionService",
        settings: "Settings",
        event_bus: Optional[Any] = None,
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
            event_bus: Optional; if set, emits CopyTradeOrderPlacedEvent for OrderAnalysisWorker.
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
        self._event_bus = event_bus
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
        open_positions = await self._position_repo.list_open_by_ledger(ledger.id)
        open_positions_count = len(open_positions)
        active_ledgers_count = await self._count_active_ledgers(wallet)

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
            self._emit_order_failed(
                reason="order_placement_failed",
                position_id=None,
                order_id=getattr(exec_result.response, "order_id", None) or "",
                tracked_wallet=wallet,
                asset=asset,
                is_open=True,
                error_message=exec_result.error,
                amount=amount_usdc,
                amount_kind="usdc",
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
        await self._position_repo.save(position)
        resp = exec_result.response
        tx_hash = (resp.transactions_hashes[0] if resp and resp.transactions_hashes else None)
        self._emit_order_placed(
            order_id=resp.order_id if resp else None,
            position_id=position.id,
            tracked_wallet=wallet,
            asset=asset,
            is_open=True,
            amount=amount_usdc,
            amount_kind="usdc",
            success=exec_result.success,
            transaction_hash=tx_hash,
        )

        ref_pt = ledger.close_stage_ref_post_tracking_shares
        if ref_pt is None:
            await self._tracking_repo.update_close_stage_ref(
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
        open_positions = await self._position_repo.list_open_by_ledger(ledger.id)
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
            await self._position_repo.mark_closed(
                position.id,
                closed_at=closed_at,
                close_proceeds_usdc=None,
                close_fees=None,
            )
            resp = exec_result.response
            tx_hash = (resp.transactions_hashes[0] if resp and resp.transactions_hashes else None)
            self._emit_order_placed(
                order_id=resp.order_id if resp else None,
                position_id=position.id,
                tracked_wallet=wallet,
                asset=asset,
                is_open=False,
                amount=float(position.shares_held),
                amount_kind="shares",
                success=exec_result.success,
                transaction_hash=tx_hash,
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
                self._emit_order_failed(
                    reason="order_placement_failed",
                    position_id=position.id,
                    order_id=resp.order_id if resp else None,
                    tracked_wallet=wallet,
                    asset=asset,
                    is_open=False,
                    error_message=exec_result.error,
                    transaction_hash=tx_hash,
                    amount=float(position.shares_held),
                    amount_kind="shares",
                )

        await self._tracking_repo.update_close_stage_ref(
            wallet, asset, ledger.post_tracking_shares
        )

    def _emit_order_failed(
        self,
        reason: str,
        position_id: Optional["UUID"],
        order_id: Optional[str],
        tracked_wallet: str,
        asset: str,
        is_open: bool,
        error_message: Optional[str] = None,
        transaction_hash: Optional[str] = None,
        amount: Optional[float] = None,
        amount_kind: Optional[Literal["usdc", "shares"]] = None,
    ) -> None:
        """Emit CopyTradeFailedEvent for TradeFailedNotifier."""
        if self._event_bus is None:
            return
        event = CopyTradeFailedEvent(
            reason=reason,
            position_id=position_id,
            order_id=order_id or "",
            tracked_wallet=tracked_wallet,
            asset=asset,
            is_open=is_open,
            error_message=error_message,
            transaction_hash=transaction_hash,
            amount=amount,
            amount_kind=amount_kind,
        )
        self._event_bus.dispatch(event)

    def _emit_order_placed(
        self,
        order_id: Optional[str],
        position_id: "UUID",
        tracked_wallet: str,
        asset: str,
        is_open: bool,
        amount: float,
        amount_kind: Literal["usdc", "shares"],
        success: bool,
        transaction_hash: Optional[str] = None,
    ) -> None:
        """Emit CopyTradeOrderPlacedEvent for OrderAnalysisWorker."""
        if self._event_bus is None or not order_id:
            return
        event = CopyTradeOrderPlacedEvent(
            order_id=order_id,
            position_id=position_id,
            tracked_wallet=tracked_wallet,
            asset=asset,
            is_open=is_open,
            amount=amount,
            amount_kind=amount_kind,
            success=success,
            transaction_hash=transaction_hash,
        )
        self._event_bus.dispatch(event)

    async def _count_active_ledgers(self, wallet: str) -> int:
        """Count ledgers that have at least one open position."""
        open_positions = await self._position_repo.list_open_by_wallet(wallet)
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
