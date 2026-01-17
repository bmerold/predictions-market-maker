"""Market data handler for managing multiple order books.

Coordinates order book builders, handles subscriptions, and monitors
data freshness.
"""

from __future__ import annotations

from collections.abc import Callable
from datetime import UTC, datetime

from market_maker.domain.errors import StaleDataError
from market_maker.domain.events import BookUpdate
from market_maker.domain.market_data import OrderBook
from market_maker.market_data.book_builder import OrderBookBuilder


class MarketDataHandler:
    """Manages market data for multiple markets.

    Handles subscriptions, processes updates, maintains order books,
    and monitors data freshness.
    """

    def __init__(self, stale_threshold_seconds: float = 5.0) -> None:
        """Initialize the handler.

        Args:
            stale_threshold_seconds: Data older than this is considered stale
        """
        self.stale_threshold_seconds = stale_threshold_seconds
        self._subscriptions: set[str] = set()
        self._builders: dict[str, OrderBookBuilder] = {}
        self._update_callback: Callable[[str, OrderBook], None] | None = None

    def subscribe(self, market_id: str) -> None:
        """Subscribe to a market.

        Args:
            market_id: Market to subscribe to
        """
        self._subscriptions.add(market_id)
        if market_id not in self._builders:
            self._builders[market_id] = OrderBookBuilder(market_id)

    def unsubscribe(self, market_id: str) -> None:
        """Unsubscribe from a market.

        Args:
            market_id: Market to unsubscribe from
        """
        self._subscriptions.discard(market_id)
        self._builders.pop(market_id, None)

    def is_subscribed(self, market_id: str) -> bool:
        """Check if subscribed to a market.

        Args:
            market_id: Market to check

        Returns:
            True if subscribed
        """
        return market_id in self._subscriptions

    @property
    def subscribed_markets(self) -> list[str]:
        """Return list of subscribed markets."""
        return list(self._subscriptions)

    def process_update(self, update: BookUpdate) -> None:
        """Process a book update.

        Args:
            update: The book update to process
        """
        market_id = update.market_id

        if market_id not in self._subscriptions:
            return

        builder = self._builders.get(market_id)
        if builder is None:
            builder = OrderBookBuilder(market_id)
            self._builders[market_id] = builder

        builder.apply_update(update)

        # Notify callback if set
        if self._update_callback is not None:
            book = builder.get_book()
            if book is not None:
                self._update_callback(market_id, book)

    def get_book(
        self,
        market_id: str,
        check_stale: bool = False,
    ) -> OrderBook | None:
        """Get the current order book for a market.

        Args:
            market_id: Market to get book for
            check_stale: If True, raise StaleDataError if data is stale

        Returns:
            Current OrderBook or None if no data

        Raises:
            StaleDataError: If check_stale=True and data is stale
        """
        builder = self._builders.get(market_id)
        if builder is None:
            return None

        if check_stale and self.is_stale(market_id):
            last_update = builder.last_update_time
            age = (
                (datetime.now(UTC) - last_update).total_seconds()
                if last_update
                else float("inf")
            )
            raise StaleDataError(
                f"Market data for {market_id} is stale",
                age_seconds=age,
                max_age_seconds=self.stale_threshold_seconds,
            )

        return builder.get_book()

    def is_stale(self, market_id: str) -> bool:
        """Check if data for a market is stale.

        Args:
            market_id: Market to check

        Returns:
            True if data is stale or no data received
        """
        builder = self._builders.get(market_id)
        if builder is None or not builder.has_book():
            return True

        last_update = builder.last_update_time
        if last_update is None:
            return True

        age = (datetime.now(UTC) - last_update).total_seconds()
        return age > self.stale_threshold_seconds

    def set_update_callback(
        self,
        callback: Callable[[str, OrderBook], None],
    ) -> None:
        """Set callback for order book updates.

        Args:
            callback: Function called with (market_id, book) on updates
        """
        self._update_callback = callback

    def clear_market(self, market_id: str) -> None:
        """Clear book data for a market, keeping subscription.

        Args:
            market_id: Market to clear
        """
        if market_id in self._builders:
            self._builders[market_id] = OrderBookBuilder(market_id)
