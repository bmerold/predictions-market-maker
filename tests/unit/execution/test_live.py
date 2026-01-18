"""Tests for live execution engine."""

from datetime import UTC, datetime
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock

import pytest

from market_maker.domain.market_data import OrderBook, PriceLevel
from market_maker.domain.orders import (
    Fill,
    Order,
    OrderRequest,
    OrderStatus,
    Quote,
    QuoteSet,
)
from market_maker.domain.types import OrderSide, Price, Quantity, Side
from market_maker.execution.live import LiveExecutionEngine


class TestLiveExecutionEngine:
    """Tests for LiveExecutionEngine."""

    @pytest.fixture
    def mock_exchange(self) -> MagicMock:
        """Create mock exchange adapter."""
        exchange = MagicMock()
        exchange.place_order = AsyncMock()
        exchange.cancel_order = AsyncMock()
        exchange.cancel_all_orders = AsyncMock(return_value=0)
        exchange.get_open_orders = AsyncMock(return_value=[])
        return exchange

    @pytest.fixture
    def engine(self, mock_exchange: MagicMock) -> LiveExecutionEngine:
        """Create live execution engine."""
        return LiveExecutionEngine(mock_exchange)

    @pytest.fixture
    def sample_order(self) -> Order:
        """Create sample order."""
        return Order(
            id="order-123",
            client_order_id="client-123",
            market_id="TEST-MARKET",
            side=Side.YES,
            order_side=OrderSide.BUY,
            price=Price(Decimal("0.45")),
            size=Quantity(10),
            filled_size=0,
            status=OrderStatus.OPEN,
            created_at=datetime.now(UTC),
            updated_at=datetime.now(UTC),
        )

    @pytest.fixture
    def sample_book(self) -> OrderBook:
        """Create sample order book."""
        return OrderBook(
            market_id="TEST-MARKET",
            yes_bids=[PriceLevel(Price(Decimal("0.45")), Quantity(100))],
            yes_asks=[PriceLevel(Price(Decimal("0.55")), Quantity(100))],
            timestamp=datetime.now(UTC),
        )

    @pytest.fixture
    def sample_request(self) -> OrderRequest:
        """Create sample order request."""
        return OrderRequest(
            market_id="TEST-MARKET",
            side=Side.YES,
            order_side=OrderSide.BUY,
            price=Price(Decimal("0.45")),
            size=Quantity(10),
            client_order_id="client-123",
        )

    @pytest.mark.asyncio
    async def test_submit_order(
        self,
        engine: LiveExecutionEngine,
        mock_exchange: MagicMock,
        sample_order: Order,
        sample_book: OrderBook,
        sample_request: OrderRequest,
    ) -> None:
        """Should submit order to exchange."""
        mock_exchange.place_order.return_value = sample_order

        result = await engine.submit_order(sample_request, sample_book)

        assert result == sample_order
        mock_exchange.place_order.assert_called_once_with(sample_request)
        assert engine.get_order("order-123") == sample_order

    @pytest.mark.asyncio
    async def test_cancel_order(
        self,
        engine: LiveExecutionEngine,
        mock_exchange: MagicMock,
        sample_order: Order,
    ) -> None:
        """Should cancel order on exchange."""
        engine._orders["order-123"] = sample_order

        result = await engine.cancel_order("order-123")

        assert result is True
        mock_exchange.cancel_order.assert_called_once_with("order-123")
        assert engine.get_order("order-123").status == OrderStatus.CANCELLED

    @pytest.mark.asyncio
    async def test_cancel_order_not_found(
        self,
        engine: LiveExecutionEngine,
        mock_exchange: MagicMock,
    ) -> None:
        """Should handle cancel of unknown order."""
        mock_exchange.cancel_order.side_effect = Exception("Not found")

        result = await engine.cancel_order("unknown")

        assert result is False

    @pytest.mark.asyncio
    async def test_cancel_all_orders(
        self,
        engine: LiveExecutionEngine,
        mock_exchange: MagicMock,
        sample_order: Order,
    ) -> None:
        """Should cancel all orders for market."""
        engine._orders["order-123"] = sample_order
        mock_exchange.cancel_all_orders.return_value = 1

        result = await engine.cancel_all_orders("TEST-MARKET")

        assert result == 1
        mock_exchange.cancel_all_orders.assert_called_once_with("TEST-MARKET")
        assert engine.get_order("order-123").status == OrderStatus.CANCELLED

    def test_get_open_orders(
        self,
        engine: LiveExecutionEngine,
        sample_order: Order,
    ) -> None:
        """Should get open orders for market."""
        engine._orders["order-123"] = sample_order

        orders = engine.get_open_orders("TEST-MARKET")

        assert len(orders) == 1
        assert orders[0].id == "order-123"

    def test_get_open_orders_filters_cancelled(
        self,
        engine: LiveExecutionEngine,
        sample_order: Order,
    ) -> None:
        """Should filter out cancelled orders."""
        cancelled = Order(
            id="order-456",
            client_order_id="client-456",
            market_id="TEST-MARKET",
            side=Side.YES,
            order_side=OrderSide.BUY,
            price=Price(Decimal("0.45")),
            size=Quantity(10),
            filled_size=0,
            status=OrderStatus.CANCELLED,
            created_at=datetime.now(UTC),
            updated_at=datetime.now(UTC),
        )
        engine._orders["order-123"] = sample_order
        engine._orders["order-456"] = cancelled

        orders = engine.get_open_orders("TEST-MARKET")

        assert len(orders) == 1
        assert orders[0].id == "order-123"

    def test_add_fill(
        self,
        engine: LiveExecutionEngine,
        sample_order: Order,
    ) -> None:
        """Should add fill and update order."""
        engine._orders["order-123"] = sample_order

        fill = Fill(
            id="trade-1",
            order_id="order-123",
            market_id="TEST-MARKET",
            side=Side.YES,
            order_side=OrderSide.BUY,
            price=Price(Decimal("0.45")),
            size=Quantity(5),
            timestamp=datetime.now(UTC),
            is_simulated=False,
        )

        engine.add_fill(fill)

        assert len(engine.get_fills()) == 1
        order = engine.get_order("order-123")
        assert order.filled_size == 5
        assert order.status == OrderStatus.PARTIALLY_FILLED

    def test_add_fill_complete(
        self,
        engine: LiveExecutionEngine,
        sample_order: Order,
    ) -> None:
        """Should mark order filled when complete."""
        engine._orders["order-123"] = sample_order

        fill = Fill(
            id="trade-1",
            order_id="order-123",
            market_id="TEST-MARKET",
            side=Side.YES,
            order_side=OrderSide.BUY,
            price=Price(Decimal("0.45")),
            size=Quantity(10),
            timestamp=datetime.now(UTC),
            is_simulated=False,
        )

        engine.add_fill(fill)

        order = engine.get_order("order-123")
        assert order.status == OrderStatus.FILLED

    @pytest.mark.asyncio
    async def test_execute_quotes_new_orders(
        self,
        engine: LiveExecutionEngine,
        mock_exchange: MagicMock,
        sample_order: Order,
        sample_book: OrderBook,
    ) -> None:
        """Should place new orders for quotes."""
        mock_exchange.place_order.return_value = sample_order

        quotes = QuoteSet(
            market_id="TEST-MARKET",
            yes_quote=Quote(
                bid_price=Price(Decimal("0.45")),
                bid_size=Quantity(10),
                ask_price=Price(Decimal("0.55")),
                ask_size=Quantity(10),
            ),
            timestamp=datetime.now(UTC),
        )

        await engine.execute_quotes(quotes, sample_book)

        # Should have placed 4 orders (yes bid/ask, no bid/ask)
        assert mock_exchange.place_order.call_count == 4

    @pytest.mark.asyncio
    async def test_sync_with_exchange(
        self,
        engine: LiveExecutionEngine,
        mock_exchange: MagicMock,
        sample_order: Order,
    ) -> None:
        """Should sync local state with exchange."""
        engine._orders["order-123"] = sample_order
        mock_exchange.get_open_orders.return_value = []

        await engine.sync_with_exchange("TEST-MARKET")

        assert engine.get_order("order-123").status == OrderStatus.CANCELLED

    @pytest.mark.asyncio
    async def test_sync_adds_missing_orders(
        self,
        engine: LiveExecutionEngine,
        mock_exchange: MagicMock,
        sample_order: Order,
    ) -> None:
        """Should add orders from exchange we don't have."""
        mock_exchange.get_open_orders.return_value = [sample_order]

        await engine.sync_with_exchange("TEST-MARKET")

        assert engine.get_order("order-123") == sample_order

    def test_update_order(
        self,
        engine: LiveExecutionEngine,
        sample_order: Order,
    ) -> None:
        """Should update order from event."""
        engine._orders["order-123"] = sample_order

        updated = Order(
            id="order-123",
            client_order_id="client-123",
            market_id="TEST-MARKET",
            side=Side.YES,
            order_side=OrderSide.BUY,
            price=Price(Decimal("0.45")),
            size=Quantity(10),
            filled_size=5,
            status=OrderStatus.PARTIALLY_FILLED,
            created_at=sample_order.created_at,
            updated_at=datetime.now(UTC),
        )

        engine.update_order(updated)

        assert engine.get_order("order-123").filled_size == 5
