"""Strategy components for pluggable quote generation.

This package provides the component interfaces and default implementations
for the strategy engine's quote generation pipeline.
"""

from market_maker.strategy.components.base import (
    QuoteSizer,
    ReservationPriceCalculator,
    SkewCalculator,
    SpreadCalculator,
)
from market_maker.strategy.components.reservation import AvellanedaStoikovReservation
from market_maker.strategy.components.sizer import AsymmetricSizer
from market_maker.strategy.components.skew import LinearSkew
from market_maker.strategy.components.spread import FixedSpread

__all__ = [
    # ABCs
    "ReservationPriceCalculator",
    "SkewCalculator",
    "SpreadCalculator",
    "QuoteSizer",
    # Implementations
    "AvellanedaStoikovReservation",
    "LinearSkew",
    "FixedSpread",
    "AsymmetricSizer",
]
