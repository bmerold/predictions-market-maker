"""Time-based risk rules.

Rules that enforce time-related trading restrictions.
"""

from __future__ import annotations

from datetime import UTC, datetime

from market_maker.domain.orders import QuoteSet
from market_maker.risk.base import RiskAction, RiskContext, RiskDecision, RiskRule


class SettlementCutoffRule(RiskRule):
    """Blocks quotes within cutoff period before settlement.

    Markets should stop quoting shortly before settlement to avoid
    execution risk near the settlement time.
    """

    def __init__(self, cutoff_minutes: int) -> None:
        """Initialize with cutoff period.

        Args:
            cutoff_minutes: Minutes before settlement to stop quoting
        """
        self._cutoff_minutes = cutoff_minutes

    @property
    def name(self) -> str:
        return "settlement_cutoff"

    def evaluate(
        self,
        proposed_quotes: QuoteSet,  # noqa: ARG002
        context: RiskContext,
    ) -> RiskDecision:
        """Check if within settlement cutoff period.

        Args:
            proposed_quotes: The proposed quotes (unused)
            context: Current state with time_to_settlement

        Returns:
            BLOCK if within cutoff, ALLOW otherwise
        """
        # Convert cutoff to hours for comparison
        cutoff_hours = self._cutoff_minutes / 60

        if context.time_to_settlement <= cutoff_hours:
            minutes_left = context.time_to_settlement * 60
            return RiskDecision(
                action=RiskAction.BLOCK,
                reason=f"Within settlement cutoff ({minutes_left:.1f} minutes "
                f"remaining, cutoff is {self._cutoff_minutes} minutes)",
            )

        return RiskDecision(action=RiskAction.ALLOW)


class StaleDataRule(RiskRule):
    """Blocks quotes when market data is stale.

    Prevents quoting when the order book data is too old to be reliable.
    """

    def __init__(self, max_age_seconds: float) -> None:
        """Initialize with max data age.

        Args:
            max_age_seconds: Maximum allowed age of order book data
        """
        self._max_age_seconds = max_age_seconds

    @property
    def name(self) -> str:
        return "stale_data"

    def evaluate(
        self,
        proposed_quotes: QuoteSet,  # noqa: ARG002
        context: RiskContext,
    ) -> RiskDecision:
        """Check if market data is stale.

        Args:
            proposed_quotes: The proposed quotes (unused)
            context: Current state with order book

        Returns:
            BLOCK if data is stale, ALLOW otherwise
        """
        book_time = context.order_book.timestamp
        now = datetime.now(UTC)
        age_seconds = (now - book_time).total_seconds()

        if age_seconds > self._max_age_seconds:
            return RiskDecision(
                action=RiskAction.BLOCK,
                reason=f"Market data is stale ({age_seconds:.1f}s old, "
                f"max allowed is {self._max_age_seconds}s)",
            )

        return RiskDecision(action=RiskAction.ALLOW)
