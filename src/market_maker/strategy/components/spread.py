"""Spread calculator implementations.

Provides implementations of the SpreadCalculator interface.
"""

from decimal import Decimal

from market_maker.strategy.components.base import SpreadCalculator


class FixedSpread(SpreadCalculator):
    """Fixed spread calculator.

    Returns a constant half-spread regardless of market conditions.
    Useful for simple strategies or testing.

    Formula:
        δ = max(base_spread, min_spread) / 2
    """

    def __init__(
        self,
        base_spread: Decimal,
        min_spread: Decimal = Decimal("0"),
    ) -> None:
        """Initialize with spread parameters.

        Args:
            base_spread: The full bid-ask spread width
            min_spread: Minimum allowed spread (default: 0)
        """
        self._base_spread = base_spread
        self._min_spread = min_spread

    @property
    def base_spread(self) -> Decimal:
        """Return the base spread parameter."""
        return self._base_spread

    def calculate(
        self,
        volatility: Decimal,  # noqa: ARG002
        inventory: int,  # noqa: ARG002
        max_inventory: int,  # noqa: ARG002
        time_to_settlement: float,  # noqa: ARG002
    ) -> Decimal:
        """Calculate fixed half-spread.

        Args:
            volatility: Not used
            inventory: Not used
            max_inventory: Not used
            time_to_settlement: Not used

        Returns:
            Half-spread (half of base_spread, respecting minimum)
        """
        effective_spread = max(self._base_spread, self._min_spread)
        return effective_spread / 2
