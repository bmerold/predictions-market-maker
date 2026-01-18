"""Base execution engine interface.

Defines the abstract interface for all execution engines.
"""

from __future__ import annotations

from abc import ABC, abstractmethod

from market_maker.domain.market_data import OrderBook
from market_maker.domain.orders import Fill, Order, OrderRequest, QuoteSet


class ExecutionEngine(ABC):
    """Abstract base for execution engines.

    Execution engines handle order placement and fill simulation/execution.
    Implementations include paper trading (simulated) and live trading.
    """

    @abstractmethod
    def submit_order(
        self,
        request: OrderRequest,
        book: OrderBook,
    ) -> Order:
        """Submit an order for execution.

        Args:
            request: Order request to submit
            book: Current order book for fill simulation

        Returns:
            Created Order object
        """
        ...

    @abstractmethod
    def cancel_order(self, order_id: str) -> bool:
        """Cancel an open order.

        Args:
            order_id: ID of order to cancel

        Returns:
            True if cancelled, False if order not found or not cancellable
        """
        ...

    @abstractmethod
    def cancel_all_orders(self, market_id: str) -> int:
        """Cancel all open orders for a market.

        Args:
            market_id: Market to cancel orders for

        Returns:
            Number of orders cancelled
        """
        ...

    @abstractmethod
    def get_order(self, order_id: str) -> Order | None:
        """Get an order by ID.

        Args:
            order_id: Order ID

        Returns:
            Order or None if not found
        """
        ...

    @abstractmethod
    def get_open_orders(self, market_id: str) -> list[Order]:
        """Get all open orders for a market.

        Args:
            market_id: Market to get orders for

        Returns:
            List of open orders
        """
        ...

    @abstractmethod
    def get_fills(self) -> list[Fill]:
        """Get all fills.

        Returns:
            List of all fills
        """
        ...

    def execute_quotes(
        self,
        quotes: QuoteSet,
        book: OrderBook,
    ) -> list[Fill]:
        """Execute a set of quotes against the order book.

        Convenience method that submits orders for all quotes and returns fills.

        Args:
            quotes: Quote set to execute
            book: Current order book

        Returns:
            List of fills generated
        """
        initial_fill_count = len(self.get_fills())

        for request in quotes.to_order_requests():
            self.submit_order(request, book)

        # Return new fills
        all_fills = self.get_fills()
        fills = all_fills[initial_fill_count:]
        return fills
