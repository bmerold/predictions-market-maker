"""Fixed volatility estimator.

Provides a constant volatility value, useful for testing and
initial strategy development.
"""

from decimal import Decimal

from market_maker.domain.market_data import Trade
from market_maker.strategy.volatility.base import VolatilityEstimator


class FixedVolatilityEstimator(VolatilityEstimator):
    """Volatility estimator that returns a fixed constant value.

    Useful for testing, backtesting with known volatility, or
    when using externally computed volatility estimates.
    """

    def __init__(self, volatility: Decimal) -> None:
        """Initialize with a fixed volatility value.

        Args:
            volatility: The fixed volatility to return
        """
        self._volatility = volatility

    def update(self, trade: Trade) -> None:
        """No-op for fixed estimator.

        Args:
            trade: Ignored
        """
        # Fixed volatility ignores all updates

    def get_volatility(self) -> Decimal:
        """Return the fixed volatility value.

        Returns:
            The configured fixed volatility
        """
        return self._volatility

    def reset(self) -> None:
        """No-op for fixed estimator."""
        # Fixed volatility has no state to reset

    def is_ready(self) -> bool:
        """Fixed estimator is always ready.

        Returns:
            Always True
        """
        return True
