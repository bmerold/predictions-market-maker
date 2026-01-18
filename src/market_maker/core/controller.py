"""Trading controller - main application loop.

Orchestrates the market data, strategy, risk, and execution components.
"""

from __future__ import annotations

import asyncio
import contextlib
import logging
import os
import signal
import time
from datetime import UTC, datetime
from decimal import ROUND_CEILING, Decimal
from typing import TYPE_CHECKING

from market_maker.core.config import ExchangeType, ExecutionMode, TradingConfig
from market_maker.db.repository import TradingRepository
from market_maker.domain.events import BookUpdate, Event, EventType, FillEvent
from market_maker.domain.orders import Fill, Quote, QuoteSet
from market_maker.domain.market_data import OrderBook
from market_maker.domain.positions import Position
from market_maker.domain.types import Price, Quantity
from market_maker.exchange.base import ExchangeAdapter
from market_maker.exchange.kalshi import KalshiExchangeAdapter
from market_maker.exchange.kalshi.auth import KalshiCredentials
from market_maker.execution.live import LiveExecutionEngine
from market_maker.execution.paper import PaperExecutionEngine
from market_maker.market_data.book_builder import OrderBookBuilder
from market_maker.market_data.handler import MarketDataHandler
from market_maker.risk.base import RiskContext
from market_maker.risk.manager import RiskManager
from market_maker.risk.rules.pnl import DailyLossLimitRule, HourlyLossLimitRule
from market_maker.risk.rules.position import MaxInventoryRule, MaxOrderSizeRule
from market_maker.risk.rules.time import SettlementCutoffRule, StaleDataRule
from market_maker.state.store import StateStore
from market_maker.strategy.engine import StrategyEngine, StrategyInput
from market_maker.strategy.factory import StrategyConfig, create_strategy_engine

if TYPE_CHECKING:
    from market_maker.execution.base import ExecutionEngine
    from market_maker.risk.base import RiskRule

logger = logging.getLogger(__name__)


class TradingController:
    """Main trading controller.

    Manages the trading loop lifecycle:
    1. Connect to exchange
    2. Subscribe to markets
    3. Process market data
    4. Generate quotes via strategy
    5. Check quotes via risk manager
    6. Execute quotes via execution engine
    7. Track state and PnL

    Features:
    - Graceful shutdown on SIGTERM/SIGINT
    - Automatic reconnection
    - Position reconciliation
    - Kill switch integration
    """

    def __init__(self, config: TradingConfig) -> None:
        """Initialize the trading controller.

        Args:
            config: Trading configuration
        """
        self._config = config
        self._running = False
        self._shutdown_event = asyncio.Event()

        # Components (initialized in start)
        self._exchange: ExchangeAdapter | None = None
        self._execution: ExecutionEngine | None = None
        self._strategy: StrategyEngine | None = None
        self._risk_manager: RiskManager | None = None
        self._state: StateStore | None = None
        self._market_data: MarketDataHandler | None = None
        self._repository: TradingRepository | None = None

        # Per-market state
        self._book_builders: dict[str, OrderBookBuilder] = {}
        self._order_books: dict[str, OrderBook] = {}
        self._last_quote_time: dict[str, float] = {}  # time.time() for throttling
        self._last_best_bid: dict[str, Decimal] = {}
        self._last_best_ask: dict[str, Decimal] = {}
        self._market_settlement_times: dict[str, datetime] = {}  # Fetched from exchange

        # Throttling config (seconds)
        self._min_quote_interval = 0.05  # 50ms minimum between quotes (was 100ms)

        # Pending quote tasks
        self._pending_quote_tasks: dict[str, asyncio.Task[None]] = {}

        # Tasks
        self._quote_task: asyncio.Task[None] | None = None
        self._reconcile_task: asyncio.Task[None] | None = None
        self._pnl_log_task: asyncio.Task[None] | None = None
        self._api_task: asyncio.Task[None] | None = None

        # Session tracking
        self._session_id = datetime.now(UTC).strftime("%Y%m%d_%H%M%S")
        self._start_time = datetime.now(UTC)
        self._fill_count = 0
        self._quote_count = 0

        # Fill history for API
        self._fills: list[Fill] = []

        # Directional market detection - track recent mid prices
        # Format: {market_id: [(timestamp, mid_price), ...]}
        self._mid_price_history: dict[str, list[tuple[float, Decimal]]] = {}
        self._mid_price_window_seconds = 30.0  # Look back 30 seconds

        # Adverse selection tracking
        # Format: {market_id: [(fill_time, fill_price, fill_side, mid_at_fill), ...]}
        self._recent_fills_for_adverse: dict[str, list[tuple[float, Decimal, str, Decimal]]] = {}
        self._adverse_selection_score: dict[str, float] = {}  # -1 to 1, negative = we're losing
        self._adverse_lookback_fills = 10  # Number of fills to consider

        # Dynamic spread multiplier based on market conditions
        self._spread_multiplier: dict[str, Decimal] = {}  # 1.0 = normal, 2.0 = double spread

    async def start(self) -> None:
        """Start the trading controller.

        Initializes all components and begins the trading loop.
        """
        logger.info("Starting trading controller")
        logger.info(f"Mode: {self._config.mode.value}")
        logger.info(f"Exchange: {self._config.exchange.type.value}")
        logger.info(f"Markets: {[m.ticker for m in self._config.markets]}")

        # Set up signal handlers
        self._setup_signal_handlers()

        # Initialize components
        await self._init_components()

        # Connect to exchange
        if self._exchange:
            await self._exchange.connect()
            self._exchange.set_event_handler(self._handle_event)

            # Subscribe to markets and fetch settlement times
            for market in self._config.markets:
                await self._exchange.subscribe_market(market.ticker)
                self._book_builders[market.ticker] = OrderBookBuilder(market.ticker)
                # Fetch market info for settlement time
                await self._fetch_market_settlement_time(market.ticker)

        self._running = True

        # Start background tasks
        self._quote_task = asyncio.create_task(self._quote_loop())
        self._reconcile_task = asyncio.create_task(self._reconciliation_loop())
        self._pnl_log_task = asyncio.create_task(self._pnl_logging_loop())

        # Start API server if configured
        api_port = getattr(self._config, "api_port", None) or 8080
        if api_port:
            self._api_task = asyncio.create_task(self._run_api_server(api_port))
            logger.info(f"API server started on http://localhost:{api_port}")

        logger.info(f"Trading controller started (session: {self._session_id})")

        # Wait for shutdown
        await self._shutdown_event.wait()

        # Clean up
        await self._shutdown()

    async def stop(self) -> None:
        """Stop the trading controller gracefully."""
        logger.info("Stopping trading controller")
        self._running = False
        self._shutdown_event.set()

    @property
    def is_running(self) -> bool:
        """Check if the controller is running."""
        return self._running

    @property
    def state_store(self) -> StateStore | None:
        """Get the state store for API access."""
        return self._state

    def get_open_orders(self, market_id: str) -> list:
        """Get open orders for a market."""
        # For paper trading, we don't maintain open orders
        # In live mode, this would query the execution engine
        return []

    def get_fills(self, market_id: str) -> list[Fill]:
        """Get fills for a market."""
        return [f for f in self._fills if f.market_id == market_id]

    def get_config(self) -> dict:
        """Get current configuration for API."""
        strategy_config = self._config.strategy
        return {
            "gamma": str(strategy_config.components.reservation_price.params.get("gamma", "0.1")),
            "sigma": str(strategy_config.components.volatility.params.get("volatility", "0.05")),
            "min_spread": str(strategy_config.min_spread),
            "max_inventory": strategy_config.max_inventory,
            "kill_switch_active": (
                self._risk_manager.kill_switch.is_active()
                if self._risk_manager
                else False
            ),
        }

    def update_config(self, updates: dict) -> None:
        """Update configuration at runtime."""
        # This would update the strategy/risk params
        # For now, just log
        logger.info(f"Config update requested: {updates}")

    async def activate_kill_switch(self) -> None:
        """Activate the kill switch."""
        if self._risk_manager:
            self._risk_manager.kill_switch.activate("API request")
            logger.warning("Kill switch activated via API")

    def deactivate_kill_switch(self) -> None:
        """Deactivate the kill switch."""
        if self._risk_manager:
            self._risk_manager.kill_switch.reset()
            logger.info("Kill switch deactivated via API")

    async def _run_api_server(self, port: int) -> None:
        """Run the API server."""
        try:
            import uvicorn

            from market_maker.monitoring.api.routes import create_app

            app = create_app(
                controller=self,
                state_store=self._state,
                mode=self._config.mode.value,
            )

            config = uvicorn.Config(
                app,
                host="0.0.0.0",
                port=port,
                log_level="warning",  # Reduce uvicorn noise
            )
            server = uvicorn.Server(config)
            await server.serve()
        except ImportError:
            logger.warning("uvicorn not installed, API server disabled")
        except Exception as e:
            logger.error(f"API server error: {e}")

    async def _init_components(self) -> None:
        """Initialize all trading components."""
        # Create exchange adapter
        self._exchange = self._create_exchange()

        # Create state store with Kalshi maker fee rate
        # Kalshi maker fee: 0.0175 × contracts × P × (1-P)
        KALSHI_MAKER_FEE_RATE = Decimal("0.0175")
        self._state = StateStore(fee_rate=KALSHI_MAKER_FEE_RATE)

        # Create SQLite repository for persistence
        self._repository = TradingRepository(
            db_url="sqlite:///trading.db",
            session_id=self._session_id,
        )
        logger.info(f"SQLite persistence enabled: trading.db (session: {self._session_id})")

        # Create strategy engine
        self._strategy = self._create_strategy()

        # Create risk manager
        self._risk_manager = self._create_risk_manager()

        # Create execution engine
        self._execution = self._create_execution()

        # Create market data handler
        self._market_data = MarketDataHandler()

    def _create_exchange(self) -> ExchangeAdapter | None:
        """Create the exchange adapter based on config."""
        exchange_config = self._config.exchange

        if exchange_config.type == ExchangeType.KALSHI:
            # Load credentials from config or environment
            api_key = exchange_config.api_key or os.environ.get(
                exchange_config.api_key_env, ""
            )
            private_key_path = exchange_config.private_key_path or os.environ.get(
                exchange_config.private_key_path_env, ""
            )

            if not api_key or not private_key_path:
                logger.warning(
                    f"Kalshi credentials not found. Set {exchange_config.api_key_env} "
                    f"and {exchange_config.private_key_path_env} environment variables, "
                    f"or provide api_key and private_key_path in config."
                )
                return None

            credentials = KalshiCredentials(
                api_key=api_key,
                private_key_path=private_key_path,
                demo=exchange_config.demo,
            )
            return KalshiExchangeAdapter(credentials)

        elif exchange_config.type == ExchangeType.MOCK:
            # For testing, return None (tests should inject mock)
            logger.info("Mock exchange mode - no adapter created")
            return None

        return None

    def _create_strategy(self) -> StrategyEngine:
        """Create the strategy engine from config."""
        strategy_config = self._config.strategy
        components = strategy_config.components

        # Build StrategyConfig from our TradingConfig
        factory_config = StrategyConfig(
            volatility_type=components.volatility.type,
            volatility_params=_convert_params(components.volatility.params),
            reservation_type=components.reservation_price.type,
            reservation_params=_convert_params(components.reservation_price.params),
            skew_type=components.skew.type,
            skew_params=_convert_params(components.skew.params),
            spread_type=components.spread.type,
            spread_params=_convert_params(components.spread.params),
            sizer_type=components.sizer.type,
            sizer_params=_convert_params(components.sizer.params),
        )

        return create_strategy_engine(factory_config)

    def _create_risk_manager(self) -> RiskManager:
        """Create the risk manager."""
        risk_config = self._config.risk

        # Build rules based on config
        rules: list[RiskRule] = []

        for rule_name in risk_config.rule_order:
            rule_conf = risk_config.rules.get(rule_name)
            if not rule_conf or not rule_conf.enabled:
                continue

            rule = self._create_risk_rule(rule_name, rule_conf)
            if rule:
                rules.append(rule)

        return RiskManager(rules=rules)

    def _create_risk_rule(
        self, name: str, conf: object
    ) -> RiskRule | None:
        """Create a risk rule from config."""
        from market_maker.core.config import RiskRuleConfig

        if not isinstance(conf, RiskRuleConfig):
            return None

        if name == "stale_data":
            max_age = conf.max_age_seconds or 5
            return StaleDataRule(max_age_seconds=max_age)

        elif name == "settlement_cutoff":
            cutoff = conf.cutoff_minutes or 3
            return SettlementCutoffRule(cutoff_minutes=cutoff)

        elif name == "daily_loss_limit":
            limit = conf.limit or Decimal("100")
            return DailyLossLimitRule(max_loss=limit)

        elif name == "hourly_loss_limit":
            limit = conf.limit or Decimal("50")
            return HourlyLossLimitRule(max_loss=limit)

        elif name == "max_inventory":
            inv_limit = int(conf.limit) if conf.limit else 1000
            return MaxInventoryRule(max_inventory=inv_limit)

        elif name == "max_order_size":
            size_limit = int(conf.limit) if conf.limit else 500
            return MaxOrderSizeRule(max_size=size_limit)

        return None

    def _create_execution(self) -> ExecutionEngine:
        """Create the execution engine based on mode."""
        if self._config.mode == ExecutionMode.PAPER:
            logger.info("Using PAPER execution engine (simulated fills)")
            return PaperExecutionEngine()
        else:
            # Live execution - requires exchange adapter
            if self._exchange:
                logger.warning("Using LIVE execution engine - REAL MONEY")
                return LiveExecutionEngine(self._exchange)
            else:
                logger.warning("No exchange adapter for live mode, falling back to paper")
                return PaperExecutionEngine()

    def _setup_signal_handlers(self) -> None:
        """Set up signal handlers for graceful shutdown."""
        loop = asyncio.get_event_loop()

        for sig in (signal.SIGTERM, signal.SIGINT):
            loop.add_signal_handler(sig, self._handle_signal, sig)

    def _handle_signal(self, sig: signal.Signals) -> None:
        """Handle shutdown signal."""
        logger.info(f"Received signal {sig.name}, initiating shutdown")
        self._shutdown_event.set()

    def _handle_event(self, event: Event) -> None:
        """Handle an event from the exchange.

        Args:
            event: Exchange event (book update, fill, etc.)
        """
        logger.debug(f"Received event: {event.event_type}")
        if event.event_type == EventType.BOOK_UPDATE:
            self._handle_book_update(event)  # type: ignore
        elif event.event_type == EventType.FILL:
            self._handle_fill(event)  # type: ignore
        elif event.event_type == EventType.ORDER_UPDATE:
            # Order updates are handled by execution engine
            pass

    def _handle_book_update(self, event: BookUpdate) -> None:
        """Handle an order book update.

        Event-driven: triggers re-quoting when book changes significantly.

        Args:
            event: Book update event
        """
        market_id = event.market_id
        builder = self._book_builders.get(market_id)

        if not builder:
            return

        # Apply update using BookUpdate
        builder.apply_update(event)

        # Update current book
        book = builder.get_book()
        if book:
            self._order_books[market_id] = book

            # Check if best bid/ask changed
            if book.yes_bids and book.yes_asks:
                new_best_bid = book.yes_bids[0].price.value
                new_best_ask = book.yes_asks[0].price.value

                old_best_bid = self._last_best_bid.get(market_id)
                old_best_ask = self._last_best_ask.get(market_id)

                # Detect significant change (any change in best bid/ask)
                book_changed = (
                    old_best_bid is None
                    or old_best_ask is None
                    or new_best_bid != old_best_bid
                    or new_best_ask != old_best_ask
                )

                # Update tracking
                self._last_best_bid[market_id] = new_best_bid
                self._last_best_ask[market_id] = new_best_ask

                # Track mid price for directional market detection
                mid_price = (new_best_bid + new_best_ask) / 2
                self._update_mid_price_history(market_id, mid_price)

                # Update volatility estimator with mid price changes
                # This makes volatility react to book changes, not just trades
                if book_changed and self._strategy:
                    vol_estimator = self._strategy.volatility_estimator
                    if hasattr(vol_estimator, 'update_from_mid_price'):
                        vol_estimator.update_from_mid_price(mid_price)

                # Trigger quote if book changed (with throttling)
                if book_changed:
                    self._maybe_trigger_quote(market_id)

    def _maybe_trigger_quote(self, market_id: str) -> None:
        """Trigger a quote for a market if throttling allows.

        Uses asyncio to schedule the quote without blocking the event handler.
        """
        now = time.time()
        last_quote = self._last_quote_time.get(market_id, 0)

        # Check throttle
        time_since_last = now - last_quote
        if time_since_last < self._min_quote_interval:
            # Too soon, skip (the book is updating faster than we can quote)
            return

        # Cancel any pending quote task for this market
        if market_id in self._pending_quote_tasks:
            task = self._pending_quote_tasks[market_id]
            if not task.done():
                task.cancel()

        # Schedule quote execution
        self._pending_quote_tasks[market_id] = asyncio.create_task(
            self._quote_single_market(market_id)
        )

    def _handle_fill(self, event: FillEvent) -> None:
        """Handle a fill event.

        Updates state and notifies execution engine of the fill.
        May trigger order cancellation if inventory limits exceeded.

        Args:
            event: Fill event
        """
        fill = event.fill
        self._fill_count += 1
        self._fills.append(fill)

        if self._state:
            self._state.apply_fill(fill)

        # Notify execution engine of fill (updates order tracking)
        if self._execution and hasattr(self._execution, 'add_fill'):
            self._execution.add_fill(fill)

        # Persist fill to database
        if self._repository:
            self._repository.save_fill(fill)

        logger.info(
            f"Fill #{self._fill_count}: {fill.order_side.value} {fill.size.value} "
            f"{fill.side.value} @ {fill.price.value:.2f} on {fill.market_id}"
        )

        # Track adverse selection - get mid price at fill time
        book = self._order_books.get(fill.market_id)
        if book and book.yes_bids and book.yes_asks:
            mid_at_fill = (book.yes_bids[0].price.value + book.yes_asks[0].price.value) / 2
            self._update_adverse_selection(
                fill.market_id,
                fill.price.value,
                fill.order_side.value,
                mid_at_fill,
            )

        # Check inventory limits SYNCHRONOUSLY and set block flags immediately
        # This prevents race conditions where more fills arrive before async cancel completes
        self._check_inventory_after_fill_sync(fill.market_id)

    def _check_inventory_after_fill_sync(self, market_id: str) -> None:
        """Check inventory after a fill and block/cancel orders if needed.

        This runs SYNCHRONOUSLY to prevent race conditions. Sets blocking flags
        immediately and schedules async cancellation.
        """
        if not self._state or not self._execution:
            return

        position = self._get_position(market_id)
        inventory = position.net_inventory()
        max_inv = self._config.strategy.max_inventory

        # Use a buffer of 1 - start blocking when we're 1 away from limit
        # This prevents fills from pushing us over before cancel completes
        effective_limit = max_inv - 1

        # Track markets that are blocked due to inventory
        if not hasattr(self, '_inventory_blocked'):
            self._inventory_blocked: dict[str, str] = {}  # market_id -> "long" or "short"

        # If inventory is near limit, block the side that would make it worse
        if inventory >= effective_limit:
            # Long inventory - block bids immediately
            self._inventory_blocked[market_id] = "long"
            logger.warning(
                f"INVENTORY BLOCK: Long inventory {inventory} >= {effective_limit}, blocking bids for {market_id}"
            )
            # Schedule async cancel of any resting bid
            asyncio.create_task(self._cancel_side_orders(market_id, "bid"))

        elif inventory <= -effective_limit:
            # Short inventory - block asks immediately
            self._inventory_blocked[market_id] = "short"
            logger.warning(
                f"INVENTORY BLOCK: Short inventory {inventory} <= -{effective_limit}, blocking asks for {market_id}"
            )
            # Schedule async cancel of any resting ask
            asyncio.create_task(self._cancel_side_orders(market_id, "ask"))

        else:
            # Clear any blocks if inventory is back within limits
            if market_id in self._inventory_blocked:
                del self._inventory_blocked[market_id]
                logger.info(f"INVENTORY UNBLOCK: {market_id} inventory {inventory} back within limits")

    async def _cancel_side_orders(self, market_id: str, side: str) -> None:
        """Cancel orders on one side due to inventory limits."""
        if not self._execution or not hasattr(self._execution, '_quote_orders'):
            return

        quote_orders = self._execution._quote_orders.get(market_id)
        if not quote_orders:
            return

        if side == "bid" and quote_orders.yes_bid_order:
            order = quote_orders.yes_bid_order
            if order and not self._execution._orders.get(order.id, order).status.is_terminal():
                logger.info(f"Cancelling bid order {order.id} due to inventory limit")
                await self._execution.cancel_order(order.id)
                quote_orders.yes_bid_order = None

        elif side == "ask" and quote_orders.yes_ask_order:
            order = quote_orders.yes_ask_order
            if order and not self._execution._orders.get(order.id, order).status.is_terminal():
                logger.info(f"Cancelling ask order {order.id} due to inventory limit")
                await self._execution.cancel_order(order.id)
                quote_orders.yes_ask_order = None

    async def _quote_loop(self) -> None:
        """Fallback quoting loop - catches any missed updates.

        The primary quoting is event-driven via _handle_book_update.
        This loop is a safety net that runs at a longer interval.
        """
        # Use a longer fallback interval (5 seconds)
        fallback_interval = 5.0
        logger.info(
            f"Quote loop started (event-driven with {fallback_interval}s fallback, "
            f"{self._min_quote_interval * 1000:.0f}ms throttle)"
        )

        while self._running:
            try:
                await self._generate_and_execute_quotes()
            except Exception as e:
                logger.error(f"Error in quote loop: {e}", exc_info=True)

            await asyncio.sleep(fallback_interval)

    async def _quote_single_market(self, market_id: str) -> None:
        """Generate and execute quotes for a single market.

        Called by the event-driven book update handler.
        """
        # Update throttle timestamp at start
        self._last_quote_time[market_id] = time.time()

        try:
            if self._risk_manager and self._risk_manager.kill_switch.is_active():
                return

            book = self._order_books.get(market_id)
            if not book:
                return

            # Find the market config
            market_config = None
            for m in self._config.markets:
                if m.ticker == market_id:
                    market_config = m
                    break

            if not market_config:
                return

            # Get current position
            position = self._get_position(market_id)

            # Calculate mid price
            mid_price = self._get_mid_price(book)
            if mid_price is None:
                return

            # Get time to settlement in hours
            time_to_settlement = self._get_time_to_settlement_hours(market_config)

            # Build strategy input
            strategy_input = StrategyInput(
                market_id=market_id,
                mid_price=mid_price,
                inventory=position.net_inventory(),
                max_inventory=self._config.strategy.max_inventory,
                base_size=self._get_base_size(),
                time_to_settlement=time_to_settlement,
                timestamp=datetime.now(UTC),
            )

            # Generate quotes
            quotes = None
            if self._strategy:
                quotes = self._strategy.generate_quotes(strategy_input)

                if quotes:
                    yq = quotes.yes_quote
                    best_bid = book.yes_bids[0].price.value if book.yes_bids else Decimal("0")
                    best_ask = book.yes_asks[0].price.value if book.yes_asks else Decimal("1")
                    logger.info(
                        f"[{market_id}] book={best_bid:.2f}/{best_ask:.2f}, "
                        f"mid={mid_price.value:.2f}, inv={position.net_inventory()}, "
                        f"quote={yq.bid_price.value:.2f}/{yq.ask_price.value:.2f}"
                    )

            # Clamp quotes to stay inside the spread (MAKER mode)
            if quotes:
                quotes = self._clamp_quotes_to_spread(quotes, book, market_id)
                if quotes is None:
                    logger.debug("Quotes skipped: spread too tight")
                    return

            # Adjust quotes for inventory reduction BEFORE risk check
            # This ensures risk manager sees one-sided quotes when at limits
            if quotes:
                quotes = self._adjust_quotes_for_inventory(
                    quotes, book,
                    position.net_inventory(),
                    self._config.strategy.max_inventory,
                )
                if quotes is None:
                    logger.debug("Quotes skipped: inventory adjustment")
                    return

            # Check for severe adverse selection - stop quoting if we're getting picked off badly
            adverse_score = self._adverse_selection_score.get(market_id, 0.0)
            if adverse_score < -0.5:  # Losing > 50% of fills to adverse selection
                logger.warning(
                    f"ADVERSE SELECTION STOP: Score {adverse_score:.2f} < -0.5, "
                    f"stopping quotes for {market_id} (we're being picked off)"
                )
                return

            # Check unrealized loss limit - stop if position is losing too much
            MAX_UNREALIZED_LOSS = Decimal("2.00")  # $2 max unrealized loss per market
            if self._state and mid_price:
                unrealized = self._state.calculate_unrealized_pnl(market_id, mid_price.value)
                if unrealized < -MAX_UNREALIZED_LOSS:
                    logger.warning(
                        f"UNREALIZED LOSS STOP: Position loss ${-unrealized:.2f} > ${MAX_UNREALIZED_LOSS}, "
                        f"stopping quotes for {market_id}"
                    )
                    return

            # Check with risk manager (after inventory adjustment)
            if quotes and self._risk_manager and self._state:
                context = self._build_risk_context(market_id, book, position)
                decision = self._risk_manager.evaluate(quotes, context)
                if decision.action.name == "BLOCK":
                    logger.info(f"Quotes blocked by risk: {decision.reason}")
                    return
                elif decision.modified_quotes:
                    quotes = decision.modified_quotes

            # Execute quotes
            if self._execution and quotes:
                await self._execute_quotes(market_id, book, quotes)

        except Exception as e:
            logger.error(f"Error quoting {market_id}: {e}", exc_info=True)

    async def _generate_and_execute_quotes(self) -> None:
        """Generate quotes for all markets and execute them."""
        if self._risk_manager and self._risk_manager.kill_switch.is_active():
            logger.debug("Kill switch active, skipping quotes")
            return

        for market in self._config.markets:
            market_id = market.ticker
            book = self._order_books.get(market_id)

            if not book:
                logger.debug(f"No order book for {market_id}, skipping")
                continue

            logger.debug(f"Book for {market_id}: {len(book.yes_bids)} bids, {len(book.yes_asks)} asks")

            # Get current position
            position = self._get_position(market_id)

            # Calculate mid price
            mid_price = self._get_mid_price(book)
            if mid_price is None:
                continue

            # Get time to settlement in hours
            time_to_settlement = self._get_time_to_settlement_hours(market)

            # Build strategy input
            strategy_input = StrategyInput(
                market_id=market_id,
                mid_price=mid_price,
                inventory=position.net_inventory(),
                max_inventory=self._config.strategy.max_inventory,
                base_size=self._get_base_size(),
                time_to_settlement=time_to_settlement,
                timestamp=datetime.now(UTC),
            )

            # Generate quotes
            if self._strategy:
                quotes = self._strategy.generate_quotes(strategy_input)

                if quotes:
                    yq = quotes.yes_quote
                    logger.info(
                        f"[{market_id}] mid={mid_price.value:.2f}, "
                        f"inv={position.net_inventory()}, "
                        f"YES bid={yq.bid_price.value:.2f}@{yq.bid_size.value}, "
                        f"YES ask={yq.ask_price.value:.2f}@{yq.ask_size.value}"
                    )

                # Clamp quotes to stay inside the spread (MAKER mode)
                # This prevents crossing the spread and becoming a taker
                quotes = self._clamp_quotes_to_spread(quotes, book, market_id)
                if quotes is None:
                    logger.info(f"Quotes skipped: spread too tight to provide liquidity")
                    continue

                # Adjust quotes for inventory reduction BEFORE risk check
                quotes = self._adjust_quotes_for_inventory(
                    quotes, book,
                    position.net_inventory(),
                    self._config.strategy.max_inventory,
                )
                if quotes is None:
                    logger.info(f"Quotes skipped: inventory adjustment")
                    continue

                # Check for severe adverse selection - stop quoting if we're getting picked off badly
                adverse_score = self._adverse_selection_score.get(market_id, 0.0)
                if adverse_score < -0.5:  # Losing > 50% of fills to adverse selection
                    logger.warning(
                        f"ADVERSE SELECTION STOP: Score {adverse_score:.2f} < -0.5, "
                        f"stopping quotes for {market_id} (we're being picked off)"
                    )
                    continue

                # Check unrealized loss limit - stop if position is losing too much
                MAX_UNREALIZED_LOSS = Decimal("2.00")  # $2 max unrealized loss per market
                if self._state and mid_price:
                    unrealized = self._state.calculate_unrealized_pnl(market_id, mid_price.value)
                    if unrealized < -MAX_UNREALIZED_LOSS:
                        logger.warning(
                            f"UNREALIZED LOSS STOP: Position loss ${-unrealized:.2f} > ${MAX_UNREALIZED_LOSS}, "
                            f"stopping quotes for {market_id}"
                        )
                        continue

                # Check with risk manager (after inventory adjustment)
                if self._risk_manager and self._state:
                    context = self._build_risk_context(market_id, book, position)
                    decision = self._risk_manager.evaluate(quotes, context)
                    if decision.action.name == "BLOCK":
                        logger.info(f"Quotes blocked by risk: {decision.reason}")
                        continue
                    elif decision.modified_quotes:
                        quotes = decision.modified_quotes

                # Execute quotes
                if self._execution and quotes:
                    await self._execute_quotes(market_id, book, quotes)

    def _get_position(self, market_id: str) -> Position:
        """Get current position for a market."""
        if self._state:
            position = self._state.get_position(market_id)
            if position:
                return position
        return Position.empty(market_id)

    def _get_mid_price(self, book: OrderBook) -> Price | None:
        """Calculate mid price from order book."""
        if not book.yes_bids or not book.yes_asks:
            return None

        best_bid = book.yes_bids[0].price.value
        best_ask = book.yes_asks[0].price.value
        mid = (best_bid + best_ask) / 2
        return Price(mid)

    def _update_mid_price_history(self, market_id: str, mid_price: Decimal) -> None:
        """Track mid price for directional market detection.

        Maintains a rolling window of recent mid prices to detect
        when the market is moving strongly in one direction.
        """
        now = time.time()

        if market_id not in self._mid_price_history:
            self._mid_price_history[market_id] = []

        self._mid_price_history[market_id].append((now, mid_price))

        # Remove old entries outside the window
        cutoff = now - self._mid_price_window_seconds
        self._mid_price_history[market_id] = [
            (t, p) for t, p in self._mid_price_history[market_id]
            if t > cutoff
        ]

    def _calculate_price_velocity(self, market_id: str) -> Decimal:
        """Calculate price velocity (cents per second) for directional detection.

        Returns:
            Price change rate in cents/second. Positive = price rising.
        """
        history = self._mid_price_history.get(market_id, [])
        if len(history) < 2:
            return Decimal("0")

        # Get oldest and newest prices in window
        oldest_time, oldest_price = history[0]
        newest_time, newest_price = history[-1]

        time_diff = newest_time - oldest_time
        if time_diff < 1.0:  # Need at least 1 second of data
            return Decimal("0")

        price_diff = newest_price - oldest_price
        velocity = price_diff / Decimal(str(time_diff))

        return velocity

    def _update_adverse_selection(
        self, market_id: str, fill_price: Decimal, fill_side: str, mid_at_fill: Decimal
    ) -> None:
        """Track adverse selection by comparing fill price to mid price.

        When we get filled, informed traders may be trading against us.
        Track whether the market moves against us after fills.

        Args:
            market_id: Market identifier
            fill_price: Price we got filled at
            fill_side: 'buy' or 'sell' (our action)
            mid_at_fill: Mid price at the time of fill
        """
        now = time.time()

        if market_id not in self._recent_fills_for_adverse:
            self._recent_fills_for_adverse[market_id] = []

        self._recent_fills_for_adverse[market_id].append(
            (now, fill_price, fill_side, mid_at_fill)
        )

        # Keep only recent fills
        self._recent_fills_for_adverse[market_id] = (
            self._recent_fills_for_adverse[market_id][-self._adverse_lookback_fills:]
        )

        # Calculate adverse selection score
        self._recalculate_adverse_selection_score(market_id)

    def _recalculate_adverse_selection_score(self, market_id: str) -> None:
        """Recalculate adverse selection score based on recent fills.

        Score ranges from -1 (bad, we're being picked off) to +1 (good).
        Uses the difference between fill price and mid price at fill time.

        For buys: if fill_price > mid_at_fill, we overpaid (bad)
        For sells: if fill_price < mid_at_fill, we undersold (bad)
        """
        fills = self._recent_fills_for_adverse.get(market_id, [])
        if not fills:
            self._adverse_selection_score[market_id] = 0.0
            return

        # Get current mid price to see how market moved since fills
        book = self._order_books.get(market_id)
        if not book or not book.yes_bids or not book.yes_asks:
            return

        current_mid = (book.yes_bids[0].price.value + book.yes_asks[0].price.value) / 2

        bad_fills = 0
        good_fills = 0

        for fill_time, fill_price, fill_side, mid_at_fill in fills:
            # How did the market move after our fill?
            market_move = current_mid - mid_at_fill

            if fill_side == 'buy':
                # We bought - if market went DOWN after, we lost (adverse)
                if market_move < -Decimal("0.01"):  # Market dropped 1c+
                    bad_fills += 1
                elif market_move > Decimal("0.01"):  # Market rose 1c+
                    good_fills += 1
            else:  # sell
                # We sold - if market went UP after, we lost (adverse)
                if market_move > Decimal("0.01"):  # Market rose 1c+
                    bad_fills += 1
                elif market_move < -Decimal("0.01"):  # Market dropped 1c+
                    good_fills += 1

        total = bad_fills + good_fills
        if total == 0:
            self._adverse_selection_score[market_id] = 0.0
        else:
            # Score: -1 (all bad) to +1 (all good)
            self._adverse_selection_score[market_id] = (good_fills - bad_fills) / total

    def _get_dynamic_spread_multiplier(self, market_id: str) -> Decimal:
        """Calculate dynamic spread multiplier based on market conditions.

        Combines:
        1. Price velocity - widen spread when market moving fast
        2. Adverse selection - widen spread when we're being picked off

        Returns:
            Multiplier (1.0 = normal, up to 3.0 = triple spread)
        """
        multiplier = Decimal("1.0")

        # Factor 1: Price velocity
        velocity = self._calculate_price_velocity(market_id)
        abs_velocity = abs(velocity)

        # If price moving > 2 cents per second, widen spread
        if abs_velocity > Decimal("0.02"):
            # Scale from 1x at 2c/s to 2x at 10c/s
            velocity_factor = Decimal("1.0") + min(
                Decimal("1.0"),
                (abs_velocity - Decimal("0.02")) / Decimal("0.08")
            )
            multiplier *= velocity_factor
            logger.debug(
                f"Velocity factor: {velocity_factor:.2f} (velocity={abs_velocity:.3f}c/s)"
            )

        # Factor 2: Adverse selection
        adverse_score = self._adverse_selection_score.get(market_id, 0.0)
        if adverse_score < -0.3:  # We're losing > 30% of fills
            # Scale from 1x at -0.3 to 1.5x at -1.0
            adverse_factor = Decimal("1.0") + Decimal(str((-adverse_score - 0.3) / 0.7)) * Decimal("0.5")
            multiplier *= adverse_factor
            logger.info(
                f"Adverse selection factor: {adverse_factor:.2f} "
                f"(score={adverse_score:.2f}, widening spread)"
            )

        # Cap at 3x
        multiplier = min(multiplier, Decimal("3.0"))

        self._spread_multiplier[market_id] = multiplier
        return multiplier

    def _calculate_kalshi_maker_fee(self, price: Decimal) -> Decimal:
        """Calculate Kalshi maker fee at a given price.

        Kalshi maker fee formula: 0.0175 × P × (1-P) per contract

        At mid prices (0.50), fee is only ~0.44 cents per contract.
        At extreme prices (0.10 or 0.90), fee is ~0.16 cents.

        We return the actual fee, not rounded, for accurate spread calculations.

        Args:
            price: Price as decimal (0.01 to 0.99)

        Returns:
            Fee per contract in dollars (not rounded)
        """
        MAKER_FEE_RATE = Decimal("0.0175")
        return MAKER_FEE_RATE * price * (1 - price)

    def _calculate_min_profitable_spread(
        self, mid_price: Decimal, market_id: str | None = None
    ) -> Decimal:
        """Calculate minimum spread needed to be profitable after fees.

        For a round-trip trade (buy + sell), we pay fees on both sides.
        Minimum profitable spread = (2 × fee_at_mid + safety_buffer) × dynamic_multiplier

        Args:
            mid_price: Current mid price
            market_id: Market ID for dynamic spread adjustment (optional)

        Returns:
            Minimum spread needed to be profitable
        """
        fee_per_side = self._calculate_kalshi_maker_fee(mid_price)
        round_trip_fees = 2 * fee_per_side

        # Add safety buffer for adverse selection (2 cents base)
        ADVERSE_SELECTION_BUFFER = Decimal("0.02")

        base_min_spread = round_trip_fees + ADVERSE_SELECTION_BUFFER

        # Apply dynamic multiplier based on market conditions
        if market_id:
            multiplier = self._get_dynamic_spread_multiplier(market_id)
            if multiplier > Decimal("1.0"):
                logger.debug(
                    f"Dynamic spread multiplier for {market_id}: {multiplier:.2f}x "
                    f"(base={base_min_spread:.3f}, adjusted={base_min_spread * multiplier:.3f})"
                )
            return base_min_spread * multiplier

        return base_min_spread

    def _clamp_quotes_to_spread(
        self,
        quotes: QuoteSet,
        book: OrderBook,
        market_id: str | None = None,
    ) -> QuoteSet | None:
        """Clamp quotes to stay inside the market spread (MAKER mode).

        To be a market MAKER (provide liquidity), we must:
        - Place bids BELOW the best ask (don't lift the ask)
        - Place asks ABOVE the best bid (don't hit the bid)
        - Ensure our spread is wide enough to cover fees + adverse selection

        Args:
            quotes: Generated quotes from strategy
            book: Current order book
            market_id: Market ID for dynamic spread adjustment

        Returns:
            Adjusted QuoteSet, or None if no valid quotes possible
        """
        if not book.yes_bids or not book.yes_asks:
            return quotes  # Can't check, pass through

        best_bid = book.yes_bids[0].price.value
        best_ask = book.yes_asks[0].price.value
        market_spread = best_ask - best_bid

        # Minimum price increment (1 cent = 0.01)
        tick = Decimal("0.01")

        # Calculate fee-aware minimum spread (with dynamic adjustment)
        mid_price = (best_bid + best_ask) / 2
        min_profitable_spread = self._calculate_min_profitable_spread(mid_price, market_id)

        # Our edge buffer should be at least half the min profitable spread
        # This ensures our quotes are far enough apart to be profitable
        EDGE_BUFFER = max(min_profitable_spread / 2, 2 * tick)

        yes_quote = quotes.yes_quote

        # Price bounds
        MIN_PRICE = Decimal("0.01")
        MAX_PRICE = Decimal("0.99")

        # Log the book state and fee info
        fee_at_mid = self._calculate_kalshi_maker_fee(mid_price)
        logger.debug(
            f"Book: bid={best_bid:.2f}, ask={best_ask:.2f}, spread={market_spread:.2f}, "
            f"fee_at_mid=${fee_at_mid:.4f}, min_profitable_spread={min_profitable_spread:.2f}"
        )

        # Check if market spread is too tight to be profitable
        # We need room to place our quotes inside the spread AND still be profitable
        if market_spread < min_profitable_spread:
            logger.info(
                f"Market spread ({market_spread:.2f}) < min profitable ({min_profitable_spread:.2f}), "
                f"skipping quotes (fee=${fee_at_mid:.3f}/side)"
            )
            return None

        # ALWAYS stay at least EDGE_BUFFER away from the opposite side
        max_bid = best_ask - EDGE_BUFFER  # Our bid must be below best ask by buffer
        min_ask = best_bid + EDGE_BUFFER  # Our ask must be above best bid by buffer

        clamped_bid = yes_quote.bid_price.value
        if clamped_bid > max_bid:
            clamped_bid = max(MIN_PRICE, max_bid)
            logger.info(
                f"Clamped bid from {yes_quote.bid_price.value:.2f} to {clamped_bid:.2f} "
                f"(max_bid={max_bid:.2f}, best_ask={best_ask:.2f}) for wider spread"
            )

        clamped_ask = yes_quote.ask_price.value
        if clamped_ask < min_ask:
            clamped_ask = min(MAX_PRICE, min_ask)
            logger.info(
                f"Clamped ask from {yes_quote.ask_price.value:.2f} to {clamped_ask:.2f} "
                f"(min_ask={min_ask:.2f}, best_bid={best_bid:.2f}) for wider spread"
            )

        # Check if our final spread is profitable
        our_spread = clamped_ask - clamped_bid
        if our_spread < min_profitable_spread:
            logger.info(
                f"Our spread ({our_spread:.2f}) < min profitable ({min_profitable_spread:.2f}), "
                f"skipping quotes"
            )
            return None

        # Ensure bid < ask after clamping
        if clamped_bid >= clamped_ask:
            logger.info(
                f"After clamping, bid >= ask ({clamped_bid:.2f} >= {clamped_ask:.2f}), "
                f"market spread too tight"
            )
            return None

        # Create adjusted quote
        adjusted_yes_quote = Quote(
            bid_price=Price(clamped_bid),
            bid_size=yes_quote.bid_size,
            ask_price=Price(clamped_ask),
            ask_size=yes_quote.ask_size,
        )

        return QuoteSet(
            market_id=quotes.market_id,
            yes_quote=adjusted_yes_quote,
            timestamp=quotes.timestamp,
        )

    def _adjust_quotes_for_inventory(
        self,
        quotes: QuoteSet,
        book: OrderBook,
        inventory: int,
        max_inventory: int,
    ) -> QuoteSet | None:
        """Adjust quotes to actively reduce inventory.

        When inventory builds up:
        - Long inventory: tighten the ask to sell faster
        - Short inventory: tighten the bid to buy faster

        When at inventory limits:
        - Only quote the side that reduces inventory
        - Skip the side that would increase inventory

        Args:
            quotes: Quotes after clamping
            book: Current order book
            inventory: Current net inventory
            max_inventory: Maximum allowed inventory

        Returns:
            Adjusted quotes, or None if should skip entirely
        """
        if not book.yes_bids or not book.yes_asks:
            return quotes

        market_id = quotes.market_id

        # Check for synchronous inventory blocks (set immediately on fill)
        # This catches the case where fills pushed us over limit before this quote cycle
        inventory_blocked = getattr(self, '_inventory_blocked', {})
        block_status = inventory_blocked.get(market_id)

        yes_quote = quotes.yes_quote
        best_bid = book.yes_bids[0].price.value
        best_ask = book.yes_asks[0].price.value

        # Start with current quote prices
        new_bid = yes_quote.bid_price.value
        new_ask = yes_quote.ask_price.value
        bid_size = yes_quote.bid_size.value
        ask_size = yes_quote.ask_size.value

        # Calculate how aggressive to be based on inventory level
        inv_ratio = abs(inventory) / max_inventory if max_inventory > 0 else 0
        tick = Decimal("0.01")

        # AGGRESSIVE INVENTORY REDUCTION
        # When inventory is building, tighten the reducing side
        if inventory > 0:
            # Long inventory - be more aggressive selling (lower ask)
            # Move ask closer to best bid to get filled faster
            # Reduced from 3c to 1c to avoid being pushed to unprofitable prices
            aggression = Decimal(str(inv_ratio)) * Decimal("0.01")  # Up to 1c tighter
            new_ask = max(new_ask - aggression, best_bid + 2 * tick)
            logger.debug(f"Inventory reduction: long {inventory}, tightening ask by {aggression:.2f}")

        elif inventory < 0:
            # Short inventory - be more aggressive buying (higher bid)
            # Move bid closer to best ask to get filled faster
            # Reduced from 3c to 1c to avoid being pushed to unprofitable prices
            aggression = Decimal(str(inv_ratio)) * Decimal("0.01")  # Up to 1c tighter
            new_bid = min(new_bid + aggression, best_ask - 2 * tick)
            logger.debug(f"Inventory reduction: short {inventory}, tightening bid by {aggression:.2f}")

        # ONE-SIDED QUOTING AT LIMITS
        # When at max inventory, only quote the reducing side
        skip_bid = False
        skip_ask = False

        # Check synchronous inventory blocks (set immediately on fill, before this quote cycle)
        if block_status == "long":
            skip_bid = True
            logger.info(f"BLOCKED: Long inventory block active, skipping bid")
        elif block_status == "short":
            skip_ask = True
            logger.info(f"BLOCKED: Short inventory block active, skipping ask")

        # Also check current inventory (may have been updated since block was set)
        if inventory >= max_inventory:
            # At max long - don't place bids (would increase long)
            skip_bid = True
            logger.info(f"At max long inventory ({inventory}), skipping bid")

        if inventory <= -max_inventory:
            # At max short - don't place asks (would increase short)
            skip_ask = True
            logger.info(f"At max short inventory ({inventory}), skipping ask")

        # If we need to skip both sides, return None
        if skip_bid and skip_ask:
            return None

        # If skipping one side, we still need valid sizes for Quote
        # Set the skipped side's price to an unfillable level
        MIN_PRICE = Decimal("0.01")
        MAX_PRICE = Decimal("0.99")

        if skip_bid:
            new_bid = MIN_PRICE  # Won't get filled at 1 cent
            bid_size = 1  # Min size, but at unfillable price

        if skip_ask:
            new_ask = MAX_PRICE  # Won't get filled at 99 cents
            ask_size = 1  # Min size, but at unfillable price

        # If we need to skip both sides, return None
        if skip_bid and skip_ask:
            logger.debug("Skipping both sides due to inventory limits")
            return None

        # Ensure bid < ask
        if new_bid >= new_ask:
            logger.debug(f"After inventory adjustment, bid >= ask ({new_bid:.2f} >= {new_ask:.2f})")
            return None

        adjusted_yes_quote = Quote(
            bid_price=Price(new_bid),
            bid_size=Quantity(bid_size),
            ask_price=Price(new_ask),
            ask_size=Quantity(ask_size),
        )

        return QuoteSet(
            market_id=quotes.market_id,
            yes_quote=adjusted_yes_quote,
            timestamp=quotes.timestamp,
        )

    def _get_base_size(self) -> int:
        """Get base order size from config."""
        sizer_params = self._config.strategy.components.sizer.params
        return int(sizer_params.get("base_size", 10))

    async def _fetch_market_settlement_time(self, ticker: str) -> None:
        """Fetch market settlement time from exchange.

        Args:
            ticker: Market ticker to fetch
        """
        if not self._exchange:
            return

        try:
            # Get the REST client from the adapter
            from market_maker.exchange.kalshi.adapter import KalshiExchangeAdapter
            if isinstance(self._exchange, KalshiExchangeAdapter):
                market_data = await self._exchange._rest.get_market(ticker)
                market_info = market_data.get("market", {})
                close_time_str = market_info.get("close_time")
                if close_time_str:
                    # Parse ISO format close time
                    close_time = datetime.fromisoformat(
                        close_time_str.replace("Z", "+00:00")
                    )
                    self._market_settlement_times[ticker] = close_time
                    logger.info(
                        f"Fetched settlement time for {ticker}: "
                        f"{close_time.isoformat()}"
                    )
        except Exception as e:
            logger.warning(f"Failed to fetch settlement time for {ticker}: {e}")

    def _get_time_to_settlement_hours(self, market: object) -> float:
        """Calculate time to settlement in hours."""
        from market_maker.core.config import MarketConfig

        ticker = None
        if isinstance(market, MarketConfig):
            ticker = market.ticker
        elif isinstance(market, str):
            ticker = market

        # First check fetched settlement times from exchange
        if ticker and ticker in self._market_settlement_times:
            settlement = self._market_settlement_times[ticker]
            now = datetime.now(UTC)
            delta = settlement - now
            hours = max(delta.total_seconds() / 3600.0, 0.0)
            return hours

        # Fall back to config if available
        if isinstance(market, MarketConfig) and market.settlement_time:
            settlement = datetime.fromisoformat(market.settlement_time)
            if settlement.tzinfo is None:
                settlement = settlement.replace(tzinfo=UTC)
            now = datetime.now(UTC)
            delta = settlement - now
            hours = max(delta.total_seconds() / 3600.0, 0.0)
            return hours

        # Default to 1 hour if not specified
        return 1.0

    def _build_risk_context(
        self,
        market_id: str,
        book: OrderBook,
        position: Position,
    ) -> RiskContext:
        """Build risk context for risk checks."""
        # Get pending exposure from resting orders
        pending_bids = 0
        pending_asks = 0
        if self._execution and hasattr(self._execution, 'get_pending_exposure'):
            pending_bids, pending_asks = self._execution.get_pending_exposure(market_id)

        # Calculate time to settlement (uses fetched exchange data or config)
        time_to_settlement = self._get_time_to_settlement_hours(market_id)

        if not self._state:
            return RiskContext(
                current_inventory=0,
                max_inventory=self._config.strategy.max_inventory,
                positions={},
                realized_pnl=Decimal("0"),
                unrealized_pnl=Decimal("0"),
                hourly_pnl=Decimal("0"),
                daily_pnl=Decimal("0"),
                time_to_settlement=time_to_settlement,
                current_volatility=Decimal("0.05"),
                order_book=book,
                pending_bid_exposure=pending_bids,
                pending_ask_exposure=pending_asks,
            )

        # Get mid price for unrealized PnL
        mid_price = self._get_mid_price(book) or Price(Decimal("0.5"))

        return RiskContext(
            current_inventory=position.net_inventory(),
            max_inventory=self._config.strategy.max_inventory,
            positions=dict(self._state.positions),
            realized_pnl=self._state.realized_pnl,
            unrealized_pnl=self._state.calculate_unrealized_pnl(
                market_id, mid_price
            ),
            hourly_pnl=self._state.hourly_pnl,
            daily_pnl=self._state.daily_pnl,
            time_to_settlement=time_to_settlement,
            current_volatility=Decimal("0.05"),
            order_book=book,
            pending_bid_exposure=pending_bids,
            pending_ask_exposure=pending_asks,
        )

    async def _execute_quotes(
        self,
        _market_id: str,  # Unused but kept for future live execution
        book: OrderBook,
        quotes: QuoteSet,
    ) -> None:
        """Execute quotes through the execution engine."""
        if not self._execution:
            return

        self._quote_count += 1

        # Handle both sync (paper) and async (live) execution
        if isinstance(self._execution, LiveExecutionEngine):
            # Live execution is async
            fills = await self._execution.execute_quotes(quotes, book)
        else:
            # Paper execution is sync
            fills = self._execution.execute_quotes(quotes, book)

        for fill in fills:
            self._fill_count += 1
            self._fills.append(fill)

            if self._state:
                self._state.apply_fill(fill)

            # Persist fill to database
            if self._repository:
                self._repository.save_fill(fill)

            logger.info(
                f"Paper fill #{self._fill_count}: {fill.order_side.value} "
                f"{fill.size.value} {fill.side.value} @ {fill.price.value:.2f}"
            )

    async def _reconciliation_loop(self) -> None:
        """Periodically reconcile local state with exchange."""
        interval = self._config.reconciliation_interval_seconds

        while self._running:
            await asyncio.sleep(interval)

            try:
                await self._reconcile_positions()
            except Exception as e:
                logger.error(f"Error in reconciliation: {e}")

    async def _reconcile_positions(self) -> None:
        """Reconcile local positions with exchange.

        If exchange position differs from local, update local to match exchange
        (exchange is the source of truth).
        """
        if not self._exchange or not self._state:
            return

        exchange_positions = await self._exchange.get_positions()

        for position in exchange_positions:
            local_position = self._state.get_position(position.market_id)

            if local_position is None:
                # No local position - adopt exchange position
                logger.warning(
                    f"Exchange has position for {position.market_id} "
                    f"but no local position - syncing from exchange: "
                    f"yes={position.yes_quantity}, no={position.no_quantity}"
                )
                self._state.set_position(position)
                continue

            if (
                local_position.yes_quantity != position.yes_quantity
                or local_position.no_quantity != position.no_quantity
            ):
                logger.warning(
                    f"Position mismatch for {position.market_id}: "
                    f"local={local_position.net_inventory()}, "
                    f"exchange={position.net_inventory()} - syncing from exchange"
                )
                # Update local position to match exchange (exchange is source of truth)
                self._state.set_position(position)

    async def _pnl_logging_loop(self) -> None:
        """Periodically log PnL summary."""
        interval = 30.0  # Log every 30 seconds
        logger.info("PnL logging started (every 30s)")

        while self._running:
            await asyncio.sleep(interval)

            try:
                self._log_pnl_summary()
            except Exception as e:
                logger.error(f"Error logging PnL: {e}")

    def _log_pnl_summary(self) -> None:
        """Log current PnL summary."""
        if not self._state:
            return

        # Calculate total unrealized PnL across all markets
        total_unrealized = Decimal("0")
        for market in self._config.markets:
            market_id = market.ticker
            book = self._order_books.get(market_id)
            if book:
                mid_price = self._get_mid_price(book) or Price(Decimal("0.5"))
                total_unrealized += self._state.calculate_unrealized_pnl(
                    market_id, mid_price
                )

        realized = self._state.realized_pnl
        total = realized + total_unrealized
        fees = self._state.total_fees

        # Runtime
        runtime = datetime.now(UTC) - self._start_time
        runtime_str = str(runtime).split(".")[0]  # Remove microseconds

        # Show fees in cents for better precision (0.43c instead of $0.00)
        fees_cents = fees * 100
        logger.info(
            f"[PnL] realized=${realized:.2f}, unrealized=${total_unrealized:.2f}, "
            f"total=${total:.2f}, fees={fees_cents:.1f}¢ | "
            f"fills={self._fill_count}, quotes={self._quote_count}, runtime={runtime_str}"
        )

    async def _shutdown(self) -> None:
        """Shut down the trading controller."""
        logger.info("Shutting down trading controller")

        self._running = False

        # Cancel background tasks
        if self._quote_task:
            self._quote_task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._quote_task

        if self._reconcile_task:
            self._reconcile_task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._reconcile_task

        if self._pnl_log_task:
            self._pnl_log_task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._pnl_log_task

        if self._api_task:
            self._api_task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._api_task

        # Disconnect from exchange
        if self._exchange:
            # Cancel all orders first
            try:
                for market in self._config.markets:
                    if hasattr(self._exchange, "cancel_all_orders"):
                        await self._exchange.cancel_all_orders(market.ticker)
            except Exception as e:
                logger.error(f"Error cancelling orders: {e}")

            await self._exchange.disconnect()

        # Print final summary
        self._print_session_summary()

        # Close repository
        if self._repository:
            self._repository.close()

        logger.info("Trading controller shut down complete")

    def _print_session_summary(self) -> None:
        """Print final session summary."""
        runtime = datetime.now(UTC) - self._start_time
        runtime_str = str(runtime).split(".")[0]

        logger.info("=" * 60)
        logger.info("SESSION SUMMARY")
        logger.info("=" * 60)
        logger.info(f"Session ID: {self._session_id}")
        logger.info(f"Runtime: {runtime_str}")
        logger.info(f"Total Quotes: {self._quote_count}")
        logger.info(f"Total Fills: {self._fill_count}")

        if self._state:
            # Calculate final PnL
            total_unrealized = Decimal("0")
            for market in self._config.markets:
                market_id = market.ticker
                book = self._order_books.get(market_id)
                position = self._state.get_position(market_id)

                if book and position:
                    mid_price = self._get_mid_price(book) or Price(Decimal("0.5"))
                    unrealized = self._state.calculate_unrealized_pnl(market_id, mid_price)
                    total_unrealized += unrealized

                    logger.info(
                        f"  {market_id}: YES={position.yes_quantity}, "
                        f"NO={position.no_quantity}, net={position.net_inventory()}"
                    )

            realized = self._state.realized_pnl
            total = realized + total_unrealized
            fees = self._state.total_fees

            fees_cents = fees * 100
            logger.info("-" * 60)
            logger.info(f"Realized PnL:   ${realized:>10.2f}")
            logger.info(f"Unrealized PnL: ${total_unrealized:>10.2f}")
            logger.info(f"Total PnL:      ${total:>10.2f}")
            logger.info(f"Total Fees:     {fees_cents:>10.1f}¢ (${fees:.4f})")
            logger.info(f"Net PnL:        ${total - fees:>10.2f}")
            logger.info("=" * 60)

        if self._repository:
            logger.info(f"Fills persisted to: trading.db (session: {self._session_id})")


def _convert_params(params: dict[str, object]) -> dict[str, str]:
    """Convert parameter dict values to strings for factory."""
    return {k: str(v) for k, v in params.items()}
