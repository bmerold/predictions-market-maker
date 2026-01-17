"""Quote sizer implementations.

Provides implementations of the QuoteSizer interface.
"""

from market_maker.strategy.components.base import QuoteSizer


class AsymmetricSizer(QuoteSizer):
    """Asymmetric quote sizer that encourages inventory rebalancing.

    When long, reduces bid size (don't buy more) and maintains ask size.
    When short, reduces ask size (don't sell more) and maintains bid size.

    Formula:
        inventory_ratio = q / Q_max (clamped to [-1, 1])
        bid_factor = 1 - max(0, inventory_ratio)
        ask_factor = 1 + min(0, inventory_ratio)
        bid_size = round(base_size * bid_factor)
        ask_size = round(base_size * ask_factor)

    At max inventory (ratio = 1): bid_size = 0, ask_size = base_size
    At min inventory (ratio = -1): bid_size = base_size, ask_size = 0
    At zero inventory: both = base_size
    """

    def calculate(
        self,
        inventory: int,
        max_inventory: int,
        base_size: int,
    ) -> tuple[int, int]:
        """Calculate asymmetric bid and ask sizes.

        Args:
            inventory: Current position (positive = long)
            max_inventory: Maximum allowed position (absolute value)
            base_size: Base quote size at zero inventory

        Returns:
            Tuple of (bid_size, ask_size), both non-negative integers
        """
        if max_inventory == 0:
            return (base_size, base_size)

        # Calculate inventory ratio, clamped to [-1, 1]
        inventory_ratio = inventory / max_inventory
        inventory_ratio = max(-1.0, min(1.0, inventory_ratio))

        # Calculate scaling factors
        # When long (positive ratio): reduce bid
        # When short (negative ratio): reduce ask
        bid_factor = 1.0 - max(0.0, inventory_ratio)
        ask_factor = 1.0 + min(0.0, inventory_ratio)

        # Calculate sizes (ensure non-negative)
        bid_size = max(0, round(base_size * bid_factor))
        ask_size = max(0, round(base_size * ask_factor))

        return (bid_size, ask_size)
