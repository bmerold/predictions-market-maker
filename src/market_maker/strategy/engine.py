"""Strategy engine for quote generation.

Composes pluggable components to generate market-making quotes
using the Avellaneda-Stoikov framework.
"""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal

from pydantic.dataclasses import dataclass

from market_maker.domain.orders import Quote, QuoteSet
from market_maker.domain.types import Price, Quantity
from market_maker.strategy.components.base import (
    QuoteSizer,
    ReservationPriceCalculator,
    SkewCalculator,
    SpreadCalculator,
)
from market_maker.strategy.volatility.base import VolatilityEstimator

# Price bounds for binary prediction markets
MIN_PRICE = Decimal("0.01")
MAX_PRICE = Decimal("0.99")


@dataclass(frozen=True)
class StrategyInput:
    """Input data for quote generation.

    Contains all market and position data needed to generate quotes.
    """

    market_id: str
    mid_price: Price  # Current market mid price
    inventory: int  # Current position (positive = long YES)
    max_inventory: int  # Maximum allowed position
    base_size: int  # Base quote size
    time_to_settlement: float  # Hours until settlement
    timestamp: datetime  # Current time


class StrategyEngine:
    """Composes strategy components to generate quotes.

    Pipeline:
    1. VolatilityEstimator → σ (volatility)
    2. ReservationPriceCalculator → r (inventory-adjusted fair value)
    3. SkewCalculator → skew (additional inventory adjustment)
    4. SpreadCalculator → δ (half-spread)
    5. QuoteSizer → (bid_size, ask_size)

    Quote calculation:
    - YES bid = reservation - skew - half_spread
    - YES ask = reservation - skew + half_spread
    - NO bid = 1 - YES ask
    - NO ask = 1 - YES bid
    """

    def __init__(
        self,
        volatility_estimator: VolatilityEstimator,
        reservation_calculator: ReservationPriceCalculator,
        skew_calculator: SkewCalculator,
        spread_calculator: SpreadCalculator,
        sizer: QuoteSizer,
    ) -> None:
        """Initialize with pluggable components.

        Args:
            volatility_estimator: Provides volatility estimates
            reservation_calculator: Calculates reservation price
            skew_calculator: Calculates inventory skew
            spread_calculator: Calculates bid-ask spread
            sizer: Calculates quote sizes
        """
        self._volatility = volatility_estimator
        self._reservation = reservation_calculator
        self._skew = skew_calculator
        self._spread = spread_calculator
        self._sizer = sizer

    @property
    def volatility_estimator(self) -> VolatilityEstimator:
        """Return the volatility estimator for external updates."""
        return self._volatility

    def generate_quotes(self, input_data: StrategyInput) -> QuoteSet:
        """Generate a complete quote set for a market.

        Args:
            input_data: Market and position data

        Returns:
            QuoteSet with YES bid/ask quotes (NO derived from YES)
        """
        # Step 1: Get volatility
        volatility = self._volatility.get_volatility()

        # Step 2: Calculate reservation price
        reservation = self._reservation.calculate(
            mid_price=input_data.mid_price.value,
            inventory=input_data.inventory,
            volatility=volatility,
            time_to_settlement=input_data.time_to_settlement,
        )

        # Step 3: Calculate skew
        skew = self._skew.calculate(
            inventory=input_data.inventory,
            max_inventory=input_data.max_inventory,
            volatility=volatility,
        )

        # Step 4: Calculate half-spread
        half_spread = self._spread.calculate(
            volatility=volatility,
            inventory=input_data.inventory,
            max_inventory=input_data.max_inventory,
            time_to_settlement=input_data.time_to_settlement,
        )

        # Step 5: Calculate sizes (ensure minimum of 1 for valid quotes)
        raw_bid_size, raw_ask_size = self._sizer.calculate(
            inventory=input_data.inventory,
            max_inventory=input_data.max_inventory,
            base_size=input_data.base_size,
        )
        bid_size = max(1, raw_bid_size)
        ask_size = max(1, raw_ask_size)

        # Step 6: Calculate quote prices
        # Apply skew to shift the midpoint, then apply spread
        adjusted_mid = reservation - skew
        raw_bid = adjusted_mid - half_spread
        raw_ask = adjusted_mid + half_spread

        # Clamp to valid price range
        bid_price = self._clamp_price(raw_bid)
        ask_price = self._clamp_price(raw_ask)

        # Ensure bid < ask after clamping
        if bid_price >= ask_price:
            # If they cross after clamping, create minimal spread
            mid = (bid_price + ask_price) / 2
            bid_price = self._clamp_price(mid - Decimal("0.01"))
            ask_price = self._clamp_price(mid + Decimal("0.01"))

        # Create YES quote
        yes_quote = Quote(
            bid_price=Price(bid_price),
            bid_size=Quantity(bid_size),
            ask_price=Price(ask_price),
            ask_size=Quantity(ask_size),
        )

        return QuoteSet(
            market_id=input_data.market_id,
            yes_quote=yes_quote,
            timestamp=input_data.timestamp,
        )

    @staticmethod
    def _clamp_price(price: Decimal) -> Decimal:
        """Clamp price to valid range [MIN_PRICE, MAX_PRICE].

        Args:
            price: Raw price value

        Returns:
            Price clamped to valid bounds
        """
        return max(MIN_PRICE, min(MAX_PRICE, price))
