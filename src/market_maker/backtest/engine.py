"""Backtest engine for running strategy against recorded data."""

from __future__ import annotations

import logging
from decimal import Decimal
from pathlib import Path

from market_maker.backtest.loader import RecordingLoader
from market_maker.backtest.types import BacktestResult, RecordingMetadata, Tick
from market_maker.domain.market_data import OrderBook
from market_maker.domain.orders import QuoteSet
from market_maker.domain.types import Price, Side
from market_maker.execution.paper import PaperExecutionEngine
from market_maker.risk.base import RiskAction, RiskContext
from market_maker.risk.manager import RiskManager
from market_maker.state.store import StateStore
from market_maker.strategy.engine import StrategyEngine, StrategyInput

logger = logging.getLogger(__name__)


class BacktestEngine:
    """Runs a strategy against recorded market data.

    The backtest engine:
    1. Loads recorded order book data
    2. Generates quotes using the strategy
    3. Applies risk management
    4. Simulates fills with paper execution
    5. Tracks positions and PnL
    6. Handles settlement at market close

    Features:
    - Full strategy/risk/execution integration
    - Settlement simulation
    - Max drawdown tracking
    - Detailed statistics
    """

    def __init__(
        self,
        strategy: StrategyEngine,
        risk_manager: RiskManager | None = None,
        state_store: StateStore | None = None,
        execution_engine: PaperExecutionEngine | None = None,
        loader: RecordingLoader | None = None,
        max_inventory: int = 100,
        base_size: int = 10,
    ) -> None:
        """Initialize the backtest engine.

        Args:
            strategy: Strategy engine for quote generation
            risk_manager: Optional risk manager (if None, no risk checks)
            state_store: Optional state store (if None, creates new one)
            execution_engine: Optional execution engine (if None, creates new one)
            loader: Optional recording loader (if None, creates new one)
            max_inventory: Maximum inventory position allowed
            base_size: Base quote size
        """
        self._strategy = strategy
        self._risk_manager = risk_manager
        self._state_store = state_store or StateStore()
        self._execution = execution_engine or PaperExecutionEngine()
        self._loader = loader or RecordingLoader()
        self._max_inventory = max_inventory
        self._base_size = base_size

        # Tracking
        self._peak_pnl = Decimal("0")
        self._max_drawdown = Decimal("0")
        self._quotes_generated = 0
        self._quotes_blocked = 0
        self._applied_fills: set[str] = set()  # Track which fills we've applied

    def run(
        self,
        file_path: str | Path,
        settlement: Side | None = None,
        skip_ticks: int = 0,
        max_ticks: int | None = None,
    ) -> BacktestResult:
        """Run backtest on a recording file.

        Args:
            file_path: Path to the recording JSON file
            settlement: Known settlement outcome (YES or NO)
            skip_ticks: Number of initial ticks to skip
            max_ticks: Maximum ticks to process (None for all)

        Returns:
            BacktestResult with statistics and fills
        """
        # Load recording
        metadata, ticks = self._loader.load_recording(file_path, settlement)

        # Apply skip/max limits
        if skip_ticks > 0:
            ticks = ticks[skip_ticks:]
        if max_ticks is not None:
            ticks = ticks[:max_ticks]

        logger.info(
            "Starting backtest",
            extra={
                "market": metadata.market_ticker,
                "ticks": len(ticks),
                "settlement": settlement.name if settlement else "unknown",
            },
        )

        # Process each tick
        for tick in ticks:
            self._process_tick(tick, metadata)

        # Apply settlement if known
        settlement_pnl = Decimal("0")
        if settlement is not None:
            settlement_pnl = self._apply_settlement(metadata.market_ticker, settlement)

        # Calculate final PnL
        final_position = self._state_store.get_position(metadata.market_ticker)
        final_yes = final_position.yes_quantity if final_position else 0
        final_no = final_position.no_quantity if final_position else 0

        # Calculate unrealized PnL using last tick's mid price
        unrealized_pnl = Decimal("0")
        if ticks and final_position:
            last_book = ticks[-1].order_book
            best_bid = last_book.best_bid()
            best_ask = last_book.best_ask()
            if best_bid and best_ask:
                mid_price = Price(
                    (best_bid.price.value + best_ask.price.value) / Decimal("2")
                )
                unrealized_pnl = self._state_store.calculate_unrealized_pnl(
                    metadata.market_ticker, mid_price
                )

        total_pnl = self._state_store.realized_pnl + unrealized_pnl + settlement_pnl

        return BacktestResult(
            metadata=metadata,
            total_ticks=len(ticks),
            total_fills=len(self._execution.get_fills()),
            fills=self._execution.get_fills(),
            final_yes_position=final_yes,
            final_no_position=final_no,
            realized_pnl=self._state_store.realized_pnl,
            unrealized_pnl=unrealized_pnl,
            total_pnl=total_pnl,
            total_fees=self._state_store.total_fees,
            settlement_pnl=settlement_pnl,
            max_drawdown=self._max_drawdown,
            quotes_generated=self._quotes_generated,
            quotes_blocked=self._quotes_blocked,
        )

    def _process_tick(self, tick: Tick, metadata: RecordingMetadata) -> None:
        """Process a single tick.

        Args:
            tick: Tick to process
            metadata: Recording metadata
        """
        book = tick.order_book
        market_id = metadata.market_ticker

        # Calculate mid price for strategy
        best_bid = book.best_bid()
        best_ask = book.best_ask()

        if not best_bid or not best_ask:
            return  # Skip if no market

        mid_price = Price(
            (best_bid.price.value + best_ask.price.value) / Decimal("2")
        )

        # Get current inventory
        inventory = self._state_store.get_net_inventory(market_id)

        # Convert time to settlement (hours)
        time_to_settlement = tick.time_to_close_seconds / 3600.0

        # Skip if too close to settlement
        if time_to_settlement <= 0:
            return

        # Generate quotes
        strategy_input = StrategyInput(
            market_id=market_id,
            mid_price=mid_price,
            inventory=inventory,
            max_inventory=self._max_inventory,
            base_size=self._base_size,
            time_to_settlement=time_to_settlement,
            timestamp=tick.timestamp,
        )

        try:
            quotes = self._strategy.generate_quotes(strategy_input)
            self._quotes_generated += 1
        except Exception as e:
            logger.warning(f"Strategy error: {e}")
            return

        # Apply risk management
        if self._risk_manager:
            # Calculate unrealized PnL for context
            unrealized_pnl = self._state_store.calculate_unrealized_pnl(
                market_id, mid_price
            )

            # Get volatility from strategy
            current_volatility = self._strategy._volatility.get_volatility()

            context = RiskContext(
                current_inventory=inventory,
                max_inventory=self._max_inventory,
                positions=self._state_store.positions,
                realized_pnl=self._state_store.realized_pnl,
                unrealized_pnl=unrealized_pnl,
                hourly_pnl=self._state_store.hourly_pnl,
                daily_pnl=self._state_store.daily_pnl,
                time_to_settlement=time_to_settlement,
                current_volatility=current_volatility,
                order_book=book,
            )

            decision = self._risk_manager.evaluate(quotes, context)

            if decision.action == RiskAction.BLOCK:
                self._quotes_blocked += 1
                return

            if decision.modified_quotes:
                quotes = decision.modified_quotes

        # Submit orders and check for fills
        self._submit_quotes(quotes, book, market_id)

        # Update PnL tracking
        self._update_drawdown()

    def _submit_quotes(
        self,
        quotes: QuoteSet,
        book: OrderBook,
        market_id: str,
    ) -> None:
        """Submit quote set as orders.

        Args:
            quotes: QuoteSet with bid/ask quotes
            book: Current order book
            market_id: Market identifier
        """
        # Cancel existing orders first
        self._execution.cancel_all_orders(market_id)

        # Use to_order_requests() to get all orders from the quote set
        order_requests = quotes.to_order_requests()

        for request in order_requests:
            order = self._execution.submit_order(request, book)
            self._apply_fills_for_order(order.id)

    def _apply_fills_for_order(self, order_id: str) -> None:
        """Apply any fills for an order to state.

        Args:
            order_id: Order ID to check
        """
        for fill in self._execution.get_fills():
            if fill.order_id == order_id and fill.id not in self._applied_fills:
                self._state_store.apply_fill(fill)
                self._applied_fills.add(fill.id)

    def _apply_settlement(self, market_id: str, settlement: Side) -> Decimal:
        """Apply settlement to calculate final PnL.

        Args:
            market_id: Market that settled
            settlement: How it settled (YES or NO)

        Returns:
            Settlement PnL
        """
        position = self._state_store.get_position(market_id)
        if position is None:
            return Decimal("0")

        settlement_pnl = Decimal("0")

        # YES positions
        if position.yes_quantity > 0:
            if settlement == Side.YES:
                # YES wins, get $1 per contract
                if position.avg_yes_price:
                    settlement_pnl += (
                        Decimal("1") - position.avg_yes_price.value
                    ) * Decimal(position.yes_quantity)
            else:
                # YES loses, get $0
                if position.avg_yes_price:
                    settlement_pnl -= position.avg_yes_price.value * Decimal(
                        position.yes_quantity
                    )

        # NO positions
        if position.no_quantity > 0:
            if settlement == Side.NO:
                # NO wins, get $1 per contract
                if position.avg_no_price:
                    settlement_pnl += (
                        Decimal("1") - position.avg_no_price.value
                    ) * Decimal(position.no_quantity)
            else:
                # NO loses, get $0
                if position.avg_no_price:
                    settlement_pnl -= position.avg_no_price.value * Decimal(
                        position.no_quantity
                    )

        return settlement_pnl

    def _update_drawdown(self) -> None:
        """Update max drawdown tracking."""
        current_pnl = self._state_store.realized_pnl

        if current_pnl > self._peak_pnl:
            self._peak_pnl = current_pnl

        drawdown = self._peak_pnl - current_pnl
        if drawdown > self._max_drawdown:
            self._max_drawdown = drawdown
