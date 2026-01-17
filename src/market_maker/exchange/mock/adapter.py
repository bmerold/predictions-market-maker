"""Mock exchange adapter for testing.

Provides a complete in-memory implementation of the exchange adapter
interface, useful for unit tests and paper trading simulations.
"""

from __future__ import annotations

from collections.abc import Callable
from datetime import UTC, datetime
from decimal import Decimal
from typing import TYPE_CHECKING

from market_maker.domain.events import Event
from market_maker.domain.orders import Order, OrderRequest, OrderStatus
from market_maker.domain.positions import Balance, Position
from market_maker.exchange.base import ExchangeAdapter, ExchangeCapabilities

if TYPE_CHECKING:
    from market_maker.exchange.factory import ExchangeConfig


class MockExchangeAdapter(ExchangeAdapter):
    """Mock exchange adapter for testing.

    All operations are in-memory and synchronous. Useful for:
    - Unit testing strategy and execution logic
    - Paper trading simulations
    - Development without exchange connectivity
    """

    def __init__(self, config: ExchangeConfig) -> None:
        """Initialize mock adapter.

        Args:
            config: Exchange configuration
        """
        self.config = config
        self._connected = False
        self._subscribed_markets: set[str] = set()
        self._orders: dict[str, Order] = {}
        self._positions: dict[str, Position] = {}
        self._balance = Balance(total=Decimal("10000"), available=Decimal("10000"))
        self._event_handler: Callable[[Event], None] | None = None
        self._order_counter = 0

    async def connect(self) -> None:
        """Simulate connection establishment."""
        self._connected = True

    async def disconnect(self) -> None:
        """Simulate disconnection."""
        self._connected = False
        self._subscribed_markets.clear()

    async def subscribe_market(self, market_id: str) -> None:
        """Add market to subscribed set."""
        self._subscribed_markets.add(market_id)

    async def unsubscribe_market(self, market_id: str) -> None:
        """Remove market from subscribed set."""
        self._subscribed_markets.discard(market_id)

    async def place_order(self, order: OrderRequest) -> Order:
        """Create and store an order.

        Args:
            order: Order request

        Returns:
            Created order with mock ID
        """
        self._order_counter += 1
        order_id = f"mock_ord_{self._order_counter:06d}"

        created_order = Order(
            id=order_id,
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

        self._orders[order_id] = created_order
        return created_order

    async def cancel_order(self, order_id: str) -> None:
        """Cancel an order.

        Args:
            order_id: Order ID to cancel

        Raises:
            OrderNotFoundError: If order doesn't exist
        """
        from market_maker.domain.errors import OrderNotFoundError

        if order_id not in self._orders:
            raise OrderNotFoundError(order_id)

        order = self._orders[order_id]
        self._orders[order_id] = order.with_status(OrderStatus.CANCELLED)

    async def get_positions(self) -> list[Position]:
        """Return all positions."""
        return list(self._positions.values())

    async def get_balance(self) -> Balance:
        """Return current balance."""
        return self._balance

    async def get_open_orders(self, market_id: str | None = None) -> list[Order]:
        """Return open orders, optionally filtered by market.

        Args:
            market_id: Optional market filter

        Returns:
            List of open orders
        """
        orders = [o for o in self._orders.values() if o.status.is_active()]
        if market_id:
            orders = [o for o in orders if o.market_id == market_id]
        return orders

    def set_event_handler(self, handler: Callable[[Event], None]) -> None:
        """Set event handler."""
        self._event_handler = handler

    @property
    def capabilities(self) -> ExchangeCapabilities:
        """Return mock capabilities."""
        return ExchangeCapabilities(
            supports_order_amendment=True,
            supports_batch_orders=True,
            max_orders_per_request=100,
            rate_limit_writes_per_second=1000,  # No real limits
            rate_limit_reads_per_second=1000,
        )

    # Test helpers

    def set_balance(self, total: Decimal, available: Decimal) -> None:
        """Set balance for testing."""
        self._balance = Balance(total=total, available=available)

    def set_position(self, position: Position) -> None:
        """Set a position for testing."""
        self._positions[position.market_id] = position

    def get_order(self, order_id: str) -> Order | None:
        """Get an order by ID for testing."""
        return self._orders.get(order_id)

    def fill_order(self, order_id: str, fill_size: int) -> Order:
        """Simulate a fill for testing.

        Args:
            order_id: Order to fill
            fill_size: Number of contracts to fill

        Returns:
            Updated order

        Raises:
            OrderNotFoundError: If order doesn't exist
        """
        from market_maker.domain.errors import OrderNotFoundError

        if order_id not in self._orders:
            raise OrderNotFoundError(order_id)

        order = self._orders[order_id]
        updated = order.with_fill(order.filled_size + fill_size)
        self._orders[order_id] = updated
        return updated

    def is_market_subscribed(self, market_id: str) -> bool:
        """Check if market is subscribed for testing."""
        return market_id in self._subscribed_markets
