"""Tests for RiskManager and KillSwitch."""

from datetime import UTC, datetime
from decimal import Decimal

import pytest

from market_maker.domain.market_data import OrderBook, PriceLevel
from market_maker.domain.orders import Quote, QuoteSet
from market_maker.domain.types import Price, Quantity
from market_maker.risk.base import RiskAction, RiskContext, RiskDecision, RiskRule
from market_maker.risk.kill_switch import KillSwitch
from market_maker.risk.manager import RiskManager
from market_maker.risk.rules.pnl import HourlyLossLimitRule
from market_maker.risk.rules.position import MaxInventoryRule, MaxOrderSizeRule


def make_context(inventory: int = 0, hourly_pnl: Decimal = Decimal("0")) -> RiskContext:
    """Create a RiskContext for testing."""
    return RiskContext(
        current_inventory=inventory,
        max_inventory=100,
        positions={},
        realized_pnl=Decimal("0"),
        unrealized_pnl=Decimal("0"),
        hourly_pnl=hourly_pnl,
        daily_pnl=Decimal("0"),
        time_to_settlement=1.0,
        current_volatility=Decimal("0.10"),
        order_book=OrderBook(
            market_id="TEST",
            yes_bids=[PriceLevel(Price(Decimal("0.48")), Quantity(100))],
            yes_asks=[PriceLevel(Price(Decimal("0.52")), Quantity(100))],
            timestamp=datetime.now(UTC),
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


class AlwaysAllowRule(RiskRule):
    """Test rule that always allows."""

    @property
    def name(self) -> str:
        return "always_allow"

    def evaluate(
        self,
        proposed_quotes: QuoteSet,  # noqa: ARG002
        context: RiskContext,  # noqa: ARG002
    ) -> RiskDecision:
        return RiskDecision(action=RiskAction.ALLOW)


class AlwaysBlockRule(RiskRule):
    """Test rule that always blocks."""

    @property
    def name(self) -> str:
        return "always_block"

    def evaluate(
        self,
        proposed_quotes: QuoteSet,  # noqa: ARG002
        context: RiskContext,  # noqa: ARG002
    ) -> RiskDecision:
        return RiskDecision(
            action=RiskAction.BLOCK,
            reason="Always blocked",
        )


class TestKillSwitch:
    """Tests for KillSwitch."""

    def test_initial_state_inactive(self) -> None:
        """Kill switch starts inactive."""
        switch = KillSwitch()
        assert not switch.is_active()

    def test_activate(self) -> None:
        """Can activate kill switch."""
        switch = KillSwitch()
        switch.activate("Test reason")
        assert switch.is_active()

    def test_activate_reason_recorded(self) -> None:
        """Activation reason is recorded."""
        switch = KillSwitch()
        switch.activate("Loss limit exceeded")
        assert switch.activation_reason == "Loss limit exceeded"

    def test_manual_reset(self) -> None:
        """Can manually reset kill switch."""
        switch = KillSwitch()
        switch.activate("Test")
        switch.reset()
        assert not switch.is_active()

    def test_activation_time_recorded(self) -> None:
        """Activation time is recorded."""
        switch = KillSwitch()
        switch.activate("Test")
        assert switch.activation_time is not None

    def test_multiple_activations_keep_first_reason(self) -> None:
        """Multiple activations keep first reason."""
        switch = KillSwitch()
        switch.activate("First reason")
        switch.activate("Second reason")
        assert switch.activation_reason == "First reason"


class TestRiskManager:
    """Tests for RiskManager."""

    def test_create_with_no_rules(self) -> None:
        """Can create manager with no rules."""
        manager = RiskManager(rules=[])
        assert len(manager.rules) == 0

    def test_create_with_rules(self) -> None:
        """Can create manager with rules."""
        rules = [MaxInventoryRule(100), MaxOrderSizeRule(50)]
        manager = RiskManager(rules=rules)
        assert len(manager.rules) == 2

    def test_evaluate_all_allow(self) -> None:
        """Returns ALLOW when all rules allow."""
        manager = RiskManager(rules=[AlwaysAllowRule(), AlwaysAllowRule()])
        quotes = make_quotes()
        context = make_context()

        result = manager.evaluate(quotes, context)
        assert result.action == RiskAction.ALLOW

    def test_evaluate_one_blocks(self) -> None:
        """Returns BLOCK when any rule blocks."""
        manager = RiskManager(rules=[AlwaysAllowRule(), AlwaysBlockRule()])
        quotes = make_quotes()
        context = make_context()

        result = manager.evaluate(quotes, context)
        assert result.action == RiskAction.BLOCK

    def test_evaluate_stops_at_first_block(self) -> None:
        """Evaluation stops at first blocking rule."""
        call_count = 0

        class CountingRule(RiskRule):
            @property
            def name(self) -> str:
                return "counting"

            def evaluate(
                self, proposed_quotes: QuoteSet, context: RiskContext
            ) -> RiskDecision:
                nonlocal call_count
                call_count += 1
                return RiskDecision(action=RiskAction.ALLOW)

        manager = RiskManager(
            rules=[AlwaysBlockRule(), CountingRule(), CountingRule()]
        )
        quotes = make_quotes()
        context = make_context()

        manager.evaluate(quotes, context)
        # The counting rules should not be called
        assert call_count == 0

    def test_evaluate_modify_passes_modified_to_next(self) -> None:
        """Modified quotes are passed to subsequent rules."""
        manager = RiskManager(
            rules=[
                MaxOrderSizeRule(50),  # Will modify to 50
                MaxInventoryRule(100),  # Will see modified quotes
            ]
        )
        quotes = make_quotes(bid_size=200, ask_size=200)
        context = make_context()

        result = manager.evaluate(quotes, context)
        # Should be modified, not blocked
        assert result.action == RiskAction.MODIFY
        assert result.modified_quotes.yes_quote.bid_size.value == 50

    def test_evaluate_returns_final_modified_quotes(self) -> None:
        """Returns the final modified quotes after all rules."""
        manager = RiskManager(rules=[MaxOrderSizeRule(50)])
        quotes = make_quotes(bid_size=100, ask_size=100)
        context = make_context()

        result = manager.evaluate(quotes, context)
        assert result.modified_quotes.yes_quote.bid_size.value == 50
        assert result.modified_quotes.yes_quote.ask_size.value == 50

    def test_kill_switch_blocks_all(self) -> None:
        """When kill switch is active, all quotes are blocked."""
        manager = RiskManager(rules=[AlwaysAllowRule()])
        manager.kill_switch.activate("Manual stop")

        quotes = make_quotes()
        context = make_context()

        result = manager.evaluate(quotes, context)
        assert result.action == RiskAction.BLOCK
        assert "kill switch" in result.reason.lower()

    def test_kill_switch_triggered_by_rule(self) -> None:
        """Kill switch activated when rule triggers it."""
        manager = RiskManager(
            rules=[HourlyLossLimitRule(max_loss=Decimal("50.00"))]
        )
        quotes = make_quotes()
        context = make_context(hourly_pnl=Decimal("-60.00"))

        result = manager.evaluate(quotes, context)
        assert result.action == RiskAction.BLOCK
        assert manager.kill_switch.is_active()

    def test_reset_kill_switch(self) -> None:
        """Can reset kill switch through manager."""
        manager = RiskManager(rules=[])
        manager.kill_switch.activate("Test")
        manager.reset_kill_switch()
        assert not manager.kill_switch.is_active()

    def test_evaluate_no_rules_allows(self) -> None:
        """With no rules, quotes are allowed."""
        manager = RiskManager(rules=[])
        quotes = make_quotes()
        context = make_context()

        result = manager.evaluate(quotes, context)
        assert result.action == RiskAction.ALLOW
