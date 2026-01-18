"""Tests for trading repository."""

import tempfile
from datetime import UTC, datetime
from decimal import Decimal

import pytest

from market_maker.db.repository import TradingRepository
from market_maker.domain.orders import Fill, Order, OrderStatus
from market_maker.domain.positions import PnLSnapshot, Position
from market_maker.domain.types import OrderSide, Price, Quantity, Side


class TestTradingRepository:
    """Tests for TradingRepository."""

    @pytest.fixture
    def repo(self) -> TradingRepository:
        """Create repository with in-memory database."""
        return TradingRepository(
            db_url="sqlite:///:memory:",
            session_id="test-session",
        )

    @pytest.fixture
    def sample_order(self) -> Order:
        """Create sample order."""
        return Order(
            id="order-123",
            client_order_id="client-123",
            market_id="TEST-MARKET",
            side=Side.YES,
            order_side=OrderSide.BUY,
            price=Price(Decimal("0.45")),
            size=Quantity(10),
            filled_size=0,
            status=OrderStatus.OPEN,
            created_at=datetime.now(UTC),
            updated_at=datetime.now(UTC),
        )

    @pytest.fixture
    def sample_fill(self) -> Fill:
        """Create sample fill."""
        return Fill(
            id="fill-1",
            order_id="order-123",
            market_id="TEST-MARKET",
            side=Side.YES,
            order_side=OrderSide.BUY,
            price=Price(Decimal("0.45")),
            size=Quantity(5),
            timestamp=datetime.now(UTC),
            is_simulated=False,
        )

    def test_save_and_get_order(
        self,
        repo: TradingRepository,
        sample_order: Order,
    ) -> None:
        """Should save and retrieve order."""
        repo.save_order(sample_order)

        result = repo.get_order("order-123")

        assert result is not None
        assert result.id == "order-123"
        assert result.market_id == "TEST-MARKET"
        assert result.price.value == Decimal("0.45")
        assert result.status == OrderStatus.OPEN

    def test_update_order(
        self,
        repo: TradingRepository,
        sample_order: Order,
    ) -> None:
        """Should update existing order."""
        repo.save_order(sample_order)

        # Update order
        updated = Order(
            id="order-123",
            client_order_id="client-123",
            market_id="TEST-MARKET",
            side=Side.YES,
            order_side=OrderSide.BUY,
            price=Price(Decimal("0.45")),
            size=Quantity(10),
            filled_size=5,
            status=OrderStatus.PARTIALLY_FILLED,
            created_at=sample_order.created_at,
            updated_at=datetime.now(UTC),
        )
        repo.save_order(updated)

        result = repo.get_order("order-123")
        assert result is not None
        assert result.filled_size == 5
        assert result.status == OrderStatus.PARTIALLY_FILLED

    def test_get_order_not_found(self, repo: TradingRepository) -> None:
        """Should return None for unknown order."""
        result = repo.get_order("unknown")
        assert result is None

    def test_get_orders_by_market(
        self,
        repo: TradingRepository,
        sample_order: Order,
    ) -> None:
        """Should get orders for market."""
        repo.save_order(sample_order)

        # Add another order for different market
        other_order = Order(
            id="order-456",
            client_order_id="client-456",
            market_id="OTHER-MARKET",
            side=Side.YES,
            order_side=OrderSide.BUY,
            price=Price(Decimal("0.50")),
            size=Quantity(5),
            filled_size=0,
            status=OrderStatus.OPEN,
            created_at=datetime.now(UTC),
            updated_at=datetime.now(UTC),
        )
        repo.save_order(other_order)

        result = repo.get_orders_by_market("TEST-MARKET")

        assert len(result) == 1
        assert result[0].id == "order-123"

    def test_get_orders_by_status(
        self,
        repo: TradingRepository,
        sample_order: Order,
    ) -> None:
        """Should filter orders by status."""
        repo.save_order(sample_order)

        # Add cancelled order
        cancelled = Order(
            id="order-456",
            client_order_id="client-456",
            market_id="TEST-MARKET",
            side=Side.YES,
            order_side=OrderSide.BUY,
            price=Price(Decimal("0.50")),
            size=Quantity(5),
            filled_size=0,
            status=OrderStatus.CANCELLED,
            created_at=datetime.now(UTC),
            updated_at=datetime.now(UTC),
        )
        repo.save_order(cancelled)

        result = repo.get_orders_by_market("TEST-MARKET", status=OrderStatus.OPEN)

        assert len(result) == 1
        assert result[0].id == "order-123"

    def test_save_and_get_fill(
        self,
        repo: TradingRepository,
        sample_fill: Fill,
    ) -> None:
        """Should save and retrieve fill."""
        repo.save_fill(sample_fill)

        result = repo.get_fills_by_order("order-123")

        assert len(result) == 1
        assert result[0].id == "fill-1"
        assert result[0].size.value == 5

    def test_get_fills_by_market(
        self,
        repo: TradingRepository,
        sample_fill: Fill,
    ) -> None:
        """Should get fills for market."""
        repo.save_fill(sample_fill)

        result = repo.get_fills_by_market("TEST-MARKET")

        assert len(result) == 1
        assert result[0].market_id == "TEST-MARKET"

    def test_save_pnl_snapshot(self, repo: TradingRepository) -> None:
        """Should save PnL snapshot."""
        position = Position(
            market_id="TEST-MARKET",
            yes_quantity=10,
            no_quantity=0,
            avg_yes_price=Price(Decimal("0.45")),
            avg_no_price=None,
        )
        snapshot = PnLSnapshot(
            timestamp=datetime.now(UTC),
            realized_pnl=Decimal("5.00"),
            unrealized_pnl=Decimal("2.50"),
            total_pnl=Decimal("7.50"),
            positions={"TEST-MARKET": position},
        )

        repo.save_pnl_snapshot("TEST-MARKET", snapshot)

        result = repo.get_latest_pnl("TEST-MARKET")

        assert result is not None
        assert result["realized_pnl"] == 5.0
        assert result["unrealized_pnl"] == 2.5
        assert result["total_pnl"] == 7.5
        assert result["yes_position"] == 10
        assert result["no_position"] == 0

    def test_get_pnl_history(self, repo: TradingRepository) -> None:
        """Should get PnL history."""
        position = Position(
            market_id="TEST-MARKET",
            yes_quantity=10,
            no_quantity=0,
            avg_yes_price=Price(Decimal("0.45")),
            avg_no_price=None,
        )
        snapshot = PnLSnapshot(
            timestamp=datetime.now(UTC),
            realized_pnl=Decimal("5.00"),
            unrealized_pnl=Decimal("2.50"),
            total_pnl=Decimal("7.50"),
            positions={"TEST-MARKET": position},
        )

        repo.save_pnl_snapshot("TEST-MARKET", snapshot)
        repo.save_pnl_snapshot("TEST-MARKET", snapshot)

        history = repo.get_pnl_history("TEST-MARKET")

        assert len(history) == 2

    def test_session_isolation(self) -> None:
        """Should isolate data by session."""
        repo1 = TradingRepository(
            db_url="sqlite:///:memory:",
            session_id="session-1",
        )
        repo2 = TradingRepository(
            db_url="sqlite:///:memory:",
            session_id="session-2",
        )

        order = Order(
            id="order-123",
            client_order_id="client-123",
            market_id="TEST-MARKET",
            side=Side.YES,
            order_side=OrderSide.BUY,
            price=Price(Decimal("0.45")),
            size=Quantity(10),
            filled_size=0,
            status=OrderStatus.OPEN,
            created_at=datetime.now(UTC),
            updated_at=datetime.now(UTC),
        )

        repo1.save_order(order)

        # Different session shouldn't see the order
        result = repo2.get_orders_by_session()
        assert len(result) == 0
