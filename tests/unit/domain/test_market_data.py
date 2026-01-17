"""Tests for market data domain models."""

from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest

from market_maker.domain.market_data import (
    MarketSnapshot,
    OrderBook,
    PriceLevel,
    Trade,
)
from market_maker.domain.types import Price, Quantity, Side


class TestPriceLevel:
    """Tests for PriceLevel value object."""

    def test_create_price_level(self) -> None:
        """PriceLevel stores price and size."""
        level = PriceLevel(
            price=Price(Decimal("0.45")),
            size=Quantity(100),
        )
        assert level.price.value == Decimal("0.45")
        assert level.size.value == 100

    def test_price_level_is_immutable(self) -> None:
        """PriceLevel should be immutable."""
        level = PriceLevel(
            price=Price(Decimal("0.45")),
            size=Quantity(100),
        )
        with pytest.raises((AttributeError, TypeError)):
            level.price = Price(Decimal("0.50"))  # type: ignore[misc]

    def test_price_level_equality(self) -> None:
        """PriceLevels with same values are equal."""
        l1 = PriceLevel(price=Price(Decimal("0.45")), size=Quantity(100))
        l2 = PriceLevel(price=Price(Decimal("0.45")), size=Quantity(100))
        assert l1 == l2

    def test_price_level_from_cents(self) -> None:
        """PriceLevel can be created from cents."""
        level = PriceLevel.from_cents(price_cents=45, size=100)
        assert level.price.value == Decimal("0.45")
        assert level.size.value == 100


class TestOrderBook:
    """Tests for OrderBook aggregate."""

    @pytest.fixture
    def sample_book(self) -> OrderBook:
        """Create a sample order book."""
        return OrderBook(
            market_id="KXBTC-25JAN17-100000",
            yes_bids=[
                PriceLevel(Price(Decimal("0.45")), Quantity(100)),
                PriceLevel(Price(Decimal("0.44")), Quantity(200)),
            ],
            yes_asks=[
                PriceLevel(Price(Decimal("0.47")), Quantity(150)),
                PriceLevel(Price(Decimal("0.48")), Quantity(100)),
            ],
            timestamp=datetime(2026, 1, 17, 12, 0, 0, tzinfo=UTC),
        )

    def test_create_order_book(self, sample_book: OrderBook) -> None:
        """OrderBook stores market ID and price levels."""
        assert sample_book.market_id == "KXBTC-25JAN17-100000"
        assert len(sample_book.yes_bids) == 2
        assert len(sample_book.yes_asks) == 2

    def test_order_book_is_immutable(self, sample_book: OrderBook) -> None:
        """OrderBook should be immutable."""
        with pytest.raises((AttributeError, TypeError)):
            sample_book.market_id = "other"  # type: ignore[misc]

    def test_best_bid(self, sample_book: OrderBook) -> None:
        """best_bid returns highest bid."""
        best_bid = sample_book.best_bid()
        assert best_bid is not None
        assert best_bid.price.value == Decimal("0.45")

    def test_best_ask(self, sample_book: OrderBook) -> None:
        """best_ask returns lowest ask."""
        best_ask = sample_book.best_ask()
        assert best_ask is not None
        assert best_ask.price.value == Decimal("0.47")

    def test_best_bid_empty(self) -> None:
        """best_bid returns None for empty book."""
        book = OrderBook(
            market_id="TEST",
            yes_bids=[],
            yes_asks=[],
            timestamp=datetime.now(UTC),
        )
        assert book.best_bid() is None

    def test_best_ask_empty(self) -> None:
        """best_ask returns None for empty book."""
        book = OrderBook(
            market_id="TEST",
            yes_bids=[],
            yes_asks=[],
            timestamp=datetime.now(UTC),
        )
        assert book.best_ask() is None

    def test_mid_price(self, sample_book: OrderBook) -> None:
        """mid_price returns average of best bid and ask."""
        mid = sample_book.mid_price()
        assert mid is not None
        # (0.45 + 0.47) / 2 = 0.46
        assert mid.value == Decimal("0.46")

    def test_mid_price_empty(self) -> None:
        """mid_price returns None for empty book."""
        book = OrderBook(
            market_id="TEST",
            yes_bids=[],
            yes_asks=[],
            timestamp=datetime.now(UTC),
        )
        assert book.mid_price() is None

    def test_spread(self, sample_book: OrderBook) -> None:
        """spread returns difference between best ask and bid."""
        spread = sample_book.spread()
        assert spread is not None
        # 0.47 - 0.45 = 0.02
        assert spread == Decimal("0.02")

    def test_spread_empty(self) -> None:
        """spread returns None for empty book."""
        book = OrderBook(
            market_id="TEST",
            yes_bids=[],
            yes_asks=[],
            timestamp=datetime.now(UTC),
        )
        assert book.spread() is None

    def test_no_bids_from_yes_asks(self, sample_book: OrderBook) -> None:
        """no_bids derived from yes_asks using complement price."""
        no_bids = sample_book.no_bids()
        assert len(no_bids) == 2
        # YES ask at 0.47 -> NO bid at 1 - 0.47 = 0.53
        assert no_bids[0].price.value == Decimal("0.53")

    def test_no_asks_from_yes_bids(self, sample_book: OrderBook) -> None:
        """no_asks derived from yes_bids using complement price."""
        no_asks = sample_book.no_asks()
        assert len(no_asks) == 2
        # YES bid at 0.45 -> NO ask at 1 - 0.45 = 0.55
        assert no_asks[0].price.value == Decimal("0.55")


class TestTrade:
    """Tests for Trade value object."""

    def test_create_trade(self) -> None:
        """Trade stores all fields."""
        trade = Trade(
            market_id="KXBTC-25JAN17-100000",
            price=Price(Decimal("0.45")),
            size=Quantity(10),
            side=Side.YES,
            timestamp=datetime(2026, 1, 17, 12, 0, 0, tzinfo=UTC),
        )
        assert trade.market_id == "KXBTC-25JAN17-100000"
        assert trade.price.value == Decimal("0.45")
        assert trade.size.value == 10
        assert trade.side == Side.YES

    def test_trade_is_immutable(self) -> None:
        """Trade should be immutable."""
        trade = Trade(
            market_id="KXBTC-25JAN17-100000",
            price=Price(Decimal("0.45")),
            size=Quantity(10),
            side=Side.YES,
            timestamp=datetime.now(UTC),
        )
        with pytest.raises((AttributeError, TypeError)):
            trade.price = Price(Decimal("0.50"))  # type: ignore[misc]

    def test_trade_from_cents(self) -> None:
        """Trade can be created from cents."""
        trade = Trade.from_cents(
            market_id="TEST",
            price_cents=45,
            size=10,
            side=Side.YES,
            timestamp=datetime.now(UTC),
        )
        assert trade.price.value == Decimal("0.45")


class TestMarketSnapshot:
    """Tests for MarketSnapshot."""

    def test_create_market_snapshot(self) -> None:
        """MarketSnapshot stores aggregated market data."""
        snapshot = MarketSnapshot(
            market_id="KXBTC-25JAN17-100000",
            mid_price=Price(Decimal("0.46")),
            spread=Decimal("0.02"),
            best_bid=PriceLevel(Price(Decimal("0.45")), Quantity(100)),
            best_ask=PriceLevel(Price(Decimal("0.47")), Quantity(150)),
            volatility=Decimal("0.15"),
            time_to_settlement=timedelta(hours=1),
            timestamp=datetime(2026, 1, 17, 12, 0, 0, tzinfo=UTC),
        )
        assert snapshot.market_id == "KXBTC-25JAN17-100000"
        assert snapshot.mid_price.value == Decimal("0.46")
        assert snapshot.volatility == Decimal("0.15")

    def test_market_snapshot_is_immutable(self) -> None:
        """MarketSnapshot should be immutable."""
        snapshot = MarketSnapshot(
            market_id="TEST",
            mid_price=Price(Decimal("0.50")),
            spread=Decimal("0.02"),
            best_bid=PriceLevel(Price(Decimal("0.49")), Quantity(100)),
            best_ask=PriceLevel(Price(Decimal("0.51")), Quantity(100)),
            volatility=Decimal("0.10"),
            time_to_settlement=timedelta(hours=1),
            timestamp=datetime.now(UTC),
        )
        with pytest.raises((AttributeError, TypeError)):
            snapshot.mid_price = Price(Decimal("0.55"))  # type: ignore[misc]

    def test_from_order_book(self) -> None:
        """MarketSnapshot can be created from OrderBook."""
        book = OrderBook(
            market_id="TEST",
            yes_bids=[PriceLevel(Price(Decimal("0.45")), Quantity(100))],
            yes_asks=[PriceLevel(Price(Decimal("0.47")), Quantity(150))],
            timestamp=datetime.now(UTC),
        )
        snapshot = MarketSnapshot.from_order_book(
            book=book,
            volatility=Decimal("0.15"),
            time_to_settlement=timedelta(hours=1),
        )
        assert snapshot.market_id == "TEST"
        assert snapshot.mid_price.value == Decimal("0.46")
        assert snapshot.spread == Decimal("0.02")
