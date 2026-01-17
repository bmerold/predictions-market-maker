"""Tests for MarketDataHandler."""

from datetime import UTC, datetime, timedelta
from decimal import Decimal
from unittest.mock import Mock

import pytest

from market_maker.domain.errors import StaleDataError
from market_maker.domain.events import BookUpdate, BookUpdateType, EventType
from market_maker.domain.market_data import OrderBook, PriceLevel
from market_maker.domain.types import Price, Quantity
from market_maker.market_data.handler import MarketDataHandler


class TestMarketDataHandler:
    """Tests for MarketDataHandler."""

    @pytest.fixture
    def handler(self) -> MarketDataHandler:
        """Create a handler with default settings."""
        return MarketDataHandler(stale_threshold_seconds=5.0)

    def test_create_handler(self, handler: MarketDataHandler) -> None:
        """Handler initializes with settings."""
        assert handler.stale_threshold_seconds == 5.0

    def test_subscribe_market(self, handler: MarketDataHandler) -> None:
        """Handler tracks subscribed markets."""
        handler.subscribe("KXBTC-25JAN17-100000")
        assert handler.is_subscribed("KXBTC-25JAN17-100000")
        assert not handler.is_subscribed("OTHER-MARKET")

    def test_unsubscribe_market(self, handler: MarketDataHandler) -> None:
        """Handler removes unsubscribed markets."""
        handler.subscribe("KXBTC-25JAN17-100000")
        handler.unsubscribe("KXBTC-25JAN17-100000")
        assert not handler.is_subscribed("KXBTC-25JAN17-100000")

    def test_process_update_creates_book(self, handler: MarketDataHandler) -> None:
        """Handler creates book builder for new market."""
        handler.subscribe("KXBTC-25JAN17-100000")

        snapshot = BookUpdate(
            event_type=EventType.BOOK_UPDATE,
            timestamp=datetime.now(UTC),
            market_id="KXBTC-25JAN17-100000",
            update_type=BookUpdateType.SNAPSHOT,
            yes_bids=[PriceLevel(Price(Decimal("0.45")), Quantity(100))],
            yes_asks=[PriceLevel(Price(Decimal("0.47")), Quantity(150))],
        )

        handler.process_update(snapshot)

        book = handler.get_book("KXBTC-25JAN17-100000")
        assert book is not None
        assert book.best_bid().price.value == Decimal("0.45")

    def test_process_update_unsubscribed_ignored(self, handler: MarketDataHandler) -> None:
        """Updates for unsubscribed markets are ignored."""
        snapshot = BookUpdate(
            event_type=EventType.BOOK_UPDATE,
            timestamp=datetime.now(UTC),
            market_id="KXBTC-25JAN17-100000",
            update_type=BookUpdateType.SNAPSHOT,
            yes_bids=[PriceLevel(Price(Decimal("0.45")), Quantity(100))],
            yes_asks=[PriceLevel(Price(Decimal("0.47")), Quantity(150))],
        )

        handler.process_update(snapshot)

        # Not subscribed, so no book
        assert handler.get_book("KXBTC-25JAN17-100000") is None

    def test_get_book_none_if_no_data(self, handler: MarketDataHandler) -> None:
        """get_book returns None if no data received."""
        handler.subscribe("KXBTC-25JAN17-100000")
        assert handler.get_book("KXBTC-25JAN17-100000") is None

    def test_is_stale_no_data(self, handler: MarketDataHandler) -> None:
        """is_stale returns True if no data received."""
        handler.subscribe("KXBTC-25JAN17-100000")
        assert handler.is_stale("KXBTC-25JAN17-100000")

    def test_is_stale_fresh_data(self, handler: MarketDataHandler) -> None:
        """is_stale returns False for fresh data."""
        handler.subscribe("KXBTC-25JAN17-100000")

        snapshot = BookUpdate(
            event_type=EventType.BOOK_UPDATE,
            timestamp=datetime.now(UTC),
            market_id="KXBTC-25JAN17-100000",
            update_type=BookUpdateType.SNAPSHOT,
            yes_bids=[PriceLevel(Price(Decimal("0.45")), Quantity(100))],
            yes_asks=[PriceLevel(Price(Decimal("0.47")), Quantity(150))],
        )
        handler.process_update(snapshot)

        assert not handler.is_stale("KXBTC-25JAN17-100000")

    def test_is_stale_old_data(self, handler: MarketDataHandler) -> None:
        """is_stale returns True for old data."""
        handler.subscribe("KXBTC-25JAN17-100000")

        old_time = datetime.now(UTC) - timedelta(seconds=10)
        snapshot = BookUpdate(
            event_type=EventType.BOOK_UPDATE,
            timestamp=old_time,
            market_id="KXBTC-25JAN17-100000",
            update_type=BookUpdateType.SNAPSHOT,
            yes_bids=[PriceLevel(Price(Decimal("0.45")), Quantity(100))],
            yes_asks=[PriceLevel(Price(Decimal("0.47")), Quantity(150))],
        )
        handler.process_update(snapshot)

        assert handler.is_stale("KXBTC-25JAN17-100000")

    def test_get_book_raises_if_stale(self, handler: MarketDataHandler) -> None:
        """get_book with check_stale=True raises for stale data."""
        handler.subscribe("KXBTC-25JAN17-100000")

        old_time = datetime.now(UTC) - timedelta(seconds=10)
        snapshot = BookUpdate(
            event_type=EventType.BOOK_UPDATE,
            timestamp=old_time,
            market_id="KXBTC-25JAN17-100000",
            update_type=BookUpdateType.SNAPSHOT,
            yes_bids=[PriceLevel(Price(Decimal("0.45")), Quantity(100))],
            yes_asks=[PriceLevel(Price(Decimal("0.47")), Quantity(150))],
        )
        handler.process_update(snapshot)

        with pytest.raises(StaleDataError):
            handler.get_book("KXBTC-25JAN17-100000", check_stale=True)

    def test_get_book_no_raise_if_check_stale_false(
        self, handler: MarketDataHandler
    ) -> None:
        """get_book with check_stale=False returns stale data."""
        handler.subscribe("KXBTC-25JAN17-100000")

        old_time = datetime.now(UTC) - timedelta(seconds=10)
        snapshot = BookUpdate(
            event_type=EventType.BOOK_UPDATE,
            timestamp=old_time,
            market_id="KXBTC-25JAN17-100000",
            update_type=BookUpdateType.SNAPSHOT,
            yes_bids=[PriceLevel(Price(Decimal("0.45")), Quantity(100))],
            yes_asks=[PriceLevel(Price(Decimal("0.47")), Quantity(150))],
        )
        handler.process_update(snapshot)

        # check_stale=False is default
        book = handler.get_book("KXBTC-25JAN17-100000")
        assert book is not None

    def test_subscribed_markets(self, handler: MarketDataHandler) -> None:
        """subscribed_markets returns list of subscribed markets."""
        handler.subscribe("MARKET1")
        handler.subscribe("MARKET2")

        markets = handler.subscribed_markets
        assert "MARKET1" in markets
        assert "MARKET2" in markets
        assert len(markets) == 2

    def test_event_callback(self, handler: MarketDataHandler) -> None:
        """Handler calls event callback on updates."""
        callback = Mock()
        handler.set_update_callback(callback)
        handler.subscribe("KXBTC-25JAN17-100000")

        snapshot = BookUpdate(
            event_type=EventType.BOOK_UPDATE,
            timestamp=datetime.now(UTC),
            market_id="KXBTC-25JAN17-100000",
            update_type=BookUpdateType.SNAPSHOT,
            yes_bids=[PriceLevel(Price(Decimal("0.45")), Quantity(100))],
            yes_asks=[PriceLevel(Price(Decimal("0.47")), Quantity(150))],
        )
        handler.process_update(snapshot)

        callback.assert_called_once()
        call_args = callback.call_args[0]
        assert call_args[0] == "KXBTC-25JAN17-100000"
        assert isinstance(call_args[1], OrderBook)

    def test_clear_market(self, handler: MarketDataHandler) -> None:
        """clear_market removes book data but keeps subscription."""
        handler.subscribe("KXBTC-25JAN17-100000")

        snapshot = BookUpdate(
            event_type=EventType.BOOK_UPDATE,
            timestamp=datetime.now(UTC),
            market_id="KXBTC-25JAN17-100000",
            update_type=BookUpdateType.SNAPSHOT,
            yes_bids=[PriceLevel(Price(Decimal("0.45")), Quantity(100))],
            yes_asks=[PriceLevel(Price(Decimal("0.47")), Quantity(150))],
        )
        handler.process_update(snapshot)

        handler.clear_market("KXBTC-25JAN17-100000")

        assert handler.is_subscribed("KXBTC-25JAN17-100000")
        assert handler.get_book("KXBTC-25JAN17-100000") is None
