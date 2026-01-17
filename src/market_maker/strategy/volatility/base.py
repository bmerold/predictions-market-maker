"""Base volatility estimator interface.

Defines the abstract interface for volatility estimation components.
"""

from abc import ABC, abstractmethod
from decimal import Decimal

from market_maker.domain.market_data import Trade


class VolatilityEstimator(ABC):
    """Abstract base class for volatility estimators.

    Volatility estimators track price movements and provide volatility
    estimates used by the strategy engine for spread calculation and
    risk adjustment.
    """

    @abstractmethod
    def update(self, trade: Trade) -> None:
        """Update the estimator with a new trade.

        Args:
            trade: The trade to incorporate into the estimate
        """

    @abstractmethod
    def get_volatility(self) -> Decimal:
        """Get the current volatility estimate.

        Returns:
            Current volatility estimate as a decimal
        """

    @abstractmethod
    def reset(self) -> None:
        """Reset the estimator to its initial state."""

    @abstractmethod
    def is_ready(self) -> bool:
        """Check if the estimator has enough data to provide reliable estimates.

        Returns:
            True if the estimator is ready, False otherwise
        """
