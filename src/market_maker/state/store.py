"""State store for position and PnL tracking.

Maintains the current state of positions and tracks realized
and unrealized PnL for risk management.
"""

from __future__ import annotations

from decimal import Decimal

from market_maker.domain.orders import Fill
from market_maker.domain.positions import Position
from market_maker.domain.types import OrderSide, Price, Side


class StateStore:
    """Manages position and PnL state.

    Tracks:
    - Positions per market (YES and NO quantities, average prices)
    - Realized PnL (from closed positions)
    - Unrealized PnL (mark-to-market)
    - Fees paid
    - Hourly and daily PnL for risk limits

    Thread-safety: This class is NOT thread-safe. External synchronization
    is required if accessed from multiple threads.
    """

    def __init__(self, fee_rate: Decimal = Decimal("0")) -> None:
        """Initialize the state store.

        Args:
            fee_rate: Fee rate as decimal (e.g., 0.01 for 1%)
        """
        self._fee_rate = fee_rate
        self._positions: dict[str, Position] = {}
        self._realized_pnl = Decimal("0")
        self._total_fees = Decimal("0")
        self._hourly_pnl = Decimal("0")
        self._daily_pnl = Decimal("0")

    @property
    def positions(self) -> dict[str, Position]:
        """Return all positions by market ID."""
        return dict(self._positions)

    @property
    def realized_pnl(self) -> Decimal:
        """Return total realized PnL."""
        return self._realized_pnl

    @property
    def total_fees(self) -> Decimal:
        """Return total fees paid."""
        return self._total_fees

    @property
    def hourly_pnl(self) -> Decimal:
        """Return PnL for current hour."""
        return self._hourly_pnl

    @property
    def daily_pnl(self) -> Decimal:
        """Return PnL for current day."""
        return self._daily_pnl

    def get_position(self, market_id: str) -> Position | None:
        """Get position for a market.

        Args:
            market_id: Market to get position for

        Returns:
            Position or None if no position
        """
        return self._positions.get(market_id)

    def get_net_inventory(self, market_id: str) -> int:
        """Get net inventory for a market (YES - NO).

        Args:
            market_id: Market to get inventory for

        Returns:
            Net inventory (positive = long YES, negative = long NO)
        """
        position = self._positions.get(market_id)
        if position is None:
            return 0
        return position.net_inventory()

    def apply_fill(self, fill: Fill) -> None:
        """Apply a fill to update position and PnL.

        Args:
            fill: The fill to apply
        """
        market_id = fill.market_id

        # Calculate and track fee
        fee = self._calculate_fee(fill)
        self._total_fees += fee

        # Get or create position
        position = self._positions.get(market_id)
        if position is None:
            position = Position(
                market_id=market_id,
                yes_quantity=0,
                no_quantity=0,
                avg_yes_price=None,
                avg_no_price=None,
            )

        # Apply fill to position
        realized = Decimal("0")
        if fill.side == Side.YES:
            position, realized = self._apply_yes_fill(position, fill)
        else:
            position, realized = self._apply_no_fill(position, fill)

        # Update position
        self._positions[market_id] = position

        # Update PnL (subtract fee from realized)
        net_realized = realized - fee
        self._realized_pnl += net_realized
        self._hourly_pnl += net_realized
        self._daily_pnl += net_realized

    def _apply_yes_fill(
        self, position: Position, fill: Fill
    ) -> tuple[Position, Decimal]:
        """Apply a YES side fill.

        Returns:
            Updated position and realized PnL from this fill
        """
        realized = Decimal("0")

        if fill.order_side == OrderSide.BUY:
            # Buying YES increases yes_quantity
            new_qty = position.yes_quantity + fill.size.value
            new_avg = self._calculate_new_avg(
                position.yes_quantity,
                position.avg_yes_price,
                fill.size.value,
                fill.price,
            )
            return (
                Position(
                    market_id=position.market_id,
                    yes_quantity=new_qty,
                    no_quantity=position.no_quantity,
                    avg_yes_price=Price(new_avg),
                    avg_no_price=position.avg_no_price,
                ),
                realized,
            )
        else:
            # Selling YES decreases yes_quantity, realize PnL
            if position.avg_yes_price is not None:
                realized = (
                    fill.price.value - position.avg_yes_price.value
                ) * Decimal(fill.size.value)

            new_qty = position.yes_quantity - fill.size.value
            # Keep avg price if still have position
            keep_avg: Price | None = position.avg_yes_price if new_qty > 0 else None

            return (
                Position(
                    market_id=position.market_id,
                    yes_quantity=new_qty,
                    no_quantity=position.no_quantity,
                    avg_yes_price=keep_avg,
                    avg_no_price=position.avg_no_price,
                ),
                realized,
            )

    def _apply_no_fill(
        self, position: Position, fill: Fill
    ) -> tuple[Position, Decimal]:
        """Apply a NO side fill.

        Returns:
            Updated position and realized PnL from this fill
        """
        realized = Decimal("0")

        if fill.order_side == OrderSide.BUY:
            # Buying NO increases no_quantity
            new_qty = position.no_quantity + fill.size.value
            new_avg = self._calculate_new_avg(
                position.no_quantity,
                position.avg_no_price,
                fill.size.value,
                fill.price,
            )
            return (
                Position(
                    market_id=position.market_id,
                    yes_quantity=position.yes_quantity,
                    no_quantity=new_qty,
                    avg_yes_price=position.avg_yes_price,
                    avg_no_price=Price(new_avg),
                ),
                realized,
            )
        else:
            # Selling NO decreases no_quantity, realize PnL
            if position.avg_no_price is not None:
                realized = (
                    fill.price.value - position.avg_no_price.value
                ) * Decimal(fill.size.value)

            new_qty = position.no_quantity - fill.size.value
            keep_avg: Price | None = position.avg_no_price if new_qty > 0 else None

            return (
                Position(
                    market_id=position.market_id,
                    yes_quantity=position.yes_quantity,
                    no_quantity=new_qty,
                    avg_yes_price=position.avg_yes_price,
                    avg_no_price=keep_avg,
                ),
                realized,
            )

    def _calculate_new_avg(
        self,
        current_qty: int,
        current_avg: Price | None,
        add_qty: int,
        add_price: Price,
    ) -> Decimal:
        """Calculate new average price after adding to position.

        Args:
            current_qty: Current quantity held
            current_avg: Current average price
            add_qty: Quantity being added
            add_price: Price of added quantity

        Returns:
            New average price
        """
        if current_qty == 0 or current_avg is None:
            return add_price.value

        total_cost = (
            Decimal(current_qty) * current_avg.value
            + Decimal(add_qty) * add_price.value
        )
        new_qty = current_qty + add_qty
        return total_cost / Decimal(new_qty)

    def _calculate_fee(self, fill: Fill) -> Decimal:
        """Calculate fee for a fill.

        Args:
            fill: The fill

        Returns:
            Fee amount
        """
        notional = fill.price.value * Decimal(fill.size.value)
        return notional * self._fee_rate

    def calculate_unrealized_pnl(
        self, market_id: str, mark_price: Price
    ) -> Decimal:
        """Calculate unrealized PnL for a position.

        Args:
            market_id: Market to calculate for
            mark_price: Current mark price for YES side

        Returns:
            Unrealized PnL (negative = loss)
        """
        position = self._positions.get(market_id)
        if position is None:
            return Decimal("0")

        unrealized = Decimal("0")

        # YES side unrealized
        if position.yes_quantity > 0 and position.avg_yes_price is not None:
            yes_pnl = (mark_price.value - position.avg_yes_price.value) * Decimal(
                position.yes_quantity
            )
            unrealized += yes_pnl

        # NO side unrealized (NO mark price = 1 - YES mark price)
        if position.no_quantity > 0 and position.avg_no_price is not None:
            no_mark = Decimal("1") - mark_price.value
            no_pnl = (no_mark - position.avg_no_price.value) * Decimal(
                position.no_quantity
            )
            unrealized += no_pnl

        return unrealized

    def reset_market(self, market_id: str) -> None:
        """Reset position for a market (e.g., after settlement).

        Args:
            market_id: Market to reset
        """
        self._positions.pop(market_id, None)

    def reset_hourly_pnl(self) -> None:
        """Reset hourly PnL counter (called at start of each hour)."""
        self._hourly_pnl = Decimal("0")

    def reset_daily_pnl(self) -> None:
        """Reset daily PnL counter (called at start of each day)."""
        self._daily_pnl = Decimal("0")
