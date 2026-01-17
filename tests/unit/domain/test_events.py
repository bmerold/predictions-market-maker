"""Tests for domain event types."""

from datetime import UTC, datetime
from decimal import Decimal

import pytest

from market_maker.domain.events import (
    BookUpdate,
    BookUpdateType,
    EventType,
    FillEvent,
    OrderUpdate,
)
from market_maker.domain.market_data import PriceLevel
from market_maker.domain.orders import Fill, Order, OrderStatus
from market_maker.domain.types import OrderSide, Price, Quantity, Side


class TestEventType:
    """Tests for EventType enum."""

    def test_event_types_defined(self) -> None:
        """EventType has expected values."""
        expected = {"BOOK_UPDATE", "FILL", "ORDER_UPDATE"}
        actual = {e.name for e in EventType}
        assert actual == expected


class TestBookUpdateType:
    """Tests for BookUpdateType enum."""

    def test_book_update_types_defined(self) -> None:
        """BookUpdateType has snapshot and delta."""
        expected = {"SNAPSHOT", "DELTA"}
        actual = {e.name for e in BookUpdateType}
        assert actual == expected


class TestEvent:
    """Tests for base Event class."""

    def test_event_has_timestamp(self) -> None:
        """All events have timestamp."""
        event = BookUpdate(
            event_type=EventType.BOOK_UPDATE,
            timestamp=datetime(2026, 1, 17, 12, 0, 0, tzinfo=UTC),
            market_id="TEST",
            update_type=BookUpdateType.SNAPSHOT,
            yes_bids=[],
            yes_asks=[],
        )
        assert event.timestamp == datetime(2026, 1, 17, 12, 0, 0, tzinfo=UTC)

    def test_event_has_type(self) -> None:
        """All events have event_type."""
        event = BookUpdate(
            event_type=EventType.BOOK_UPDATE,
            timestamp=datetime.now(UTC),
            market_id="TEST",
            update_type=BookUpdateType.SNAPSHOT,
            yes_bids=[],
            yes_asks=[],
        )
        assert event.event_type == EventType.BOOK_UPDATE


class TestBookUpdate:
    """Tests for BookUpdate event."""

    def test_create_snapshot(self) -> None:
        """BookUpdate can be snapshot."""
        bids = [PriceLevel.from_cents(45, 100)]
        asks = [PriceLevel.from_cents(47, 150)]
        event = BookUpdate(
            event_type=EventType.BOOK_UPDATE,
            timestamp=datetime(2026, 1, 17, 12, 0, 0, tzinfo=UTC),
            market_id="KXBTC-25JAN17-100000",
            update_type=BookUpdateType.SNAPSHOT,
            yes_bids=bids,
            yes_asks=asks,
        )
        assert event.update_type == BookUpdateType.SNAPSHOT
        assert len(event.yes_bids) == 1
        assert len(event.yes_asks) == 1

    def test_create_delta(self) -> None:
        """BookUpdate can be delta with price and delta fields."""
        event = BookUpdate(
            event_type=EventType.BOOK_UPDATE,
            timestamp=datetime(2026, 1, 17, 12, 0, 0, tzinfo=UTC),
            market_id="KXBTC-25JAN17-100000",
            update_type=BookUpdateType.DELTA,
            yes_bids=[],
            yes_asks=[],
            delta_price=Price(Decimal("0.45")),
            delta_size=50,
            delta_side=Side.YES,
            delta_is_bid=True,
        )
        assert event.update_type == BookUpdateType.DELTA
        assert event.delta_price is not None
        assert event.delta_price.value == Decimal("0.45")
        assert event.delta_size == 50

    def test_book_update_is_immutable(self) -> None:
        """BookUpdate should be immutable."""
        event = BookUpdate(
            event_type=EventType.BOOK_UPDATE,
            timestamp=datetime.now(UTC),
            market_id="TEST",
            update_type=BookUpdateType.SNAPSHOT,
            yes_bids=[],
            yes_asks=[],
        )
        with pytest.raises((AttributeError, TypeError)):
            event.market_id = "other"  # type: ignore[misc]

    def test_is_snapshot(self) -> None:
        """is_snapshot returns True for snapshot."""
        event = BookUpdate(
            event_type=EventType.BOOK_UPDATE,
            timestamp=datetime.now(UTC),
            market_id="TEST",
            update_type=BookUpdateType.SNAPSHOT,
            yes_bids=[],
            yes_asks=[],
        )
        assert event.is_snapshot()
        assert not event.is_delta()

    def test_is_delta(self) -> None:
        """is_delta returns True for delta."""
        event = BookUpdate(
            event_type=EventType.BOOK_UPDATE,
            timestamp=datetime.now(UTC),
            market_id="TEST",
            update_type=BookUpdateType.DELTA,
            yes_bids=[],
            yes_asks=[],
        )
        assert event.is_delta()
        assert not event.is_snapshot()


class TestFillEvent:
    """Tests for FillEvent."""

    def test_create_fill_event(self) -> None:
        """FillEvent wraps a Fill."""
        fill = Fill(
            id="fill_123",
            order_id="ord_456",
            market_id="KXBTC-25JAN17-100000",
            side=Side.YES,
            order_side=OrderSide.BUY,
            price=Price(Decimal("0.45")),
            size=Quantity(50),
            timestamp=datetime(2026, 1, 17, 12, 0, 0, tzinfo=UTC),
            is_simulated=False,
        )
        event = FillEvent(
            event_type=EventType.FILL,
            timestamp=datetime(2026, 1, 17, 12, 0, 0, tzinfo=UTC),
            fill=fill,
        )
        assert event.event_type == EventType.FILL
        assert event.fill.id == "fill_123"
        assert event.fill.size.value == 50

    def test_fill_event_is_immutable(self) -> None:
        """FillEvent should be immutable."""
        fill = Fill(
            id="fill_123",
            order_id="ord_456",
            market_id="TEST",
            side=Side.YES,
            order_side=OrderSide.BUY,
            price=Price(Decimal("0.45")),
            size=Quantity(50),
            timestamp=datetime.now(UTC),
            is_simulated=False,
        )
        event = FillEvent(
            event_type=EventType.FILL,
            timestamp=datetime.now(UTC),
            fill=fill,
        )
        with pytest.raises((AttributeError, TypeError)):
            event.fill = fill  # type: ignore[misc]

    def test_fill_event_market_id(self) -> None:
        """FillEvent.market_id returns fill's market_id."""
        fill = Fill(
            id="fill_123",
            order_id="ord_456",
            market_id="KXBTC-25JAN17-100000",
            side=Side.YES,
            order_side=OrderSide.BUY,
            price=Price(Decimal("0.45")),
            size=Quantity(50),
            timestamp=datetime.now(UTC),
            is_simulated=False,
        )
        event = FillEvent(
            event_type=EventType.FILL,
            timestamp=datetime.now(UTC),
            fill=fill,
        )
        assert event.market_id == "KXBTC-25JAN17-100000"


class TestOrderUpdate:
    """Tests for OrderUpdate event."""

    def test_create_order_update(self) -> None:
        """OrderUpdate wraps an Order."""
        order = Order(
            id="ord_123",
            client_order_id="client_456",
            market_id="KXBTC-25JAN17-100000",
            side=Side.YES,
            order_side=OrderSide.BUY,
            price=Price(Decimal("0.45")),
            size=Quantity(100),
            filled_size=50,
            status=OrderStatus.PARTIALLY_FILLED,
            created_at=datetime(2026, 1, 17, 12, 0, 0, tzinfo=UTC),
            updated_at=datetime(2026, 1, 17, 12, 0, 5, tzinfo=UTC),
        )
        event = OrderUpdate(
            event_type=EventType.ORDER_UPDATE,
            timestamp=datetime(2026, 1, 17, 12, 0, 5, tzinfo=UTC),
            order=order,
        )
        assert event.event_type == EventType.ORDER_UPDATE
        assert event.order.id == "ord_123"
        assert event.order.status == OrderStatus.PARTIALLY_FILLED

    def test_order_update_is_immutable(self) -> None:
        """OrderUpdate should be immutable."""
        order = Order(
            id="ord_123",
            client_order_id="client_456",
            market_id="TEST",
            side=Side.YES,
            order_side=OrderSide.BUY,
            price=Price(Decimal("0.45")),
            size=Quantity(100),
            filled_size=0,
            status=OrderStatus.OPEN,
            created_at=datetime.now(UTC),
            updated_at=datetime.now(UTC),
        )
        event = OrderUpdate(
            event_type=EventType.ORDER_UPDATE,
            timestamp=datetime.now(UTC),
            order=order,
        )
        with pytest.raises((AttributeError, TypeError)):
            event.order = order  # type: ignore[misc]

    def test_order_update_market_id(self) -> None:
        """OrderUpdate.market_id returns order's market_id."""
        order = Order(
            id="ord_123",
            client_order_id="client_456",
            market_id="KXBTC-25JAN17-100000",
            side=Side.YES,
            order_side=OrderSide.BUY,
            price=Price(Decimal("0.45")),
            size=Quantity(100),
            filled_size=0,
            status=OrderStatus.OPEN,
            created_at=datetime.now(UTC),
            updated_at=datetime.now(UTC),
        )
        event = OrderUpdate(
            event_type=EventType.ORDER_UPDATE,
            timestamp=datetime.now(UTC),
            order=order,
        )
        assert event.market_id == "KXBTC-25JAN17-100000"
