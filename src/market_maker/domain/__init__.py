"""Domain models for the trading system.

This package contains all domain models that are exchange-agnostic.
All models are immutable and use Decimal for prices.
"""

from market_maker.domain.errors import (
    ConfigurationError,
    ExchangeError,
    InsufficientBalanceError,
    OrderError,
    OrderNotFoundError,
    OrderRejectedError,
    RiskViolation,
    StaleDataError,
    TradingError,
)
from market_maker.domain.events import (
    BookUpdate,
    BookUpdateType,
    Event,
    EventType,
    FillEvent,
    OrderUpdate,
)
from market_maker.domain.market_data import (
    MarketSnapshot,
    OrderBook,
    PriceLevel,
    Trade,
)
from market_maker.domain.orders import (
    Fill,
    Order,
    OrderRequest,
    OrderStatus,
    Quote,
    QuoteSet,
)
from market_maker.domain.positions import Balance, PnLSnapshot, Position
from market_maker.domain.types import OrderSide, Price, Quantity, Side

__all__ = [
    # Types
    "OrderSide",
    "Price",
    "Quantity",
    "Side",
    # Market Data
    "MarketSnapshot",
    "OrderBook",
    "PriceLevel",
    "Trade",
    # Orders
    "Fill",
    "Order",
    "OrderRequest",
    "OrderStatus",
    "Quote",
    "QuoteSet",
    # Positions
    "Balance",
    "PnLSnapshot",
    "Position",
    # Events
    "BookUpdate",
    "BookUpdateType",
    "Event",
    "EventType",
    "FillEvent",
    "OrderUpdate",
    # Errors
    "ConfigurationError",
    "ExchangeError",
    "InsufficientBalanceError",
    "OrderError",
    "OrderNotFoundError",
    "OrderRejectedError",
    "RiskViolation",
    "StaleDataError",
    "TradingError",
]
