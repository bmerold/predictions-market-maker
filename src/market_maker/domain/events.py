"""Domain event types.

Events represent things that happen in the trading system and are
used for communication between components. All events are immutable.
"""

from __future__ import annotations

from datetime import datetime
from enum import Enum

from pydantic.dataclasses import dataclass

from market_maker.domain.market_data import PriceLevel
from market_maker.domain.orders import Fill, Order
from market_maker.domain.types import Price, Side


class EventType(str, Enum):
    """Types of events in the trading system."""

    BOOK_UPDATE = "book_update"
    FILL = "fill"
    ORDER_UPDATE = "order_update"


class BookUpdateType(str, Enum):
    """Type of order book update."""

    SNAPSHOT = "snapshot"  # Full book replacement
    DELTA = "delta"  # Incremental update


@dataclass(frozen=True)
class Event:
    """Base class for all events.

    All events have a type and timestamp.
    """

    event_type: EventType
    timestamp: datetime


@dataclass(frozen=True)
class BookUpdate(Event):
    """Order book update event.

    Can be either a full snapshot or an incremental delta.
    """

    market_id: str
    update_type: BookUpdateType
    yes_bids: list[PriceLevel]
    yes_asks: list[PriceLevel]
    # Delta-specific fields (only set for DELTA updates)
    delta_price: Price | None = None
    delta_size: int | None = None
    delta_side: Side | None = None
    delta_is_bid: bool | None = None

    def is_snapshot(self) -> bool:
        """Return True if this is a full snapshot."""
        return self.update_type == BookUpdateType.SNAPSHOT

    def is_delta(self) -> bool:
        """Return True if this is an incremental delta."""
        return self.update_type == BookUpdateType.DELTA


@dataclass(frozen=True)
class FillEvent(Event):
    """Fill notification event.

    Emitted when an order receives a fill (partial or complete).
    """

    fill: Fill

    @property
    def market_id(self) -> str:
        """Return the market ID from the fill."""
        return self.fill.market_id


@dataclass(frozen=True)
class OrderUpdate(Event):
    """Order state change event.

    Emitted when an order's status changes.
    """

    order: Order

    @property
    def market_id(self) -> str:
        """Return the market ID from the order."""
        return self.order.market_id
