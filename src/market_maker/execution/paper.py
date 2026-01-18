"""Paper execution engine for simulated trading.

Simulates order execution against live market data without
placing real orders on the exchange.
"""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import uuid4

from market_maker.domain.market_data import OrderBook
from market_maker.domain.orders import Fill, Order, OrderRequest, OrderStatus
from market_maker.domain.types import OrderSide, Price, Quantity, Side
from market_maker.execution.base import ExecutionEngine


class PaperExecutionEngine(ExecutionEngine):
    """Simulates order execution for paper trading.

    Features:
    - Simulates fills against live order book
    - Tracks open orders and fills
    - Supports partial fills based on book liquidity
    - All fills marked as simulated

    Does NOT:
    - Place real orders on exchange
    - Simulate market impact
    - Simulate latency
    """

    def __init__(self) -> None:
        """Initialize the paper execution engine."""
        self._orders: dict[str, Order] = {}  # order_id -> Order
        self._fills: list[Fill] = []

    def submit_order(
        self,
        request: OrderRequest,
        book: OrderBook,
    ) -> Order:
        """Submit an order for execution.

        Immediately checks if order crosses the spread and simulates fill.

        Args:
            request: Order request to submit
            book: Current order book for fill simulation

        Returns:
            Created Order object
        """
        order_id = f"paper_{uuid4().hex[:12]}"
        now = datetime.now(UTC)

        order = Order(
            id=order_id,
            client_order_id=request.client_order_id,
            market_id=request.market_id,
            side=request.side,
            order_side=request.order_side,
            price=request.price,
            size=request.size,
            filled_size=0,
            status=OrderStatus.OPEN,
            created_at=now,
            updated_at=now,
        )

        self._orders[order_id] = order

        # Try to fill immediately
        self._try_fill(order, book)

        return self._orders.get(order_id, order)

    def cancel_order(self, order_id: str) -> bool:
        """Cancel an open order.

        Args:
            order_id: ID of order to cancel

        Returns:
            True if cancelled, False if order not found or not cancellable
        """
        order = self._orders.get(order_id)
        if order is None:
            return False

        if order.status.is_terminal():
            return False

        self._orders[order_id] = order.with_status(OrderStatus.CANCELLED)
        return True

    def cancel_all_orders(self, market_id: str) -> int:
        """Cancel all open orders for a market.

        Args:
            market_id: Market to cancel orders for

        Returns:
            Number of orders cancelled
        """
        count = 0
        for order_id, order in list(self._orders.items()):
            if order.market_id == market_id and order.status.is_active():
                self._orders[order_id] = order.with_status(OrderStatus.CANCELLED)
                count += 1
        return count

    def get_order(self, order_id: str) -> Order | None:
        """Get an order by ID.

        Args:
            order_id: Order ID

        Returns:
            Order or None if not found
        """
        return self._orders.get(order_id)

    def get_open_orders(self, market_id: str) -> list[Order]:
        """Get all open orders for a market.

        Args:
            market_id: Market to get orders for

        Returns:
            List of open orders
        """
        return [
            order
            for order in self._orders.values()
            if order.market_id == market_id and order.status.is_active()
        ]

    def get_fills(self) -> list[Fill]:
        """Get all fills.

        Returns:
            List of all fills
        """
        return list(self._fills)

    def _try_fill(self, order: Order, book: OrderBook) -> None:
        """Try to fill an order against the book.

        Args:
            order: Order to try filling
            book: Order book to match against
        """
        # Get the relevant book level for fill check
        fill_price, available_size = self._get_matching_level(order, book)

        if fill_price is None or available_size == 0:
            return  # No fill possible

        # Check if order price crosses
        if not self._price_crosses(order, fill_price):
            return  # Order doesn't cross

        # Calculate fill size
        fill_size = min(order.size.value, available_size)

        # Create fill
        fill = Fill(
            id=f"fill_{uuid4().hex[:12]}",
            order_id=order.id,
            market_id=order.market_id,
            side=order.side,
            order_side=order.order_side,
            price=fill_price,
            size=Quantity(fill_size),
            timestamp=datetime.now(UTC),
            is_simulated=True,
        )
        self._fills.append(fill)

        # Update order
        self._orders[order.id] = order.with_fill(fill_size)

    def _get_matching_level(
        self,
        order: Order,
        book: OrderBook,
    ) -> tuple[Price | None, int]:
        """Get the book level that could fill this order.

        Args:
            order: Order to match
            book: Order book

        Returns:
            Tuple of (fill_price, available_size)
        """
        if order.side == Side.YES:
            if order.order_side == OrderSide.BUY:
                # YES BUY matches against YES asks
                best = book.best_ask()
                return (best.price, best.size.value) if best else (None, 0)
            else:
                # YES SELL matches against YES bids
                best = book.best_bid()
                return (best.price, best.size.value) if best else (None, 0)
        else:
            # NO orders - convert prices
            # NO BUY = buying NO = selling YES on the other side
            # NO bid matches against YES ask (converted)
            if order.order_side == OrderSide.BUY:
                # NO BUY at X means willing to pay X for NO
                # This is equivalent to selling YES at 1-X
                # So match against YES ask
                best = book.best_ask()
                if best:
                    # Return the NO-equivalent price
                    no_price = best.price.complement()
                    return (no_price, best.size.value)
                return (None, 0)
            else:
                # NO SELL at X means willing to sell NO at X
                # This is equivalent to buying YES at 1-X
                # So match against YES bid
                best = book.best_bid()
                if best:
                    no_price = best.price.complement()
                    return (no_price, best.size.value)
                return (None, 0)

    def _price_crosses(self, order: Order, fill_price: Price) -> bool:
        """Check if order price crosses the available fill price.

        Args:
            order: Order to check
            fill_price: Price at which fill would occur

        Returns:
            True if order would fill
        """
        if order.order_side == OrderSide.BUY:
            # Buy crosses if order price >= fill price
            return order.price.value >= fill_price.value
        else:
            # Sell crosses if order price <= fill price
            return order.price.value <= fill_price.value
