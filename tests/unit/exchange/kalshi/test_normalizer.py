"""Tests for Kalshi data normalizer."""

from datetime import UTC, datetime
from decimal import Decimal

import pytest

from market_maker.domain.events import BookUpdateType, EventType
from market_maker.domain.orders import OrderStatus
from market_maker.domain.types import OrderSide, Price, Quantity, Side
from market_maker.exchange.kalshi.normalizer import KalshiNormalizer


class TestKalshiNormalizerPrices:
    """Tests for price conversion."""

    @pytest.fixture
    def normalizer(self) -> KalshiNormalizer:
        """Create normalizer instance."""
        return KalshiNormalizer()

    def test_normalize_price_from_cents(self, normalizer: KalshiNormalizer) -> None:
        """Should convert cents to decimal Price."""
        price = normalizer.normalize_price(50)
        assert price.value == Decimal("0.5")

    def test_normalize_price_low(self, normalizer: KalshiNormalizer) -> None:
        """Should handle low prices."""
        price = normalizer.normalize_price(1)
        assert price.value == Decimal("0.01")

    def test_normalize_price_high(self, normalizer: KalshiNormalizer) -> None:
        """Should handle high prices."""
        price = normalizer.normalize_price(99)
        assert price.value == Decimal("0.99")

    def test_denormalize_price_to_cents(self, normalizer: KalshiNormalizer) -> None:
        """Should convert Price to cents."""
        price = Price(Decimal("0.65"))
        cents = normalizer.denormalize_price(price)
        assert cents == 65

    def test_denormalize_price_rounds(self, normalizer: KalshiNormalizer) -> None:
        """Should round decimal prices."""
        price = Price(Decimal("0.555"))
        cents = normalizer.denormalize_price(price)
        assert cents == 55


class TestKalshiNormalizerSides:
    """Tests for side conversion."""

    @pytest.fixture
    def normalizer(self) -> KalshiNormalizer:
        """Create normalizer instance."""
        return KalshiNormalizer()

    def test_normalize_side_yes(self, normalizer: KalshiNormalizer) -> None:
        """Should convert 'yes' to Side.YES."""
        assert normalizer.normalize_side("yes") == Side.YES
        assert normalizer.normalize_side("YES") == Side.YES

    def test_normalize_side_no(self, normalizer: KalshiNormalizer) -> None:
        """Should convert 'no' to Side.NO."""
        assert normalizer.normalize_side("no") == Side.NO
        assert normalizer.normalize_side("NO") == Side.NO

    def test_denormalize_side_yes(self, normalizer: KalshiNormalizer) -> None:
        """Should convert Side.YES to 'yes'."""
        assert normalizer.denormalize_side(Side.YES) == "yes"

    def test_denormalize_side_no(self, normalizer: KalshiNormalizer) -> None:
        """Should convert Side.NO to 'no'."""
        assert normalizer.denormalize_side(Side.NO) == "no"


class TestKalshiNormalizerOrderSide:
    """Tests for order side (action) conversion."""

    @pytest.fixture
    def normalizer(self) -> KalshiNormalizer:
        """Create normalizer instance."""
        return KalshiNormalizer()

    def test_normalize_order_side_buy(self, normalizer: KalshiNormalizer) -> None:
        """Should convert 'buy' to OrderSide.BUY."""
        assert normalizer.normalize_order_side("buy") == OrderSide.BUY
        assert normalizer.normalize_order_side("BUY") == OrderSide.BUY

    def test_normalize_order_side_sell(self, normalizer: KalshiNormalizer) -> None:
        """Should convert 'sell' to OrderSide.SELL."""
        assert normalizer.normalize_order_side("sell") == OrderSide.SELL
        assert normalizer.normalize_order_side("SELL") == OrderSide.SELL

    def test_denormalize_order_side_buy(self, normalizer: KalshiNormalizer) -> None:
        """Should convert OrderSide.BUY to 'buy'."""
        assert normalizer.denormalize_order_side(OrderSide.BUY) == "buy"

    def test_denormalize_order_side_sell(self, normalizer: KalshiNormalizer) -> None:
        """Should convert OrderSide.SELL to 'sell'."""
        assert normalizer.denormalize_order_side(OrderSide.SELL) == "sell"


class TestKalshiNormalizerTimestamp:
    """Tests for timestamp conversion."""

    @pytest.fixture
    def normalizer(self) -> KalshiNormalizer:
        """Create normalizer instance."""
        return KalshiNormalizer()

    def test_normalize_timestamp_with_z(self, normalizer: KalshiNormalizer) -> None:
        """Should handle Z suffix."""
        ts = normalizer.normalize_timestamp("2024-01-15T12:00:00Z")
        assert ts.tzinfo is not None

    def test_normalize_timestamp_with_offset(
        self, normalizer: KalshiNormalizer
    ) -> None:
        """Should handle timezone offset."""
        ts = normalizer.normalize_timestamp("2024-01-15T12:00:00+00:00")
        assert ts.tzinfo is not None

    def test_normalize_timestamp_none(self, normalizer: KalshiNormalizer) -> None:
        """Should return current time for None."""
        ts = normalizer.normalize_timestamp(None)
        assert ts is not None
        assert ts.tzinfo is not None


class TestKalshiNormalizerOrderStatus:
    """Tests for order status conversion."""

    @pytest.fixture
    def normalizer(self) -> KalshiNormalizer:
        """Create normalizer instance."""
        return KalshiNormalizer()

    def test_normalize_status_resting(self, normalizer: KalshiNormalizer) -> None:
        """Should convert resting to OPEN."""
        assert normalizer.normalize_order_status("resting") == OrderStatus.OPEN

    def test_normalize_status_pending(self, normalizer: KalshiNormalizer) -> None:
        """Should convert pending to PENDING."""
        assert normalizer.normalize_order_status("pending") == OrderStatus.PENDING

    def test_normalize_status_canceled(self, normalizer: KalshiNormalizer) -> None:
        """Should convert canceled/cancelled to CANCELLED."""
        assert normalizer.normalize_order_status("canceled") == OrderStatus.CANCELLED
        assert normalizer.normalize_order_status("cancelled") == OrderStatus.CANCELLED

    def test_normalize_status_executed(self, normalizer: KalshiNormalizer) -> None:
        """Should convert executed to FILLED."""
        assert normalizer.normalize_order_status("executed") == OrderStatus.FILLED

    def test_normalize_status_partial(self, normalizer: KalshiNormalizer) -> None:
        """Should convert partial to PARTIALLY_FILLED."""
        assert (
            normalizer.normalize_order_status("partial") == OrderStatus.PARTIALLY_FILLED
        )

    def test_normalize_status_unknown(self, normalizer: KalshiNormalizer) -> None:
        """Should default unknown status to PENDING."""
        assert normalizer.normalize_order_status("unknown") == OrderStatus.PENDING


class TestKalshiNormalizerOrderBook:
    """Tests for order book normalization."""

    @pytest.fixture
    def normalizer(self) -> KalshiNormalizer:
        """Create normalizer instance."""
        return KalshiNormalizer()

    def test_normalize_orderbook_empty(self, normalizer: KalshiNormalizer) -> None:
        """Should handle empty order book."""
        book = normalizer.normalize_orderbook({}, "TEST-MARKET")
        assert book.market_id == "TEST-MARKET"
        assert len(book.yes_bids) == 0
        assert len(book.yes_asks) == 0

    def test_normalize_orderbook_with_yes_bids(
        self, normalizer: KalshiNormalizer
    ) -> None:
        """Should convert YES bids."""
        data = {"yes": [[50, 100], [45, 50]]}
        book = normalizer.normalize_orderbook(data, "TEST")

        assert len(book.yes_bids) == 2
        # Bids should be sorted descending by price
        assert book.yes_bids[0].price.value == Decimal("0.50")
        assert book.yes_bids[0].size.value == 100
        assert book.yes_bids[1].price.value == Decimal("0.45")

    def test_normalize_orderbook_with_no_bids(
        self, normalizer: KalshiNormalizer
    ) -> None:
        """Should convert NO bids to YES asks (complement)."""
        # NO bid at 60c means YES ask at 40c (100 - 60 = 40)
        data = {"no": [[60, 100]]}
        book = normalizer.normalize_orderbook(data, "TEST")

        assert len(book.yes_asks) == 1
        assert book.yes_asks[0].price.value == Decimal("0.40")
        assert book.yes_asks[0].size.value == 100

    def test_normalize_orderbook_sorts_correctly(
        self, normalizer: KalshiNormalizer
    ) -> None:
        """Should sort bids descending and asks ascending."""
        data = {
            "yes": [[40, 10], [50, 20], [45, 30]],  # Unsorted
            "no": [[70, 100], [60, 50]],  # NO bids → YES asks at 30c, 40c
        }
        book = normalizer.normalize_orderbook(data, "TEST")

        # Bids: 50, 45, 40 (descending)
        assert book.yes_bids[0].price.value == Decimal("0.50")
        assert book.yes_bids[1].price.value == Decimal("0.45")
        assert book.yes_bids[2].price.value == Decimal("0.40")

        # Asks: 30, 40 (ascending)
        assert book.yes_asks[0].price.value == Decimal("0.30")
        assert book.yes_asks[1].price.value == Decimal("0.40")


class TestKalshiNormalizerOrder:
    """Tests for order normalization."""

    @pytest.fixture
    def normalizer(self) -> KalshiNormalizer:
        """Create normalizer instance."""
        return KalshiNormalizer()

    def test_normalize_order(self, normalizer: KalshiNormalizer) -> None:
        """Should convert Kalshi order to domain Order."""
        data = {
            "order_id": "ord_123",
            "client_order_id": "client_456",
            "ticker": "TEST-MARKET",
            "side": "yes",
            "action": "buy",
            "yes_price": 55,
            "count": 10,
            "filled_count": 3,
            "status": "partial",
            "created_time": "2024-01-15T12:00:00Z",
            "updated_time": "2024-01-15T12:01:00Z",
        }

        order = normalizer.normalize_order(data)

        assert order.id == "ord_123"
        assert order.client_order_id == "client_456"
        assert order.market_id == "TEST-MARKET"
        assert order.side == Side.YES
        assert order.order_side == OrderSide.BUY
        assert order.price.value == Decimal("0.55")
        assert order.size.value == 10
        assert order.filled_size == 3
        assert order.status == OrderStatus.PARTIALLY_FILLED


class TestKalshiNormalizerFill:
    """Tests for fill normalization."""

    @pytest.fixture
    def normalizer(self) -> KalshiNormalizer:
        """Create normalizer instance."""
        return KalshiNormalizer()

    def test_normalize_fill(self, normalizer: KalshiNormalizer) -> None:
        """Should convert Kalshi fill to domain Fill."""
        data = {
            "trade_id": "trade_123",
            "order_id": "ord_456",
            "ticker": "TEST-MARKET",
            "side": "no",
            "action": "sell",
            "yes_price": 45,
            "count": 5,
            "created_time": "2024-01-15T12:00:00Z",
        }

        fill = normalizer.normalize_fill(data)

        assert fill.id == "trade_123"
        assert fill.order_id == "ord_456"
        assert fill.market_id == "TEST-MARKET"
        assert fill.side == Side.NO
        assert fill.order_side == OrderSide.SELL
        assert fill.price.value == Decimal("0.45")
        assert fill.size.value == 5
        assert not fill.is_simulated


class TestKalshiNormalizerPosition:
    """Tests for position normalization."""

    @pytest.fixture
    def normalizer(self) -> KalshiNormalizer:
        """Create normalizer instance."""
        return KalshiNormalizer()

    def test_normalize_position_long_yes(
        self, normalizer: KalshiNormalizer
    ) -> None:
        """Should handle long YES position."""
        data = {
            "ticker": "TEST-MARKET",
            "position": 100,
            "average_price": 50,
        }

        position = normalizer.normalize_position(data)

        assert position.market_id == "TEST-MARKET"
        assert position.yes_quantity == 100
        assert position.no_quantity == 0
        assert position.avg_yes_price is not None
        assert position.avg_yes_price.value == Decimal("0.50")

    def test_normalize_position_long_no(
        self, normalizer: KalshiNormalizer
    ) -> None:
        """Should handle negative position (long NO)."""
        data = {
            "ticker": "TEST-MARKET",
            "position": -50,
        }

        position = normalizer.normalize_position(data)

        assert position.market_id == "TEST-MARKET"
        assert position.yes_quantity == 0
        assert position.no_quantity == 50


class TestKalshiNormalizerBalance:
    """Tests for balance normalization."""

    @pytest.fixture
    def normalizer(self) -> KalshiNormalizer:
        """Create normalizer instance."""
        return KalshiNormalizer()

    def test_normalize_balance(self, normalizer: KalshiNormalizer) -> None:
        """Should convert cents to dollars."""
        data = {"balance": 10050}  # $100.50 in cents

        balance = normalizer.normalize_balance(data)

        assert balance.available == Decimal("100.50")
        assert balance.total == Decimal("100.50")


class TestKalshiNormalizerEvents:
    """Tests for event normalization."""

    @pytest.fixture
    def normalizer(self) -> KalshiNormalizer:
        """Create normalizer instance."""
        return KalshiNormalizer()

    def test_normalize_orderbook_delta(self, normalizer: KalshiNormalizer) -> None:
        """Should convert WebSocket orderbook delta to BookUpdate."""
        data = {
            "type": "orderbook_delta",
            "msg": {
                "market_ticker": "TEST-MARKET",
                "price": 50,
                "delta": 10,
                "side": "yes",
            },
        }

        event = normalizer.normalize_orderbook_delta(data)

        assert event.event_type == EventType.BOOK_UPDATE
        assert event.market_id == "TEST-MARKET"
        assert event.update_type == BookUpdateType.DELTA
        assert event.delta_price is not None
        assert event.delta_price.value == Decimal("0.50")
        assert event.delta_size == 10
        assert event.delta_side == Side.YES
        assert event.delta_is_bid is True

    def test_normalize_fill_event(self, normalizer: KalshiNormalizer) -> None:
        """Should convert WebSocket fill to FillEvent."""
        data = {
            "type": "fill",
            "msg": {
                "trade_id": "trade_123",
                "order_id": "ord_456",
                "ticker": "TEST-MARKET",
                "side": "yes",
                "action": "buy",
                "yes_price": 55,
                "count": 10,
                "created_time": "2024-01-15T12:00:00Z",
            },
        }

        event = normalizer.normalize_fill_event(data)

        assert event.event_type == EventType.FILL
        assert event.fill.id == "trade_123"
        assert event.fill.market_id == "TEST-MARKET"

    def test_normalize_order_event(self, normalizer: KalshiNormalizer) -> None:
        """Should convert WebSocket order to OrderUpdate."""
        data = {
            "type": "order",
            "msg": {
                "order_id": "ord_123",
                "ticker": "TEST-MARKET",
                "side": "yes",
                "action": "buy",
                "yes_price": 55,
                "count": 10,
                "status": "resting",
                "created_time": "2024-01-15T12:00:00Z",
                "updated_time": "2024-01-15T12:00:00Z",
            },
        }

        event = normalizer.normalize_order_event(data)

        assert event.event_type == EventType.ORDER_UPDATE
        assert event.order.id == "ord_123"
        assert event.order.status == OrderStatus.OPEN
