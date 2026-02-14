"""Application event bus (bubus). Singleton instance for publish/subscribe."""

from __future__ import annotations

from bubus import EventBus  # type: ignore[import-untyped]

_event_bus: EventBus | None = None


def get_event_bus() -> EventBus:
    """Return the application event bus singleton. Created on first call."""
    global _event_bus
    if _event_bus is None:
        _event_bus = EventBus(
            name="PolymarketCopyTrading",
            max_history_size=100,
            wal_path=None,
        )
    return _event_bus


def set_event_bus(bus: EventBus) -> None:
    """Set the event bus instance (e.g. for testing or DI). None resets to lazy default."""
    global _event_bus
    _event_bus = bus
