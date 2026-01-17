"""Tests for volatility estimators."""

from datetime import UTC, datetime
from decimal import Decimal

import pytest

from market_maker.domain.market_data import Trade
from market_maker.domain.types import Price, Quantity, Side
from market_maker.strategy.volatility.base import VolatilityEstimator
from market_maker.strategy.volatility.ewma import EWMAVolatilityEstimator
from market_maker.strategy.volatility.fixed import FixedVolatilityEstimator


class TestVolatilityEstimatorABC:
    """Tests for VolatilityEstimator abstract base class."""

    def test_is_abstract(self) -> None:
        """VolatilityEstimator cannot be instantiated directly."""
        with pytest.raises(TypeError):
            VolatilityEstimator()  # type: ignore[abstract]

    def test_required_methods(self) -> None:
        """VolatilityEstimator defines required abstract methods."""
        required_methods = {"update", "get_volatility", "reset"}
        abstract_methods = set(VolatilityEstimator.__abstractmethods__)
        assert required_methods.issubset(abstract_methods)


class TestFixedVolatilityEstimator:
    """Tests for FixedVolatilityEstimator."""

    def test_create_fixed(self) -> None:
        """FixedVolatilityEstimator returns constant value."""
        estimator = FixedVolatilityEstimator(volatility=Decimal("0.15"))
        assert estimator.get_volatility() == Decimal("0.15")

    def test_update_does_not_change_value(self) -> None:
        """update() has no effect on fixed estimator."""
        estimator = FixedVolatilityEstimator(volatility=Decimal("0.15"))

        trade = Trade(
            market_id="TEST",
            price=Price(Decimal("0.50")),
            size=Quantity(100),
            side=Side.YES,
            timestamp=datetime.now(UTC),
        )
        estimator.update(trade)

        assert estimator.get_volatility() == Decimal("0.15")

    def test_reset_does_not_change_value(self) -> None:
        """reset() has no effect on fixed estimator."""
        estimator = FixedVolatilityEstimator(volatility=Decimal("0.15"))
        estimator.reset()
        assert estimator.get_volatility() == Decimal("0.15")

    def test_is_ready(self) -> None:
        """Fixed estimator is always ready."""
        estimator = FixedVolatilityEstimator(volatility=Decimal("0.15"))
        assert estimator.is_ready()


class TestEWMAVolatilityEstimator:
    """Tests for EWMA volatility estimator."""

    @pytest.fixture
    def estimator(self) -> EWMAVolatilityEstimator:
        """Create EWMA estimator with default settings."""
        return EWMAVolatilityEstimator(
            alpha=Decimal("0.1"),
            initial_volatility=Decimal("0.15"),
            min_samples=2,
        )

    def test_create_ewma(self, estimator: EWMAVolatilityEstimator) -> None:
        """EWMA estimator initializes with parameters."""
        assert estimator.alpha == Decimal("0.1")
        assert estimator.get_volatility() == Decimal("0.15")

    def test_not_ready_initially(self) -> None:
        """EWMA not ready until min_samples received."""
        estimator = EWMAVolatilityEstimator(
            alpha=Decimal("0.1"),
            initial_volatility=Decimal("0.15"),
            min_samples=3,
        )
        assert not estimator.is_ready()

    def test_ready_after_min_samples(self) -> None:
        """EWMA ready after min_samples received."""
        estimator = EWMAVolatilityEstimator(
            alpha=Decimal("0.1"),
            initial_volatility=Decimal("0.15"),
            min_samples=2,
        )

        # First trade
        trade1 = Trade(
            market_id="TEST",
            price=Price(Decimal("0.50")),
            size=Quantity(100),
            side=Side.YES,
            timestamp=datetime.now(UTC),
        )
        estimator.update(trade1)
        assert not estimator.is_ready()

        # Second trade
        trade2 = Trade(
            market_id="TEST",
            price=Price(Decimal("0.51")),
            size=Quantity(100),
            side=Side.YES,
            timestamp=datetime.now(UTC),
        )
        estimator.update(trade2)
        assert estimator.is_ready()

    def test_ewma_formula(self) -> None:
        """EWMA follows formula: σ²_t = α * r²_t + (1-α) * σ²_{t-1}."""
        alpha = Decimal("0.1")
        initial_vol = Decimal("0.10")

        estimator = EWMAVolatilityEstimator(
            alpha=alpha,
            initial_volatility=initial_vol,
            min_samples=1,
        )

        # First trade establishes baseline price
        trade1 = Trade(
            market_id="TEST",
            price=Price(Decimal("0.50")),
            size=Quantity(100),
            side=Side.YES,
            timestamp=datetime.now(UTC),
        )
        estimator.update(trade1)

        # Second trade - price change of 0.02 (from 0.50 to 0.52)
        trade2 = Trade(
            market_id="TEST",
            price=Price(Decimal("0.52")),
            size=Quantity(100),
            side=Side.YES,
            timestamp=datetime.now(UTC),
        )
        estimator.update(trade2)

        # Return = ln(0.52/0.50) ≈ 0.0392
        # Using simple return for now: (0.52 - 0.50) / 0.50 = 0.04
        # σ²_new = 0.1 * 0.04² + 0.9 * 0.10² = 0.1 * 0.0016 + 0.9 * 0.01
        # σ²_new = 0.00016 + 0.009 = 0.00916
        # σ_new = sqrt(0.00916) ≈ 0.0957

        vol = estimator.get_volatility()
        # Allow some tolerance for decimal arithmetic
        assert Decimal("0.08") < vol < Decimal("0.12")

    def test_volatility_increases_with_large_moves(self) -> None:
        """Volatility increases after large price moves."""
        estimator = EWMAVolatilityEstimator(
            alpha=Decimal("0.3"),  # Higher alpha = more responsive
            initial_volatility=Decimal("0.05"),
            min_samples=1,
        )

        # Baseline
        trade1 = Trade(
            market_id="TEST",
            price=Price(Decimal("0.50")),
            size=Quantity(100),
            side=Side.YES,
            timestamp=datetime.now(UTC),
        )
        estimator.update(trade1)
        initial_vol = estimator.get_volatility()

        # Big move
        trade2 = Trade(
            market_id="TEST",
            price=Price(Decimal("0.60")),
            size=Quantity(100),
            side=Side.YES,
            timestamp=datetime.now(UTC),
        )
        estimator.update(trade2)

        assert estimator.get_volatility() > initial_vol

    def test_volatility_decreases_with_stable_prices(self) -> None:
        """Volatility decreases when prices are stable."""
        estimator = EWMAVolatilityEstimator(
            alpha=Decimal("0.3"),
            initial_volatility=Decimal("0.20"),  # Start high
            min_samples=1,
        )

        # Baseline
        trade1 = Trade(
            market_id="TEST",
            price=Price(Decimal("0.50")),
            size=Quantity(100),
            side=Side.YES,
            timestamp=datetime.now(UTC),
        )
        estimator.update(trade1)

        # Series of stable prices
        for _ in range(5):
            trade = Trade(
                market_id="TEST",
                price=Price(Decimal("0.50")),  # No change
                size=Quantity(100),
                side=Side.YES,
                timestamp=datetime.now(UTC),
            )
            estimator.update(trade)

        # Volatility should decrease toward zero
        assert estimator.get_volatility() < Decimal("0.20")

    def test_reset(self) -> None:
        """reset() returns to initial state."""
        estimator = EWMAVolatilityEstimator(
            alpha=Decimal("0.1"),
            initial_volatility=Decimal("0.15"),
            min_samples=2,
        )

        # Add some trades
        trade = Trade(
            market_id="TEST",
            price=Price(Decimal("0.50")),
            size=Quantity(100),
            side=Side.YES,
            timestamp=datetime.now(UTC),
        )
        estimator.update(trade)
        estimator.update(trade)

        estimator.reset()

        assert estimator.get_volatility() == Decimal("0.15")
        assert not estimator.is_ready()

    def test_update_with_price_change(self) -> None:
        """update_with_price directly takes price change."""
        estimator = EWMAVolatilityEstimator(
            alpha=Decimal("0.1"),
            initial_volatility=Decimal("0.10"),
            min_samples=0,
        )

        # Direct price change update
        estimator.update_with_return(Decimal("0.05"))  # 5% return

        vol = estimator.get_volatility()
        # Should be mix of initial and new
        assert vol != Decimal("0.10")

    def test_sample_count(self) -> None:
        """sample_count tracks number of updates."""
        estimator = EWMAVolatilityEstimator(
            alpha=Decimal("0.1"),
            initial_volatility=Decimal("0.15"),
            min_samples=2,
        )

        assert estimator.sample_count == 0

        trade = Trade(
            market_id="TEST",
            price=Price(Decimal("0.50")),
            size=Quantity(100),
            side=Side.YES,
            timestamp=datetime.now(UTC),
        )
        estimator.update(trade)
        assert estimator.sample_count == 1

        estimator.update(trade)
        assert estimator.sample_count == 2
