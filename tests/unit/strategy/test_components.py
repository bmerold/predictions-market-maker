"""Tests for strategy components."""

from decimal import Decimal

import pytest

from market_maker.strategy.components.base import (
    QuoteSizer,
    ReservationPriceCalculator,
    SkewCalculator,
    SpreadCalculator,
)
from market_maker.strategy.components.reservation import AvellanedaStoikovReservation
from market_maker.strategy.components.sizer import AsymmetricSizer
from market_maker.strategy.components.skew import LinearSkew
from market_maker.strategy.components.spread import FixedSpread


class TestReservationPriceCalculatorABC:
    """Tests for ReservationPriceCalculator abstract base class."""

    def test_is_abstract(self) -> None:
        """ReservationPriceCalculator cannot be instantiated directly."""
        with pytest.raises(TypeError):
            ReservationPriceCalculator()  # type: ignore[abstract]

    def test_required_methods(self) -> None:
        """ReservationPriceCalculator defines required abstract methods."""
        required_methods = {"calculate"}
        abstract_methods = set(ReservationPriceCalculator.__abstractmethods__)
        assert required_methods.issubset(abstract_methods)


class TestSkewCalculatorABC:
    """Tests for SkewCalculator abstract base class."""

    def test_is_abstract(self) -> None:
        """SkewCalculator cannot be instantiated directly."""
        with pytest.raises(TypeError):
            SkewCalculator()  # type: ignore[abstract]

    def test_required_methods(self) -> None:
        """SkewCalculator defines required abstract methods."""
        required_methods = {"calculate"}
        abstract_methods = set(SkewCalculator.__abstractmethods__)
        assert required_methods.issubset(abstract_methods)


class TestSpreadCalculatorABC:
    """Tests for SpreadCalculator abstract base class."""

    def test_is_abstract(self) -> None:
        """SpreadCalculator cannot be instantiated directly."""
        with pytest.raises(TypeError):
            SpreadCalculator()  # type: ignore[abstract]

    def test_required_methods(self) -> None:
        """SpreadCalculator defines required abstract methods."""
        required_methods = {"calculate"}
        abstract_methods = set(SpreadCalculator.__abstractmethods__)
        assert required_methods.issubset(abstract_methods)


class TestQuoteSizerABC:
    """Tests for QuoteSizer abstract base class."""

    def test_is_abstract(self) -> None:
        """QuoteSizer cannot be instantiated directly."""
        with pytest.raises(TypeError):
            QuoteSizer()  # type: ignore[abstract]

    def test_required_methods(self) -> None:
        """QuoteSizer defines required abstract methods."""
        required_methods = {"calculate"}
        abstract_methods = set(QuoteSizer.__abstractmethods__)
        assert required_methods.issubset(abstract_methods)


class TestAvellanedaStoikovReservation:
    """Tests for Avellaneda-Stoikov reservation price calculator."""

    @pytest.fixture
    def calculator(self) -> AvellanedaStoikovReservation:
        """Create calculator with default gamma."""
        return AvellanedaStoikovReservation(gamma=Decimal("0.1"))

    def test_create(self, calculator: AvellanedaStoikovReservation) -> None:
        """AvellanedaStoikov initializes with gamma parameter."""
        assert calculator.gamma == Decimal("0.1")

    def test_formula_no_inventory(self, calculator: AvellanedaStoikovReservation) -> None:
        """With zero inventory, reservation price equals mid price."""
        # r = s - q / (γ * σ² * T)
        # With q=0: r = s
        result = calculator.calculate(
            mid_price=Decimal("0.50"),
            inventory=0,
            volatility=Decimal("0.10"),
            time_to_settlement=1.0,
        )
        assert result == Decimal("0.50")

    def test_formula_positive_inventory(
        self, calculator: AvellanedaStoikovReservation
    ) -> None:
        """With positive inventory, reservation price is below mid."""
        # r = s - q / (γ * σ² * T)
        # s = 0.50, q = 10, γ = 0.1, σ = 0.10, T = 1.0
        # r = 0.50 - 10 / (0.1 * 0.01 * 1.0)
        # r = 0.50 - 10 / 0.001 = 0.50 - 10000 = very negative
        # Let's use smaller inventory for practical test
        result = calculator.calculate(
            mid_price=Decimal("0.50"),
            inventory=1,
            volatility=Decimal("0.10"),
            time_to_settlement=1.0,
        )
        # r = 0.50 - 1 / (0.1 * 0.01 * 1.0)
        # r = 0.50 - 1 / 0.001 = 0.50 - 1000 (unbounded)
        # This shows we should use realistic parameters
        assert result < Decimal("0.50")  # Below mid when long

    def test_formula_negative_inventory(
        self, calculator: AvellanedaStoikovReservation
    ) -> None:
        """With negative inventory, reservation price is above mid."""
        result = calculator.calculate(
            mid_price=Decimal("0.50"),
            inventory=-1,
            volatility=Decimal("0.10"),
            time_to_settlement=1.0,
        )
        assert result > Decimal("0.50")  # Above mid when short

    def test_higher_gamma_reduces_adjustment(self) -> None:
        """Higher gamma (more risk averse) means smaller price adjustment."""
        low_gamma = AvellanedaStoikovReservation(gamma=Decimal("0.01"))
        high_gamma = AvellanedaStoikovReservation(gamma=Decimal("1.0"))

        low_result = low_gamma.calculate(
            mid_price=Decimal("0.50"),
            inventory=1,
            volatility=Decimal("0.10"),
            time_to_settlement=1.0,
        )
        high_result = high_gamma.calculate(
            mid_price=Decimal("0.50"),
            inventory=1,
            volatility=Decimal("0.10"),
            time_to_settlement=1.0,
        )

        # Both below mid (positive inventory), but high gamma closer to mid
        assert low_result < high_result < Decimal("0.50")

    def test_shorter_time_increases_adjustment(
        self, calculator: AvellanedaStoikovReservation
    ) -> None:
        """Shorter time to settlement increases adjustment magnitude."""
        long_time = calculator.calculate(
            mid_price=Decimal("0.50"),
            inventory=1,
            volatility=Decimal("0.10"),
            time_to_settlement=1.0,
        )
        short_time = calculator.calculate(
            mid_price=Decimal("0.50"),
            inventory=1,
            volatility=Decimal("0.10"),
            time_to_settlement=0.1,
        )

        # Both below mid, but shorter time = more aggressive adjustment
        assert short_time < long_time < Decimal("0.50")

    def test_handles_zero_time(self, calculator: AvellanedaStoikovReservation) -> None:
        """Handles edge case of zero time (avoid division by zero)."""
        result = calculator.calculate(
            mid_price=Decimal("0.50"),
            inventory=1,
            volatility=Decimal("0.10"),
            time_to_settlement=0.0,
        )
        # Should return mid price or clamped value, not crash
        assert result is not None

    def test_handles_zero_volatility(
        self, calculator: AvellanedaStoikovReservation
    ) -> None:
        """Handles edge case of zero volatility."""
        result = calculator.calculate(
            mid_price=Decimal("0.50"),
            inventory=1,
            volatility=Decimal("0"),
            time_to_settlement=1.0,
        )
        # Should return mid price or clamped value, not crash
        assert result is not None


class TestLinearSkew:
    """Tests for LinearSkew calculator."""

    @pytest.fixture
    def skew(self) -> LinearSkew:
        """Create LinearSkew with default intensity."""
        return LinearSkew(intensity=Decimal("0.01"))

    def test_create(self, skew: LinearSkew) -> None:
        """LinearSkew initializes with intensity parameter."""
        assert skew.intensity == Decimal("0.01")

    def test_zero_inventory_no_skew(self, skew: LinearSkew) -> None:
        """With zero inventory, skew is zero."""
        result = skew.calculate(
            inventory=0,
            max_inventory=100,
            volatility=Decimal("0.10"),
        )
        assert result == Decimal("0")

    def test_positive_inventory_positive_skew(self, skew: LinearSkew) -> None:
        """Positive inventory creates positive skew (shift quotes down)."""
        result = skew.calculate(
            inventory=50,
            max_inventory=100,
            volatility=Decimal("0.10"),
        )
        # skew = k * (q / Q_max) = 0.01 * (50 / 100) = 0.005
        assert result == Decimal("0.005")

    def test_negative_inventory_negative_skew(self, skew: LinearSkew) -> None:
        """Negative inventory creates negative skew (shift quotes up)."""
        result = skew.calculate(
            inventory=-50,
            max_inventory=100,
            volatility=Decimal("0.10"),
        )
        # skew = k * (q / Q_max) = 0.01 * (-50 / 100) = -0.005
        assert result == Decimal("-0.005")

    def test_max_inventory_max_skew(self, skew: LinearSkew) -> None:
        """At max inventory, skew equals intensity."""
        result = skew.calculate(
            inventory=100,
            max_inventory=100,
            volatility=Decimal("0.10"),
        )
        # skew = k * (q / Q_max) = 0.01 * (100 / 100) = 0.01
        assert result == Decimal("0.01")

    def test_intensity_scales_skew(self) -> None:
        """Higher intensity creates larger skew."""
        low = LinearSkew(intensity=Decimal("0.01"))
        high = LinearSkew(intensity=Decimal("0.05"))

        low_result = low.calculate(
            inventory=50, max_inventory=100, volatility=Decimal("0.10")
        )
        high_result = high.calculate(
            inventory=50, max_inventory=100, volatility=Decimal("0.10")
        )

        assert high_result > low_result


class TestFixedSpread:
    """Tests for FixedSpread calculator."""

    @pytest.fixture
    def spread(self) -> FixedSpread:
        """Create FixedSpread with default base spread."""
        return FixedSpread(base_spread=Decimal("0.02"))

    def test_create(self, spread: FixedSpread) -> None:
        """FixedSpread initializes with base_spread parameter."""
        assert spread.base_spread == Decimal("0.02")

    def test_returns_half_spread(self, spread: FixedSpread) -> None:
        """Returns half of base spread."""
        result = spread.calculate(
            volatility=Decimal("0.10"),
            inventory=0,
            max_inventory=100,
            time_to_settlement=1.0,
        )
        # δ = base_spread / 2 = 0.02 / 2 = 0.01
        assert result == Decimal("0.01")

    def test_ignores_volatility(self, spread: FixedSpread) -> None:
        """Fixed spread ignores volatility."""
        low_vol = spread.calculate(
            volatility=Decimal("0.01"),
            inventory=0,
            max_inventory=100,
            time_to_settlement=1.0,
        )
        high_vol = spread.calculate(
            volatility=Decimal("0.50"),
            inventory=0,
            max_inventory=100,
            time_to_settlement=1.0,
        )
        assert low_vol == high_vol == Decimal("0.01")

    def test_ignores_inventory(self, spread: FixedSpread) -> None:
        """Fixed spread ignores inventory."""
        no_inv = spread.calculate(
            volatility=Decimal("0.10"),
            inventory=0,
            max_inventory=100,
            time_to_settlement=1.0,
        )
        full_inv = spread.calculate(
            volatility=Decimal("0.10"),
            inventory=100,
            max_inventory=100,
            time_to_settlement=1.0,
        )
        assert no_inv == full_inv == Decimal("0.01")

    def test_respects_min_spread(self) -> None:
        """Returns at least minimum spread."""
        tiny_spread = FixedSpread(base_spread=Decimal("0.001"), min_spread=Decimal("0.01"))
        result = tiny_spread.calculate(
            volatility=Decimal("0.10"),
            inventory=0,
            max_inventory=100,
            time_to_settlement=1.0,
        )
        # base_spread/2 = 0.0005, but min_spread/2 = 0.005
        assert result == Decimal("0.005")


class TestAsymmetricSizer:
    """Tests for AsymmetricSizer."""

    @pytest.fixture
    def sizer(self) -> AsymmetricSizer:
        """Create AsymmetricSizer with default settings."""
        return AsymmetricSizer()

    def test_zero_inventory_equal_sizes(self, sizer: AsymmetricSizer) -> None:
        """With zero inventory, bid and ask sizes are equal."""
        bid_size, ask_size = sizer.calculate(
            inventory=0,
            max_inventory=100,
            base_size=100,
        )
        assert bid_size == ask_size == 100

    def test_positive_inventory_smaller_bid(self, sizer: AsymmetricSizer) -> None:
        """Positive inventory reduces bid size (don't buy more)."""
        bid_size, ask_size = sizer.calculate(
            inventory=50,
            max_inventory=100,
            base_size=100,
        )
        assert bid_size < ask_size
        assert bid_size < 100
        assert ask_size <= 100

    def test_negative_inventory_smaller_ask(self, sizer: AsymmetricSizer) -> None:
        """Negative inventory reduces ask size (don't sell more)."""
        bid_size, ask_size = sizer.calculate(
            inventory=-50,
            max_inventory=100,
            base_size=100,
        )
        assert ask_size < bid_size
        assert ask_size < 100
        assert bid_size <= 100

    def test_max_inventory_zero_bid(self, sizer: AsymmetricSizer) -> None:
        """At max inventory, bid size is zero."""
        bid_size, ask_size = sizer.calculate(
            inventory=100,
            max_inventory=100,
            base_size=100,
        )
        assert bid_size == 0
        assert ask_size > 0

    def test_min_inventory_zero_ask(self, sizer: AsymmetricSizer) -> None:
        """At min inventory (negative max), ask size is zero."""
        bid_size, ask_size = sizer.calculate(
            inventory=-100,
            max_inventory=100,
            base_size=100,
        )
        assert ask_size == 0
        assert bid_size > 0

    def test_returns_integers(self, sizer: AsymmetricSizer) -> None:
        """Sizes are always integers."""
        bid_size, ask_size = sizer.calculate(
            inventory=33,
            max_inventory=100,
            base_size=100,
        )
        assert isinstance(bid_size, int)
        assert isinstance(ask_size, int)

    def test_sizes_non_negative(self, sizer: AsymmetricSizer) -> None:
        """Sizes are never negative."""
        bid_size, ask_size = sizer.calculate(
            inventory=150,  # Beyond max
            max_inventory=100,
            base_size=100,
        )
        assert bid_size >= 0
        assert ask_size >= 0
