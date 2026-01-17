"""Position and PnL domain models.

These models track positions held and profit/loss calculations.
All models are immutable.
"""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal

from pydantic.dataclasses import dataclass

from market_maker.domain.types import Price


@dataclass(frozen=True)
class Position:
    """Position in a single market.

    Tracks quantities of YES and NO contracts held, along with
    average entry prices for PnL calculations.
    """

    market_id: str
    yes_quantity: int
    no_quantity: int
    avg_yes_price: Price | None  # None if no YES position
    avg_no_price: Price | None  # None if no NO position

    def net_inventory(self) -> int:
        """Return net inventory: positive = long YES, negative = long NO."""
        return self.yes_quantity - self.no_quantity

    def notional_exposure(self) -> Decimal:
        """Return total notional exposure across both sides."""
        yes_notional = (
            Decimal(self.yes_quantity) * self.avg_yes_price.value
            if self.avg_yes_price
            else Decimal("0")
        )
        no_notional = (
            Decimal(self.no_quantity) * self.avg_no_price.value
            if self.avg_no_price
            else Decimal("0")
        )
        return yes_notional + no_notional

    def is_empty(self) -> bool:
        """Return True if position has no contracts on either side."""
        return self.yes_quantity == 0 and self.no_quantity == 0

    @classmethod
    def empty(cls, market_id: str) -> Position:
        """Create an empty position for a market."""
        return cls(
            market_id=market_id,
            yes_quantity=0,
            no_quantity=0,
            avg_yes_price=None,
            avg_no_price=None,
        )

    def with_fill(
        self,
        side_is_yes: bool,
        is_buy: bool,
        quantity: int,
        price: Price,
    ) -> Position:
        """Return a copy updated for a fill.

        Args:
            side_is_yes: True for YES side, False for NO
            is_buy: True for buy, False for sell
            quantity: Number of contracts filled
            price: Execution price

        Returns:
            New Position with updated quantities and average prices
        """
        if side_is_yes:
            return self._with_yes_fill(is_buy, quantity, price)
        else:
            return self._with_no_fill(is_buy, quantity, price)

    def _with_yes_fill(self, is_buy: bool, quantity: int, price: Price) -> Position:
        """Update YES position for a fill."""
        new_avg: Price | None
        if is_buy:
            new_qty = self.yes_quantity + quantity
            new_avg = self._calculate_avg_price(
                current_qty=self.yes_quantity,
                current_avg=self.avg_yes_price,
                fill_qty=quantity,
                fill_price=price,
            )
        else:
            new_qty = max(0, self.yes_quantity - quantity)
            new_avg = self.avg_yes_price if new_qty > 0 else None

        return Position(
            market_id=self.market_id,
            yes_quantity=new_qty,
            no_quantity=self.no_quantity,
            avg_yes_price=new_avg,
            avg_no_price=self.avg_no_price,
        )

    def _with_no_fill(self, is_buy: bool, quantity: int, price: Price) -> Position:
        """Update NO position for a fill."""
        new_avg: Price | None
        if is_buy:
            new_qty = self.no_quantity + quantity
            new_avg = self._calculate_avg_price(
                current_qty=self.no_quantity,
                current_avg=self.avg_no_price,
                fill_qty=quantity,
                fill_price=price,
            )
        else:
            new_qty = max(0, self.no_quantity - quantity)
            new_avg = self.avg_no_price if new_qty > 0 else None

        return Position(
            market_id=self.market_id,
            yes_quantity=self.yes_quantity,
            no_quantity=new_qty,
            avg_yes_price=self.avg_yes_price,
            avg_no_price=new_avg,
        )

    def _calculate_avg_price(
        self,
        current_qty: int,
        current_avg: Price | None,
        fill_qty: int,
        fill_price: Price,
    ) -> Price:
        """Calculate weighted average price after a fill."""
        if current_qty == 0 or current_avg is None:
            return fill_price

        current_value = Decimal(current_qty) * current_avg.value
        fill_value = Decimal(fill_qty) * fill_price.value
        new_qty = current_qty + fill_qty
        new_avg = (current_value + fill_value) / Decimal(new_qty)
        return Price(new_avg)


@dataclass(frozen=True)
class Balance:
    """Account balance information.

    Tracks total balance and available (non-reserved) balance.
    """

    total: Decimal
    available: Decimal

    def reserved(self) -> Decimal:
        """Return amount reserved for open orders."""
        return self.total - self.available

    def can_afford(self, amount: Decimal) -> bool:
        """Return True if available balance covers amount."""
        return self.available >= amount


@dataclass(frozen=True)
class PnLSnapshot:
    """Snapshot of profit/loss at a point in time.

    Includes both realized PnL (from closed trades) and unrealized
    PnL (mark-to-market on open positions).
    """

    timestamp: datetime
    realized_pnl: Decimal
    unrealized_pnl: Decimal
    total_pnl: Decimal
    positions: dict[str, Position]

    @classmethod
    def from_positions(
        cls,
        positions: dict[str, Position],
        current_prices: dict[str, Price],
        realized_pnl: Decimal,
    ) -> PnLSnapshot:
        """Create a snapshot calculating unrealized PnL from positions.

        Args:
            positions: Current positions by market_id
            current_prices: Current mid prices by market_id
            realized_pnl: Accumulated realized PnL

        Returns:
            PnLSnapshot with calculated unrealized PnL
        """
        unrealized = Decimal("0")

        for market_id, position in positions.items():
            current_price = current_prices.get(market_id)
            if current_price is None:
                continue

            # YES position unrealized PnL
            if position.yes_quantity > 0 and position.avg_yes_price is not None:
                unrealized += Decimal(position.yes_quantity) * (
                    current_price.value - position.avg_yes_price.value
                )

            # NO position unrealized PnL (NO price = 1 - YES price)
            if position.no_quantity > 0 and position.avg_no_price is not None:
                no_current_price = Decimal("1") - current_price.value
                unrealized += Decimal(position.no_quantity) * (
                    no_current_price - position.avg_no_price.value
                )

        return cls(
            timestamp=datetime.now(UTC),
            realized_pnl=realized_pnl,
            unrealized_pnl=unrealized,
            total_pnl=realized_pnl + unrealized,
            positions=positions,
        )
