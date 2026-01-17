"""Reservation price calculator implementations.

Provides implementations of the ReservationPriceCalculator interface.
"""

from decimal import Decimal

from market_maker.strategy.components.base import ReservationPriceCalculator


class AvellanedaStoikovReservation(ReservationPriceCalculator):
    """Avellaneda-Stoikov reservation price calculator.

    Implements the Avellaneda-Stoikov formula for optimal market making:
        r = s - q / (γ * σ² * T)

    Where:
        - r is the reservation price
        - s is the mid price
        - q is the inventory
        - γ (gamma) is the risk aversion parameter
        - σ is the volatility
        - T is the time to settlement

    Higher gamma (more risk averse) reduces the inventory adjustment.
    As T→0, the adjustment increases (more urgency to flatten inventory).
    """

    def __init__(self, gamma: Decimal) -> None:
        """Initialize with risk aversion parameter.

        Args:
            gamma: Risk aversion parameter (typical range: 0.01 to 1.0)
                   Higher values = more risk averse = smaller adjustments
        """
        self._gamma = gamma

    @property
    def gamma(self) -> Decimal:
        """Return the risk aversion parameter."""
        return self._gamma

    def calculate(
        self,
        mid_price: Decimal,
        inventory: int,
        volatility: Decimal,
        time_to_settlement: float,
    ) -> Decimal:
        """Calculate reservation price using A-S formula.

        Handles edge cases:
        - Zero time: Returns mid price (can't adjust)
        - Zero volatility: Returns mid price (can't price risk)
        - Large adjustments: Clamped to reasonable bounds

        Args:
            mid_price: Current market mid price
            inventory: Current position (positive = long)
            volatility: Current volatility estimate
            time_to_settlement: Time until settlement in hours

        Returns:
            Reservation price adjusted for inventory
        """
        # Handle edge cases to avoid division by zero
        if time_to_settlement <= 0 or volatility <= 0:
            return mid_price

        # A-S formula: r = s - q / (γ * σ² * T)
        variance = volatility ** 2
        denominator = self._gamma * variance * Decimal(str(time_to_settlement))

        if denominator == 0:
            return mid_price

        adjustment = Decimal(inventory) / denominator
        reservation = mid_price - adjustment

        return reservation
