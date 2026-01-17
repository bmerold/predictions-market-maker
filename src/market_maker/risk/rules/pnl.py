"""PnL-based risk rules.

Rules that enforce profit and loss limits, triggering kill switch
when limits are breached.
"""

from __future__ import annotations

from decimal import Decimal

from market_maker.domain.orders import QuoteSet
from market_maker.risk.base import RiskAction, RiskContext, RiskDecision, RiskRule


class HourlyLossLimitRule(RiskRule):
    """Blocks quotes and triggers kill switch when hourly loss exceeds limit.

    This is a critical safety rule that protects against rapid losses.
    """

    def __init__(self, max_loss: Decimal) -> None:
        """Initialize with loss limit.

        Args:
            max_loss: Maximum allowed loss per hour (positive value)
        """
        self._max_loss = max_loss

    @property
    def name(self) -> str:
        return "hourly_loss_limit"

    def evaluate(
        self,
        proposed_quotes: QuoteSet,  # noqa: ARG002
        context: RiskContext,
    ) -> RiskDecision:
        """Check if hourly loss exceeds limit.

        Args:
            proposed_quotes: The proposed quotes (unused)
            context: Current state with hourly PnL

        Returns:
            BLOCK with kill_switch if loss exceeds limit, ALLOW otherwise
        """
        # hourly_pnl is negative for losses
        if context.hourly_pnl < -self._max_loss:
            return RiskDecision(
                action=RiskAction.BLOCK,
                reason=f"Hourly loss limit exceeded "
                f"(loss: ${-context.hourly_pnl:.2f}, limit: ${self._max_loss:.2f})",
                trigger_kill_switch=True,
            )

        return RiskDecision(action=RiskAction.ALLOW)


class DailyLossLimitRule(RiskRule):
    """Blocks quotes and triggers kill switch when daily loss exceeds limit.

    This is a critical safety rule that protects against sustained losses.
    """

    def __init__(self, max_loss: Decimal) -> None:
        """Initialize with loss limit.

        Args:
            max_loss: Maximum allowed loss per day (positive value)
        """
        self._max_loss = max_loss

    @property
    def name(self) -> str:
        return "daily_loss_limit"

    def evaluate(
        self,
        proposed_quotes: QuoteSet,  # noqa: ARG002
        context: RiskContext,
    ) -> RiskDecision:
        """Check if daily loss exceeds limit.

        Args:
            proposed_quotes: The proposed quotes (unused)
            context: Current state with daily PnL

        Returns:
            BLOCK with kill_switch if loss exceeds limit, ALLOW otherwise
        """
        # daily_pnl is negative for losses
        if context.daily_pnl < -self._max_loss:
            return RiskDecision(
                action=RiskAction.BLOCK,
                reason=f"Daily loss limit exceeded "
                f"(loss: ${-context.daily_pnl:.2f}, limit: ${self._max_loss:.2f})",
                trigger_kill_switch=True,
            )

        return RiskDecision(action=RiskAction.ALLOW)
