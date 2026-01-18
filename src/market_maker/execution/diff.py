"""Order differ for intelligent quote updates.

Calculates minimal set of order operations to transition from
current orders to new quotes.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

from market_maker.domain.orders import Order, OrderRequest, QuoteSet
from market_maker.domain.types import Price, Quantity


@dataclass
class QuoteOrders:
    """Tracks orders corresponding to a quote set."""

    market_id: str
    yes_bid_order: Order | None = None
    yes_ask_order: Order | None = None
    no_bid_order: Order | None = None
    no_ask_order: Order | None = None


@dataclass
class OrderAction:
    """An action to take on an order."""

    action_type: str  # "new", "cancel", "amend", "keep"
    quote_type: str  # "yes_bid", "yes_ask", "no_bid", "no_ask"
    order_id: str | None = None
    request: OrderRequest | None = None


class OrderDiffer:
    """Calculates diff between current orders and new quotes.

    Minimizes API calls by:
    - Keeping orders that match new quotes
    - Only cancelling orders that don't match
    - Only placing new orders where needed
    """

    def __init__(
        self,
        price_tolerance: Decimal = Decimal("0.01"),  # 1 cent tolerance to reduce churn
        size_tolerance: int = 0,
    ) -> None:
        """Initialize differ with tolerances.

        Args:
            price_tolerance: Max price difference to consider equal (default 1 cent)
            size_tolerance: Max size difference to consider equal
        """
        self._price_tolerance = price_tolerance
        self._size_tolerance = size_tolerance

    def diff(
        self,
        new_quotes: QuoteSet,
        current_orders: QuoteOrders | None,
    ) -> list[OrderAction]:
        """Calculate actions needed to update orders to match quotes.

        Args:
            new_quotes: New quotes to achieve
            current_orders: Current quote orders (if any)

        Returns:
            List of actions to execute
        """
        actions: list[OrderAction] = []

        # Convert quotes to order requests
        requests = new_quotes.to_order_requests()

        # Map requests to quote types
        request_map: dict[str, OrderRequest] = {}
        for req in requests:
            # Determine quote type from request
            if req.side.value == "yes":
                if req.order_side.value == "buy":
                    request_map["yes_bid"] = req
                else:
                    request_map["yes_ask"] = req
            else:
                if req.order_side.value == "buy":
                    request_map["no_bid"] = req
                else:
                    request_map["no_ask"] = req

        # Compare each quote type (YES side only - NO orders are redundant)
        for quote_type in ["yes_bid", "yes_ask"]:
            new_request = request_map.get(quote_type)
            current_order = self._get_current_order(current_orders, quote_type)

            # Skip orders at unfillable prices or with size 0 (used for one-sided quoting)
            # Bid at 0.01 or Ask at 0.99 indicates "don't place this side"
            # Size 0 also means "don't place this side"
            if new_request:
                price = new_request.price.value
                size = new_request.size.value
                if size <= 0:
                    new_request = None  # Skip zero-size orders
                elif quote_type == "yes_bid" and price <= Decimal("0.01"):
                    new_request = None  # Skip this bid
                elif quote_type == "yes_ask" and price >= Decimal("0.99"):
                    new_request = None  # Skip this ask

            action = self._diff_single(quote_type, new_request, current_order)
            if action:
                actions.append(action)

        return actions

    def _get_current_order(
        self,
        current_orders: QuoteOrders | None,
        quote_type: str,
    ) -> Order | None:
        """Get current order for a quote type."""
        if not current_orders:
            return None

        return {
            "yes_bid": current_orders.yes_bid_order,
            "yes_ask": current_orders.yes_ask_order,
            "no_bid": current_orders.no_bid_order,
            "no_ask": current_orders.no_ask_order,
        }.get(quote_type)

    def _diff_single(
        self,
        quote_type: str,
        new_request: OrderRequest | None,
        current_order: Order | None,
    ) -> OrderAction | None:
        """Diff a single quote/order pair.

        Args:
            quote_type: Type of quote
            new_request: New order request (if any)
            current_order: Current order (if any)

        Returns:
            Action to take, or None if no action needed
        """
        # No new quote, no current order - nothing to do
        if not new_request and not current_order:
            return None

        # No new quote but have current order - cancel it
        if not new_request and current_order:
            return OrderAction(
                action_type="cancel",
                quote_type=quote_type,
                order_id=current_order.id,
            )

        # Have new quote but no current order - place new
        if new_request and not current_order:
            return OrderAction(
                action_type="new",
                quote_type=quote_type,
                request=new_request,
            )

        # Both exist - check if they match
        if new_request and current_order:
            if self._orders_match(new_request, current_order):
                return OrderAction(
                    action_type="keep",
                    quote_type=quote_type,
                    order_id=current_order.id,
                )
            else:
                # Need to amend (cancel + new)
                return OrderAction(
                    action_type="amend",
                    quote_type=quote_type,
                    order_id=current_order.id,
                    request=new_request,
                )

        return None

    def _orders_match(self, request: OrderRequest, order: Order) -> bool:
        """Check if an order matches a request within tolerances.

        Args:
            request: New order request
            order: Existing order

        Returns:
            True if they match within tolerances
        """
        # Check price
        price_diff = abs(request.price.value - order.price.value)
        if price_diff > self._price_tolerance:
            return False

        # Check size (compare remaining size)
        # filled_size is an int, not Quantity
        remaining = order.size.value - order.filled_size
        size_diff = abs(request.size.value - remaining)
        if size_diff > self._size_tolerance:
            return False

        # Check side
        if request.side != order.side:
            return False

        # Check order side (buy/sell)
        if request.order_side != order.order_side:
            return False

        return True

    def calculate_stats(
        self,
        actions: list[OrderAction],
    ) -> dict[str, int]:
        """Calculate statistics about diff actions.

        Args:
            actions: List of actions

        Returns:
            Dict with counts of each action type
        """
        stats = {"new": 0, "cancel": 0, "amend": 0, "keep": 0}
        for action in actions:
            stats[action.action_type] = stats.get(action.action_type, 0) + 1
        return stats
