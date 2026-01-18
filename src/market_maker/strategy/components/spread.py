"""Spread calculator implementations.

Provides implementations of the SpreadCalculator interface.
"""

import math
from decimal import Decimal

from market_maker.strategy.components.base import SpreadCalculator


class AvellanedaStoikovSpread(SpreadCalculator):
    """Avellaneda-Stoikov optimal spread calculator.

    Calculates spread based on the A-S formula which considers:
    - Volatility (σ): Higher vol → wider spread
    - Time to settlement (T): Less time → tighter spread
    - Risk aversion (γ): Higher γ → wider spread
    - Inventory: Higher inventory → asymmetric spread

    Formula (simplified):
        δ = γσ²T + (2/γ) × ln(1 + γ/k)

    For binary markets, we also enforce a minimum spread to cover fees.
    Maker fee at mid: ~0.44¢, so min spread ≈ 2-3¢ for profitability.

    NOTE: For binary markets (price 0-1), volatility should be in the same
    units (e.g., 0.10 = 10% std dev). Use the volatility parameter to
    override the global volatility estimate which may be scaled differently.
    """

    def __init__(
        self,
        gamma: Decimal,
        k: Decimal = Decimal("1.5"),  # Order arrival rate parameter
        min_spread: Decimal = Decimal("0.03"),  # Min 3¢ to cover fees
        max_spread: Decimal = Decimal("0.10"),  # Max 10¢ for binary markets
        volatility: Decimal | None = None,  # Override global volatility for spread calc
    ) -> None:
        """Initialize with A-S parameters.

        Args:
            gamma: Risk aversion (higher = wider spread, less inventory risk)
            k: Order arrival rate parameter (higher = tighter spread)
            min_spread: Minimum spread floor (to cover fees)
            max_spread: Maximum spread cap (for binary markets bounded 0-1)
            volatility: Fixed volatility for spread calc (overrides global estimate).
                        For binary markets, use 0.05-0.20. If None, uses global.

        NOTE: The classic A-S formula produces very large spreads for typical
        parameters. The max_spread cap makes it practical for binary markets.
        """
        self._gamma = gamma
        self._k = k
        self._min_spread = min_spread
        self._max_spread = max_spread
        self._volatility_override = volatility

    def calculate(
        self,
        volatility: Decimal,
        inventory: int,
        max_inventory: int,
        time_to_settlement: float,
    ) -> Decimal:
        """Calculate optimal half-spread using A-S formula.

        Args:
            volatility: Current volatility estimate (σ) - may be overridden
            inventory: Current position (for inventory penalty)
            max_inventory: Maximum allowed position
            time_to_settlement: Hours until settlement (T)

        Returns:
            Optimal half-spread
        """
        gamma = float(self._gamma)
        # Use override if set, otherwise use passed volatility
        sigma = float(self._volatility_override if self._volatility_override else volatility)
        k = float(self._k)
        T = max(time_to_settlement, 0.01)  # Avoid division by zero

        # A-S spread formula: δ = γσ²T + (2/γ) × ln(1 + γ/k)
        inventory_risk_term = gamma * (sigma ** 2) * T
        market_impact_term = (2 / gamma) * math.log(1 + gamma / k)

        optimal_spread = inventory_risk_term + market_impact_term

        # Add inventory penalty - widen spread when inventory is high
        if max_inventory > 0:
            inv_ratio = abs(inventory) / max_inventory
            inventory_penalty = inv_ratio * 0.02  # Up to 2¢ wider at max inventory
            optimal_spread += inventory_penalty

        # Convert to Decimal and clamp to [min_spread, max_spread]
        half_spread = Decimal(str(optimal_spread)) / 2
        min_half_spread = self._min_spread / 2
        max_half_spread = self._max_spread / 2

        return max(min_half_spread, min(half_spread, max_half_spread))


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
