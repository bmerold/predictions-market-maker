"""Types for backtest module."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal

from market_maker.domain.market_data import OrderBook
from market_maker.domain.orders import Fill
from market_maker.domain.types import Side


@dataclass(frozen=True)
class RecordingMetadata:
    """Metadata about a recorded market session.

    Attributes:
        market_ticker: Full market ticker (e.g., KXBTCD-25DEC1516-T86249.99)
        event_ticker: Event ticker (e.g., KXBTCD-25DEC1516)
        recording_started: When recording began
        recording_ended: When recording ended
        market_close_time: When the market closes/settles
        tick_interval_ms: Milliseconds between ticks
        orderbook_depth: Number of price levels recorded
        settlement: How the market settled (YES or NO), if known
        file_path: Path to the recording file
    """

    market_ticker: str
    event_ticker: str
    recording_started: datetime
    recording_ended: datetime
    market_close_time: datetime
    tick_interval_ms: int
    orderbook_depth: int
    settlement: Side | None
    file_path: str


@dataclass(frozen=True)
class Tick:
    """A single tick from a recorded session.

    Attributes:
        timestamp: When this tick occurred
        tick_number: Sequential tick number
        time_to_close_seconds: Seconds remaining until market close
        order_book: Full order book snapshot
    """

    timestamp: datetime
    tick_number: int
    time_to_close_seconds: float
    order_book: OrderBook


@dataclass(frozen=True)
class BacktestResult:
    """Results from a backtest run.

    Attributes:
        metadata: Recording metadata
        total_ticks: Number of ticks processed
        total_fills: Number of fills executed
        fills: List of all fills
        final_yes_position: Final YES position quantity
        final_no_position: Final NO position quantity
        realized_pnl: Total realized PnL
        unrealized_pnl: Unrealized PnL at end (mark-to-market)
        total_pnl: Realized + unrealized PnL
        total_fees: Total fees paid
        settlement_pnl: PnL from settlement (if settled)
        max_drawdown: Maximum drawdown during backtest
        quotes_generated: Total number of quote sets generated
        quotes_blocked: Number of quotes blocked by risk rules
    """

    metadata: RecordingMetadata
    total_ticks: int
    total_fills: int
    fills: list[Fill]
    final_yes_position: int
    final_no_position: int
    realized_pnl: Decimal
    unrealized_pnl: Decimal
    total_pnl: Decimal
    total_fees: Decimal
    settlement_pnl: Decimal
    max_drawdown: Decimal
    quotes_generated: int
    quotes_blocked: int

    @property
    def net_position(self) -> int:
        """Net position (YES - NO)."""
        return self.final_yes_position - self.final_no_position

    @property
    def fill_rate(self) -> float:
        """Percentage of quotes that resulted in fills."""
        if self.quotes_generated == 0:
            return 0.0
        return self.total_fills / self.quotes_generated

    @property
    def block_rate(self) -> float:
        """Percentage of quotes blocked by risk rules."""
        if self.quotes_generated == 0:
            return 0.0
        return self.quotes_blocked / self.quotes_generated
