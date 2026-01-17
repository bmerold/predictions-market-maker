"""EWMA (Exponentially Weighted Moving Average) volatility estimator.

Implements the EWMA volatility model commonly used in financial applications.
"""

from decimal import Decimal

from market_maker.domain.market_data import Trade
from market_maker.strategy.volatility.base import VolatilityEstimator


class EWMAVolatilityEstimator(VolatilityEstimator):
    """EWMA volatility estimator.

    Implements the formula:
        σ²_t = α * r²_t + (1-α) * σ²_{t-1}

    Where:
        - σ²_t is the variance at time t
        - α is the decay factor (higher = more reactive to recent data)
        - r_t is the return at time t
        - σ²_{t-1} is the previous variance

    The volatility is the square root of the variance.
    """

    def __init__(
        self,
        alpha: Decimal,
        initial_volatility: Decimal,
        min_samples: int = 1,
    ) -> None:
        """Initialize the EWMA estimator.

        Args:
            alpha: Decay factor (0 < alpha < 1). Higher values weight
                   recent observations more heavily.
            initial_volatility: Starting volatility estimate
            min_samples: Minimum number of samples before is_ready() returns True
        """
        self._alpha = alpha
        self._initial_volatility = initial_volatility
        self._min_samples = min_samples

        # Current variance (volatility squared)
        self._variance = initial_volatility ** 2
        self._last_price: Decimal | None = None
        self._sample_count = 0

    @property
    def alpha(self) -> Decimal:
        """Return the decay factor."""
        return self._alpha

    @property
    def sample_count(self) -> int:
        """Return the number of samples processed."""
        return self._sample_count

    def update(self, trade: Trade) -> None:
        """Update volatility estimate with a new trade.

        Calculates the return from the previous price and updates
        the EWMA variance estimate.

        Args:
            trade: The trade to incorporate
        """
        current_price = trade.price.value
        self._sample_count += 1

        if self._last_price is not None:
            # Calculate simple return
            ret = (current_price - self._last_price) / self._last_price
            self._update_variance(ret)

        self._last_price = current_price

    def update_with_return(self, return_value: Decimal) -> None:
        """Update volatility estimate directly with a return value.

        Useful when you have pre-computed returns or want to
        update without trade objects.

        Args:
            return_value: The return to incorporate (e.g., 0.05 for 5%)
        """
        self._update_variance(return_value)
        self._sample_count += 1

    def _update_variance(self, return_value: Decimal) -> None:
        """Apply the EWMA formula to update variance.

        Args:
            return_value: The return to incorporate
        """
        # EWMA formula: σ²_t = α * r²_t + (1-α) * σ²_{t-1}
        return_squared = return_value ** 2
        one_minus_alpha = Decimal("1") - self._alpha
        self._variance = self._alpha * return_squared + one_minus_alpha * self._variance

    def get_volatility(self) -> Decimal:
        """Return the current volatility estimate.

        Returns:
            Square root of the EWMA variance
        """
        return self._variance.sqrt()

    def reset(self) -> None:
        """Reset to initial state."""
        self._variance = self._initial_volatility ** 2
        self._last_price = None
        self._sample_count = 0

    def is_ready(self) -> bool:
        """Check if enough samples have been collected.

        Returns:
            True if sample_count >= min_samples
        """
        return self._sample_count >= self._min_samples
