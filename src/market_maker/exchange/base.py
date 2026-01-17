"""Exchange adapter abstractions.

Defines the interfaces that all exchange adapters must implement,
enabling the system to work with multiple exchanges through a
common abstraction.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Callable
from typing import TYPE_CHECKING, Any

from pydantic.dataclasses import dataclass

if TYPE_CHECKING:
    from market_maker.domain.events import Event
    from market_maker.domain.orders import Order, OrderRequest
    from market_maker.domain.positions import Balance, Position


@dataclass(frozen=True)
class ExchangeCapabilities:
    """Describes an exchange's capabilities.

    Used to handle differences between exchanges gracefully.
    """

    supports_order_amendment: bool
    """Whether the exchange supports amending orders in place."""

    supports_batch_orders: bool
    """Whether multiple orders can be submitted in one request."""

    max_orders_per_request: int
    """Maximum orders per batch request (1 if batching not supported)."""

    rate_limit_writes_per_second: int
    """Maximum write operations (orders, cancels) per second."""

    rate_limit_reads_per_second: int
    """Maximum read operations (positions, balance) per second."""


class ExchangeAdapter(ABC):
    """Abstract base for all exchange integrations.

    All exchange-specific code should be isolated in implementations
    of this interface. The core system depends only on this abstraction.

    Implementations must:
    - Handle authentication
    - Normalize data to domain models
    - Manage rate limiting
    - Handle reconnection
    """

    @abstractmethod
    async def connect(self) -> None:
        """Establish connection to the exchange.

        Should:
        - Authenticate if required
        - Establish WebSocket connection
        - Verify connectivity

        Raises:
            ExchangeError: If connection fails
        """
        ...

    @abstractmethod
    async def disconnect(self) -> None:
        """Gracefully disconnect from the exchange.

        Should:
        - Close WebSocket connection
        - Cancel any pending operations
        - Clean up resources
        """
        ...

    @abstractmethod
    async def subscribe_market(self, market_id: str) -> None:
        """Subscribe to market data for a market.

        Args:
            market_id: The market identifier

        Raises:
            ExchangeError: If subscription fails
        """
        ...

    @abstractmethod
    async def unsubscribe_market(self, market_id: str) -> None:
        """Unsubscribe from market data for a market.

        Args:
            market_id: The market identifier
        """
        ...

    @abstractmethod
    async def place_order(self, order: OrderRequest) -> Order:
        """Place an order on the exchange.

        Args:
            order: The order request to place

        Returns:
            The created order with exchange-assigned ID

        Raises:
            OrderRejectedError: If the exchange rejects the order
            ExchangeError: If there's a communication error
        """
        ...

    @abstractmethod
    async def cancel_order(self, order_id: str) -> None:
        """Cancel an order on the exchange.

        Args:
            order_id: The exchange-assigned order ID

        Raises:
            OrderNotFoundError: If the order doesn't exist
            ExchangeError: If there's a communication error
        """
        ...

    @abstractmethod
    async def get_positions(self) -> list[Position]:
        """Get current positions from the exchange.

        Returns:
            List of current positions

        Raises:
            ExchangeError: If there's a communication error
        """
        ...

    @abstractmethod
    async def get_balance(self) -> Balance:
        """Get current account balance from the exchange.

        Returns:
            Current balance information

        Raises:
            ExchangeError: If there's a communication error
        """
        ...

    @abstractmethod
    async def get_open_orders(self, market_id: str | None = None) -> list[Order]:
        """Get open orders from the exchange.

        Args:
            market_id: Optional market filter

        Returns:
            List of open orders

        Raises:
            ExchangeError: If there's a communication error
        """
        ...

    @abstractmethod
    def set_event_handler(self, handler: Callable[[Event], None]) -> None:
        """Set the handler for exchange events.

        The handler will be called for:
        - Order book updates
        - Fill notifications
        - Order status changes

        Args:
            handler: Callback function for events
        """
        ...

    @property
    @abstractmethod
    def capabilities(self) -> ExchangeCapabilities:
        """Return the exchange's capabilities."""
        ...


class WebSocketClient(ABC):
    """Abstract base for WebSocket connections.

    Handles the low-level WebSocket communication, providing
    a clean interface for the exchange adapter.
    """

    @abstractmethod
    async def connect(self) -> None:
        """Establish WebSocket connection.

        Raises:
            ExchangeError: If connection fails
        """
        ...

    @abstractmethod
    async def disconnect(self) -> None:
        """Close WebSocket connection gracefully."""
        ...

    @abstractmethod
    async def subscribe(self, channels: list[str]) -> None:
        """Subscribe to channels.

        Args:
            channels: List of channel names to subscribe to

        Raises:
            ExchangeError: If subscription fails
        """
        ...

    @abstractmethod
    async def unsubscribe(self, channels: list[str]) -> None:
        """Unsubscribe from channels.

        Args:
            channels: List of channel names to unsubscribe from
        """
        ...

    @abstractmethod
    def is_connected(self) -> bool:
        """Return True if WebSocket is connected."""
        ...

    @abstractmethod
    def set_message_handler(self, handler: Callable[[dict[str, Any]], None]) -> None:
        """Set handler for incoming messages.

        Args:
            handler: Callback for parsed JSON messages
        """
        ...
