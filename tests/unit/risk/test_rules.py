"""Tests for risk rules."""

from datetime import UTC, datetime
from decimal import Decimal

import pytest

from market_maker.domain.market_data import OrderBook, PriceLevel
from market_maker.domain.orders import Quote, QuoteSet
from market_maker.domain.types import Price, Quantity
from market_maker.risk.base import RiskAction, RiskContext
from market_maker.risk.rules.pnl import DailyLossLimitRule, HourlyLossLimitRule
from market_maker.risk.rules.position import MaxInventoryRule, MaxOrderSizeRule
from market_maker.risk.rules.time import SettlementCutoffRule, StaleDataRule


def make_context(
    inventory: int = 0,
    max_inventory: int = 100,
    hourly_pnl: Decimal = Decimal("0"),
    daily_pnl: Decimal = Decimal("0"),
    time_to_settlement: float = 1.0,
    data_age_seconds: float = 1.0,
) -> RiskContext:
    """Create a RiskContext for testing."""
    # Create order book with timestamp reflecting data age
    book_time = datetime.now(UTC)
    return RiskContext(
        current_inventory=inventory,
        max_inventory=max_inventory,
        positions={},
        realized_pnl=Decimal("0"),
        unrealized_pnl=Decimal("0"),
        hourly_pnl=hourly_pnl,
        daily_pnl=daily_pnl,
        time_to_settlement=time_to_settlement,
        current_volatility=Decimal("0.10"),
        order_book=OrderBook(
            market_id="TEST",
            yes_bids=[PriceLevel(Price(Decimal("0.48")), Quantity(100))],
            yes_asks=[PriceLevel(Price(Decimal("0.52")), Quantity(100))],
            timestamp=book_time,
        ),
    )


def make_quotes(bid_size: int = 100, ask_size: int = 100) -> QuoteSet:
    """Create a QuoteSet for testing."""
    return QuoteSet(
        market_id="TEST",
        yes_quote=Quote(
            bid_price=Price(Decimal("0.45")),
            bid_size=Quantity(bid_size),
            ask_price=Price(Decimal("0.55")),
            ask_size=Quantity(ask_size),
        ),
        timestamp=datetime.now(UTC),
    )


class TestMaxInventoryRule:
    """Tests for MaxInventoryRule."""

    def test_name(self) -> None:
        """Rule has descriptive name."""
        rule = MaxInventoryRule(max_inventory=100)
        assert rule.name == "max_inventory"

    def test_allows_within_limit(self) -> None:
        """Allows quotes when inventory would stay within limit."""
        rule = MaxInventoryRule(max_inventory=100)
        context = make_context(inventory=50)
        quotes = make_quotes(bid_size=40, ask_size=40)

        decision = rule.evaluate(quotes, context)
        assert decision.action == RiskAction.ALLOW

    def test_blocks_bid_when_would_exceed(self) -> None:
        """Blocks quotes when buying would exceed inventory limit."""
        rule = MaxInventoryRule(max_inventory=100)
        context = make_context(inventory=90)
        quotes = make_quotes(bid_size=20, ask_size=20)  # Buying 20 would make 110

        decision = rule.evaluate(quotes, context)
        assert decision.action == RiskAction.BLOCK
        assert "inventory" in decision.reason.lower()

    def test_blocks_ask_when_would_exceed_short(self) -> None:
        """Blocks quotes when selling would exceed short limit."""
        rule = MaxInventoryRule(max_inventory=100)
        context = make_context(inventory=-90)
        quotes = make_quotes(bid_size=20, ask_size=20)  # Selling 20 would make -110

        decision = rule.evaluate(quotes, context)
        assert decision.action == RiskAction.BLOCK

    def test_allows_at_limit(self) -> None:
        """Allows quotes that bring inventory exactly to limit."""
        rule = MaxInventoryRule(max_inventory=100)
        context = make_context(inventory=80)
        quotes = make_quotes(bid_size=20, ask_size=20)  # Buying 20 would make 100

        decision = rule.evaluate(quotes, context)
        assert decision.action == RiskAction.ALLOW


class TestMaxOrderSizeRule:
    """Tests for MaxOrderSizeRule."""

    def test_name(self) -> None:
        """Rule has descriptive name."""
        rule = MaxOrderSizeRule(max_size=50)
        assert rule.name == "max_order_size"

    def test_allows_within_limit(self) -> None:
        """Allows quotes within size limit."""
        rule = MaxOrderSizeRule(max_size=100)
        quotes = make_quotes(bid_size=50, ask_size=50)
        context = make_context()

        decision = rule.evaluate(quotes, context)
        assert decision.action == RiskAction.ALLOW

    def test_modifies_oversized_quotes(self) -> None:
        """Modifies quotes that exceed size limit."""
        rule = MaxOrderSizeRule(max_size=50)
        quotes = make_quotes(bid_size=100, ask_size=100)
        context = make_context()

        decision = rule.evaluate(quotes, context)
        assert decision.action == RiskAction.MODIFY
        assert decision.modified_quotes is not None
        assert decision.modified_quotes.yes_quote.bid_size.value == 50
        assert decision.modified_quotes.yes_quote.ask_size.value == 50

    def test_modifies_only_oversized_side(self) -> None:
        """Only modifies the side that exceeds limit."""
        rule = MaxOrderSizeRule(max_size=50)
        quotes = make_quotes(bid_size=100, ask_size=30)
        context = make_context()

        decision = rule.evaluate(quotes, context)
        assert decision.action == RiskAction.MODIFY
        assert decision.modified_quotes.yes_quote.bid_size.value == 50
        assert decision.modified_quotes.yes_quote.ask_size.value == 30


class TestSettlementCutoffRule:
    """Tests for SettlementCutoffRule."""

    def test_name(self) -> None:
        """Rule has descriptive name."""
        rule = SettlementCutoffRule(cutoff_minutes=3)
        assert rule.name == "settlement_cutoff"

    def test_allows_outside_cutoff(self) -> None:
        """Allows quotes when well before settlement."""
        rule = SettlementCutoffRule(cutoff_minutes=3)
        context = make_context(time_to_settlement=1.0)  # 1 hour
        quotes = make_quotes()

        decision = rule.evaluate(quotes, context)
        assert decision.action == RiskAction.ALLOW

    def test_blocks_within_cutoff(self) -> None:
        """Blocks quotes when within cutoff period."""
        rule = SettlementCutoffRule(cutoff_minutes=3)
        context = make_context(time_to_settlement=2 / 60)  # 2 minutes
        quotes = make_quotes()

        decision = rule.evaluate(quotes, context)
        assert decision.action == RiskAction.BLOCK
        assert "settlement" in decision.reason.lower()

    def test_blocks_at_cutoff(self) -> None:
        """Blocks quotes exactly at cutoff."""
        rule = SettlementCutoffRule(cutoff_minutes=3)
        context = make_context(time_to_settlement=3 / 60)  # 3 minutes
        quotes = make_quotes()

        decision = rule.evaluate(quotes, context)
        assert decision.action == RiskAction.BLOCK


class TestStaleDataRule:
    """Tests for StaleDataRule."""

    def test_name(self) -> None:
        """Rule has descriptive name."""
        rule = StaleDataRule(max_age_seconds=5.0)
        assert rule.name == "stale_data"

    def test_allows_fresh_data(self) -> None:
        """Allows quotes when data is fresh."""
        rule = StaleDataRule(max_age_seconds=5.0)
        context = make_context()  # Fresh data
        quotes = make_quotes()

        decision = rule.evaluate(quotes, context)
        assert decision.action == RiskAction.ALLOW

    def test_blocks_stale_data(self) -> None:
        """Blocks quotes when data is stale."""
        rule = StaleDataRule(max_age_seconds=5.0)

        # Create context with old timestamp
        from datetime import timedelta

        old_time = datetime.now(UTC) - timedelta(seconds=10)
        context = RiskContext(
            current_inventory=0,
            max_inventory=100,
            positions={},
            realized_pnl=Decimal("0"),
            unrealized_pnl=Decimal("0"),
            hourly_pnl=Decimal("0"),
            daily_pnl=Decimal("0"),
            time_to_settlement=1.0,
            current_volatility=Decimal("0.10"),
            order_book=OrderBook(
                market_id="TEST",
                yes_bids=[],
                yes_asks=[],
                timestamp=old_time,
            ),
        )
        quotes = make_quotes()

        decision = rule.evaluate(quotes, context)
        assert decision.action == RiskAction.BLOCK
        assert "stale" in decision.reason.lower()


class TestHourlyLossLimitRule:
    """Tests for HourlyLossLimitRule."""

    def test_name(self) -> None:
        """Rule has descriptive name."""
        rule = HourlyLossLimitRule(max_loss=Decimal("50.00"))
        assert rule.name == "hourly_loss_limit"

    def test_allows_within_limit(self) -> None:
        """Allows quotes when loss within limit."""
        rule = HourlyLossLimitRule(max_loss=Decimal("50.00"))
        context = make_context(hourly_pnl=Decimal("-30.00"))
        quotes = make_quotes()

        decision = rule.evaluate(quotes, context)
        assert decision.action == RiskAction.ALLOW

    def test_blocks_exceeds_limit(self) -> None:
        """Blocks and triggers kill switch when loss exceeds limit."""
        rule = HourlyLossLimitRule(max_loss=Decimal("50.00"))
        context = make_context(hourly_pnl=Decimal("-60.00"))
        quotes = make_quotes()

        decision = rule.evaluate(quotes, context)
        assert decision.action == RiskAction.BLOCK
        assert decision.trigger_kill_switch is True
        assert "hourly" in decision.reason.lower()

    def test_allows_profit(self) -> None:
        """Allows quotes when in profit."""
        rule = HourlyLossLimitRule(max_loss=Decimal("50.00"))
        context = make_context(hourly_pnl=Decimal("100.00"))
        quotes = make_quotes()

        decision = rule.evaluate(quotes, context)
        assert decision.action == RiskAction.ALLOW


class TestDailyLossLimitRule:
    """Tests for DailyLossLimitRule."""

    def test_name(self) -> None:
        """Rule has descriptive name."""
        rule = DailyLossLimitRule(max_loss=Decimal("100.00"))
        assert rule.name == "daily_loss_limit"

    def test_allows_within_limit(self) -> None:
        """Allows quotes when loss within limit."""
        rule = DailyLossLimitRule(max_loss=Decimal("100.00"))
        context = make_context(daily_pnl=Decimal("-50.00"))
        quotes = make_quotes()

        decision = rule.evaluate(quotes, context)
        assert decision.action == RiskAction.ALLOW

    def test_blocks_exceeds_limit(self) -> None:
        """Blocks and triggers kill switch when loss exceeds limit."""
        rule = DailyLossLimitRule(max_loss=Decimal("100.00"))
        context = make_context(daily_pnl=Decimal("-110.00"))
        quotes = make_quotes()

        decision = rule.evaluate(quotes, context)
        assert decision.action == RiskAction.BLOCK
        assert decision.trigger_kill_switch is True
        assert "daily" in decision.reason.lower()
