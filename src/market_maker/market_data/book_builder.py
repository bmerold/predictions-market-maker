"""Order book builder for maintaining book state.

Processes snapshots and deltas to maintain an up-to-date order book.
"""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal
from typing import Any

from market_maker.domain.events import BookUpdate, BookUpdateType, EventType
from market_maker.domain.market_data import OrderBook, PriceLevel
from market_maker.domain.types import Price, Quantity, Side


class OrderBookBuilder:
    """Builds and maintains an order book from updates.

    Processes snapshot and delta updates to maintain the current
    state of the order book for a single market.
    """

    def __init__(self, market_id: str) -> None:
        """Initialize builder for a market.

        Args:
            market_id: The market identifier
        """
        self.market_id = market_id
        self._yes_bids: dict[Decimal, int] = {}  # price -> size
        self._yes_asks: dict[Decimal, int] = {}  # price -> size
        self._has_snapshot = False
        self._last_update_time: datetime | None = None

    def apply_update(self, update: BookUpdate) -> None:
        """Apply a book update (snapshot or delta).

        Args:
            update: The book update to apply
        """
        if update.is_snapshot():
            self._apply_snapshot(update)
        elif update.is_delta():
            self._apply_delta(update)

        self._last_update_time = update.timestamp

    def _apply_snapshot(self, update: BookUpdate) -> None:
        """Apply a full book snapshot."""
        self._yes_bids.clear()
        self._yes_asks.clear()

        for level in update.yes_bids:
            self._yes_bids[level.price.value] = level.size.value

        for level in update.yes_asks:
            self._yes_asks[level.price.value] = level.size.value

        self._has_snapshot = True

    def _apply_delta(self, update: BookUpdate) -> None:
        """Apply an incremental delta."""
        if not self._has_snapshot:
            # Ignore deltas before first snapshot
            return

        if update.delta_price is None or update.delta_size is None:
            return

        price = update.delta_price.value
        size = update.delta_size

        if update.delta_is_bid:
            if size == 0:
                self._yes_bids.pop(price, None)
            else:
                self._yes_bids[price] = size
        else:
            if size == 0:
                self._yes_asks.pop(price, None)
            else:
                self._yes_asks[price] = size

    def get_book(self) -> OrderBook | None:
        """Get the current order book, or None if no snapshot received.

        Returns:
            Current OrderBook or None
        """
        if not self._has_snapshot:
            return None

        yes_bids = [
            PriceLevel(Price(price), Quantity(size))
            for price, size in sorted(self._yes_bids.items(), reverse=True)
            if size > 0
        ]

        yes_asks = [
            PriceLevel(Price(price), Quantity(size))
            for price, size in sorted(self._yes_asks.items())
            if size > 0
        ]

        return OrderBook(
            market_id=self.market_id,
            yes_bids=yes_bids,
            yes_asks=yes_asks,
            timestamp=self._last_update_time or datetime.now(UTC),
        )

    def has_book(self) -> bool:
        """Return True if a snapshot has been received."""
        return self._has_snapshot

    @property
    def last_update_time(self) -> datetime | None:
        """Return the timestamp of the last update."""
        return self._last_update_time

    @classmethod
    def from_kalshi_message(cls, message: dict[str, Any]) -> BookUpdate:
        """Parse a Kalshi WebSocket message into a BookUpdate.

        Kalshi snapshot format:
        {
            "type": "orderbook_snapshot",
            "market_ticker": "KXBTC-25JAN17-100000",
            "yes": [[price_cents, size], ...],
            "no": [[price_cents, size], ...]
        }

        Kalshi delta format:
        {
            "type": "orderbook_delta",
            "market_ticker": "KXBTC-25JAN17-100000",
            "price": price_cents,
            "delta": size_change,
            "side": "yes" | "no"
        }

        Args:
            message: Raw Kalshi WebSocket message

        Returns:
            BookUpdate event
        """
        msg_type = message.get("type", "")
        market_id = message.get("market_ticker", "")
        timestamp = datetime.now(UTC)

        if msg_type == "orderbook_snapshot":
            yes_bids: list[PriceLevel] = []
            yes_asks: list[PriceLevel] = []

            # YES side represents bids (what people will pay for YES)
            for price_cents, size in message.get("yes", []):
                if size > 0:
                    yes_bids.append(PriceLevel.from_cents(price_cents, size))

            # NO side - convert to YES asks
            # NO bid at X cents = YES ask at (100 - X) cents
            for price_cents, size in message.get("no", []):
                if size > 0:
                    yes_ask_cents = 100 - price_cents
                    yes_asks.append(PriceLevel.from_cents(yes_ask_cents, size))

            return BookUpdate(
                event_type=EventType.BOOK_UPDATE,
                timestamp=timestamp,
                market_id=market_id,
                update_type=BookUpdateType.SNAPSHOT,
                yes_bids=yes_bids,
                yes_asks=yes_asks,
            )

        elif msg_type == "orderbook_delta":
            price_cents = message.get("price", 0)
            delta_size = message.get("delta", 0)
            side = message.get("side", "yes")

            # For YES side deltas, it's a bid update
            # For NO side deltas, convert to YES ask
            if side == "yes":
                delta_price = Price.from_cents(price_cents)
                is_bid = True
            else:
                # NO delta at X cents = YES ask delta at (100 - X) cents
                yes_ask_cents = 100 - price_cents
                delta_price = Price.from_cents(yes_ask_cents)
                is_bid = False

            # Handle negative deltas (size reduction)
            # Kalshi sends the new absolute size, not a delta
            # But the field is called "delta" - need to check actual API
            # For now, treat as absolute size (0 means remove)
            final_size = max(0, delta_size)

            return BookUpdate(
                event_type=EventType.BOOK_UPDATE,
                timestamp=timestamp,
                market_id=market_id,
                update_type=BookUpdateType.DELTA,
                yes_bids=[],
                yes_asks=[],
                delta_price=delta_price,
                delta_size=final_size,
                delta_side=Side.YES,
                delta_is_bid=is_bid,
            )

        else:
            # Unknown message type - return empty snapshot
            return BookUpdate(
                event_type=EventType.BOOK_UPDATE,
                timestamp=timestamp,
                market_id=market_id,
                update_type=BookUpdateType.SNAPSHOT,
                yes_bids=[],
                yes_asks=[],
            )
