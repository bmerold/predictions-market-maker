"""Tests for order domain models."""

from datetime import UTC, datetime
from decimal import Decimal

import pytest

from market_maker.domain.orders import (
    Fill,
    Order,
    OrderRequest,
    OrderStatus,
    Quote,
    QuoteSet,
)
from market_maker.domain.types import OrderSide, Price, Quantity, Side


class TestOrderStatus:
    """Tests for OrderStatus enum."""

    def test_all_statuses_defined(self) -> None:
        """OrderStatus has all expected states."""
        expected = {
            "PENDING",
            "OPEN",
            "PARTIALLY_FILLED",
            "FILLED",
            "CANCELLING",
            "CANCELLED",
            "REJECTED",
        }
        actual = {s.name for s in OrderStatus}
        assert actual == expected

    def test_is_terminal_filled(self) -> None:
        """FILLED is terminal."""
        assert OrderStatus.FILLED.is_terminal()

    def test_is_terminal_cancelled(self) -> None:
        """CANCELLED is terminal."""
        assert OrderStatus.CANCELLED.is_terminal()

    def test_is_terminal_rejected(self) -> None:
        """REJECTED is terminal."""
        assert OrderStatus.REJECTED.is_terminal()

    def test_is_terminal_open_not(self) -> None:
        """OPEN is not terminal."""
        assert not OrderStatus.OPEN.is_terminal()

    def test_is_terminal_pending_not(self) -> None:
        """PENDING is not terminal."""
        assert not OrderStatus.PENDING.is_terminal()

    def test_is_terminal_partially_filled_not(self) -> None:
        """PARTIALLY_FILLED is not terminal."""
        assert not OrderStatus.PARTIALLY_FILLED.is_terminal()

    def test_is_active_open(self) -> None:
        """OPEN is active."""
        assert OrderStatus.OPEN.is_active()

    def test_is_active_partially_filled(self) -> None:
        """PARTIALLY_FILLED is active."""
        assert OrderStatus.PARTIALLY_FILLED.is_active()

    def test_is_active_filled_not(self) -> None:
        """FILLED is not active."""
        assert not OrderStatus.FILLED.is_active()


class TestOrder:
    """Tests for Order model."""

    @pytest.fixture
    def sample_order(self) -> Order:
        """Create a sample order."""
        return Order(
            id="ord_123",
            client_order_id="client_456",
            market_id="KXBTC-25JAN17-100000",
            side=Side.YES,
            order_side=OrderSide.BUY,
            price=Price(Decimal("0.45")),
            size=Quantity(100),
            filled_size=0,
            status=OrderStatus.OPEN,
            created_at=datetime(2026, 1, 17, 12, 0, 0, tzinfo=UTC),
            updated_at=datetime(2026, 1, 17, 12, 0, 0, tzinfo=UTC),
        )

    def test_create_order(self, sample_order: Order) -> None:
        """Order stores all fields."""
        assert sample_order.id == "ord_123"
        assert sample_order.client_order_id == "client_456"
        assert sample_order.market_id == "KXBTC-25JAN17-100000"
        assert sample_order.side == Side.YES
        assert sample_order.order_side == OrderSide.BUY
        assert sample_order.price.value == Decimal("0.45")
        assert sample_order.size.value == 100

    def test_order_is_immutable(self, sample_order: Order) -> None:
        """Order should be immutable."""
        with pytest.raises((AttributeError, TypeError)):
            sample_order.status = OrderStatus.FILLED  # type: ignore[misc]

    def test_remaining_size_no_fills(self, sample_order: Order) -> None:
        """remaining_size equals size when no fills."""
        assert sample_order.remaining_size() == 100

    def test_remaining_size_partial(self) -> None:
        """remaining_size reflects filled amount."""
        order = Order(
            id="ord_123",
            client_order_id="client_456",
            market_id="TEST",
            side=Side.YES,
            order_side=OrderSide.BUY,
            price=Price(Decimal("0.45")),
            size=Quantity(100),
            filled_size=60,
            status=OrderStatus.PARTIALLY_FILLED,
            created_at=datetime.now(UTC),
            updated_at=datetime.now(UTC),
        )
        assert order.remaining_size() == 40

    def test_is_terminal_open(self, sample_order: Order) -> None:
        """OPEN order is not terminal."""
        assert not sample_order.is_terminal()

    def test_is_terminal_filled(self) -> None:
        """FILLED order is terminal."""
        order = Order(
            id="ord_123",
            client_order_id="client_456",
            market_id="TEST",
            side=Side.YES,
            order_side=OrderSide.BUY,
            price=Price(Decimal("0.45")),
            size=Quantity(100),
            filled_size=100,
            status=OrderStatus.FILLED,
            created_at=datetime.now(UTC),
            updated_at=datetime.now(UTC),
        )
        assert order.is_terminal()

    def test_with_status(self, sample_order: Order) -> None:
        """with_status returns new order with updated status."""
        new_order = sample_order.with_status(OrderStatus.CANCELLED)
        assert new_order.status == OrderStatus.CANCELLED
        assert new_order.id == sample_order.id
        # Original unchanged
        assert sample_order.status == OrderStatus.OPEN

    def test_with_fill(self, sample_order: Order) -> None:
        """with_fill returns new order with updated fill info."""
        new_order = sample_order.with_fill(fill_size=50)
        assert new_order.filled_size == 50
        assert new_order.status == OrderStatus.PARTIALLY_FILLED
        # Original unchanged
        assert sample_order.filled_size == 0

    def test_with_fill_complete(self, sample_order: Order) -> None:
        """with_fill marks as FILLED when fully filled."""
        new_order = sample_order.with_fill(fill_size=100)
        assert new_order.filled_size == 100
        assert new_order.status == OrderStatus.FILLED


class TestOrderRequest:
    """Tests for OrderRequest model."""

    def test_create_order_request(self) -> None:
        """OrderRequest stores all fields."""
        request = OrderRequest(
            client_order_id="client_456",
            market_id="KXBTC-25JAN17-100000",
            side=Side.YES,
            order_side=OrderSide.BUY,
            price=Price(Decimal("0.45")),
            size=Quantity(100),
        )
        assert request.client_order_id == "client_456"
        assert request.market_id == "KXBTC-25JAN17-100000"
        assert request.side == Side.YES

    def test_order_request_is_immutable(self) -> None:
        """OrderRequest should be immutable."""
        request = OrderRequest(
            client_order_id="client_456",
            market_id="TEST",
            side=Side.YES,
            order_side=OrderSide.BUY,
            price=Price(Decimal("0.45")),
            size=Quantity(100),
        )
        with pytest.raises((AttributeError, TypeError)):
            request.size = Quantity(200)  # type: ignore[misc]

    def test_order_request_generate_client_id(self) -> None:
        """OrderRequest can generate client_order_id."""
        request = OrderRequest.create(
            market_id="TEST",
            side=Side.YES,
            order_side=OrderSide.BUY,
            price=Price(Decimal("0.45")),
            size=Quantity(100),
        )
        assert request.client_order_id is not None
        assert len(request.client_order_id) > 0


class TestQuote:
    """Tests for Quote model."""

    def test_create_quote(self) -> None:
        """Quote stores bid and ask."""
        quote = Quote(
            bid_price=Price(Decimal("0.44")),
            bid_size=Quantity(100),
            ask_price=Price(Decimal("0.46")),
            ask_size=Quantity(150),
        )
        assert quote.bid_price.value == Decimal("0.44")
        assert quote.ask_price.value == Decimal("0.46")

    def test_quote_is_immutable(self) -> None:
        """Quote should be immutable."""
        quote = Quote(
            bid_price=Price(Decimal("0.44")),
            bid_size=Quantity(100),
            ask_price=Price(Decimal("0.46")),
            ask_size=Quantity(150),
        )
        with pytest.raises((AttributeError, TypeError)):
            quote.bid_price = Price(Decimal("0.45"))  # type: ignore[misc]

    def test_quote_spread(self) -> None:
        """Quote.spread returns ask - bid."""
        quote = Quote(
            bid_price=Price(Decimal("0.44")),
            bid_size=Quantity(100),
            ask_price=Price(Decimal("0.46")),
            ask_size=Quantity(150),
        )
        assert quote.spread() == Decimal("0.02")


class TestQuoteSet:
    """Tests for QuoteSet model."""

    def test_create_quote_set(self) -> None:
        """QuoteSet stores YES quote for a market."""
        yes_quote = Quote(
            bid_price=Price(Decimal("0.44")),
            bid_size=Quantity(100),
            ask_price=Price(Decimal("0.46")),
            ask_size=Quantity(150),
        )
        quote_set = QuoteSet(
            market_id="KXBTC-25JAN17-100000",
            yes_quote=yes_quote,
            timestamp=datetime(2026, 1, 17, 12, 0, 0, tzinfo=UTC),
        )
        assert quote_set.market_id == "KXBTC-25JAN17-100000"
        assert quote_set.yes_quote.bid_price.value == Decimal("0.44")

    def test_quote_set_is_immutable(self) -> None:
        """QuoteSet should be immutable."""
        yes_quote = Quote(
            bid_price=Price(Decimal("0.44")),
            bid_size=Quantity(100),
            ask_price=Price(Decimal("0.46")),
            ask_size=Quantity(150),
        )
        quote_set = QuoteSet(
            market_id="TEST",
            yes_quote=yes_quote,
            timestamp=datetime.now(UTC),
        )
        with pytest.raises((AttributeError, TypeError)):
            quote_set.market_id = "other"  # type: ignore[misc]

    def test_no_quote_derived_from_yes(self) -> None:
        """no_quote is derived from yes_quote using complement prices."""
        yes_quote = Quote(
            bid_price=Price(Decimal("0.44")),
            bid_size=Quantity(100),
            ask_price=Price(Decimal("0.46")),
            ask_size=Quantity(150),
        )
        quote_set = QuoteSet(
            market_id="TEST",
            yes_quote=yes_quote,
            timestamp=datetime.now(UTC),
        )
        no_quote = quote_set.no_quote()
        # NO bid = 1 - YES ask = 1 - 0.46 = 0.54
        assert no_quote.bid_price.value == Decimal("0.54")
        # NO ask = 1 - YES bid = 1 - 0.44 = 0.56
        assert no_quote.ask_price.value == Decimal("0.56")
        # Sizes from opposite side
        assert no_quote.bid_size.value == 150  # from YES ask size
        assert no_quote.ask_size.value == 100  # from YES bid size

    def test_to_order_requests(self) -> None:
        """to_order_requests generates 4 order requests."""
        yes_quote = Quote(
            bid_price=Price(Decimal("0.44")),
            bid_size=Quantity(100),
            ask_price=Price(Decimal("0.46")),
            ask_size=Quantity(150),
        )
        quote_set = QuoteSet(
            market_id="TEST",
            yes_quote=yes_quote,
            timestamp=datetime.now(UTC),
        )
        requests = quote_set.to_order_requests()
        assert len(requests) == 4

        # Check we have all combinations
        sides_and_order_sides = {(r.side, r.order_side) for r in requests}
        expected = {
            (Side.YES, OrderSide.BUY),  # YES bid
            (Side.YES, OrderSide.SELL),  # YES ask
            (Side.NO, OrderSide.BUY),  # NO bid
            (Side.NO, OrderSide.SELL),  # NO ask
        }
        assert sides_and_order_sides == expected


class TestFill:
    """Tests for Fill model."""

    def test_create_fill(self) -> None:
        """Fill stores all fields."""
        fill = Fill(
            id="fill_123",
            order_id="ord_456",
            market_id="KXBTC-25JAN17-100000",
            side=Side.YES,
            order_side=OrderSide.BUY,
            price=Price(Decimal("0.45")),
            size=Quantity(50),
            timestamp=datetime(2026, 1, 17, 12, 0, 0, tzinfo=UTC),
            is_simulated=False,
        )
        assert fill.id == "fill_123"
        assert fill.order_id == "ord_456"
        assert fill.size.value == 50
        assert not fill.is_simulated

    def test_fill_is_immutable(self) -> None:
        """Fill should be immutable."""
        fill = Fill(
            id="fill_123",
            order_id="ord_456",
            market_id="TEST",
            side=Side.YES,
            order_side=OrderSide.BUY,
            price=Price(Decimal("0.45")),
            size=Quantity(50),
            timestamp=datetime.now(UTC),
            is_simulated=False,
        )
        with pytest.raises((AttributeError, TypeError)):
            fill.size = Quantity(100)  # type: ignore[misc]

    def test_fill_simulated(self) -> None:
        """Fill can be marked as simulated for paper trading."""
        fill = Fill(
            id="fill_sim_123",
            order_id="ord_456",
            market_id="TEST",
            side=Side.YES,
            order_side=OrderSide.BUY,
            price=Price(Decimal("0.45")),
            size=Quantity(50),
            timestamp=datetime.now(UTC),
            is_simulated=True,
        )
        assert fill.is_simulated

    def test_fill_notional(self) -> None:
        """notional returns price * size."""
        fill = Fill(
            id="fill_123",
            order_id="ord_456",
            market_id="TEST",
            side=Side.YES,
            order_side=OrderSide.BUY,
            price=Price(Decimal("0.45")),
            size=Quantity(100),
            timestamp=datetime.now(UTC),
            is_simulated=False,
        )
        # 0.45 * 100 = 45.00
        assert fill.notional() == Decimal("45.00")
