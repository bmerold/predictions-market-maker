"""Tests for StateStore."""

from datetime import UTC, datetime
from decimal import Decimal

import pytest

from market_maker.domain.orders import Fill, OrderSide
from market_maker.domain.positions import Position
from market_maker.domain.types import Price, Quantity, Side
from market_maker.state.store import StateStore


class TestStateStore:
    """Tests for StateStore."""

    @pytest.fixture
    def store(self) -> StateStore:
        """Create a StateStore with default settings."""
        return StateStore(fee_rate=Decimal("0.01"))  # 1% fee

    def test_initial_state(self, store: StateStore) -> None:
        """Store starts with no positions."""
        assert len(store.positions) == 0
        assert store.get_position("TEST") is None

    def test_apply_fill_creates_position(self, store: StateStore) -> None:
        """Applying a fill creates a new position."""
        fill = Fill(
            id="fill_1",
            order_id="order_1",
            market_id="TEST",
            side=Side.YES,
            order_side=OrderSide.BUY,
            price=Price(Decimal("0.50")),
            size=Quantity(100),
            timestamp=datetime.now(UTC),
            is_simulated=True,
        )
        store.apply_fill(fill)

        position = store.get_position("TEST")
        assert position is not None
        assert position.yes_quantity == 100
        assert position.avg_yes_price.value == Decimal("0.50")

    def test_apply_fill_updates_existing_position(self, store: StateStore) -> None:
        """Applying a fill updates existing position."""
        fill1 = Fill(
            id="fill_1",
            order_id="order_1",
            market_id="TEST",
            side=Side.YES,
            order_side=OrderSide.BUY,
            price=Price(Decimal("0.40")),
            size=Quantity(100),
            timestamp=datetime.now(UTC),
            is_simulated=True,
        )
        fill2 = Fill(
            id="fill_2",
            order_id="order_2",
            market_id="TEST",
            side=Side.YES,
            order_side=OrderSide.BUY,
            price=Price(Decimal("0.60")),
            size=Quantity(100),
            timestamp=datetime.now(UTC),
            is_simulated=True,
        )
        store.apply_fill(fill1)
        store.apply_fill(fill2)

        position = store.get_position("TEST")
        assert position.yes_quantity == 200
        # Avg price = (100 * 0.40 + 100 * 0.60) / 200 = 0.50
        assert position.avg_yes_price.value == Decimal("0.50")

    def test_apply_sell_fill_reduces_position(self, store: StateStore) -> None:
        """Selling reduces position size."""
        buy = Fill(
            id="fill_1",
            order_id="order_1",
            market_id="TEST",
            side=Side.YES,
            order_side=OrderSide.BUY,
            price=Price(Decimal("0.50")),
            size=Quantity(100),
            timestamp=datetime.now(UTC),
            is_simulated=True,
        )
        sell = Fill(
            id="fill_2",
            order_id="order_2",
            market_id="TEST",
            side=Side.YES,
            order_side=OrderSide.SELL,
            price=Price(Decimal("0.60")),
            size=Quantity(50),
            timestamp=datetime.now(UTC),
            is_simulated=True,
        )
        store.apply_fill(buy)
        store.apply_fill(sell)

        position = store.get_position("TEST")
        assert position.yes_quantity == 50

    def test_net_inventory(self, store: StateStore) -> None:
        """Net inventory calculated correctly."""
        yes_fill = Fill(
            id="fill_1",
            order_id="order_1",
            market_id="TEST",
            side=Side.YES,
            order_side=OrderSide.BUY,
            price=Price(Decimal("0.50")),
            size=Quantity(100),
            timestamp=datetime.now(UTC),
            is_simulated=True,
        )
        no_fill = Fill(
            id="fill_2",
            order_id="order_2",
            market_id="TEST",
            side=Side.NO,
            order_side=OrderSide.BUY,
            price=Price(Decimal("0.50")),
            size=Quantity(30),
            timestamp=datetime.now(UTC),
            is_simulated=True,
        )
        store.apply_fill(yes_fill)
        store.apply_fill(no_fill)

        assert store.get_net_inventory("TEST") == 70  # 100 YES - 30 NO

    def test_realized_pnl_from_sell(self, store: StateStore) -> None:
        """Realized PnL calculated correctly on sell."""
        buy = Fill(
            id="fill_1",
            order_id="order_1",
            market_id="TEST",
            side=Side.YES,
            order_side=OrderSide.BUY,
            price=Price(Decimal("0.40")),
            size=Quantity(100),
            timestamp=datetime.now(UTC),
            is_simulated=True,
        )
        sell = Fill(
            id="fill_2",
            order_id="order_2",
            market_id="TEST",
            side=Side.YES,
            order_side=OrderSide.SELL,
            price=Price(Decimal("0.60")),
            size=Quantity(100),
            timestamp=datetime.now(UTC),
            is_simulated=True,
        )
        store.apply_fill(buy)
        store.apply_fill(sell)

        # Profit: (0.60 - 0.40) * 100 = 20.00
        # Fee on buy: 0.40 * 100 * 0.01 = 0.40
        # Fee on sell: 0.60 * 100 * 0.01 = 0.60
        # Net: 20.00 - 0.40 - 0.60 = 19.00
        assert store.realized_pnl == Decimal("19.00")

    def test_total_fees(self, store: StateStore) -> None:
        """Fees are tracked correctly."""
        fill = Fill(
            id="fill_1",
            order_id="order_1",
            market_id="TEST",
            side=Side.YES,
            order_side=OrderSide.BUY,
            price=Price(Decimal("0.50")),
            size=Quantity(100),
            timestamp=datetime.now(UTC),
            is_simulated=True,
        )
        store.apply_fill(fill)

        # Fee: 0.50 * 100 * 0.01 = 0.50
        assert store.total_fees == Decimal("0.50")

    def test_unrealized_pnl(self, store: StateStore) -> None:
        """Unrealized PnL calculated from mark price."""
        fill = Fill(
            id="fill_1",
            order_id="order_1",
            market_id="TEST",
            side=Side.YES,
            order_side=OrderSide.BUY,
            price=Price(Decimal("0.40")),
            size=Quantity(100),
            timestamp=datetime.now(UTC),
            is_simulated=True,
        )
        store.apply_fill(fill)

        # Mark price at 0.60: unrealized = (0.60 - 0.40) * 100 = 20.00
        unrealized = store.calculate_unrealized_pnl("TEST", Price(Decimal("0.60")))
        assert unrealized == Decimal("20.00")

    def test_reset_market(self, store: StateStore) -> None:
        """Can reset a market's position."""
        fill = Fill(
            id="fill_1",
            order_id="order_1",
            market_id="TEST",
            side=Side.YES,
            order_side=OrderSide.BUY,
            price=Price(Decimal("0.50")),
            size=Quantity(100),
            timestamp=datetime.now(UTC),
            is_simulated=True,
        )
        store.apply_fill(fill)
        store.reset_market("TEST")

        assert store.get_position("TEST") is None

    def test_multiple_markets(self, store: StateStore) -> None:
        """Supports multiple markets independently."""
        fill1 = Fill(
            id="fill_1",
            order_id="order_1",
            market_id="MARKET1",
            side=Side.YES,
            order_side=OrderSide.BUY,
            price=Price(Decimal("0.50")),
            size=Quantity(100),
            timestamp=datetime.now(UTC),
            is_simulated=True,
        )
        fill2 = Fill(
            id="fill_2",
            order_id="order_2",
            market_id="MARKET2",
            side=Side.YES,
            order_side=OrderSide.BUY,
            price=Price(Decimal("0.60")),
            size=Quantity(50),
            timestamp=datetime.now(UTC),
            is_simulated=True,
        )
        store.apply_fill(fill1)
        store.apply_fill(fill2)

        assert store.get_position("MARKET1").yes_quantity == 100
        assert store.get_position("MARKET2").yes_quantity == 50

    def test_hourly_pnl_tracking(self, store: StateStore) -> None:
        """Hourly PnL is tracked separately."""
        buy = Fill(
            id="fill_1",
            order_id="order_1",
            market_id="TEST",
            side=Side.YES,
            order_side=OrderSide.BUY,
            price=Price(Decimal("0.40")),
            size=Quantity(100),
            timestamp=datetime.now(UTC),
            is_simulated=True,
        )
        sell = Fill(
            id="fill_2",
            order_id="order_2",
            market_id="TEST",
            side=Side.YES,
            order_side=OrderSide.SELL,
            price=Price(Decimal("0.60")),
            size=Quantity(100),
            timestamp=datetime.now(UTC),
            is_simulated=True,
        )
        store.apply_fill(buy)
        store.apply_fill(sell)

        # Before reset, hourly matches realized
        assert store.hourly_pnl == store.realized_pnl

    def test_reset_hourly_pnl(self, store: StateStore) -> None:
        """Hourly PnL can be reset."""
        buy = Fill(
            id="fill_1",
            order_id="order_1",
            market_id="TEST",
            side=Side.YES,
            order_side=OrderSide.BUY,
            price=Price(Decimal("0.40")),
            size=Quantity(100),
            timestamp=datetime.now(UTC),
            is_simulated=True,
        )
        sell = Fill(
            id="fill_2",
            order_id="order_2",
            market_id="TEST",
            side=Side.YES,
            order_side=OrderSide.SELL,
            price=Price(Decimal("0.60")),
            size=Quantity(100),
            timestamp=datetime.now(UTC),
            is_simulated=True,
        )
        store.apply_fill(buy)
        store.apply_fill(sell)
        store.reset_hourly_pnl()

        assert store.hourly_pnl == Decimal("0")
        # Realized PnL should still be tracked
        assert store.realized_pnl == Decimal("19.00")
