# -*- coding: utf-8 -*-
"""Dependency injection container (dependency-injector)."""

from __future__ import annotations

from dependency_injector import containers, providers

from polymarket_copy_trading.config import Settings, get_settings
from polymarket_copy_trading.events.bus import get_event_bus
from polymarket_copy_trading.queue import InMemoryQueue, QueueMessage
from polymarket_copy_trading.clients.clob_client import AsyncClobClient
from polymarket_copy_trading.clients.data_api import DataApiClient
from polymarket_copy_trading.clients.http import AsyncHttpClient
from polymarket_copy_trading.clients.rcp_client import RpcClient
from polymarket_copy_trading.notifications.notification_manager import NotificationService
from polymarket_copy_trading.notifications.strategies.base import BaseNotificationStrategy
from polymarket_copy_trading.notifications.strategies.console import ConsoleNotifier
from polymarket_copy_trading.notifications.strategies.telegram import TelegramNotifier
from polymarket_copy_trading.notifications.stylers.notification_styler import EventNotificationStyler
from polymarket_copy_trading.persistence.repositories.in_memory import (
    InMemoryBotPositionRepository,
    InMemorySeenTradeRepository,
    InMemoryTrackingRepository,
    InMemoryTrackingSessionRepository,
)
from polymarket_copy_trading.services.copy_trading import CopyTradingEngineService
from polymarket_copy_trading.services.order_execution.market_order_execution import MarketOrderExecutionService
from polymarket_copy_trading.services.account_value import AccountValueService
from polymarket_copy_trading.services.snapshot import SnapshotBuilderService
from polymarket_copy_trading.services.tracking_trader import TradeTracker, DataApiTradeDTO
from polymarket_copy_trading.services.trade_processing import (
    PostTrackingEngine,
    TradeProcessorService,
)
from polymarket_copy_trading.consumers.trade_consumer import TradeConsumer


def _build_trade_queue(settings: Settings) -> InMemoryQueue[QueueMessage[DataApiTradeDTO]]:
    """Build the trade queue with size from settings."""
    return InMemoryQueue[QueueMessage[DataApiTradeDTO]](maxsize=settings.tracking.queue_size)


def _build_notification_notifiers(
    settings: Settings,
    styler: EventNotificationStyler,
) -> list[BaseNotificationStrategy]:
    notifiers: list[BaseNotificationStrategy] = []
    if settings.console.enabled:
        notifiers.append(ConsoleNotifier(settings=settings, styler=styler))
    if settings.telegram.enabled:
        notifiers.append(TelegramNotifier(settings=settings, styler=styler))
    return notifiers


class Container(containers.DeclarativeContainer):
    """Application container. Wires settings, HTTP client, API clients, cache, tracker."""

    config = providers.Callable(get_settings)

    http_client = providers.Singleton(
        AsyncHttpClient,
        settings=config,
    )

    data_api_client = providers.Singleton(
        DataApiClient,
        http_client=http_client,
        settings=config,
    )

    rpc_client = providers.Singleton(
        RpcClient,
        http_client=http_client,
        settings=config,
    )

    clob_client = providers.Singleton(
        AsyncClobClient,
        settings=config,
    )

    event_bus = providers.Callable(get_event_bus)

    market_order_execution_service = providers.Singleton(
        MarketOrderExecutionService,
        settings=config,
        clob_client=clob_client,
        data_api=data_api_client,
        event_bus=event_bus,
    )

    notification_styler = providers.Singleton(EventNotificationStyler)

    notification_service = providers.Singleton(
        NotificationService,
        notifiers=providers.Callable(_build_notification_notifiers, config, notification_styler),
    )

    trade_queue = providers.Singleton(_build_trade_queue, config)

    tracking_repository = providers.Singleton(InMemoryTrackingRepository)

    bot_position_repository = providers.Singleton(InMemoryBotPositionRepository)

    seen_trade_repository = providers.Singleton(InMemorySeenTradeRepository)

    tracking_session_repository = providers.Singleton(InMemoryTrackingSessionRepository)

    snapshot_builder_service = providers.Singleton(
        SnapshotBuilderService,
        data_api=data_api_client,
        tracking_repository=tracking_repository,
        tracking_session_repository=tracking_session_repository,
    )

    account_value_service = providers.Singleton(
        AccountValueService,
        rpc_client=rpc_client,
        data_api=data_api_client,
    )

    copy_trading_engine_service = providers.Singleton(
        CopyTradingEngineService,
        tracking_repository=tracking_repository,
        bot_position_repository=bot_position_repository,
        account_value_service=account_value_service,
        data_api=data_api_client,
        market_order_execution=market_order_execution_service,
        settings=config,
    )

    post_tracking_engine = providers.Singleton(
        PostTrackingEngine,
        tracking_repository=tracking_repository,
    )

    trade_processor_service = providers.Singleton(
        TradeProcessorService,
        post_tracking_engine=post_tracking_engine,
        copy_trading_engine=copy_trading_engine_service,
    )

    trade_consumer = providers.Singleton(
        TradeConsumer,
        queue=trade_queue,
        trade_processor=trade_processor_service,
    )

    trade_tracker = providers.Singleton(
        TradeTracker,
        settings=config,
        data_api=data_api_client,
        queue=trade_queue,
        seen_trade_repository=seen_trade_repository,
    )
