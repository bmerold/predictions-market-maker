"""Market data domain models.

These models represent market data received from exchanges, normalized
to a common format. All models are immutable.
"""

from __future__ import annotations

from datetime import datetime, timedelta
from decimal import Decimal

from pydantic.dataclasses import dataclass

from market_maker.domain.types import Price, Quantity, Side


@dataclass(frozen=True)
class PriceLevel:
    """A single price level in an order book.

    Represents quantity available at a specific price.
    """

    price: Price
    size: Quantity

    @classmethod
    def from_cents(cls, price_cents: int, size: int) -> PriceLevel:
        """Create a PriceLevel from cents and raw size.

        Args:
            price_cents: Price in cents (1-99)
            size: Number of contracts

        Returns:
            PriceLevel with converted price
        """
        return cls(
            price=Price.from_cents(price_cents),
            size=Quantity(size),
        )


@dataclass(frozen=True)
class OrderBook:
    """Order book for a binary market.

    Contains bid and ask levels for the YES side. NO side levels are
    derived from YES side using price complement (NO_bid = 1 - YES_ask).

    Bids are sorted descending by price (best bid first).
    Asks are sorted ascending by price (best ask first).
    """

    market_id: str
    yes_bids: list[PriceLevel]
    yes_asks: list[PriceLevel]
    timestamp: datetime

    def best_bid(self) -> PriceLevel | None:
        """Return the highest bid, or None if no bids."""
        if not self.yes_bids:
            return None
        return max(self.yes_bids, key=lambda x: x.price.value)

    def best_ask(self) -> PriceLevel | None:
        """Return the lowest ask, or None if no asks."""
        if not self.yes_asks:
            return None
        return min(self.yes_asks, key=lambda x: x.price.value)

    def mid_price(self) -> Price | None:
        """Return the mid-price, or None if book is empty on either side."""
        bid = self.best_bid()
        ask = self.best_ask()
        if bid is None or ask is None:
            return None
        mid = (bid.price.value + ask.price.value) / 2
        return Price(mid)

    def spread(self) -> Decimal | None:
        """Return the spread (best_ask - best_bid), or None if empty."""
        bid = self.best_bid()
        ask = self.best_ask()
        if bid is None or ask is None:
            return None
        return ask.price.value - bid.price.value

    def no_bids(self) -> list[PriceLevel]:
        """Derive NO bids from YES asks.

        NO bid price = 1 - YES ask price.
        Returns levels sorted descending by price.
        """
        levels = [
            PriceLevel(price=level.price.complement(), size=level.size)
            for level in self.yes_asks
        ]
        return sorted(levels, key=lambda x: x.price.value, reverse=True)

    def no_asks(self) -> list[PriceLevel]:
        """Derive NO asks from YES bids.

        NO ask price = 1 - YES bid price.
        Returns levels sorted ascending by price.
        """
        levels = [
            PriceLevel(price=level.price.complement(), size=level.size)
            for level in self.yes_bids
        ]
        return sorted(levels, key=lambda x: x.price.value)


@dataclass(frozen=True)
class Trade:
    """A single trade that occurred in the market."""

    market_id: str
    price: Price
    size: Quantity
    side: Side
    timestamp: datetime

    @classmethod
    def from_cents(
        cls,
        market_id: str,
        price_cents: int,
        size: int,
        side: Side,
        timestamp: datetime,
    ) -> Trade:
        """Create a Trade from cents.

        Args:
            market_id: Market identifier
            price_cents: Price in cents (1-99)
            size: Number of contracts
            side: YES or NO
            timestamp: When the trade occurred

        Returns:
            Trade with converted price
        """
        return cls(
            market_id=market_id,
            price=Price.from_cents(price_cents),
            size=Quantity(size),
            side=side,
            timestamp=timestamp,
        )


@dataclass(frozen=True)
class MarketSnapshot:
    """Aggregated market data snapshot.

    Contains derived data useful for strategy decisions.
    """

    market_id: str
    mid_price: Price
    spread: Decimal
    best_bid: PriceLevel
    best_ask: PriceLevel
    volatility: Decimal
    time_to_settlement: timedelta
    timestamp: datetime

    @classmethod
    def from_order_book(
        cls,
        book: OrderBook,
        volatility: Decimal,
        time_to_settlement: timedelta,
    ) -> MarketSnapshot:
        """Create a snapshot from an order book.

        Args:
            book: The order book to derive data from
            volatility: Current volatility estimate
            time_to_settlement: Time until market settles

        Returns:
            MarketSnapshot with derived data

        Raises:
            ValueError: If order book is empty on either side
        """
        best_bid = book.best_bid()
        best_ask = book.best_ask()

        if best_bid is None or best_ask is None:
            raise ValueError("Cannot create snapshot from empty order book")

        mid_price = book.mid_price()
        spread = book.spread()

        if mid_price is None or spread is None:
            raise ValueError("Cannot compute mid price or spread")

        return cls(
            market_id=book.market_id,
            mid_price=mid_price,
            spread=spread,
            best_bid=best_bid,
            best_ask=best_ask,
            volatility=volatility,
            time_to_settlement=time_to_settlement,
            timestamp=book.timestamp,
        )
