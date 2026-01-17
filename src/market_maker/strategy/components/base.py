"""Abstract base classes for strategy components.

These define the interfaces for the pluggable components that
compose the strategy engine's quote generation pipeline.
"""

from abc import ABC, abstractmethod
from decimal import Decimal


class ReservationPriceCalculator(ABC):
    """Calculates inventory-adjusted fair value (reservation price).

    The reservation price represents the price at which the market maker
    is indifferent to buying or selling, given their current inventory.
    """

    @abstractmethod
    def calculate(
        self,
        mid_price: Decimal,
        inventory: int,
        volatility: Decimal,
        time_to_settlement: float,
    ) -> Decimal:
        """Calculate the reservation price.

        Args:
            mid_price: Current market mid price
            inventory: Current inventory position (positive = long, negative = short)
            volatility: Current volatility estimate
            time_to_settlement: Time remaining until settlement (hours or fraction)

        Returns:
            The reservation price adjusted for inventory
        """


class SkewCalculator(ABC):
    """Calculates quote skew based on inventory.

    Skew shifts both bid and ask quotes to encourage inventory rebalancing.
    Positive skew shifts quotes down (encourage buying), negative shifts up.
    """

    @abstractmethod
    def calculate(
        self,
        inventory: int,
        max_inventory: int,
        volatility: Decimal,
    ) -> Decimal:
        """Calculate the skew adjustment.

        Args:
            inventory: Current inventory position
            max_inventory: Maximum allowed inventory (absolute value)
            volatility: Current volatility estimate

        Returns:
            Skew adjustment (positive = shift down, negative = shift up)
        """


class SpreadCalculator(ABC):
    """Calculates bid-ask spread.

    Determines how wide to quote around the reservation price.
    """

    @abstractmethod
    def calculate(
        self,
        volatility: Decimal,
        inventory: int,
        max_inventory: int,
        time_to_settlement: float,
    ) -> Decimal:
        """Calculate the half-spread (distance from mid to bid/ask).

        Args:
            volatility: Current volatility estimate
            inventory: Current inventory position
            max_inventory: Maximum allowed inventory
            time_to_settlement: Time remaining until settlement

        Returns:
            Half-spread (δ) - the distance from mid to each quote
        """


class QuoteSizer(ABC):
    """Calculates quote sizes for bid and ask.

    Determines how many contracts to quote on each side based
    on inventory and risk limits.
    """

    @abstractmethod
    def calculate(
        self,
        inventory: int,
        max_inventory: int,
        base_size: int,
    ) -> tuple[int, int]:
        """Calculate bid and ask sizes.

        Args:
            inventory: Current inventory position
            max_inventory: Maximum allowed inventory
            base_size: Base quote size (when inventory is zero)

        Returns:
            Tuple of (bid_size, ask_size)
        """
