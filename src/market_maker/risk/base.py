"""Risk management base classes.

Defines the core abstractions for the pluggable risk rule system.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from decimal import Decimal
from enum import Enum

from pydantic.dataclasses import dataclass

from market_maker.domain.market_data import OrderBook
from market_maker.domain.orders import QuoteSet
from market_maker.domain.positions import Position


class RiskAction(str, Enum):
    """Action to take on proposed quotes.

    - ALLOW: Quotes pass this rule unchanged
    - MODIFY: Rule modified the quotes (see modified_quotes)
    - BLOCK: Quotes rejected by this rule
    """

    ALLOW = "allow"
    MODIFY = "modify"
    BLOCK = "block"


@dataclass
class RiskDecision:
    """Result of evaluating quotes against a risk rule.

    Attributes:
        action: Whether to allow, modify, or block the quotes
        reason: Human-readable explanation (especially for MODIFY/BLOCK)
        modified_quotes: If action is MODIFY, the adjusted quotes
        trigger_kill_switch: If True, activates emergency stop
    """

    action: RiskAction
    reason: str | None = None
    modified_quotes: QuoteSet | None = None
    trigger_kill_switch: bool = False

    def is_blocked(self) -> bool:
        """Return True if this decision blocks the quotes."""
        return self.action == RiskAction.BLOCK


@dataclass
class RiskContext:
    """Context provided to risk rules for evaluation.

    Contains all state and market data that risk rules might need
    to make their decisions.
    """

    # Position state
    current_inventory: int  # Net inventory (YES - NO contracts)
    max_inventory: int  # Configured max inventory limit
    positions: dict[str, Position]  # All positions by market

    # PnL state
    realized_pnl: Decimal  # Realized profit/loss
    unrealized_pnl: Decimal  # Mark-to-market unrealized PnL
    hourly_pnl: Decimal  # PnL in the current hour
    daily_pnl: Decimal  # PnL for the current day

    # Market state
    time_to_settlement: float  # Hours until settlement
    current_volatility: Decimal  # Current volatility estimate
    order_book: OrderBook  # Current order book

    # Pending exposure from resting orders (to prevent over-trading)
    pending_bid_exposure: int = 0  # Size of resting bid orders that could fill
    pending_ask_exposure: int = 0  # Size of resting ask orders that could fill

    def total_pnl(self) -> Decimal:
        """Return total PnL (realized + unrealized)."""
        return self.realized_pnl + self.unrealized_pnl

    def effective_inventory_if_bids_fill(self) -> int:
        """Return inventory if all pending bids fill."""
        return self.current_inventory + self.pending_bid_exposure

    def effective_inventory_if_asks_fill(self) -> int:
        """Return inventory if all pending asks fill."""
        return self.current_inventory - self.pending_ask_exposure


class RiskRule(ABC):
    """Abstract base class for risk rules.

    Risk rules evaluate proposed quotes and decide whether to:
    - ALLOW: Let the quotes through unchanged
    - MODIFY: Adjust the quotes (e.g., reduce size)
    - BLOCK: Reject the quotes entirely

    Rules can also trigger the kill switch for severe violations.
    """

    @property
    @abstractmethod
    def name(self) -> str:
        """Human-readable rule name for logging and display."""

    @abstractmethod
    def evaluate(
        self,
        proposed_quotes: QuoteSet,
        context: RiskContext,
    ) -> RiskDecision:
        """Evaluate proposed quotes against this rule.

        Args:
            proposed_quotes: The quotes to evaluate
            context: Current state and market data

        Returns:
            RiskDecision indicating whether to allow, modify, or block
        """
