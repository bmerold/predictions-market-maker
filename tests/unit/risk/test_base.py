"""Tests for risk management base classes."""

from datetime import UTC, datetime
from decimal import Decimal

import pytest

from market_maker.domain.market_data import OrderBook, PriceLevel
from market_maker.domain.orders import Quote, QuoteSet
from market_maker.domain.positions import Position
from market_maker.domain.types import Price, Quantity, Side
from market_maker.risk.base import (
    RiskAction,
    RiskContext,
    RiskDecision,
    RiskRule,
)


class TestRiskAction:
    """Tests for RiskAction enum."""

    def test_actions_exist(self) -> None:
        """RiskAction has ALLOW, MODIFY, and BLOCK."""
        assert RiskAction.ALLOW
        assert RiskAction.MODIFY
        assert RiskAction.BLOCK


class TestRiskDecision:
    """Tests for RiskDecision dataclass."""

    def test_allow_decision(self) -> None:
        """Can create an ALLOW decision."""
        decision = RiskDecision(action=RiskAction.ALLOW)
        assert decision.action == RiskAction.ALLOW
        assert decision.reason is None
        assert decision.modified_quotes is None
        assert decision.trigger_kill_switch is False

    def test_block_decision_with_reason(self) -> None:
        """Can create a BLOCK decision with reason."""
        decision = RiskDecision(
            action=RiskAction.BLOCK,
            reason="Position limit exceeded",
        )
        assert decision.action == RiskAction.BLOCK
        assert decision.reason == "Position limit exceeded"

    def test_modify_decision_with_quotes(self) -> None:
        """Can create a MODIFY decision with modified quotes."""
        modified = QuoteSet(
            market_id="TEST",
            yes_quote=Quote(
                bid_price=Price(Decimal("0.45")),
                bid_size=Quantity(50),
                ask_price=Price(Decimal("0.55")),
                ask_size=Quantity(50),
            ),
            timestamp=datetime.now(UTC),
        )
        decision = RiskDecision(
            action=RiskAction.MODIFY,
            reason="Order size reduced",
            modified_quotes=modified,
        )
        assert decision.action == RiskAction.MODIFY
        assert decision.modified_quotes is not None
        assert decision.modified_quotes.yes_quote.bid_size.value == 50

    def test_kill_switch_trigger(self) -> None:
        """Can create a decision that triggers kill switch."""
        decision = RiskDecision(
            action=RiskAction.BLOCK,
            reason="Daily loss limit exceeded",
            trigger_kill_switch=True,
        )
        assert decision.trigger_kill_switch is True

    def test_is_blocked(self) -> None:
        """is_blocked helper method."""
        allow = RiskDecision(action=RiskAction.ALLOW)
        block = RiskDecision(action=RiskAction.BLOCK)
        assert allow.is_blocked() is False
        assert block.is_blocked() is True


class TestRiskContext:
    """Tests for RiskContext dataclass."""

    def test_create_context(self) -> None:
        """Can create a RiskContext with all required fields."""
        context = RiskContext(
            current_inventory=50,
            max_inventory=100,
            positions={
                "TEST": Position(
                    market_id="TEST",
                    yes_quantity=50,
                    no_quantity=0,
                    avg_yes_price=Price(Decimal("0.45")),
                    avg_no_price=None,
                )
            },
            realized_pnl=Decimal("10.00"),
            unrealized_pnl=Decimal("5.00"),
            hourly_pnl=Decimal("-2.00"),
            daily_pnl=Decimal("8.00"),
            time_to_settlement=0.5,  # 30 minutes
            current_volatility=Decimal("0.15"),
            order_book=OrderBook(
                market_id="TEST",
                yes_bids=[PriceLevel(Price(Decimal("0.48")), Quantity(100))],
                yes_asks=[PriceLevel(Price(Decimal("0.52")), Quantity(100))],
                timestamp=datetime.now(UTC),
            ),
        )
        assert context.current_inventory == 50
        assert context.max_inventory == 100

    def test_total_pnl(self) -> None:
        """total_pnl returns sum of realized and unrealized."""
        context = RiskContext(
            current_inventory=0,
            max_inventory=100,
            positions={},
            realized_pnl=Decimal("10.00"),
            unrealized_pnl=Decimal("-3.00"),
            hourly_pnl=Decimal("0"),
            daily_pnl=Decimal("0"),
            time_to_settlement=1.0,
            current_volatility=Decimal("0.10"),
            order_book=OrderBook(
                market_id="TEST",
                yes_bids=[],
                yes_asks=[],
                timestamp=datetime.now(UTC),
            ),
        )
        assert context.total_pnl() == Decimal("7.00")


class TestRiskRuleABC:
    """Tests for RiskRule abstract base class."""

    def test_is_abstract(self) -> None:
        """RiskRule cannot be instantiated directly."""
        with pytest.raises(TypeError):
            RiskRule()  # type: ignore[abstract]

    def test_required_methods(self) -> None:
        """RiskRule defines required abstract methods."""
        required = {"evaluate"}
        abstract_methods = set(RiskRule.__abstractmethods__)
        assert required.issubset(abstract_methods)

    def test_required_properties(self) -> None:
        """RiskRule defines required abstract properties."""
        assert "name" in RiskRule.__abstractmethods__


class DummyRule(RiskRule):
    """Concrete rule for testing."""

    @property
    def name(self) -> str:
        return "dummy_rule"

    def evaluate(
        self,
        proposed_quotes: QuoteSet,
        context: RiskContext,
    ) -> RiskDecision:
        return RiskDecision(action=RiskAction.ALLOW)


class TestConcreteRiskRule:
    """Tests for concrete RiskRule implementation."""

    def test_can_implement_risk_rule(self) -> None:
        """Can create concrete implementation of RiskRule."""
        rule = DummyRule()
        assert rule.name == "dummy_rule"

    def test_can_evaluate(self) -> None:
        """Concrete rule can evaluate quotes."""
        rule = DummyRule()
        quotes = QuoteSet(
            market_id="TEST",
            yes_quote=Quote(
                bid_price=Price(Decimal("0.45")),
                bid_size=Quantity(100),
                ask_price=Price(Decimal("0.55")),
                ask_size=Quantity(100),
            ),
            timestamp=datetime.now(UTC),
        )
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
                timestamp=datetime.now(UTC),
            ),
        )

        decision = rule.evaluate(quotes, context)
        assert decision.action == RiskAction.ALLOW
