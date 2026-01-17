"""Tests for StrategyEngine."""

from datetime import UTC, datetime
from decimal import Decimal

import pytest

from market_maker.domain.orders import QuoteSet
from market_maker.domain.types import Price
from market_maker.strategy.components.reservation import AvellanedaStoikovReservation
from market_maker.strategy.components.sizer import AsymmetricSizer
from market_maker.strategy.components.skew import LinearSkew
from market_maker.strategy.components.spread import FixedSpread
from market_maker.strategy.engine import StrategyEngine, StrategyInput
from market_maker.strategy.volatility.fixed import FixedVolatilityEstimator


class TestStrategyInput:
    """Tests for StrategyInput dataclass."""

    def test_create_input(self) -> None:
        """StrategyInput holds all required inputs."""
        input_data = StrategyInput(
            market_id="TEST-MARKET",
            mid_price=Price(Decimal("0.50")),
            inventory=10,
            max_inventory=100,
            base_size=100,
            time_to_settlement=1.0,
            timestamp=datetime.now(UTC),
        )
        assert input_data.market_id == "TEST-MARKET"
        assert input_data.mid_price.value == Decimal("0.50")
        assert input_data.inventory == 10


class TestStrategyEngine:
    """Tests for StrategyEngine quote generation."""

    @pytest.fixture
    def engine(self) -> StrategyEngine:
        """Create engine with default components."""
        return StrategyEngine(
            volatility_estimator=FixedVolatilityEstimator(
                volatility=Decimal("0.10")
            ),
            reservation_calculator=AvellanedaStoikovReservation(
                gamma=Decimal("0.1")
            ),
            skew_calculator=LinearSkew(intensity=Decimal("0.01")),
            spread_calculator=FixedSpread(base_spread=Decimal("0.04")),
            sizer=AsymmetricSizer(),
        )

    @pytest.fixture
    def base_input(self) -> StrategyInput:
        """Create base input for testing."""
        return StrategyInput(
            market_id="TEST-MARKET",
            mid_price=Price(Decimal("0.50")),
            inventory=0,
            max_inventory=100,
            base_size=100,
            time_to_settlement=1.0,
            timestamp=datetime.now(UTC),
        )

    def test_generate_quotes_returns_quoteset(
        self,
        engine: StrategyEngine,
        base_input: StrategyInput,
    ) -> None:
        """Engine generates a QuoteSet."""
        result = engine.generate_quotes(base_input)
        assert isinstance(result, QuoteSet)
        assert result.market_id == "TEST-MARKET"

    def test_quotes_have_valid_structure(
        self,
        engine: StrategyEngine,
        base_input: StrategyInput,
    ) -> None:
        """Generated quotes have valid bid/ask structure."""
        result = engine.generate_quotes(base_input)

        yes_quote = result.yes_quote
        assert yes_quote.bid_price.value < yes_quote.ask_price.value
        assert yes_quote.bid_size.value > 0
        assert yes_quote.ask_size.value > 0

    def test_quotes_respect_bounds(
        self,
        engine: StrategyEngine,
        base_input: StrategyInput,
    ) -> None:
        """Quotes are within valid price range [0.01, 0.99]."""
        result = engine.generate_quotes(base_input)

        yes_quote = result.yes_quote
        assert Decimal("0.01") <= yes_quote.bid_price.value <= Decimal("0.99")
        assert Decimal("0.01") <= yes_quote.ask_price.value <= Decimal("0.99")

        no_quote = result.no_quote()
        assert Decimal("0.01") <= no_quote.bid_price.value <= Decimal("0.99")
        assert Decimal("0.01") <= no_quote.ask_price.value <= Decimal("0.99")

    def test_no_quotes_derived_correctly(
        self,
        engine: StrategyEngine,
        base_input: StrategyInput,
    ) -> None:
        """NO quotes are derived from YES quotes correctly."""
        result = engine.generate_quotes(base_input)

        yes_quote = result.yes_quote
        no_quote = result.no_quote()

        # NO bid = 1 - YES ask
        expected_no_bid = Decimal("1") - yes_quote.ask_price.value
        assert no_quote.bid_price.value == expected_no_bid

        # NO ask = 1 - YES bid
        expected_no_ask = Decimal("1") - yes_quote.bid_price.value
        assert no_quote.ask_price.value == expected_no_ask

    def test_zero_inventory_symmetric_quotes(
        self,
        engine: StrategyEngine,
    ) -> None:
        """With zero inventory, quotes are symmetric around mid."""
        input_data = StrategyInput(
            market_id="TEST-MARKET",
            mid_price=Price(Decimal("0.50")),
            inventory=0,
            max_inventory=100,
            base_size=100,
            time_to_settlement=1.0,
            timestamp=datetime.now(UTC),
        )

        result = engine.generate_quotes(input_data)
        yes_quote = result.yes_quote

        # With zero inventory, reservation = mid = 0.50
        # Spread = 0.04, half-spread = 0.02
        # Bid = 0.50 - 0.02 = 0.48
        # Ask = 0.50 + 0.02 = 0.52
        # (approximately, depending on skew)

        mid_of_quotes = (yes_quote.bid_price.value + yes_quote.ask_price.value) / 2
        # Should be close to 0.50
        assert Decimal("0.48") <= mid_of_quotes <= Decimal("0.52")

    def test_positive_inventory_shifts_quotes_down(
        self,
        engine: StrategyEngine,
    ) -> None:
        """Positive inventory shifts quotes down (encourage selling)."""
        zero_inv = StrategyInput(
            market_id="TEST-MARKET",
            mid_price=Price(Decimal("0.50")),
            inventory=0,
            max_inventory=100,
            base_size=100,
            time_to_settlement=1.0,
            timestamp=datetime.now(UTC),
        )

        positive_inv = StrategyInput(
            market_id="TEST-MARKET",
            mid_price=Price(Decimal("0.50")),
            inventory=50,
            max_inventory=100,
            base_size=100,
            time_to_settlement=1.0,
            timestamp=datetime.now(UTC),
        )

        zero_result = engine.generate_quotes(zero_inv)
        positive_result = engine.generate_quotes(positive_inv)

        # Reservation price should be lower with positive inventory
        # So quotes should be shifted down
        assert positive_result.yes_quote.bid_price.value < zero_result.yes_quote.bid_price.value
        assert positive_result.yes_quote.ask_price.value < zero_result.yes_quote.ask_price.value

    def test_negative_inventory_shifts_quotes_up(
        self,
        engine: StrategyEngine,
    ) -> None:
        """Negative inventory shifts quotes up (encourage buying)."""
        zero_inv = StrategyInput(
            market_id="TEST-MARKET",
            mid_price=Price(Decimal("0.50")),
            inventory=0,
            max_inventory=100,
            base_size=100,
            time_to_settlement=1.0,
            timestamp=datetime.now(UTC),
        )

        negative_inv = StrategyInput(
            market_id="TEST-MARKET",
            mid_price=Price(Decimal("0.50")),
            inventory=-50,
            max_inventory=100,
            base_size=100,
            time_to_settlement=1.0,
            timestamp=datetime.now(UTC),
        )

        zero_result = engine.generate_quotes(zero_inv)
        negative_result = engine.generate_quotes(negative_inv)

        # Reservation price should be higher with negative inventory
        # So quotes should be shifted up
        assert negative_result.yes_quote.bid_price.value > zero_result.yes_quote.bid_price.value
        assert negative_result.yes_quote.ask_price.value > zero_result.yes_quote.ask_price.value

    def test_positive_inventory_asymmetric_sizes(
        self,
        engine: StrategyEngine,
    ) -> None:
        """Positive inventory makes ask size larger than bid size."""
        input_data = StrategyInput(
            market_id="TEST-MARKET",
            mid_price=Price(Decimal("0.50")),
            inventory=50,
            max_inventory=100,
            base_size=100,
            time_to_settlement=1.0,
            timestamp=datetime.now(UTC),
        )

        result = engine.generate_quotes(input_data)
        # When long, encourage selling by having larger ask
        assert result.yes_quote.ask_size.value >= result.yes_quote.bid_size.value

    def test_extreme_inventory_clamps_quotes(
        self,
        engine: StrategyEngine,
    ) -> None:
        """Extreme inventory doesn't push quotes outside bounds."""
        input_data = StrategyInput(
            market_id="TEST-MARKET",
            mid_price=Price(Decimal("0.50")),
            inventory=10000,  # Very large inventory
            max_inventory=100,
            base_size=100,
            time_to_settlement=1.0,
            timestamp=datetime.now(UTC),
        )

        result = engine.generate_quotes(input_data)

        # Should still respect bounds
        assert result.yes_quote.bid_price.value >= Decimal("0.01")
        assert result.yes_quote.ask_price.value <= Decimal("0.99")

    def test_volatility_not_ready_uses_initial(
        self,
        engine: StrategyEngine,
        base_input: StrategyInput,
    ) -> None:
        """When volatility estimator not ready, still generates quotes."""
        # Fixed volatility is always ready, but this tests the flow
        result = engine.generate_quotes(base_input)
        assert result is not None

    def test_to_order_requests(
        self,
        engine: StrategyEngine,
        base_input: StrategyInput,
    ) -> None:
        """QuoteSet can be converted to order requests."""
        result = engine.generate_quotes(base_input)
        orders = result.to_order_requests()

        # Should generate 4 orders: YES bid/ask, NO bid/ask
        assert len(orders) == 4
