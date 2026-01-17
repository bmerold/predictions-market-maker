"""Tests for Paper Execution Engine."""

from datetime import UTC, datetime
from decimal import Decimal

import pytest

from market_maker.domain.market_data import OrderBook, PriceLevel
from market_maker.domain.orders import OrderRequest, OrderSide, Quote, QuoteSet
from market_maker.domain.types import Price, Quantity, Side
from market_maker.execution.paper import PaperExecutionEngine


def make_order_book(
    best_bid: Decimal = Decimal("0.48"),
    best_ask: Decimal = Decimal("0.52"),
    bid_size: int = 100,
    ask_size: int = 100,
) -> OrderBook:
    """Create an OrderBook for testing."""
    return OrderBook(
        market_id="TEST",
        yes_bids=[PriceLevel(Price(best_bid), Quantity(bid_size))],
        yes_asks=[PriceLevel(Price(best_ask), Quantity(ask_size))],
        timestamp=datetime.now(UTC),
    )


class TestPaperExecutionEngine:
    """Tests for PaperExecutionEngine."""

    @pytest.fixture
    def engine(self) -> PaperExecutionEngine:
        """Create a paper execution engine."""
        return PaperExecutionEngine()

    def test_submit_order_returns_order(self, engine: PaperExecutionEngine) -> None:
        """Submitting an order returns an Order object."""
        request = OrderRequest.create(
            market_id="TEST",
            side=Side.YES,
            order_side=OrderSide.BUY,
            price=Price(Decimal("0.50")),
            size=Quantity(100),
        )
        book = make_order_book()

        order = engine.submit_order(request, book)

        assert order is not None
        assert order.market_id == "TEST"
        assert order.side == Side.YES
        assert order.price.value == Decimal("0.50")

    def test_buy_order_fills_at_ask(self, engine: PaperExecutionEngine) -> None:
        """Buy order fills when price >= best ask."""
        request = OrderRequest.create(
            market_id="TEST",
            side=Side.YES,
            order_side=OrderSide.BUY,
            price=Price(Decimal("0.52")),  # At best ask
            size=Quantity(50),
        )
        book = make_order_book(best_ask=Decimal("0.52"), ask_size=100)

        order = engine.submit_order(request, book)

        # Should fill immediately
        fills = engine.get_fills()
        assert len(fills) == 1
        assert fills[0].price.value == Decimal("0.52")
        assert fills[0].size.value == 50

    def test_sell_order_fills_at_bid(self, engine: PaperExecutionEngine) -> None:
        """Sell order fills when price <= best bid."""
        request = OrderRequest.create(
            market_id="TEST",
            side=Side.YES,
            order_side=OrderSide.SELL,
            price=Price(Decimal("0.48")),  # At best bid
            size=Quantity(50),
        )
        book = make_order_book(best_bid=Decimal("0.48"), bid_size=100)

        order = engine.submit_order(request, book)

        fills = engine.get_fills()
        assert len(fills) == 1
        assert fills[0].price.value == Decimal("0.48")
        assert fills[0].size.value == 50

    def test_order_not_filled_if_price_not_crossed(
        self, engine: PaperExecutionEngine
    ) -> None:
        """Order doesn't fill if price doesn't cross spread."""
        request = OrderRequest.create(
            market_id="TEST",
            side=Side.YES,
            order_side=OrderSide.BUY,
            price=Price(Decimal("0.50")),  # Below best ask of 0.52
            size=Quantity(50),
        )
        book = make_order_book(best_ask=Decimal("0.52"))

        engine.submit_order(request, book)

        fills = engine.get_fills()
        assert len(fills) == 0

    def test_partial_fill(self, engine: PaperExecutionEngine) -> None:
        """Order partially fills if book size is smaller."""
        request = OrderRequest.create(
            market_id="TEST",
            side=Side.YES,
            order_side=OrderSide.BUY,
            price=Price(Decimal("0.52")),
            size=Quantity(150),  # Larger than book size
        )
        book = make_order_book(best_ask=Decimal("0.52"), ask_size=100)

        engine.submit_order(request, book)

        fills = engine.get_fills()
        assert len(fills) == 1
        assert fills[0].size.value == 100  # Only filled available size

    def test_cancel_order(self, engine: PaperExecutionEngine) -> None:
        """Can cancel an open order."""
        request = OrderRequest.create(
            market_id="TEST",
            side=Side.YES,
            order_side=OrderSide.BUY,
            price=Price(Decimal("0.45")),  # Won't fill
            size=Quantity(100),
        )
        book = make_order_book(best_ask=Decimal("0.52"))

        order = engine.submit_order(request, book)
        success = engine.cancel_order(order.id)

        assert success is True
        assert engine.get_order(order.id) is None or engine.get_order(order.id).status.is_terminal()

    def test_get_open_orders(self, engine: PaperExecutionEngine) -> None:
        """Can get list of open orders."""
        request1 = OrderRequest.create(
            market_id="TEST",
            side=Side.YES,
            order_side=OrderSide.BUY,
            price=Price(Decimal("0.45")),
            size=Quantity(100),
        )
        request2 = OrderRequest.create(
            market_id="TEST",
            side=Side.YES,
            order_side=OrderSide.SELL,
            price=Price(Decimal("0.55")),
            size=Quantity(100),
        )
        book = make_order_book()

        engine.submit_order(request1, book)
        engine.submit_order(request2, book)

        open_orders = engine.get_open_orders("TEST")
        assert len(open_orders) == 2

    def test_cancel_all_orders(self, engine: PaperExecutionEngine) -> None:
        """Can cancel all orders for a market."""
        for i in range(3):
            request = OrderRequest.create(
                market_id="TEST",
                side=Side.YES,
                order_side=OrderSide.BUY,
                price=Price(Decimal("0.45")),
                size=Quantity(100),
            )
            engine.submit_order(request, make_order_book())

        count = engine.cancel_all_orders("TEST")

        assert count == 3
        assert len(engine.get_open_orders("TEST")) == 0

    def test_fills_marked_as_simulated(self, engine: PaperExecutionEngine) -> None:
        """All fills are marked as simulated."""
        request = OrderRequest.create(
            market_id="TEST",
            side=Side.YES,
            order_side=OrderSide.BUY,
            price=Price(Decimal("0.52")),
            size=Quantity(50),
        )
        book = make_order_book(best_ask=Decimal("0.52"))

        engine.submit_order(request, book)

        fills = engine.get_fills()
        assert all(f.is_simulated for f in fills)

    def test_no_side_order_converts_price(self, engine: PaperExecutionEngine) -> None:
        """NO side orders use the converted price."""
        # NO bid should match against YES ask (which is 1 - NO bid)
        request = OrderRequest.create(
            market_id="TEST",
            side=Side.NO,
            order_side=OrderSide.BUY,
            price=Price(Decimal("0.48")),  # NO bid of 0.48 = YES ask of 0.52
            size=Quantity(50),
        )
        book = make_order_book(best_ask=Decimal("0.52"))  # YES ask

        engine.submit_order(request, book)

        fills = engine.get_fills()
        assert len(fills) == 1
        # Fill should be recorded at the NO price
        assert fills[0].side == Side.NO
