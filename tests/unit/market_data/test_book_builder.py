"""Tests for OrderBookBuilder."""

from datetime import UTC, datetime
from decimal import Decimal

import pytest

from market_maker.domain.events import BookUpdate, BookUpdateType, EventType
from market_maker.domain.market_data import OrderBook, PriceLevel
from market_maker.domain.types import Price, Quantity, Side
from market_maker.market_data.book_builder import OrderBookBuilder


class TestOrderBookBuilder:
    """Tests for OrderBookBuilder."""

    @pytest.fixture
    def builder(self) -> OrderBookBuilder:
        """Create a fresh builder."""
        return OrderBookBuilder(market_id="KXBTC-25JAN17-100000")

    def test_create_builder(self, builder: OrderBookBuilder) -> None:
        """Builder initializes with market_id."""
        assert builder.market_id == "KXBTC-25JAN17-100000"

    def test_empty_book_initially(self, builder: OrderBookBuilder) -> None:
        """Builder has no book before any updates."""
        assert builder.get_book() is None

    def test_apply_snapshot(self, builder: OrderBookBuilder) -> None:
        """Snapshot replaces entire book."""
        snapshot = BookUpdate(
            event_type=EventType.BOOK_UPDATE,
            timestamp=datetime.now(UTC),
            market_id="KXBTC-25JAN17-100000",
            update_type=BookUpdateType.SNAPSHOT,
            yes_bids=[
                PriceLevel(Price(Decimal("0.45")), Quantity(100)),
                PriceLevel(Price(Decimal("0.44")), Quantity(200)),
            ],
            yes_asks=[
                PriceLevel(Price(Decimal("0.47")), Quantity(150)),
                PriceLevel(Price(Decimal("0.48")), Quantity(100)),
            ],
        )

        builder.apply_update(snapshot)
        book = builder.get_book()

        assert book is not None
        assert len(book.yes_bids) == 2
        assert len(book.yes_asks) == 2
        assert book.best_bid().price.value == Decimal("0.45")
        assert book.best_ask().price.value == Decimal("0.47")

    def test_apply_delta_add_bid(self, builder: OrderBookBuilder) -> None:
        """Delta adds new bid level."""
        # First apply snapshot
        snapshot = BookUpdate(
            event_type=EventType.BOOK_UPDATE,
            timestamp=datetime.now(UTC),
            market_id="KXBTC-25JAN17-100000",
            update_type=BookUpdateType.SNAPSHOT,
            yes_bids=[PriceLevel(Price(Decimal("0.45")), Quantity(100))],
            yes_asks=[PriceLevel(Price(Decimal("0.47")), Quantity(150))],
        )
        builder.apply_update(snapshot)

        # Then apply delta to add a new bid
        delta = BookUpdate(
            event_type=EventType.BOOK_UPDATE,
            timestamp=datetime.now(UTC),
            market_id="KXBTC-25JAN17-100000",
            update_type=BookUpdateType.DELTA,
            yes_bids=[],
            yes_asks=[],
            delta_price=Price(Decimal("0.44")),
            delta_size=200,
            delta_side=Side.YES,
            delta_is_bid=True,
        )
        builder.apply_update(delta)

        book = builder.get_book()
        assert book is not None
        assert len(book.yes_bids) == 2
        # Best bid should still be 0.45
        assert book.best_bid().price.value == Decimal("0.45")

    def test_apply_delta_update_bid(self, builder: OrderBookBuilder) -> None:
        """Delta updates existing bid level."""
        snapshot = BookUpdate(
            event_type=EventType.BOOK_UPDATE,
            timestamp=datetime.now(UTC),
            market_id="KXBTC-25JAN17-100000",
            update_type=BookUpdateType.SNAPSHOT,
            yes_bids=[PriceLevel(Price(Decimal("0.45")), Quantity(100))],
            yes_asks=[PriceLevel(Price(Decimal("0.47")), Quantity(150))],
        )
        builder.apply_update(snapshot)

        # Delta to update the 0.45 bid to 150 size
        delta = BookUpdate(
            event_type=EventType.BOOK_UPDATE,
            timestamp=datetime.now(UTC),
            market_id="KXBTC-25JAN17-100000",
            update_type=BookUpdateType.DELTA,
            yes_bids=[],
            yes_asks=[],
            delta_price=Price(Decimal("0.45")),
            delta_size=150,
            delta_side=Side.YES,
            delta_is_bid=True,
        )
        builder.apply_update(delta)

        book = builder.get_book()
        assert book is not None
        assert len(book.yes_bids) == 1
        assert book.yes_bids[0].size.value == 150

    def test_apply_delta_remove_bid(self, builder: OrderBookBuilder) -> None:
        """Delta with size 0 removes bid level."""
        snapshot = BookUpdate(
            event_type=EventType.BOOK_UPDATE,
            timestamp=datetime.now(UTC),
            market_id="KXBTC-25JAN17-100000",
            update_type=BookUpdateType.SNAPSHOT,
            yes_bids=[
                PriceLevel(Price(Decimal("0.45")), Quantity(100)),
                PriceLevel(Price(Decimal("0.44")), Quantity(200)),
            ],
            yes_asks=[PriceLevel(Price(Decimal("0.47")), Quantity(150))],
        )
        builder.apply_update(snapshot)

        # Delta to remove the 0.45 bid
        delta = BookUpdate(
            event_type=EventType.BOOK_UPDATE,
            timestamp=datetime.now(UTC),
            market_id="KXBTC-25JAN17-100000",
            update_type=BookUpdateType.DELTA,
            yes_bids=[],
            yes_asks=[],
            delta_price=Price(Decimal("0.45")),
            delta_size=0,
            delta_side=Side.YES,
            delta_is_bid=True,
        )
        builder.apply_update(delta)

        book = builder.get_book()
        assert book is not None
        assert len(book.yes_bids) == 1
        assert book.best_bid().price.value == Decimal("0.44")

    def test_apply_delta_add_ask(self, builder: OrderBookBuilder) -> None:
        """Delta adds new ask level."""
        snapshot = BookUpdate(
            event_type=EventType.BOOK_UPDATE,
            timestamp=datetime.now(UTC),
            market_id="KXBTC-25JAN17-100000",
            update_type=BookUpdateType.SNAPSHOT,
            yes_bids=[PriceLevel(Price(Decimal("0.45")), Quantity(100))],
            yes_asks=[PriceLevel(Price(Decimal("0.47")), Quantity(150))],
        )
        builder.apply_update(snapshot)

        # Delta to add a new ask at 0.48
        delta = BookUpdate(
            event_type=EventType.BOOK_UPDATE,
            timestamp=datetime.now(UTC),
            market_id="KXBTC-25JAN17-100000",
            update_type=BookUpdateType.DELTA,
            yes_bids=[],
            yes_asks=[],
            delta_price=Price(Decimal("0.48")),
            delta_size=100,
            delta_side=Side.YES,
            delta_is_bid=False,
        )
        builder.apply_update(delta)

        book = builder.get_book()
        assert book is not None
        assert len(book.yes_asks) == 2
        assert book.best_ask().price.value == Decimal("0.47")

    def test_delta_before_snapshot_ignored(self, builder: OrderBookBuilder) -> None:
        """Deltas before any snapshot are ignored."""
        delta = BookUpdate(
            event_type=EventType.BOOK_UPDATE,
            timestamp=datetime.now(UTC),
            market_id="KXBTC-25JAN17-100000",
            update_type=BookUpdateType.DELTA,
            yes_bids=[],
            yes_asks=[],
            delta_price=Price(Decimal("0.45")),
            delta_size=100,
            delta_side=Side.YES,
            delta_is_bid=True,
        )
        builder.apply_update(delta)

        # Still no book
        assert builder.get_book() is None

    def test_new_snapshot_replaces_book(self, builder: OrderBookBuilder) -> None:
        """New snapshot completely replaces existing book."""
        snapshot1 = BookUpdate(
            event_type=EventType.BOOK_UPDATE,
            timestamp=datetime.now(UTC),
            market_id="KXBTC-25JAN17-100000",
            update_type=BookUpdateType.SNAPSHOT,
            yes_bids=[PriceLevel(Price(Decimal("0.45")), Quantity(100))],
            yes_asks=[PriceLevel(Price(Decimal("0.47")), Quantity(150))],
        )
        builder.apply_update(snapshot1)

        snapshot2 = BookUpdate(
            event_type=EventType.BOOK_UPDATE,
            timestamp=datetime.now(UTC),
            market_id="KXBTC-25JAN17-100000",
            update_type=BookUpdateType.SNAPSHOT,
            yes_bids=[PriceLevel(Price(Decimal("0.50")), Quantity(200))],
            yes_asks=[PriceLevel(Price(Decimal("0.52")), Quantity(250))],
        )
        builder.apply_update(snapshot2)

        book = builder.get_book()
        assert book is not None
        assert book.best_bid().price.value == Decimal("0.50")
        assert book.best_ask().price.value == Decimal("0.52")

    def test_last_update_timestamp(self, builder: OrderBookBuilder) -> None:
        """Builder tracks last update timestamp."""
        ts = datetime(2026, 1, 17, 12, 0, 0, tzinfo=UTC)
        snapshot = BookUpdate(
            event_type=EventType.BOOK_UPDATE,
            timestamp=ts,
            market_id="KXBTC-25JAN17-100000",
            update_type=BookUpdateType.SNAPSHOT,
            yes_bids=[PriceLevel(Price(Decimal("0.45")), Quantity(100))],
            yes_asks=[PriceLevel(Price(Decimal("0.47")), Quantity(150))],
        )
        builder.apply_update(snapshot)

        assert builder.last_update_time == ts

    def test_has_book(self, builder: OrderBookBuilder) -> None:
        """has_book returns True after snapshot."""
        assert not builder.has_book()

        snapshot = BookUpdate(
            event_type=EventType.BOOK_UPDATE,
            timestamp=datetime.now(UTC),
            market_id="KXBTC-25JAN17-100000",
            update_type=BookUpdateType.SNAPSHOT,
            yes_bids=[PriceLevel(Price(Decimal("0.45")), Quantity(100))],
            yes_asks=[PriceLevel(Price(Decimal("0.47")), Quantity(150))],
        )
        builder.apply_update(snapshot)

        assert builder.has_book()


class TestOrderBookBuilderFromKalshiFormat:
    """Tests for parsing Kalshi WebSocket format."""

    @pytest.fixture
    def builder(self) -> OrderBookBuilder:
        """Create a fresh builder."""
        return OrderBookBuilder(market_id="KXBTC-25JAN17-100000")

    def test_from_kalshi_snapshot(self, builder: OrderBookBuilder) -> None:
        """Parse Kalshi snapshot format."""
        kalshi_snapshot = {
            "type": "orderbook_snapshot",
            "market_ticker": "KXBTC-25JAN17-100000",
            "yes": [
                [45, 100],  # price in cents, size
                [44, 200],
            ],
            "no": [
                [56, 100],
                [57, 200],
            ],
        }

        update = OrderBookBuilder.from_kalshi_message(kalshi_snapshot)
        builder.apply_update(update)

        book = builder.get_book()
        assert book is not None
        assert book.best_bid().price.value == Decimal("0.45")
        # NO bids at 56 cents means YES asks at 44 cents
        # Actually for Kalshi: yes bids are the bid side, no is the ask side
        # Let me reconsider this...

    def test_from_kalshi_delta(self, builder: OrderBookBuilder) -> None:
        """Parse Kalshi delta format."""
        # First apply snapshot
        kalshi_snapshot = {
            "type": "orderbook_snapshot",
            "market_ticker": "KXBTC-25JAN17-100000",
            "yes": [[45, 100]],
            "no": [[56, 100]],
        }
        builder.apply_update(OrderBookBuilder.from_kalshi_message(kalshi_snapshot))

        # Then apply delta
        kalshi_delta = {
            "type": "orderbook_delta",
            "market_ticker": "KXBTC-25JAN17-100000",
            "price": 44,
            "delta": 200,
            "side": "yes",
        }

        update = OrderBookBuilder.from_kalshi_message(kalshi_delta)
        builder.apply_update(update)

        book = builder.get_book()
        assert book is not None
        # Should have 2 bid levels now
        assert len(book.yes_bids) == 2
