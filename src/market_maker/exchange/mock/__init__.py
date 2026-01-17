"""Mock exchange adapter for testing.

Provides a complete implementation of the exchange adapter interface
that operates entirely in memory, useful for unit tests and paper
trading simulations.
"""

from market_maker.exchange.mock.adapter import MockExchangeAdapter

__all__ = ["MockExchangeAdapter"]
