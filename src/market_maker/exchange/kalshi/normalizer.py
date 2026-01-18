"""Kalshi data normalizer.

Converts Kalshi API responses and WebSocket messages to domain models.
"""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal
from typing import Any

from market_maker.domain.events import (
    BookUpdate,
    BookUpdateType,
    EventType,
    FillEvent,
    OrderUpdate,
)
from market_maker.domain.market_data import OrderBook, PriceLevel
from market_maker.domain.orders import Fill, Order, OrderStatus
from market_maker.domain.positions import Balance, Position
from market_maker.domain.types import OrderSide, Price, Quantity, Side


class KalshiNormalizer:
    """Converts Kalshi data formats to domain models.

    Kalshi uses:
    - Prices in cents (1-99)
    - "yes"/"no" for sides
    - "buy"/"sell" for actions
    - Timestamps in ISO format
    """

    @staticmethod
    def normalize_price(cents: int) -> Price:
        """Convert cents to Price.

        Args:
            cents: Price in cents (1-99)

        Returns:
            Price object with decimal value
        """
        return Price(Decimal(cents) / Decimal(100))

    @staticmethod
    def denormalize_price(price: Price) -> int:
        """Convert Price to cents.

        Args:
            price: Price object

        Returns:
            Price in cents (1-99)
        """
        return int(price.value * 100)

    @staticmethod
    def normalize_side(side: str) -> Side:
        """Convert Kalshi side string to Side enum.

        Args:
            side: "yes" or "no"

        Returns:
            Side enum
        """
        return Side.YES if side.lower() == "yes" else Side.NO

    @staticmethod
    def denormalize_side(side: Side) -> str:
        """Convert Side enum to Kalshi string.

        Args:
            side: Side enum

        Returns:
            "yes" or "no"
        """
        return "yes" if side == Side.YES else "no"

    @staticmethod
    def normalize_order_side(action: str) -> OrderSide:
        """Convert Kalshi action string to OrderSide enum.

        Args:
            action: "buy" or "sell"

        Returns:
            OrderSide enum
        """
        return OrderSide.BUY if action.lower() == "buy" else OrderSide.SELL

    @staticmethod
    def denormalize_order_side(order_side: OrderSide) -> str:
        """Convert OrderSide enum to Kalshi string.

        Args:
            order_side: OrderSide enum

        Returns:
            "buy" or "sell"
        """
        return "buy" if order_side == OrderSide.BUY else "sell"

    @staticmethod
    def normalize_timestamp(ts: str | None) -> datetime:
        """Convert Kalshi timestamp to datetime.

        Args:
            ts: ISO format timestamp string

        Returns:
            datetime object (UTC)
        """
        if not ts:
            return datetime.now(UTC)

        # Handle various formats
        ts = ts.replace("Z", "+00:00")
        dt = datetime.fromisoformat(ts)

        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=UTC)

        return dt

    @staticmethod
    def normalize_order_status(status: str) -> OrderStatus:
        """Convert Kalshi order status to OrderStatus enum.

        Args:
            status: Kalshi status string

        Returns:
            OrderStatus enum
        """
        status_map = {
            "resting": OrderStatus.OPEN,
            "pending": OrderStatus.PENDING,
            "canceled": OrderStatus.CANCELLED,
            "cancelled": OrderStatus.CANCELLED,
            "executed": OrderStatus.FILLED,
            "partial": OrderStatus.PARTIALLY_FILLED,
        }
        return status_map.get(status.lower(), OrderStatus.PENDING)

    def normalize_orderbook(
        self, data: dict[str, Any], ticker: str
    ) -> OrderBook:
        """Convert Kalshi order book to OrderBook.

        Args:
            data: Kalshi orderbook response
            ticker: Market ticker

        Returns:
            OrderBook domain object
        """
        # Parse YES bids and asks
        yes_bids = []
        yes_asks = []

        # Kalshi format: {"yes": [[price, size], ...], "no": [[price, size], ...]}
        for price_cents, size in data.get("yes", []):
            if size > 0:
                # Bids are on the buy side
                level = PriceLevel(
                    self.normalize_price(price_cents),
                    Quantity(size),
                )
                yes_bids.append(level)

        for price_cents, size in data.get("no", []):
            if size > 0:
                # NO bids correspond to YES asks (complement)
                yes_price = 100 - price_cents
                level = PriceLevel(
                    self.normalize_price(yes_price),
                    Quantity(size),
                )
                yes_asks.append(level)

        # Sort: bids descending, asks ascending
        yes_bids.sort(key=lambda x: x.price.value, reverse=True)
        yes_asks.sort(key=lambda x: x.price.value)

        return OrderBook(
            market_id=ticker,
            yes_bids=yes_bids,
            yes_asks=yes_asks,
            timestamp=datetime.now(UTC),
        )

    def normalize_orderbook_snapshot(
        self, data: dict[str, Any]
    ) -> BookUpdate:
        """Convert Kalshi orderbook snapshot to BookUpdate event.

        Args:
            data: WebSocket orderbook_snapshot message

        Returns:
            BookUpdate event with snapshot type
        """
        msg = data.get("msg", {})
        ticker = msg.get("market_ticker", "")

        # Parse YES bids - the yes array contains buy orders for YES
        yes_bids = []
        for price_cents, size in msg.get("yes", []):
            if size > 0:
                level = PriceLevel(
                    self.normalize_price(price_cents),
                    Quantity(size),
                )
                yes_bids.append(level)

        # Parse NO bids - convert to YES asks (complement)
        yes_asks = []
        for price_cents, size in msg.get("no", []):
            if size > 0:
                # NO bid at price P = YES ask at price (100-P)
                yes_price = 100 - price_cents
                level = PriceLevel(
                    self.normalize_price(yes_price),
                    Quantity(size),
                )
                yes_asks.append(level)

        # Sort: bids descending, asks ascending
        yes_bids.sort(key=lambda x: x.price.value, reverse=True)
        yes_asks.sort(key=lambda x: x.price.value)

        return BookUpdate(
            event_type=EventType.BOOK_UPDATE,
            timestamp=datetime.now(UTC),
            market_id=ticker,
            update_type=BookUpdateType.SNAPSHOT,
            yes_bids=yes_bids,
            yes_asks=yes_asks,
        )

    def normalize_orderbook_delta(
        self, data: dict[str, Any]
    ) -> BookUpdate:
        """Convert Kalshi orderbook delta to BookUpdate event.

        Args:
            data: WebSocket orderbook_delta message

        Returns:
            BookUpdate event
        """
        msg = data.get("msg", {})
        ticker = msg.get("market_ticker", "")

        # Parse delta
        price = msg.get("price", 0)
        delta = msg.get("delta", 0)
        side = msg.get("side", "yes")

        return BookUpdate(
            event_type=EventType.BOOK_UPDATE,
            timestamp=datetime.now(UTC),
            market_id=ticker,
            update_type=BookUpdateType.DELTA,
            yes_bids=[],
            yes_asks=[],
            delta_price=self.normalize_price(price),
            delta_size=abs(delta),
            delta_side=self.normalize_side(side),
            delta_is_bid=delta > 0,  # Positive delta = bid added
        )

    def normalize_order(self, data: dict[str, Any]) -> Order:
        """Convert Kalshi order to Order domain object.

        Args:
            data: Kalshi order response

        Returns:
            Order domain object
        """
        return Order(
            id=data.get("order_id", ""),
            client_order_id=data.get("client_order_id", ""),
            market_id=data.get("ticker", ""),
            side=self.normalize_side(data.get("side", "yes")),
            order_side=self.normalize_order_side(data.get("action", "buy")),
            price=self.normalize_price(data.get("yes_price", 50)),
            size=Quantity(data.get("count", 0)),
            filled_size=data.get("filled_count", 0),
            status=self.normalize_order_status(data.get("status", "pending")),
            created_at=self.normalize_timestamp(data.get("created_time")),
            updated_at=self.normalize_timestamp(data.get("updated_time")),
        )

    def normalize_fill(self, data: dict[str, Any]) -> Fill:
        """Convert Kalshi fill to Fill domain object.

        Args:
            data: Kalshi fill data

        Returns:
            Fill domain object
        """
        return Fill(
            id=data.get("trade_id", ""),
            order_id=data.get("order_id", ""),
            market_id=data.get("ticker", ""),
            side=self.normalize_side(data.get("side", "yes")),
            order_side=self.normalize_order_side(data.get("action", "buy")),
            price=self.normalize_price(data.get("yes_price", 50)),
            size=Quantity(data.get("count", 0)),
            timestamp=self.normalize_timestamp(data.get("created_time")),
            is_simulated=False,
        )

    def normalize_position(self, data: dict[str, Any]) -> Position:
        """Convert Kalshi position to Position domain object.

        Args:
            data: Kalshi position response

        Returns:
            Position domain object
        """
        ticker = data.get("ticker", "")

        # Kalshi positions have separate yes/no quantities
        yes_qty = data.get("position", 0)  # Positive = long YES
        no_qty = 0  # Kalshi typically shows net position

        # If negative, we're short YES (or long NO)
        if yes_qty < 0:
            no_qty = abs(yes_qty)
            yes_qty = 0

        # Average prices (if available)
        avg_yes = None
        avg_no = None
        if data.get("average_price"):
            avg_yes = self.normalize_price(data["average_price"])

        return Position(
            market_id=ticker,
            yes_quantity=yes_qty,
            no_quantity=no_qty,
            avg_yes_price=avg_yes,
            avg_no_price=avg_no,
        )

    def normalize_balance(self, data: dict[str, Any]) -> Balance:
        """Convert Kalshi balance to Balance domain object.

        Args:
            data: Kalshi balance response

        Returns:
            Balance domain object
        """
        # Kalshi returns balance in cents
        available = Decimal(data.get("balance", 0)) / Decimal(100)
        # Total might include open order exposure
        total = available

        return Balance(
            total=total,
            available=available,
        )

    def normalize_fill_event(self, data: dict[str, Any]) -> FillEvent:
        """Convert Kalshi WebSocket fill to FillEvent.

        Args:
            data: WebSocket fill message

        Returns:
            FillEvent
        """
        fill = self.normalize_fill(data.get("msg", {}))
        return FillEvent(
            event_type=EventType.FILL,
            timestamp=fill.timestamp,
            fill=fill,
        )

    def normalize_order_event(self, data: dict[str, Any]) -> OrderUpdate:
        """Convert Kalshi WebSocket order update to OrderUpdate.

        Args:
            data: WebSocket order message

        Returns:
            OrderUpdate event
        """
        order = self.normalize_order(data.get("msg", {}))
        return OrderUpdate(
            event_type=EventType.ORDER_UPDATE,
            timestamp=order.updated_at,
            order=order,
        )
