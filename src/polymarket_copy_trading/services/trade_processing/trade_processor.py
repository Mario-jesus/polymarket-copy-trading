# -*- coding: utf-8 -*-
"""Service that processes trade messages from the queue (log + optional notifications)."""

from __future__ import annotations

import structlog
from typing import Any, Callable, Optional

from polymarket_copy_trading.queue.messages import QueueMessage
from polymarket_copy_trading.services.tracking_trader.trade_dto import DataApiTradeDTO
from polymarket_copy_trading.utils.validation import mask_address


class TradeProcessorService:
    """Processes each trade message: logs and optionally sends a notification."""

    def __init__(
        self,
        *,
        get_logger: Callable[[str], Any] = structlog.get_logger,
        logger_name: Optional[str] = None,
    ) -> None:
        """Initialize the processor.

        Args:
            get_logger: Logger factory (injected).
            logger_name: Optional logger name (defaults to class name).
        """
        self._logger = get_logger(logger_name or self.__class__.__name__)

    async def process(self, message: QueueMessage[DataApiTradeDTO]) -> None:
        """Process a single trade message: log and optionally notify.

        Args:
            message: Queue message with trade payload and metadata (e.g. wallet, is_snapshot).
        """
        trade = message.payload
        meta = message.metadata or {}
        wallet = meta.get("wallet", "")
        is_snapshot = meta.get("is_snapshot", False)

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
