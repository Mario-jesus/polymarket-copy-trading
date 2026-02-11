# -*- coding: utf-8 -*-
"""Service that processes trade messages from the queue (log + optional post-tracking)."""

from __future__ import annotations

import structlog
from typing import Any, Callable, Optional, TYPE_CHECKING

from polymarket_copy_trading.queue.messages import QueueMessage
from polymarket_copy_trading.services.tracking_trader.trade_dto import DataApiTradeDTO
from polymarket_copy_trading.utils.validation import mask_address

if TYPE_CHECKING:
    from polymarket_copy_trading.services.trade_processing.post_tracking_engine import (
        PostTrackingEngine,
    )


class TradeProcessorService:
    """Processes each trade message: applies post-tracking rule (if engine set) and logs."""

    def __init__(
        self,
        *,
        post_tracking_engine: Optional["PostTrackingEngine"] = None,
        get_logger: Callable[[str], Any] = structlog.get_logger,
        logger_name: Optional[str] = None,
    ) -> None:
        """Initialize the processor.

        Args:
            post_tracking_engine: Optional; if set, ledger is updated per BUY/SELL before logging.
            get_logger: Logger factory (injected).
            logger_name: Optional logger name (defaults to class name).
        """
        self._post_tracking_engine = post_tracking_engine
        self._logger = get_logger(logger_name or self.__class__.__name__)

    async def process(self, message: QueueMessage[DataApiTradeDTO]) -> None:
        """Process a single trade message: apply post-tracking (if engine set), then log.

        Args:
            message: Queue message with trade payload and metadata (e.g. wallet, is_snapshot).
        """
        trade = message.payload
        meta = message.metadata or {}
        wallet = meta.get("wallet", "")
        is_snapshot = meta.get("is_snapshot", False)

        if self._post_tracking_engine is not None and wallet and not is_snapshot:
            self._post_tracking_engine.apply_trade(wallet, trade)

        self._logger.info(
            "trade_processed",
            message_id=str(message.id),
            trade_timestamp=trade.timestamp,
            trade_condition_id=trade.condition_id,
            trade_outcome=trade.outcome,
            trade_side=trade.side,
            trade_price=trade.price,
            trade_size=trade.size,
            trade_transaction_hash=trade.transaction_hash,
            wallet_masked=mask_address(wallet) if wallet else None,
            is_snapshot=is_snapshot,
        )
