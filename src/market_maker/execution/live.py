"""Live execution engine for real order management.

Places actual orders on the exchange via REST API.
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime
from typing import TYPE_CHECKING

from market_maker.domain.market_data import OrderBook
from market_maker.domain.orders import (
    Fill,
    Order,
    OrderRequest,
    OrderStatus,
    QuoteSet,
)
from market_maker.execution.base import ExecutionEngine
from market_maker.execution.diff import OrderDiffer, QuoteOrders

if TYPE_CHECKING:
    from market_maker.exchange.base import ExchangeAdapter

logger = logging.getLogger(__name__)


class LiveExecutionEngine(ExecutionEngine):
    """Execution engine that places real orders on the exchange.

    Features:
    - Diff-based order updates to minimize API calls
    - Order state tracking
    - Fill collection from exchange events
    - Rate limit awareness
    """

    def __init__(self, exchange: ExchangeAdapter) -> None:
        """Initialize with exchange adapter.

        Args:
            exchange: Exchange adapter for order operations
        """
        self._exchange = exchange
        self._differ = OrderDiffer()

        # Track orders by ID
        self._orders: dict[str, Order] = {}

        # Track current quote orders by market
        self._quote_orders: dict[str, QuoteOrders] = {}

        # Collect fills
        self._fills: list[Fill] = []

    async def submit_order(
        self,
        request: OrderRequest,
        book: OrderBook,
    ) -> Order:
        """Submit an order to the exchange.

        Args:
            request: Order request to submit
            book: Current order book (unused for live, used for paper)

        Returns:
            Created Order object
        """
        try:
            order = await self._exchange.place_order(request)
            self._orders[order.id] = order
            logger.info(
                f"Order placed: {order.id} {order.order_side.value} "
                f"{order.size.value} {order.side.value} @ {order.price.value:.2f}"
            )
            return order
        except Exception as e:
            logger.error(f"Failed to place order: {e}")
            raise

    async def cancel_order(self, order_id: str) -> bool:
        """Cancel an order on the exchange.

        Args:
            order_id: ID of order to cancel

        Returns:
            True if cancelled successfully
        """
        try:
            await self._exchange.cancel_order(order_id)
            if order_id in self._orders:
                order = self._orders[order_id]
                self._orders[order_id] = Order(
                    id=order.id,
                    client_order_id=order.client_order_id,
                    market_id=order.market_id,
                    side=order.side,
                    order_side=order.order_side,
                    price=order.price,
                    size=order.size,
                    filled_size=order.filled_size,
                    status=OrderStatus.CANCELLED,
                    created_at=order.created_at,
                    updated_at=datetime.now(UTC),
                )
            logger.info(f"Order cancelled: {order_id}")
            return True
        except Exception as e:
            logger.error(f"Failed to cancel order {order_id}: {e}")
            return False

    async def cancel_all_orders(self, market_id: str) -> int:
        """Cancel all orders for a market.

        Args:
            market_id: Market to cancel orders for

        Returns:
            Number of orders cancelled
        """
        try:
            count = await self._exchange.cancel_all_orders(market_id)
            # Update local state
            for order_id, order in list(self._orders.items()):
                if order.market_id == market_id and order.status == OrderStatus.OPEN:
                    self._orders[order_id] = Order(
                        id=order.id,
                        client_order_id=order.client_order_id,
                        market_id=order.market_id,
                        side=order.side,
                        order_side=order.order_side,
                        price=order.price,
                        size=order.size,
                        filled_size=order.filled_size,
                        status=OrderStatus.CANCELLED,
                        created_at=order.created_at,
                        updated_at=datetime.now(UTC),
                    )
            # Clear quote orders for market
            self._quote_orders.pop(market_id, None)
            logger.info(f"Cancelled {count} orders for {market_id}")
            return count
        except Exception as e:
            logger.error(f"Failed to cancel orders for {market_id}: {e}")
            return 0

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
            if order.market_id == market_id and order.status == OrderStatus.OPEN
        ]

    def get_fills(self) -> list[Fill]:
        """Get all fills.

        Returns:
            List of all fills
        """
        return list(self._fills)

    def add_fill(self, fill: Fill) -> None:
        """Add a fill from the exchange.

        Called by the controller when a fill event is received.

        Args:
            fill: Fill to add
        """
        self._fills.append(fill)

        # Update order state if we have it
        if fill.order_id and fill.order_id in self._orders:
            order = self._orders[fill.order_id]
            new_filled = order.filled_size + fill.size.value
            new_status = (
                OrderStatus.FILLED
                if new_filled >= order.size.value
                else OrderStatus.PARTIALLY_FILLED
            )
            self._orders[fill.order_id] = Order(
                id=order.id,
                client_order_id=order.client_order_id,
                market_id=order.market_id,
                side=order.side,
                order_side=order.order_side,
                price=order.price,
                size=order.size,
                filled_size=new_filled,
                status=new_status,
                created_at=order.created_at,
                updated_at=datetime.now(UTC),
            )

    async def execute_quotes(
        self,
        quotes: QuoteSet,
        book: OrderBook,
    ) -> list[Fill]:
        """Execute quotes using diff-based order management.

        Compares new quotes to existing orders and only sends
        necessary updates (new orders, cancels, amends).

        Args:
            quotes: Quote set to execute
            book: Current order book

        Returns:
            List of fills (may be empty for live - fills come async)
        """
        market_id = quotes.market_id
        current = self._quote_orders.get(market_id)

        # Calculate diff
        actions = self._differ.diff(quotes, current)

        # Execute actions
        new_quote_orders = QuoteOrders(market_id=market_id)

        for action in actions:
            if action.action_type == "cancel" and action.order_id:
                await self.cancel_order(action.order_id)

            elif action.action_type == "new" and action.request:
                order = await self.submit_order(action.request, book)
                # Track which quote this order represents
                if action.quote_type == "yes_bid":
                    new_quote_orders.yes_bid_order = order
                elif action.quote_type == "yes_ask":
                    new_quote_orders.yes_ask_order = order
                elif action.quote_type == "no_bid":
                    new_quote_orders.no_bid_order = order
                elif action.quote_type == "no_ask":
                    new_quote_orders.no_ask_order = order

            elif action.action_type == "amend" and action.order_id and action.request:
                # Amend = cancel old + place new
                await self.cancel_order(action.order_id)
                order = await self.submit_order(action.request, book)
                if action.quote_type == "yes_bid":
                    new_quote_orders.yes_bid_order = order
                elif action.quote_type == "yes_ask":
                    new_quote_orders.yes_ask_order = order
                elif action.quote_type == "no_bid":
                    new_quote_orders.no_bid_order = order
                elif action.quote_type == "no_ask":
                    new_quote_orders.no_ask_order = order

            elif action.action_type == "keep" and action.order_id:
                # Keep existing order
                order = self._orders.get(action.order_id)
                if order:
                    if action.quote_type == "yes_bid":
                        new_quote_orders.yes_bid_order = order
                    elif action.quote_type == "yes_ask":
                        new_quote_orders.yes_ask_order = order
                    elif action.quote_type == "no_bid":
                        new_quote_orders.no_bid_order = order
                    elif action.quote_type == "no_ask":
                        new_quote_orders.no_ask_order = order

        # Update tracked quote orders
        self._quote_orders[market_id] = new_quote_orders

        # For live execution, fills come asynchronously via WebSocket
        # Return empty list - controller handles fill events separately
        return []

    async def sync_with_exchange(self, market_id: str) -> None:
        """Sync local state with exchange state.

        Reconciliation to ensure local tracking matches exchange.

        Args:
            market_id: Market to sync
        """
        try:
            exchange_orders = await self._exchange.get_open_orders(market_id)

            # Update local state with exchange state
            exchange_order_ids = {o.id for o in exchange_orders}

            # Mark orders as cancelled if not on exchange
            for order_id, order in list(self._orders.items()):
                if (
                    order.market_id == market_id
                    and order.status == OrderStatus.OPEN
                    and order_id not in exchange_order_ids
                ):
                    self._orders[order_id] = Order(
                        id=order.id,
                        client_order_id=order.client_order_id,
                        market_id=order.market_id,
                        side=order.side,
                        order_side=order.order_side,
                        price=order.price,
                        size=order.size,
                        filled_size=order.filled_size,
                        status=OrderStatus.CANCELLED,
                        created_at=order.created_at,
                        updated_at=datetime.now(UTC),
                    )

            # Add any orders from exchange we don't have
            for order in exchange_orders:
                if order.id not in self._orders:
                    self._orders[order.id] = order

            logger.debug(f"Synced {len(exchange_orders)} orders for {market_id}")

        except Exception as e:
            logger.error(f"Failed to sync orders for {market_id}: {e}")

    def update_order(self, order: Order) -> None:
        """Update order from exchange event.

        Args:
            order: Updated order
        """
        self._orders[order.id] = order
