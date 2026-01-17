"""Order domain models.

These models represent orders, quotes, and fills in the trading system.
All models are immutable.
"""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal
from enum import Enum
from uuid import uuid4

from pydantic.dataclasses import dataclass

from market_maker.domain.types import OrderSide, Price, Quantity, Side


class OrderStatus(str, Enum):
    """Order lifecycle states.

    State transitions:
    - PENDING -> OPEN (accepted by exchange)
    - PENDING -> REJECTED (exchange rejected)
    - OPEN -> PARTIALLY_FILLED (partial execution)
    - OPEN -> FILLED (full execution)
    - OPEN -> CANCELLING (cancel requested)
    - PARTIALLY_FILLED -> FILLED (remaining executed)
    - PARTIALLY_FILLED -> CANCELLING (cancel requested)
    - CANCELLING -> CANCELLED (cancel confirmed)
    """

    PENDING = "pending"  # Submitted, awaiting exchange ack
    OPEN = "open"  # Accepted by exchange, on book
    PARTIALLY_FILLED = "partially_filled"  # Some fills received
    FILLED = "filled"  # Fully executed (terminal)
    CANCELLING = "cancelling"  # Cancel request sent
    CANCELLED = "cancelled"  # Cancel confirmed (terminal)
    REJECTED = "rejected"  # Exchange rejected (terminal)

    def is_terminal(self) -> bool:
        """Return True if this status is final (no further transitions)."""
        return self in (OrderStatus.FILLED, OrderStatus.CANCELLED, OrderStatus.REJECTED)

    def is_active(self) -> bool:
        """Return True if order is on the book and can receive fills."""
        return self in (OrderStatus.OPEN, OrderStatus.PARTIALLY_FILLED)


@dataclass(frozen=True)
class Order:
    """An order in the trading system.

    Immutable - use with_status() or with_fill() to get updated copies.
    """

    id: str  # Exchange-assigned order ID
    client_order_id: str  # Our internal ID for correlation
    market_id: str
    side: Side  # YES or NO
    order_side: OrderSide  # BUY or SELL
    price: Price
    size: Quantity
    filled_size: int  # Number of contracts filled so far
    status: OrderStatus
    created_at: datetime
    updated_at: datetime

    def remaining_size(self) -> int:
        """Return unfilled quantity."""
        return self.size.value - self.filled_size

    def is_terminal(self) -> bool:
        """Return True if order is in terminal state."""
        return self.status.is_terminal()

    def with_status(self, status: OrderStatus, updated_at: datetime | None = None) -> Order:
        """Return a copy with updated status.

        Args:
            status: New order status
            updated_at: Update timestamp (defaults to now)

        Returns:
            New Order with updated status
        """

        return Order(
            id=self.id,
            client_order_id=self.client_order_id,
            market_id=self.market_id,
            side=self.side,
            order_side=self.order_side,
            price=self.price,
            size=self.size,
            filled_size=self.filled_size,
            status=status,
            created_at=self.created_at,
            updated_at=updated_at or datetime.now(UTC),
        )

    def with_fill(self, fill_size: int, updated_at: datetime | None = None) -> Order:
        """Return a copy with updated fill information.

        Args:
            fill_size: New total filled size (not incremental)
            updated_at: Update timestamp (defaults to now)

        Returns:
            New Order with updated fill info and status
        """

        new_status = (
            OrderStatus.FILLED if fill_size >= self.size.value else OrderStatus.PARTIALLY_FILLED
        )
        return Order(
            id=self.id,
            client_order_id=self.client_order_id,
            market_id=self.market_id,
            side=self.side,
            order_side=self.order_side,
            price=self.price,
            size=self.size,
            filled_size=fill_size,
            status=new_status,
            created_at=self.created_at,
            updated_at=updated_at or datetime.now(UTC),
        )


@dataclass(frozen=True)
class OrderRequest:
    """Request to place a new order.

    Does not include exchange-assigned ID (that comes in the response).
    """

    client_order_id: str
    market_id: str
    side: Side
    order_side: OrderSide
    price: Price
    size: Quantity

    @classmethod
    def create(
        cls,
        market_id: str,
        side: Side,
        order_side: OrderSide,
        price: Price,
        size: Quantity,
        client_order_id: str | None = None,
    ) -> OrderRequest:
        """Create an OrderRequest, generating client_order_id if not provided.

        Args:
            market_id: Market to place order in
            side: YES or NO
            order_side: BUY or SELL
            price: Order price
            size: Order size
            client_order_id: Optional custom client ID

        Returns:
            OrderRequest with all fields populated
        """
        return cls(
            client_order_id=client_order_id or f"mm_{uuid4().hex[:12]}",
            market_id=market_id,
            side=side,
            order_side=order_side,
            price=price,
            size=size,
        )


@dataclass(frozen=True)
class Quote:
    """A two-sided quote (bid and ask) for one side of a binary market.

    Represents the prices and sizes at which we're willing to buy and sell.
    """

    bid_price: Price
    bid_size: Quantity
    ask_price: Price
    ask_size: Quantity

    def spread(self) -> Decimal:
        """Return the spread (ask - bid)."""
        return self.ask_price.value - self.bid_price.value


@dataclass(frozen=True)
class QuoteSet:
    """Complete quote set for a binary market.

    Contains YES quote. NO quote is derived using price complement.
    """

    market_id: str
    yes_quote: Quote
    timestamp: datetime

    def no_quote(self) -> Quote:
        """Derive NO quote from YES quote.

        NO bid = 1 - YES ask (we buy NO when others want to sell YES)
        NO ask = 1 - YES bid (we sell NO when others want to buy YES)
        Sizes come from the opposite side.
        """
        return Quote(
            bid_price=self.yes_quote.ask_price.complement(),
            bid_size=self.yes_quote.ask_size,
            ask_price=self.yes_quote.bid_price.complement(),
            ask_size=self.yes_quote.bid_size,
        )

    def to_order_requests(self) -> list[OrderRequest]:
        """Convert quotes to order requests.

        Returns 4 orders:
        - YES BUY (bid)
        - YES SELL (ask)
        - NO BUY (bid)
        - NO SELL (ask)
        """
        no_quote = self.no_quote()

        return [
            OrderRequest.create(
                market_id=self.market_id,
                side=Side.YES,
                order_side=OrderSide.BUY,
                price=self.yes_quote.bid_price,
                size=self.yes_quote.bid_size,
            ),
            OrderRequest.create(
                market_id=self.market_id,
                side=Side.YES,
                order_side=OrderSide.SELL,
                price=self.yes_quote.ask_price,
                size=self.yes_quote.ask_size,
            ),
            OrderRequest.create(
                market_id=self.market_id,
                side=Side.NO,
                order_side=OrderSide.BUY,
                price=no_quote.bid_price,
                size=no_quote.bid_size,
            ),
            OrderRequest.create(
                market_id=self.market_id,
                side=Side.NO,
                order_side=OrderSide.SELL,
                price=no_quote.ask_price,
                size=no_quote.ask_size,
            ),
        ]


@dataclass(frozen=True)
class Fill:
    """Record of an order execution.

    Created when an order is partially or fully filled.
    """

    id: str  # Fill ID (exchange-assigned or generated for paper)
    order_id: str  # Order that was filled
    market_id: str
    side: Side
    order_side: OrderSide
    price: Price  # Execution price
    size: Quantity  # Fill size
    timestamp: datetime
    is_simulated: bool  # True for paper trading fills

    def notional(self) -> Decimal:
        """Return notional value (price * size)."""
        return self.price.value * Decimal(self.size.value)
