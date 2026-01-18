"""Prometheus metrics for market maker monitoring.

Provides metrics for:
- Trading performance (PnL, fills, orders)
- System health (latency, errors, uptime)
- Market data (spreads, book depth)
"""

from __future__ import annotations

import logging
import time
from contextlib import contextmanager
from typing import TYPE_CHECKING, Any, Generator

logger = logging.getLogger(__name__)

# Try to import prometheus_client, fall back to no-op if not available
try:
    from prometheus_client import (
        Counter,
        Gauge,
        Histogram,
        Info,
        generate_latest,
    )

    PROMETHEUS_AVAILABLE = True
except ImportError:
    PROMETHEUS_AVAILABLE = False


class MetricsCollector:
    """Collects and exposes Prometheus metrics.

    Provides trading and system metrics for monitoring dashboards.
    Falls back to no-op if prometheus_client is not installed.
    """

    def __init__(self, prefix: str = "market_maker") -> None:
        """Initialize metrics collector.

        Args:
            prefix: Metric name prefix
        """
        self._prefix = prefix
        self._enabled = PROMETHEUS_AVAILABLE

        if not self._enabled:
            logger.warning("prometheus_client not installed, metrics disabled")
            return

        # Info metrics
        self._info = Info(
            f"{prefix}_info",
            "Market maker information",
        )

        # Trading metrics
        self._orders_placed = Counter(
            f"{prefix}_orders_placed_total",
            "Total orders placed",
            ["market_id", "side", "order_side"],
        )

        self._orders_cancelled = Counter(
            f"{prefix}_orders_cancelled_total",
            "Total orders cancelled",
            ["market_id"],
        )

        self._orders_filled = Counter(
            f"{prefix}_orders_filled_total",
            "Total orders filled",
            ["market_id", "side", "order_side"],
        )

        self._fill_volume = Counter(
            f"{prefix}_fill_volume_total",
            "Total fill volume in contracts",
            ["market_id", "side"],
        )

        self._fill_notional = Counter(
            f"{prefix}_fill_notional_total",
            "Total fill notional value",
            ["market_id", "side"],
        )

        # Position metrics
        self._yes_position = Gauge(
            f"{prefix}_yes_position",
            "Current YES position",
            ["market_id"],
        )

        self._no_position = Gauge(
            f"{prefix}_no_position",
            "Current NO position",
            ["market_id"],
        )

        self._net_inventory = Gauge(
            f"{prefix}_net_inventory",
            "Net inventory (YES - NO)",
            ["market_id"],
        )

        # PnL metrics
        self._realized_pnl = Gauge(
            f"{prefix}_realized_pnl",
            "Realized PnL",
            ["market_id"],
        )

        self._unrealized_pnl = Gauge(
            f"{prefix}_unrealized_pnl",
            "Unrealized PnL",
            ["market_id"],
        )

        self._total_pnl = Gauge(
            f"{prefix}_total_pnl",
            "Total PnL (realized + unrealized)",
            ["market_id"],
        )

        # Market data metrics
        self._bid_ask_spread = Gauge(
            f"{prefix}_bid_ask_spread",
            "Current bid-ask spread",
            ["market_id"],
        )

        self._book_imbalance = Gauge(
            f"{prefix}_book_imbalance",
            "Order book imbalance (bid_size - ask_size) / total",
            ["market_id"],
        )

        self._mid_price = Gauge(
            f"{prefix}_mid_price",
            "Current mid price",
            ["market_id"],
        )

        # Quote metrics
        self._quotes_generated = Counter(
            f"{prefix}_quotes_generated_total",
            "Total quotes generated",
            ["market_id"],
        )

        self._quote_spread = Gauge(
            f"{prefix}_quote_spread",
            "Current quote spread",
            ["market_id"],
        )

        # Risk metrics
        self._risk_checks = Counter(
            f"{prefix}_risk_checks_total",
            "Total risk checks performed",
            ["result"],
        )

        self._kill_switch_active = Gauge(
            f"{prefix}_kill_switch_active",
            "Kill switch status (1=active, 0=inactive)",
        )

        # Latency metrics
        self._quote_latency = Histogram(
            f"{prefix}_quote_latency_seconds",
            "Quote generation latency",
            ["market_id"],
            buckets=[0.001, 0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0],
        )

        self._order_latency = Histogram(
            f"{prefix}_order_latency_seconds",
            "Order placement latency",
            ["market_id"],
            buckets=[0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0],
        )

        self._ws_message_latency = Histogram(
            f"{prefix}_ws_message_latency_seconds",
            "WebSocket message processing latency",
            buckets=[0.0001, 0.0005, 0.001, 0.005, 0.01, 0.05, 0.1],
        )

        # Error metrics
        self._errors = Counter(
            f"{prefix}_errors_total",
            "Total errors",
            ["error_type"],
        )

        # Connection metrics
        self._ws_connected = Gauge(
            f"{prefix}_ws_connected",
            "WebSocket connection status (1=connected, 0=disconnected)",
        )

        self._ws_reconnects = Counter(
            f"{prefix}_ws_reconnects_total",
            "Total WebSocket reconnections",
        )

    @property
    def enabled(self) -> bool:
        """Check if metrics are enabled."""
        return self._enabled

    def set_info(self, **kwargs: str) -> None:
        """Set info metric values."""
        if self._enabled:
            self._info.info(kwargs)

    # --- Order Metrics ---

    def inc_orders_placed(
        self, market_id: str, side: str, order_side: str
    ) -> None:
        """Increment orders placed counter."""
        if self._enabled:
            self._orders_placed.labels(
                market_id=market_id, side=side, order_side=order_side
            ).inc()

    def inc_orders_cancelled(self, market_id: str) -> None:
        """Increment orders cancelled counter."""
        if self._enabled:
            self._orders_cancelled.labels(market_id=market_id).inc()

    def inc_orders_filled(
        self, market_id: str, side: str, order_side: str
    ) -> None:
        """Increment orders filled counter."""
        if self._enabled:
            self._orders_filled.labels(
                market_id=market_id, side=side, order_side=order_side
            ).inc()

    def add_fill_volume(self, market_id: str, side: str, volume: int) -> None:
        """Add to fill volume counter."""
        if self._enabled:
            self._fill_volume.labels(market_id=market_id, side=side).inc(volume)

    def add_fill_notional(
        self, market_id: str, side: str, notional: float
    ) -> None:
        """Add to fill notional counter."""
        if self._enabled:
            self._fill_notional.labels(market_id=market_id, side=side).inc(notional)

    # --- Position Metrics ---

    def set_position(
        self, market_id: str, yes_qty: int, no_qty: int
    ) -> None:
        """Update position gauges."""
        if self._enabled:
            self._yes_position.labels(market_id=market_id).set(yes_qty)
            self._no_position.labels(market_id=market_id).set(no_qty)
            self._net_inventory.labels(market_id=market_id).set(yes_qty - no_qty)

    # --- PnL Metrics ---

    def set_pnl(
        self,
        market_id: str,
        realized: float,
        unrealized: float,
        total: float,
    ) -> None:
        """Update PnL gauges."""
        if self._enabled:
            self._realized_pnl.labels(market_id=market_id).set(realized)
            self._unrealized_pnl.labels(market_id=market_id).set(unrealized)
            self._total_pnl.labels(market_id=market_id).set(total)

    # --- Market Data Metrics ---

    def set_market_data(
        self,
        market_id: str,
        spread: float,
        mid_price: float,
        imbalance: float,
    ) -> None:
        """Update market data gauges."""
        if self._enabled:
            self._bid_ask_spread.labels(market_id=market_id).set(spread)
            self._mid_price.labels(market_id=market_id).set(mid_price)
            self._book_imbalance.labels(market_id=market_id).set(imbalance)

    # --- Quote Metrics ---

    def inc_quotes_generated(self, market_id: str) -> None:
        """Increment quotes generated counter."""
        if self._enabled:
            self._quotes_generated.labels(market_id=market_id).inc()

    def set_quote_spread(self, market_id: str, spread: float) -> None:
        """Update quote spread gauge."""
        if self._enabled:
            self._quote_spread.labels(market_id=market_id).set(spread)

    # --- Risk Metrics ---

    def inc_risk_check(self, result: str) -> None:
        """Increment risk check counter."""
        if self._enabled:
            self._risk_checks.labels(result=result).inc()

    def set_kill_switch(self, active: bool) -> None:
        """Update kill switch gauge."""
        if self._enabled:
            self._kill_switch_active.set(1 if active else 0)

    # --- Latency Metrics ---

    def observe_quote_latency(self, market_id: str, seconds: float) -> None:
        """Record quote generation latency."""
        if self._enabled:
            self._quote_latency.labels(market_id=market_id).observe(seconds)

    def observe_order_latency(self, market_id: str, seconds: float) -> None:
        """Record order placement latency."""
        if self._enabled:
            self._order_latency.labels(market_id=market_id).observe(seconds)

    def observe_ws_message_latency(self, seconds: float) -> None:
        """Record WebSocket message latency."""
        if self._enabled:
            self._ws_message_latency.observe(seconds)

    @contextmanager
    def time_quote(self, market_id: str) -> Generator[None, None, None]:
        """Context manager to time quote generation."""
        start = time.perf_counter()
        try:
            yield
        finally:
            self.observe_quote_latency(market_id, time.perf_counter() - start)

    @contextmanager
    def time_order(self, market_id: str) -> Generator[None, None, None]:
        """Context manager to time order placement."""
        start = time.perf_counter()
        try:
            yield
        finally:
            self.observe_order_latency(market_id, time.perf_counter() - start)

    # --- Error Metrics ---

    def inc_error(self, error_type: str) -> None:
        """Increment error counter."""
        if self._enabled:
            self._errors.labels(error_type=error_type).inc()

    # --- Connection Metrics ---

    def set_ws_connected(self, connected: bool) -> None:
        """Update WebSocket connection status."""
        if self._enabled:
            self._ws_connected.set(1 if connected else 0)

    def inc_ws_reconnects(self) -> None:
        """Increment WebSocket reconnection counter."""
        if self._enabled:
            self._ws_reconnects.inc()

    # --- Export ---

    def get_metrics(self) -> bytes:
        """Get metrics in Prometheus format.

        Returns:
            Metrics as bytes in Prometheus exposition format
        """
        if self._enabled:
            return generate_latest()
        return b""


# Global metrics collector instance
_metrics: MetricsCollector | None = None


def get_metrics() -> MetricsCollector:
    """Get global metrics collector.

    Returns:
        Global MetricsCollector instance
    """
    global _metrics
    if _metrics is None:
        _metrics = MetricsCollector()
    return _metrics


def init_metrics(prefix: str = "market_maker") -> MetricsCollector:
    """Initialize global metrics collector.

    Args:
        prefix: Metric name prefix

    Returns:
        Initialized MetricsCollector
    """
    global _metrics
    _metrics = MetricsCollector(prefix=prefix)
    return _metrics
