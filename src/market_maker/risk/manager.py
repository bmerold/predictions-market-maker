"""Risk manager for evaluating quotes against risk rules.

Provides a pipeline that evaluates proposed quotes against
a configurable set of risk rules.
"""

from __future__ import annotations

from market_maker.domain.orders import QuoteSet
from market_maker.risk.base import RiskAction, RiskContext, RiskDecision, RiskRule
from market_maker.risk.kill_switch import KillSwitch


class RiskManager:
    """Manages risk rules and evaluates quotes.

    The risk manager:
    1. Maintains a kill switch for emergency stops
    2. Evaluates quotes against a chain of risk rules
    3. Supports rule modification of quotes (passed to subsequent rules)
    4. Stops evaluation on first BLOCK

    Pipeline flow:
        ProposedQuotes → Rule1 → Rule2 → Rule3 → ApprovedQuotes
                          │        │        │
                          ▼        ▼        ▼
                        ALLOW    MODIFY   BLOCK
                                (adjust)  (reject)
    """

    def __init__(self, rules: list[RiskRule]) -> None:
        """Initialize with a list of risk rules.

        Args:
            rules: Risk rules to evaluate, in order of priority
        """
        self._rules = list(rules)
        self._kill_switch = KillSwitch()

    @property
    def rules(self) -> list[RiskRule]:
        """Return the list of risk rules."""
        return self._rules

    @property
    def kill_switch(self) -> KillSwitch:
        """Return the kill switch."""
        return self._kill_switch

    def evaluate(
        self,
        proposed_quotes: QuoteSet,
        context: RiskContext,
    ) -> RiskDecision:
        """Evaluate proposed quotes against all risk rules.

        If the kill switch is active, immediately blocks all quotes.

        Args:
            proposed_quotes: The quotes to evaluate
            context: Current state and market data

        Returns:
            RiskDecision indicating whether quotes are allowed, modified, or blocked
        """
        # Check kill switch first
        if self._kill_switch.is_active():
            return RiskDecision(
                action=RiskAction.BLOCK,
                reason=f"Kill switch is active: {self._kill_switch.activation_reason}",
            )

        # No rules = allow everything
        if not self._rules:
            return RiskDecision(action=RiskAction.ALLOW)

        # Evaluate each rule in order
        current_quotes = proposed_quotes
        was_modified = False

        for rule in self._rules:
            decision = rule.evaluate(current_quotes, context)

            # If rule triggers kill switch, activate it
            if decision.trigger_kill_switch:
                self._kill_switch.activate(
                    f"{rule.name}: {decision.reason or 'Kill switch triggered'}"
                )

            # BLOCK stops evaluation immediately
            if decision.action == RiskAction.BLOCK:
                return decision

            # MODIFY updates the quotes for subsequent rules
            if decision.action == RiskAction.MODIFY and decision.modified_quotes:
                current_quotes = decision.modified_quotes
                was_modified = True

        # All rules passed
        if was_modified:
            return RiskDecision(
                action=RiskAction.MODIFY,
                reason="Quotes modified by risk rules",
                modified_quotes=current_quotes,
            )

        return RiskDecision(action=RiskAction.ALLOW)

    def reset_kill_switch(self) -> None:
        """Reset the kill switch to allow trading to resume."""
        self._kill_switch.reset()
