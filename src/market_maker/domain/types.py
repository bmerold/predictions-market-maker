"""Core value objects for the trading system.

These types form the foundation of the domain model and are used throughout
the system. All types are immutable to ensure thread safety and prevent
accidental state mutation.
"""

from __future__ import annotations

from decimal import ROUND_HALF_UP, Decimal
from enum import Enum

from pydantic import field_validator
from pydantic.dataclasses import dataclass


@dataclass(frozen=True)
class Price:
    """Represents a price for binary contracts (0.01 to 0.99).

    Prices are stored as Decimal for precision. On Kalshi, prices are
    expressed as cents (1-99). On Polymarket, prices are in USDC.
    This domain model normalizes to a decimal probability.
    """

    value: Decimal

    @field_validator("value")
    @classmethod
    def validate_price_range(cls, v: Decimal) -> Decimal:
        """Ensure price is within valid range for binary contracts."""
        if v < Decimal("0.01") or v > Decimal("0.99"):
            raise ValueError("Price must be between 0.01 and 0.99")
        return v

    def as_cents(self) -> int:
        """Convert price to cents (1-99), rounding to nearest."""
        cents = self.value * Decimal("100")
        return int(cents.quantize(Decimal("1"), rounding=ROUND_HALF_UP))

    def as_probability(self) -> Decimal:
        """Return price as probability (same as value for binary contracts)."""
        return self.value

    def complement(self) -> Price:
        """Return complement price (1 - price) for YES/NO conversion.

        If YES price is 0.45, NO price is 0.55.
        """
        return Price(Decimal("1") - self.value)

    @classmethod
    def from_cents(cls, cents: int) -> Price:
        """Create a Price from cents (1-99)."""
        value = Decimal(cents) / Decimal("100")
        return cls(value)

    def __repr__(self) -> str:
        return f"Price({self.value})"


@dataclass(frozen=True)
class Quantity:
    """Represents a number of contracts.

    Quantities are always positive integers representing the number
    of contracts to buy/sell or currently held.
    """

    value: int

    @field_validator("value")
    @classmethod
    def validate_positive(cls, v: int) -> int:
        """Ensure quantity is positive."""
        if v <= 0:
            raise ValueError("Quantity must be positive")
        return v

    def __repr__(self) -> str:
        return f"Quantity({self.value})"


class Side(str, Enum):
    """Contract side: YES or NO.

    Binary prediction markets have two outcomes. On Kalshi these are
    explicitly YES/NO. On Polymarket they are outcome tokens.
    """

    YES = "yes"
    NO = "no"

    def opposite(self) -> Side:
        """Return the opposite side."""
        return Side.NO if self == Side.YES else Side.YES


class OrderSide(str, Enum):
    """Order direction: BUY or SELL.

    Indicates whether an order is to buy or sell contracts.
    """

    BUY = "buy"
    SELL = "sell"

    def opposite(self) -> OrderSide:
        """Return the opposite order side."""
        return OrderSide.SELL if self == OrderSide.BUY else OrderSide.BUY
