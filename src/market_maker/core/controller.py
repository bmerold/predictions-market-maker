"""Trading controller - main application loop.

Orchestrates the market data, strategy, risk, and execution components.
"""

from __future__ import annotations

import asyncio
import contextlib
import logging
import os
import signal
from datetime import UTC, datetime
from decimal import Decimal
from typing import TYPE_CHECKING

from market_maker.core.config import ExchangeType, ExecutionMode, TradingConfig
from market_maker.db.repository import TradingRepository
from market_maker.domain.events import BookUpdate, Event, EventType, FillEvent
from market_maker.domain.orders import Fill
from market_maker.domain.market_data import OrderBook
from market_maker.domain.orders import QuoteSet
from market_maker.domain.positions import Position
from market_maker.domain.types import Price
from market_maker.exchange.base import ExchangeAdapter
from market_maker.exchange.kalshi import KalshiExchangeAdapter
from market_maker.exchange.kalshi.auth import KalshiCredentials
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
        self._last_quote_time: dict[str, datetime] = {}

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

            # Subscribe to markets
            for market in self._config.markets:
                await self._exchange.subscribe_market(market.ticker)
                self._book_builders[market.ticker] = OrderBookBuilder(market.ticker)

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

        # Create state store
        self._state = StateStore()

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
            return PaperExecutionEngine()
        else:
            # Live execution would go here
            # For now, default to paper
            logger.warning("Live execution not implemented, using paper")
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

    def _handle_fill(self, event: FillEvent) -> None:
        """Handle a fill event.

        Args:
            event: Fill event
        """
        fill = event.fill
        self._fill_count += 1
        self._fills.append(fill)

        if self._state:
            self._state.apply_fill(fill)

        # Persist fill to database
        if self._repository:
            self._repository.save_fill(fill)

        logger.info(
            f"Fill #{self._fill_count}: {fill.order_side.value} {fill.size.value} "
            f"{fill.side.value} @ {fill.price.value:.2f} on {fill.market_id}"
        )

    async def _quote_loop(self) -> None:
        """Main quoting loop - generates and executes quotes."""
        interval = self._config.quote_interval_ms / 1000.0
        logger.info(f"Quote loop started, interval: {interval}s")

        while self._running:
            try:
                await self._generate_and_execute_quotes()
            except Exception as e:
                logger.error(f"Error in quote loop: {e}", exc_info=True)

            await asyncio.sleep(interval)

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

                # Check with risk manager
                if self._risk_manager and self._state:
                    context = self._build_risk_context(market_id, book, position)
                    decision = self._risk_manager.evaluate(quotes, context)
                    if decision.action.name == "BLOCK":
                        logger.debug(f"Quotes blocked: {decision.reason}")
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

    def _get_base_size(self) -> int:
        """Get base order size from config."""
        sizer_params = self._config.strategy.components.sizer.params
        return int(sizer_params.get("base_size", 10))

    def _get_time_to_settlement_hours(self, market: object) -> float:
        """Calculate time to settlement in hours."""
        from market_maker.core.config import MarketConfig

        if not isinstance(market, MarketConfig):
            return 1.0

        if market.settlement_time:
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
        if not self._state:
            return RiskContext(
                current_inventory=0,
                max_inventory=self._config.strategy.max_inventory,
                positions={},
                realized_pnl=Decimal("0"),
                unrealized_pnl=Decimal("0"),
                hourly_pnl=Decimal("0"),
                daily_pnl=Decimal("0"),
                time_to_settlement=1.0,
                current_volatility=Decimal("0.05"),
                order_book=book,
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
            time_to_settlement=1.0,
            current_volatility=Decimal("0.05"),
            order_book=book,
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

        # For paper trading, we simulate fills against the book
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
        """Reconcile local positions with exchange."""
        if not self._exchange or not self._state:
            return

        exchange_positions = await self._exchange.get_positions()

        for position in exchange_positions:
            local_position = self._state.get_position(position.market_id)

            if local_position is None:
                logger.warning(
                    f"Exchange has position for {position.market_id} "
                    f"but no local position"
                )
                continue

            if (
                local_position.yes_quantity != position.yes_quantity
                or local_position.no_quantity != position.no_quantity
            ):
                logger.warning(
                    f"Position mismatch for {position.market_id}: "
                    f"local={local_position.net_inventory()}, "
                    f"exchange={position.net_inventory()}"
                )

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

        logger.info(
            f"[PnL] realized=${realized:.2f}, unrealized=${total_unrealized:.2f}, "
            f"total=${total:.2f}, fees=${fees:.2f} | "
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

            logger.info("-" * 60)
            logger.info(f"Realized PnL:   ${realized:>10.2f}")
            logger.info(f"Unrealized PnL: ${total_unrealized:>10.2f}")
            logger.info(f"Total PnL:      ${total:>10.2f}")
            logger.info(f"Total Fees:     ${fees:>10.2f}")
            logger.info(f"Net PnL:        ${total - fees:>10.2f}")
            logger.info("=" * 60)

        if self._repository:
            logger.info(f"Fills persisted to: trading.db (session: {self._session_id})")


def _convert_params(params: dict[str, object]) -> dict[str, str]:
    """Convert parameter dict values to strings for factory."""
    return {k: str(v) for k, v in params.items()}
