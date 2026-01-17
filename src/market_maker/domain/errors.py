"""Exception hierarchy for trading system errors.

All trading-related errors inherit from TradingError, allowing code to catch
broad categories of errors. Each error type includes relevant context for
debugging and logging.

Error categories:
- ExchangeError: Issues with exchange connectivity or API
- OrderError: Order placement, cancellation, or execution failures
- RiskViolation: Pre-trade risk check failures
- StaleDataError: Market data freshness issues
- ConfigurationError: Invalid configuration
"""

from __future__ import annotations

from typing import Any


class TradingError(Exception):
    """Base exception for all trading-related errors.

    All errors in the trading system inherit from this class, allowing
    code to catch broad categories of errors when needed.
    """

    def __init__(self, message: str, context: dict[str, Any] | None = None) -> None:
        """Initialize with message and optional context.

        Args:
            message: Human-readable error description
            context: Additional structured data for logging/debugging
        """
        super().__init__(message)
        self.context = context or {}


class ExchangeError(TradingError):
    """Error related to exchange connectivity or API.

    Raised when:
    - WebSocket connection fails
    - REST API returns unexpected errors
    - Authentication fails
    - Rate limits are hit
    """

    def __init__(
        self,
        message: str,
        exchange: str | None = None,
        context: dict[str, Any] | None = None,
    ) -> None:
        """Initialize with message and exchange name.

        Args:
            message: Human-readable error description
            exchange: Name of the exchange (e.g., "kalshi", "polymarket")
            context: Additional structured data
        """
        super().__init__(message, context)
        self.exchange = exchange


class OrderError(TradingError):
    """Error related to order operations.

    Base class for order-specific errors. Stores order_id when available.
    """

    def __init__(
        self,
        message: str,
        order_id: str | None = None,
        context: dict[str, Any] | None = None,
    ) -> None:
        """Initialize with message and order ID.

        Args:
            message: Human-readable error description
            order_id: The order ID involved in the error
            context: Additional structured data
        """
        super().__init__(message, context)
        self.order_id = order_id


class OrderNotFoundError(OrderError):
    """Order not found on exchange.

    Raised when attempting to cancel or query an order that doesn't exist.
    This may indicate the order was already filled or cancelled.
    """

    def __init__(self, order_id: str, context: dict[str, Any] | None = None) -> None:
        """Initialize with order ID.

        Args:
            order_id: The order ID that was not found
            context: Additional structured data
        """
        super().__init__(f"Order not found: {order_id}", order_id, context)


class OrderRejectedError(OrderError):
    """Order was rejected by the exchange.

    Raised when the exchange refuses to accept an order, typically due to:
    - Invalid price
    - Insufficient balance
    - Market closed
    - Position limits exceeded on exchange side
    """

    def __init__(
        self,
        message: str,
        order_id: str | None = None,
        reason: str | None = None,
        context: dict[str, Any] | None = None,
    ) -> None:
        """Initialize with message and rejection reason.

        Args:
            message: Human-readable error description
            order_id: The order ID that was rejected
            reason: Exchange-specific rejection reason code
            context: Additional structured data
        """
        super().__init__(message, order_id, context)
        self.reason = reason


class RiskViolation(TradingError):
    """Pre-trade risk check failed.

    Raised when a proposed trade would violate risk limits:
    - Position size limits
    - Exposure limits
    - PnL limits (daily/hourly loss)
    - Order size limits
    """

    def __init__(
        self,
        message: str,
        rule_name: str | None = None,
        limit_value: float | int | None = None,
        actual_value: float | int | None = None,
        context: dict[str, Any] | None = None,
    ) -> None:
        """Initialize with rule details.

        Args:
            message: Human-readable error description
            rule_name: Name of the risk rule that was violated
            limit_value: The configured limit that was exceeded
            actual_value: The actual value that exceeded the limit
            context: Additional structured data
        """
        super().__init__(message, context)
        self.rule_name = rule_name
        self.limit_value = limit_value
        self.actual_value = actual_value


class StaleDataError(TradingError):
    """Market data is stale.

    Raised when market data hasn't been updated within the acceptable
    freshness threshold. Trading on stale data is dangerous and should
    be avoided.
    """

    def __init__(
        self,
        message: str,
        age_seconds: float | None = None,
        max_age_seconds: float | None = None,
        context: dict[str, Any] | None = None,
    ) -> None:
        """Initialize with data age information.

        Args:
            message: Human-readable error description
            age_seconds: How old the data actually is
            max_age_seconds: Maximum acceptable age
            context: Additional structured data
        """
        super().__init__(message, context)
        self.age_seconds = age_seconds
        self.max_age_seconds = max_age_seconds


class InsufficientBalanceError(TradingError):
    """Insufficient account balance for operation.

    Raised when:
    - Order would require more capital than available
    - Account balance is below minimum trading threshold
    """

    def __init__(
        self,
        message: str,
        required: float | None = None,
        available: float | None = None,
        context: dict[str, Any] | None = None,
    ) -> None:
        """Initialize with balance information.

        Args:
            message: Human-readable error description
            required: Amount required for the operation
            available: Amount currently available
            context: Additional structured data
        """
        super().__init__(message, context)
        self.required = required
        self.available = available


class ConfigurationError(TradingError):
    """Invalid configuration.

    Raised when:
    - Configuration file is malformed
    - Required configuration values are missing
    - Configuration values fail validation
    """

    def __init__(
        self,
        message: str,
        field: str | None = None,
        context: dict[str, Any] | None = None,
    ) -> None:
        """Initialize with field information.

        Args:
            message: Human-readable error description
            field: Name of the configuration field with the issue
            context: Additional structured data
        """
        super().__init__(message, context)
        self.field = field
