"""Tests for exchange adapter abstractions."""

from collections.abc import Callable
from datetime import UTC, datetime
from decimal import Decimal

import pytest

from market_maker.domain.events import Event
from market_maker.domain.orders import Order, OrderRequest, OrderStatus
from market_maker.domain.positions import Balance, Position
from market_maker.domain.types import OrderSide, Price, Quantity, Side
from market_maker.exchange.base import (
    ExchangeAdapter,
    ExchangeCapabilities,
    WebSocketClient,
)


class TestExchangeAdapter:
    """Tests for ExchangeAdapter ABC."""

    def test_is_abstract(self) -> None:
        """ExchangeAdapter is abstract and cannot be instantiated directly."""
        with pytest.raises(TypeError):
            ExchangeAdapter()  # type: ignore[abstract]

    def test_required_methods(self) -> None:
        """ExchangeAdapter defines required abstract methods."""
        required_methods = {
            "connect",
            "disconnect",
            "subscribe_market",
            "unsubscribe_market",
            "place_order",
            "cancel_order",
            "get_positions",
            "get_balance",
            "get_open_orders",
        }
        abstract_methods = set(ExchangeAdapter.__abstractmethods__)
        assert required_methods.issubset(abstract_methods)

    def test_concrete_implementation(self) -> None:
        """Concrete implementation can be created."""

        class MockAdapter(ExchangeAdapter):
            async def connect(self) -> None:
                pass

            async def disconnect(self) -> None:
                pass

            async def subscribe_market(self, market_id: str) -> None:
                pass

            async def unsubscribe_market(self, market_id: str) -> None:
                pass

            async def place_order(self, order: OrderRequest) -> Order:
                return Order(
                    id="ord_123",
                    client_order_id=order.client_order_id,
                    market_id=order.market_id,
                    side=order.side,
                    order_side=order.order_side,
                    price=order.price,
                    size=order.size,
                    filled_size=0,
                    status=OrderStatus.OPEN,
                    created_at=datetime.now(UTC),
                    updated_at=datetime.now(UTC),
                )

            async def cancel_order(self, order_id: str) -> None:
                pass

            async def get_positions(self) -> list[Position]:
                return []

            async def get_balance(self) -> Balance:
                return Balance(total=Decimal("1000"), available=Decimal("1000"))

            async def get_open_orders(self, _market_id: str | None = None) -> list[Order]:
                return []

            def set_event_handler(self, handler: Callable[[Event], None]) -> None:
                pass

            @property
            def capabilities(self) -> ExchangeCapabilities:
                return ExchangeCapabilities(
                    supports_order_amendment=False,
                    supports_batch_orders=False,
                    max_orders_per_request=1,
                    rate_limit_writes_per_second=10,
                    rate_limit_reads_per_second=20,
                )

        adapter = MockAdapter()
        assert adapter is not None


class TestExchangeCapabilities:
    """Tests for ExchangeCapabilities."""

    def test_create_capabilities(self) -> None:
        """ExchangeCapabilities stores capability flags."""
        caps = ExchangeCapabilities(
            supports_order_amendment=True,
            supports_batch_orders=True,
            max_orders_per_request=10,
            rate_limit_writes_per_second=10,
            rate_limit_reads_per_second=20,
        )
        assert caps.supports_order_amendment is True
        assert caps.supports_batch_orders is True
        assert caps.max_orders_per_request == 10
        assert caps.rate_limit_writes_per_second == 10

    def test_kalshi_like_capabilities(self) -> None:
        """Kalshi-like capabilities."""
        caps = ExchangeCapabilities(
            supports_order_amendment=True,
            supports_batch_orders=False,
            max_orders_per_request=1,
            rate_limit_writes_per_second=10,
            rate_limit_reads_per_second=20,
        )
        assert caps.supports_order_amendment is True
        assert caps.supports_batch_orders is False

    def test_polymarket_like_capabilities(self) -> None:
        """Polymarket-like capabilities."""
        caps = ExchangeCapabilities(
            supports_order_amendment=False,
            supports_batch_orders=True,
            max_orders_per_request=100,
            rate_limit_writes_per_second=50,
            rate_limit_reads_per_second=100,
        )
        assert caps.supports_order_amendment is False
        assert caps.supports_batch_orders is True


class TestWebSocketClient:
    """Tests for WebSocketClient ABC."""

    def test_is_abstract(self) -> None:
        """WebSocketClient is abstract."""
        with pytest.raises(TypeError):
            WebSocketClient()  # type: ignore[abstract]

    def test_required_methods(self) -> None:
        """WebSocketClient defines required abstract methods."""
        required_methods = {
            "connect",
            "disconnect",
            "subscribe",
            "unsubscribe",
            "is_connected",
        }
        abstract_methods = set(WebSocketClient.__abstractmethods__)
        assert required_methods.issubset(abstract_methods)

    def test_concrete_implementation(self) -> None:
        """Concrete WebSocketClient implementation can be created."""

        class MockWSClient(WebSocketClient):
            def __init__(self) -> None:
                self._connected = False
                self._message_handler: Callable[[dict], None] | None = None

            async def connect(self) -> None:
                self._connected = True

            async def disconnect(self) -> None:
                self._connected = False

            async def subscribe(self, channels: list[str]) -> None:
                pass

            async def unsubscribe(self, channels: list[str]) -> None:
                pass

            def is_connected(self) -> bool:
                return self._connected

            def set_message_handler(self, handler: Callable[[dict], None]) -> None:
                self._message_handler = handler

        client = MockWSClient()
        assert not client.is_connected()


@pytest.mark.asyncio
async def test_adapter_place_order_flow() -> None:
    """Test placing an order through adapter."""

    class TestAdapter(ExchangeAdapter):
        def __init__(self) -> None:
            self.orders_placed: list[OrderRequest] = []

        async def connect(self) -> None:
            pass

        async def disconnect(self) -> None:
            pass

        async def subscribe_market(self, market_id: str) -> None:
            pass

        async def unsubscribe_market(self, market_id: str) -> None:
            pass

        async def place_order(self, order: OrderRequest) -> Order:
            self.orders_placed.append(order)
            return Order(
                id=f"ord_{len(self.orders_placed)}",
                client_order_id=order.client_order_id,
                market_id=order.market_id,
                side=order.side,
                order_side=order.order_side,
                price=order.price,
                size=order.size,
                filled_size=0,
                status=OrderStatus.OPEN,
                created_at=datetime.now(UTC),
                updated_at=datetime.now(UTC),
            )

        async def cancel_order(self, order_id: str) -> None:
            pass

        async def get_positions(self) -> list[Position]:
            return []

        async def get_balance(self) -> Balance:
            return Balance(total=Decimal("1000"), available=Decimal("1000"))

        async def get_open_orders(self, _market_id: str | None = None) -> list[Order]:
            return []

        def set_event_handler(self, handler: Callable[[Event], None]) -> None:
            pass

        @property
        def capabilities(self) -> ExchangeCapabilities:
            return ExchangeCapabilities(
                supports_order_amendment=False,
                supports_batch_orders=False,
                max_orders_per_request=1,
                rate_limit_writes_per_second=10,
                rate_limit_reads_per_second=20,
            )

    adapter = TestAdapter()
    request = OrderRequest.create(
        market_id="TEST",
        side=Side.YES,
        order_side=OrderSide.BUY,
        price=Price(Decimal("0.45")),
        size=Quantity(100),
    )

    result = await adapter.place_order(request)

    assert len(adapter.orders_placed) == 1
    assert result.id == "ord_1"
    assert result.status == OrderStatus.OPEN
    assert result.market_id == "TEST"


@pytest.mark.asyncio
async def test_websocket_connect_disconnect() -> None:
    """Test WebSocket connect/disconnect flow."""

    class TestWSClient(WebSocketClient):
        def __init__(self) -> None:
            self._connected = False

        async def connect(self) -> None:
            self._connected = True

        async def disconnect(self) -> None:
            self._connected = False

        async def subscribe(self, _channels: list[str]) -> None:
            if not self._connected:
                raise RuntimeError("Not connected")

        async def unsubscribe(self, channels: list[str]) -> None:
            pass

        def is_connected(self) -> bool:
            return self._connected

        def set_message_handler(self, handler: Callable[[dict], None]) -> None:
            pass

    client = TestWSClient()
    assert not client.is_connected()

    await client.connect()
    assert client.is_connected()

    await client.subscribe(["orderbook.TEST"])

    await client.disconnect()
    assert not client.is_connected()
