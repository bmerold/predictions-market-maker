"""Skew calculator implementations.

Provides implementations of the SkewCalculator interface.
"""

from decimal import Decimal

from market_maker.strategy.components.base import SkewCalculator


class LinearSkew(SkewCalculator):
    """Linear inventory skew calculator.

    Implements a simple linear skew formula:
        skew = k * (q / Q_max)

    Where:
        - k is the intensity parameter
        - q is the current inventory
        - Q_max is the maximum inventory

    The skew shifts both quotes in the same direction to encourage
    inventory rebalancing:
    - Positive inventory → positive skew → shift quotes down → encourage buying
    - Negative inventory → negative skew → shift quotes up → encourage selling
    """

    def __init__(self, intensity: Decimal) -> None:
        """Initialize with intensity parameter.

        Args:
            intensity: Skew intensity (k parameter)
                       Typical range: 0.001 to 0.05
        """
        self._intensity = intensity

    @property
    def intensity(self) -> Decimal:
        """Return the intensity parameter."""
        return self._intensity

    def calculate(
        self,
        inventory: int,
        max_inventory: int,
        volatility: Decimal,  # noqa: ARG002
    ) -> Decimal:
        """Calculate linear skew.

        Args:
            inventory: Current position
            max_inventory: Maximum allowed position
            volatility: Not used in linear skew

        Returns:
            Skew adjustment (positive = shift down)
        """
        if max_inventory == 0:
            return Decimal("0")

        # Linear formula: skew = k * (q / Q_max)
        inventory_ratio = Decimal(inventory) / Decimal(max_inventory)
        return self._intensity * inventory_ratio
