"""Tests for position and PnL domain models."""

from datetime import UTC, datetime
from decimal import Decimal

import pytest

from market_maker.domain.positions import Balance, PnLSnapshot, Position
from market_maker.domain.types import Price


class TestPosition:
    """Tests for Position model."""

    def test_create_position(self) -> None:
        """Position stores all fields."""
        position = Position(
            market_id="KXBTC-25JAN17-100000",
            yes_quantity=100,
            no_quantity=50,
            avg_yes_price=Price(Decimal("0.45")),
            avg_no_price=Price(Decimal("0.55")),
        )
        assert position.market_id == "KXBTC-25JAN17-100000"
        assert position.yes_quantity == 100
        assert position.no_quantity == 50

    def test_position_is_immutable(self) -> None:
        """Position should be immutable."""
        position = Position(
            market_id="TEST",
            yes_quantity=100,
            no_quantity=50,
            avg_yes_price=Price(Decimal("0.45")),
            avg_no_price=Price(Decimal("0.55")),
        )
        with pytest.raises((AttributeError, TypeError)):
            position.yes_quantity = 200  # type: ignore[misc]

    def test_net_inventory_long_yes(self) -> None:
        """net_inventory positive when net long YES."""
        position = Position(
            market_id="TEST",
            yes_quantity=100,
            no_quantity=30,
            avg_yes_price=Price(Decimal("0.45")),
            avg_no_price=Price(Decimal("0.55")),
        )
        assert position.net_inventory() == 70  # 100 - 30

    def test_net_inventory_long_no(self) -> None:
        """net_inventory negative when net long NO."""
        position = Position(
            market_id="TEST",
            yes_quantity=30,
            no_quantity=100,
            avg_yes_price=Price(Decimal("0.45")),
            avg_no_price=Price(Decimal("0.55")),
        )
        assert position.net_inventory() == -70  # 30 - 100

    def test_net_inventory_flat(self) -> None:
        """net_inventory zero when flat."""
        position = Position(
            market_id="TEST",
            yes_quantity=50,
            no_quantity=50,
            avg_yes_price=Price(Decimal("0.45")),
            avg_no_price=Price(Decimal("0.55")),
        )
        assert position.net_inventory() == 0

    def test_notional_exposure_yes_only(self) -> None:
        """notional_exposure for YES position."""
        position = Position(
            market_id="TEST",
            yes_quantity=100,
            no_quantity=0,
            avg_yes_price=Price(Decimal("0.45")),
            avg_no_price=None,
        )
        # 100 * 0.45 = 45
        assert position.notional_exposure() == Decimal("45")

    def test_notional_exposure_both_sides(self) -> None:
        """notional_exposure sums both sides."""
        position = Position(
            market_id="TEST",
            yes_quantity=100,
            no_quantity=50,
            avg_yes_price=Price(Decimal("0.45")),
            avg_no_price=Price(Decimal("0.55")),
        )
        # (100 * 0.45) + (50 * 0.55) = 45 + 27.5 = 72.5
        assert position.notional_exposure() == Decimal("72.5")

    def test_empty_position(self) -> None:
        """Empty position has zero quantities."""
        position = Position.empty(market_id="TEST")
        assert position.yes_quantity == 0
        assert position.no_quantity == 0
        assert position.avg_yes_price is None
        assert position.avg_no_price is None

    def test_is_empty_true(self) -> None:
        """is_empty returns True for empty position."""
        position = Position.empty(market_id="TEST")
        assert position.is_empty()

    def test_is_empty_false(self) -> None:
        """is_empty returns False for non-empty position."""
        position = Position(
            market_id="TEST",
            yes_quantity=100,
            no_quantity=0,
            avg_yes_price=Price(Decimal("0.45")),
            avg_no_price=None,
        )
        assert not position.is_empty()

    def test_with_fill_buy_yes(self) -> None:
        """with_fill updates YES position correctly."""
        position = Position.empty(market_id="TEST")
        new_position = position.with_fill(
            side_is_yes=True,
            is_buy=True,
            quantity=100,
            price=Price(Decimal("0.45")),
        )
        assert new_position.yes_quantity == 100
        assert new_position.avg_yes_price is not None
        assert new_position.avg_yes_price.value == Decimal("0.45")

    def test_with_fill_sell_yes(self) -> None:
        """with_fill decreases YES position on sell."""
        position = Position(
            market_id="TEST",
            yes_quantity=100,
            no_quantity=0,
            avg_yes_price=Price(Decimal("0.45")),
            avg_no_price=None,
        )
        new_position = position.with_fill(
            side_is_yes=True,
            is_buy=False,
            quantity=40,
            price=Price(Decimal("0.50")),
        )
        assert new_position.yes_quantity == 60
        # Avg price unchanged on sell
        assert new_position.avg_yes_price is not None
        assert new_position.avg_yes_price.value == Decimal("0.45")

    def test_with_fill_avg_price_calculation(self) -> None:
        """with_fill calculates weighted average price."""
        position = Position(
            market_id="TEST",
            yes_quantity=100,
            no_quantity=0,
            avg_yes_price=Price(Decimal("0.40")),
            avg_no_price=None,
        )
        # Add 100 more at 0.50
        new_position = position.with_fill(
            side_is_yes=True,
            is_buy=True,
            quantity=100,
            price=Price(Decimal("0.50")),
        )
        assert new_position.yes_quantity == 200
        # Weighted avg: (100 * 0.40 + 100 * 0.50) / 200 = 0.45
        assert new_position.avg_yes_price is not None
        assert new_position.avg_yes_price.value == Decimal("0.45")


class TestBalance:
    """Tests for Balance model."""

    def test_create_balance(self) -> None:
        """Balance stores total and available."""
        balance = Balance(
            total=Decimal("1000.00"),
            available=Decimal("800.00"),
        )
        assert balance.total == Decimal("1000.00")
        assert balance.available == Decimal("800.00")

    def test_balance_is_immutable(self) -> None:
        """Balance should be immutable."""
        balance = Balance(
            total=Decimal("1000.00"),
            available=Decimal("800.00"),
        )
        with pytest.raises((AttributeError, TypeError)):
            balance.total = Decimal("2000.00")  # type: ignore[misc]

    def test_reserved(self) -> None:
        """reserved returns total - available."""
        balance = Balance(
            total=Decimal("1000.00"),
            available=Decimal("800.00"),
        )
        assert balance.reserved() == Decimal("200.00")

    def test_can_afford_true(self) -> None:
        """can_afford True when amount <= available."""
        balance = Balance(
            total=Decimal("1000.00"),
            available=Decimal("800.00"),
        )
        assert balance.can_afford(Decimal("500.00"))
        assert balance.can_afford(Decimal("800.00"))

    def test_can_afford_false(self) -> None:
        """can_afford False when amount > available."""
        balance = Balance(
            total=Decimal("1000.00"),
            available=Decimal("800.00"),
        )
        assert not balance.can_afford(Decimal("900.00"))


class TestPnLSnapshot:
    """Tests for PnLSnapshot model."""

    def test_create_pnl_snapshot(self) -> None:
        """PnLSnapshot stores PnL data."""
        snapshot = PnLSnapshot(
            timestamp=datetime(2026, 1, 17, 12, 0, 0, tzinfo=UTC),
            realized_pnl=Decimal("50.00"),
            unrealized_pnl=Decimal("25.00"),
            total_pnl=Decimal("75.00"),
            positions={"TEST": Position.empty("TEST")},
        )
        assert snapshot.realized_pnl == Decimal("50.00")
        assert snapshot.total_pnl == Decimal("75.00")

    def test_pnl_snapshot_is_immutable(self) -> None:
        """PnLSnapshot should be immutable."""
        snapshot = PnLSnapshot(
            timestamp=datetime.now(UTC),
            realized_pnl=Decimal("50.00"),
            unrealized_pnl=Decimal("25.00"),
            total_pnl=Decimal("75.00"),
            positions={},
        )
        with pytest.raises((AttributeError, TypeError)):
            snapshot.realized_pnl = Decimal("100.00")  # type: ignore[misc]

    def test_from_positions(self) -> None:
        """from_positions calculates unrealized PnL."""
        positions = {
            "TEST": Position(
                market_id="TEST",
                yes_quantity=100,
                no_quantity=0,
                avg_yes_price=Price(Decimal("0.40")),
                avg_no_price=None,
            )
        }
        current_prices = {"TEST": Price(Decimal("0.50"))}

        snapshot = PnLSnapshot.from_positions(
            positions=positions,
            current_prices=current_prices,
            realized_pnl=Decimal("10.00"),
        )

        # Unrealized: 100 * (0.50 - 0.40) = 10.00
        assert snapshot.unrealized_pnl == Decimal("10.00")
        assert snapshot.total_pnl == Decimal("20.00")  # 10 realized + 10 unrealized

    def test_from_positions_loss(self) -> None:
        """from_positions handles unrealized losses."""
        positions = {
            "TEST": Position(
                market_id="TEST",
                yes_quantity=100,
                no_quantity=0,
                avg_yes_price=Price(Decimal("0.50")),
                avg_no_price=None,
            )
        }
        current_prices = {"TEST": Price(Decimal("0.40"))}

        snapshot = PnLSnapshot.from_positions(
            positions=positions,
            current_prices=current_prices,
            realized_pnl=Decimal("0.00"),
        )

        # Unrealized: 100 * (0.40 - 0.50) = -10.00
        assert snapshot.unrealized_pnl == Decimal("-10.00")
        assert snapshot.total_pnl == Decimal("-10.00")
