"""Trade tracking service (polling)."""

from __future__ import annotations

import asyncio
from collections.abc import Callable
from typing import TYPE_CHECKING, Any, cast

import structlog

from polymarket_copy_trading.models.seen_trade import SeenTrade
from polymarket_copy_trading.queue import QueueMessage
from polymarket_copy_trading.services.tracking_trader.trade_dto import (
    DataApiTradeDTO,
)
from polymarket_copy_trading.utils.dedupe import trade_key
from polymarket_copy_trading.utils.validation import is_hex_address, mask_address

if TYPE_CHECKING:
    from polymarket_copy_trading.clients.data_api import DataApiClient
    from polymarket_copy_trading.config import Settings
    from polymarket_copy_trading.persistence.repositories.interfaces.seen_trade_repository import (
        ISeenTradeRepository,
    )
    from polymarket_copy_trading.queue import IAsyncQueue


class TradeTracker:
    """Tracks a wallet's new Polymarket trades via polling (Data API only)."""

    def __init__(
        self,
        settings: Settings,
        data_api: DataApiClient,
        queue: IAsyncQueue[QueueMessage[DataApiTradeDTO]],
        seen_trade_repository: ISeenTradeRepository,
        *,
        get_logger: Callable[[str], Any] = structlog.get_logger,
        logger_name: str | None = None,
    ) -> None:
        """Initialize the tracker.

        Args:
            settings: Application settings (uses settings.tracking).
            data_api: Data API client (injected).
            queue: Async queue for new trades (injected).
            seen_trade_repository: Repository for deduplication (in-memory or DB).
            get_logger: Logger factory (injected) with default of structlog.get_logger.
            logger_name: Optional logger name (defaults to class name).
        """
        self._data_api = data_api
        self._settings = settings
        self._queue = queue
        self._seen_repo = seen_trade_repository
        self._logger = get_logger(logger_name or self.__class__.__name__)

    async def track(
        self,
        wallet: str,
        *,
        poll_seconds: float | None = None,
        limit: int | None = None,
    ) -> None:
        """Poll for new trades and push them to the queue.

        First poll establishes a baseline (seen_trade_repository). Subsequent polls
        push only trades whose key was not seen before. Stop with Ctrl+C.

        Args:
            wallet: 0x wallet address (42 chars).
            poll_seconds: Polling interval; default from settings.tracking.poll_seconds.
            limit: Trades per poll; default from settings.tracking.trades_limit.
        """
        if not is_hex_address(wallet):
            raise ValueError("wallet must be a valid 0x wallet address (42 chars)")

        tr = self._settings.tracking
        poll_seconds = poll_seconds if poll_seconds is not None else tr.poll_seconds
        limit = limit if limit is not None else tr.trades_limit
        if poll_seconds <= 0:
            poll_seconds = 1.0
        if limit <= 0:
            limit = 10

        # Baseline fetch: mark all current trades as seen
        latest = await self._data_api.get_trades(wallet, limit=limit, offset=0)
        baseline = [SeenTrade.create(wallet, trade_key(cast(dict[str, Any], t))) for t in latest]
        if baseline:
            await self._seen_repo.add_batch(baseline)

        wallet_masked = mask_address(wallet)
        self._logger.debug(
            "tracking_started",
            tracking_wallet_masked=wallet_masked,
            tracking_poll_seconds=poll_seconds,
            tracking_limit=limit,
        )
        self._logger.debug(
            "tracking_waiting_for_trades",
            tracking_wallet_masked=wallet_masked,
        )

        try:
            while True:
                await asyncio.sleep(poll_seconds)
                newest = await self._data_api.get_trades(wallet, limit=limit, offset=0)
                for t in reversed(newest):
                    t_dict = cast(dict[str, Any], t)
                    k = trade_key(t_dict)
                    if await self._seen_repo.contains(wallet, k):
                        continue
                    await self._seen_repo.add(SeenTrade.create(wallet, k))
                    trade = DataApiTradeDTO.from_response(t_dict)
                    self._logger.debug(
                        "tracking_new_trade",
                        tracking_wallet_masked=wallet_masked,
                        trade_timestamp=trade.timestamp,
                        trade_condition_id=trade.condition_id,
                        trade_outcome=trade.outcome,
                        trade_side=trade.side,
                        trade_price=trade.price,
                        trade_size=trade.size,
                        trade_transaction_hash=trade.transaction_hash,
                    )
                    await self._queue.put(
                        item=QueueMessage[DataApiTradeDTO].create(
                            payload=trade,
                            metadata={"wallet": wallet},
                        )
                    )
        except asyncio.CancelledError:
            self._logger.debug(
                "tracking_stopped",
                tracking_wallet_masked=wallet_masked,
                tracking_stop_reason="cancelled",
            )
            raise
        except KeyboardInterrupt:
            self._logger.debug(
                "tracking_stopped",
                tracking_wallet_masked=wallet_masked,
                tracking_stop_reason="keyboard_interrupt",
            )
        except Exception as e:
            self._logger.exception(
                "tracking_exception",
                tracking_wallet_masked=wallet_masked,
                tracking_exception_type=type(e).__name__,
                tracking_exception_message=str(e),
            )
            raise
