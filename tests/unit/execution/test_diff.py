"""Tests for order differ."""

from datetime import UTC, datetime
from decimal import Decimal

import pytest

from market_maker.domain.orders import Order, OrderStatus, Quote, QuoteSet
from market_maker.domain.types import OrderSide, Price, Quantity, Side
from market_maker.execution.diff import OrderDiffer, QuoteOrders


class TestOrderDiffer:
    """Tests for OrderDiffer."""

    @pytest.fixture
    def differ(self) -> OrderDiffer:
        """Create differ with default tolerances."""
        return OrderDiffer()

    @pytest.fixture
    def sample_quotes(self) -> QuoteSet:
        """Create sample quote set."""
        return QuoteSet(
            market_id="TEST-MARKET",
            yes_quote=Quote(
                bid_price=Price(Decimal("0.45")),
                bid_size=Quantity(10),
                ask_price=Price(Decimal("0.55")),
                ask_size=Quantity(10),
            ),
            timestamp=datetime.now(UTC),
        )

    def _make_order(
        self,
        order_id: str,
        side: Side,
        order_side: OrderSide,
        price: Decimal,
        size: int,
        filled_size: int = 0,
    ) -> Order:
        """Helper to create an order."""
        return Order(
            id=order_id,
            client_order_id=f"client-{order_id}",
            market_id="TEST-MARKET",
            side=side,
            order_side=order_side,
            price=Price(price),
            size=Quantity(size),
            filled_size=filled_size,  # int, not Quantity
            status=OrderStatus.OPEN,
            created_at=datetime.now(UTC),
            updated_at=datetime.now(UTC),
        )

    def test_diff_no_current_orders(
        self, differ: OrderDiffer, sample_quotes: QuoteSet
    ) -> None:
        """Diff with no current orders should create all new."""
        actions = differ.diff(sample_quotes, None)

        # Should have 4 new actions (yes bid/ask, no bid/ask)
        assert len(actions) == 4
        assert all(a.action_type == "new" for a in actions)
        assert all(a.request is not None for a in actions)

    def test_diff_matching_orders(
        self, differ: OrderDiffer, sample_quotes: QuoteSet
    ) -> None:
        """Diff with matching orders should keep all."""
        current = QuoteOrders(
            market_id="TEST-MARKET",
            yes_bid_order=self._make_order(
                "order1", Side.YES, OrderSide.BUY, Decimal("0.45"), 10
            ),
            yes_ask_order=self._make_order(
                "order2", Side.YES, OrderSide.SELL, Decimal("0.55"), 10
            ),
            no_bid_order=self._make_order(
                "order3", Side.NO, OrderSide.BUY, Decimal("0.45"), 10
            ),
            no_ask_order=self._make_order(
                "order4", Side.NO, OrderSide.SELL, Decimal("0.55"), 10
            ),
        )

        actions = differ.diff(sample_quotes, current)

        # All should be keep
        assert len(actions) == 4
        assert all(a.action_type == "keep" for a in actions)

    def test_diff_price_change(
        self, differ: OrderDiffer, sample_quotes: QuoteSet
    ) -> None:
        """Diff with price change should amend."""
        current = QuoteOrders(
            market_id="TEST-MARKET",
            yes_bid_order=self._make_order(
                "order1", Side.YES, OrderSide.BUY, Decimal("0.40"), 10  # Different price
            ),
        )

        actions = differ.diff(sample_quotes, current)

        # Yes bid should be amended
        yes_bid_action = next(a for a in actions if a.quote_type == "yes_bid")
        assert yes_bid_action.action_type == "amend"
        assert yes_bid_action.order_id == "order1"
        assert yes_bid_action.request is not None

    def test_diff_size_change(
        self, differ: OrderDiffer, sample_quotes: QuoteSet
    ) -> None:
        """Diff with size change should amend."""
        current = QuoteOrders(
            market_id="TEST-MARKET",
            yes_bid_order=self._make_order(
                "order1", Side.YES, OrderSide.BUY, Decimal("0.45"), 5  # Different size
            ),
        )

        actions = differ.diff(sample_quotes, current)

        yes_bid_action = next(a for a in actions if a.quote_type == "yes_bid")
        assert yes_bid_action.action_type == "amend"

    def test_diff_cancel_extra_orders(self, differ: OrderDiffer) -> None:
        """Diff with changed quotes should amend/cancel as needed."""
        # Quotes with very different prices
        new_quotes = QuoteSet(
            market_id="TEST-MARKET",
            yes_quote=Quote(
                bid_price=Price(Decimal("0.20")),  # Very different from 0.45
                bid_size=Quantity(10),
                ask_price=Price(Decimal("0.80")),
                ask_size=Quantity(10),
            ),
            timestamp=datetime.now(UTC),
        )

        current = QuoteOrders(
            market_id="TEST-MARKET",
            yes_bid_order=self._make_order(
                "order1", Side.YES, OrderSide.BUY, Decimal("0.45"), 10
            ),
        )

        actions = differ.diff(new_quotes, current)

        # Yes bid should be amended since price changed significantly
        yes_bid_action = next(a for a in actions if a.quote_type == "yes_bid")
        assert yes_bid_action.action_type == "amend"
        assert yes_bid_action.order_id == "order1"

    def test_diff_within_price_tolerance(self, differ: OrderDiffer) -> None:
        """Prices within tolerance should match."""
        # Create differ with larger tolerance
        tolerant_differ = OrderDiffer(price_tolerance=Decimal("0.01"))

        quotes = QuoteSet(
            market_id="TEST-MARKET",
            yes_quote=Quote(
                bid_price=Price(Decimal("0.45")),
                bid_size=Quantity(10),
                ask_price=Price(Decimal("0.55")),
                ask_size=Quantity(10),
            ),
            timestamp=datetime.now(UTC),
        )

        # Order with price within tolerance
        current = QuoteOrders(
            market_id="TEST-MARKET",
            yes_bid_order=self._make_order(
                "order1", Side.YES, OrderSide.BUY, Decimal("0.455"), 10
            ),
        )

        actions = tolerant_differ.diff(quotes, current)

        yes_bid_action = next(a for a in actions if a.quote_type == "yes_bid")
        assert yes_bid_action.action_type == "keep"

    def test_calculate_stats(self, differ: OrderDiffer, sample_quotes: QuoteSet) -> None:
        """Should calculate action statistics."""
        current = QuoteOrders(
            market_id="TEST-MARKET",
            yes_bid_order=self._make_order(
                "order1", Side.YES, OrderSide.BUY, Decimal("0.45"), 10
            ),
        )

        actions = differ.diff(sample_quotes, current)
        stats = differ.calculate_stats(actions)

        assert "new" in stats
        assert "keep" in stats
        assert "amend" in stats
        assert "cancel" in stats
        assert sum(stats.values()) == len(actions)

    def test_diff_partial_fill_remaining(self, differ: OrderDiffer) -> None:
        """Should consider remaining size after partial fills."""
        quotes = QuoteSet(
            market_id="TEST-MARKET",
            yes_quote=Quote(
                bid_price=Price(Decimal("0.45")),
                bid_size=Quantity(5),  # Want 5
                ask_price=Price(Decimal("0.55")),
                ask_size=Quantity(10),
            ),
            timestamp=datetime.now(UTC),
        )

        # Order with 10 size but 5 filled = 5 remaining
        order = Order(
            id="order1",
            client_order_id="client-order1",
            market_id="TEST-MARKET",
            side=Side.YES,
            order_side=OrderSide.BUY,
            price=Price(Decimal("0.45")),
            size=Quantity(10),
            filled_size=5,  # 5 filled, 5 remaining (int, not Quantity)
            status=OrderStatus.PARTIALLY_FILLED,
            created_at=datetime.now(UTC),
            updated_at=datetime.now(UTC),
        )

        current = QuoteOrders(
            market_id="TEST-MARKET",
            yes_bid_order=order,
        )

        actions = differ.diff(quotes, current)

        # Should keep since remaining matches
        yes_bid_action = next(a for a in actions if a.quote_type == "yes_bid")
        assert yes_bid_action.action_type == "keep"
