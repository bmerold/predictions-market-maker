"""Exchange adapters for the trading system.

This package contains the exchange abstraction layer and concrete
implementations for supported exchanges.
"""

from market_maker.exchange.base import (
    ExchangeAdapter,
    ExchangeCapabilities,
    WebSocketClient,
)
from market_maker.exchange.factory import (
    ExchangeConfig,
    ExchangeType,
    create_adapter,
    register_adapter,
)

__all__ = [
    "ExchangeAdapter",
    "ExchangeCapabilities",
    "ExchangeConfig",
    "ExchangeType",
    "WebSocketClient",
    "create_adapter",
    "register_adapter",
]
