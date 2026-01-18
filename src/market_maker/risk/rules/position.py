"""Position-based risk rules.

Rules that enforce position and order size limits.
"""

from __future__ import annotations

from market_maker.domain.orders import Quote, QuoteSet
from market_maker.domain.types import Quantity
from market_maker.risk.base import RiskAction, RiskContext, RiskDecision, RiskRule


class MaxInventoryRule(RiskRule):
    """Blocks quotes that would cause inventory to exceed limit.

    Checks both long and short directions against the max inventory.
    """

    def __init__(self, max_inventory: int) -> None:
        """Initialize with inventory limit.

        Args:
            max_inventory: Maximum absolute inventory allowed
        """
        self._max_inventory = max_inventory

    @property
    def name(self) -> str:
        return "max_inventory"

    def evaluate(
        self,
        proposed_quotes: QuoteSet,
        context: RiskContext,
    ) -> RiskDecision:
        """Check if quotes would cause inventory to exceed limit.

        Considers both current inventory AND pending exposure from resting orders.
        This prevents placing new orders when existing orders could already push
        us over the limit if filled.

        Args:
            proposed_quotes: The proposed quotes
            context: Current state

        Returns:
            BLOCK if any direction would exceed limit, ALLOW otherwise
        """
        current = context.current_inventory
        pending_bids = context.pending_bid_exposure
        pending_asks = context.pending_ask_exposure
        bid_size = proposed_quotes.yes_quote.bid_size.value
        ask_size = proposed_quotes.yes_quote.ask_size.value

        # Effective inventory if all pending orders fill
        effective_long = current + pending_bids  # If all bids fill
        effective_short = current - pending_asks  # If all asks fill

        # Check if at/over long limit - block bids
        if effective_long >= self._max_inventory and bid_size > 0:
            return RiskDecision(
                action=RiskAction.BLOCK,
                reason=f"At max long inventory ({current} + {pending_bids} pending >= {self._max_inventory}), "
                f"blocking further buys",
            )

        # Check if at/over short limit - block asks
        if effective_short <= -self._max_inventory and ask_size > 0:
            return RiskDecision(
                action=RiskAction.BLOCK,
                reason=f"At max short inventory ({current} - {pending_asks} pending <= -{self._max_inventory}), "
                f"blocking further sells",
            )

        # Check if new bid + pending would exceed long inventory limit
        if effective_long + bid_size > self._max_inventory:
            return RiskDecision(
                action=RiskAction.BLOCK,
                reason=f"Buying {bid_size} would exceed inventory limit "
                f"({current} inv + {pending_bids} pending + {bid_size} new > {self._max_inventory})",
            )

        # Check if new ask + pending would exceed short inventory limit
        if effective_short - ask_size < -self._max_inventory:
            return RiskDecision(
                action=RiskAction.BLOCK,
                reason=f"Selling {ask_size} would exceed inventory limit "
                f"({current} inv - {pending_asks} pending - {ask_size} new < -{self._max_inventory})",
            )

        return RiskDecision(action=RiskAction.ALLOW)


class MaxOrderSizeRule(RiskRule):
    """Modifies quotes that exceed maximum order size.

    Rather than blocking, this rule reduces oversized orders to the
    maximum allowed size.
    """

    def __init__(self, max_size: int) -> None:
        """Initialize with size limit.

        Args:
            max_size: Maximum allowed order size
        """
        self._max_size = max_size

    @property
    def name(self) -> str:
        return "max_order_size"

    def evaluate(
        self,
        proposed_quotes: QuoteSet,
        context: RiskContext,  # noqa: ARG002
    ) -> RiskDecision:
        """Check and modify oversized orders.

        Args:
            proposed_quotes: The proposed quotes
            context: Current state (unused)

        Returns:
            MODIFY if any size exceeds limit, ALLOW otherwise
        """
        yes_quote = proposed_quotes.yes_quote
        bid_size = yes_quote.bid_size.value
        ask_size = yes_quote.ask_size.value

        needs_modification = bid_size > self._max_size or ask_size > self._max_size

        if not needs_modification:
            return RiskDecision(action=RiskAction.ALLOW)

        # Create modified quotes with capped sizes
        new_bid_size = min(bid_size, self._max_size)
        new_ask_size = min(ask_size, self._max_size)

        modified_yes_quote = Quote(
            bid_price=yes_quote.bid_price,
            bid_size=Quantity(new_bid_size),
            ask_price=yes_quote.ask_price,
            ask_size=Quantity(new_ask_size),
        )

        modified_quotes = QuoteSet(
            market_id=proposed_quotes.market_id,
            yes_quote=modified_yes_quote,
            timestamp=proposed_quotes.timestamp,
        )

        return RiskDecision(
            action=RiskAction.MODIFY,
            reason=f"Order size reduced from ({bid_size}, {ask_size}) "
            f"to ({new_bid_size}, {new_ask_size})",
            modified_quotes=modified_quotes,
        )
