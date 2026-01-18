"""Kalshi exchange adapter.

Full implementation of ExchangeAdapter for Kalshi.
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from typing import Any

from market_maker.domain.events import Event
from market_maker.domain.market_data import OrderBook
from market_maker.domain.orders import Order, OrderRequest
from market_maker.domain.positions import Balance, Position
from market_maker.exchange.base import ExchangeAdapter, ExchangeCapabilities
from market_maker.exchange.kalshi.auth import KalshiAuth, KalshiCredentials
from market_maker.exchange.kalshi.normalizer import KalshiNormalizer
from market_maker.exchange.kalshi.rate_limiter import (
    RateLimiter,
    create_kalshi_rate_limiters,
)
from market_maker.exchange.kalshi.rest import KalshiRestClient
from market_maker.exchange.kalshi.websocket import KalshiWebSocketClient

logger = logging.getLogger(__name__)


class KalshiExchangeAdapter(ExchangeAdapter):
    """Kalshi exchange adapter.

    Provides a unified interface to Kalshi's REST and WebSocket APIs.

    Features:
    - Automatic authentication and token refresh
    - WebSocket connection with auto-reconnect
    - Rate limiting for API calls
    - Data normalization to domain models
    """

    def __init__(
        self,
        credentials: KalshiCredentials,
        write_limiter: RateLimiter | None = None,
        read_limiter: RateLimiter | None = None,
    ) -> None:
        """Initialize the Kalshi adapter.

        Args:
            credentials: Kalshi account credentials
            write_limiter: Optional custom write rate limiter
            read_limiter: Optional custom read rate limiter
        """
        self._auth = KalshiAuth(credentials)
        self._normalizer = KalshiNormalizer()

        # Create rate limiters
        if write_limiter and read_limiter:
            self._write_limiter = write_limiter
            self._read_limiter = read_limiter
        else:
            self._write_limiter, self._read_limiter = create_kalshi_rate_limiters()

        # Create REST client
        self._rest = KalshiRestClient(
            self._auth,
            self._write_limiter,
            self._read_limiter,
        )

        # Create WebSocket client
        self._ws = KalshiWebSocketClient(
            self._auth,
            on_message=self._handle_ws_message,
            on_connect=self._handle_ws_connect,
            on_disconnect=self._handle_ws_disconnect,
        )

        self._event_handler: Callable[[Event], None] | None = None
        self._subscribed_markets: set[str] = set()

    @property
    def capabilities(self) -> ExchangeCapabilities:
        """Return Kalshi's capabilities."""
        return ExchangeCapabilities(
            supports_order_amendment=False,
            supports_batch_orders=True,
            max_orders_per_request=100,
            rate_limit_writes_per_second=10,
            rate_limit_reads_per_second=30,
        )

    async def connect(self) -> None:
        """Connect to Kalshi.

        Establishes REST client and WebSocket connection.
        """
        logger.info(
            f"Connecting to Kalshi ({'demo' if self._auth.is_demo else 'live'})"
        )

        # Start REST client (authenticates)
        await self._rest.start()

        # Connect WebSocket
        await self._ws.connect()

        # Subscribe to fills (orders channel may not exist)
        await self._ws.subscribe_fills()

        logger.info("Kalshi connection established")

    async def disconnect(self) -> None:
        """Disconnect from Kalshi."""
        logger.info("Disconnecting from Kalshi")

        await self._ws.disconnect()
        await self._rest.stop()

        logger.info("Kalshi disconnected")

    async def subscribe_market(self, market_id: str) -> None:
        """Subscribe to market data.

        Args:
            market_id: Market ticker
        """
        if market_id in self._subscribed_markets:
            return

        await self._ws.subscribe_orderbook(market_id)
        self._subscribed_markets.add(market_id)

        logger.info(f"Subscribed to market: {market_id}")

    async def unsubscribe_market(self, market_id: str) -> None:
        """Unsubscribe from market data.

        Args:
            market_id: Market ticker
        """
        if market_id not in self._subscribed_markets:
            return

        await self._ws.unsubscribe_orderbook(market_id)
        self._subscribed_markets.discard(market_id)

        logger.info(f"Unsubscribed from market: {market_id}")

    async def place_order(self, request: OrderRequest) -> Order:
        """Place an order on Kalshi.

        Args:
            request: Order request

        Returns:
            Created order with Kalshi-assigned ID
        """
        response = await self._rest.place_order(
            ticker=request.market_id,
            side=self._normalizer.denormalize_side(request.side),
            action=self._normalizer.denormalize_order_side(request.order_side),
            count=request.size.value,
            price=self._normalizer.denormalize_price(request.price),
            client_order_id=request.client_order_id,
        )

        order_data = response.get("order", {})
        return self._normalizer.normalize_order(order_data)

    async def cancel_order(self, order_id: str) -> None:
        """Cancel an order.

        Args:
            order_id: Kalshi order ID
        """
        await self._rest.cancel_order(order_id)

    async def cancel_all_orders(self, market_id: str | None = None) -> int:
        """Cancel all orders, optionally filtered by market.

        Args:
            market_id: Optional market filter

        Returns:
            Number of orders cancelled
        """
        # Get open orders
        response = await self._rest.get_orders(
            ticker=market_id, status="resting"
        )
        orders = response.get("orders", [])

        if not orders:
            return 0

        # Batch cancel
        order_ids = [o.get("order_id") for o in orders if o.get("order_id")]
        if order_ids:
            await self._rest.batch_cancel_orders(order_ids)

        return len(order_ids)

    async def get_positions(self) -> list[Position]:
        """Get current positions.

        Returns:
            List of positions
        """
        response = await self._rest.get_positions()
        positions_data = response.get("market_positions", [])

        return [
            self._normalizer.normalize_position(p)
            for p in positions_data
        ]

    async def get_balance(self) -> Balance:
        """Get account balance.

        Returns:
            Balance information
        """
        response = await self._rest.get_balance()
        return self._normalizer.normalize_balance(response)

    async def get_open_orders(self, market_id: str | None = None) -> list[Order]:
        """Get open orders.

        Args:
            market_id: Optional market filter

        Returns:
            List of open orders
        """
        response = await self._rest.get_orders(
            ticker=market_id, status="resting"
        )
        orders_data = response.get("orders", [])

        return [
            self._normalizer.normalize_order(o)
            for o in orders_data
        ]

    async def get_orderbook(self, market_id: str) -> OrderBook:
        """Get current order book.

        Args:
            market_id: Market ticker

        Returns:
            Order book data
        """
        response = await self._rest.get_orderbook(market_id)
        return self._normalizer.normalize_orderbook(
            response.get("orderbook", {}), market_id
        )

    def set_event_handler(self, handler: Callable[[Event], None]) -> None:
        """Set the event handler callback.

        Args:
            handler: Callback for exchange events
        """
        self._event_handler = handler

    def _handle_ws_message(self, message: dict[str, Any]) -> None:
        """Handle incoming WebSocket message.

        Args:
            message: Parsed message
        """
        msg_type = message.get("type")
        logger.debug(f"WebSocket message received, type: {msg_type}")

        try:
            event: Event | None = None

            if msg_type == "orderbook_snapshot":
                event = self._normalizer.normalize_orderbook_snapshot(message)
            elif msg_type == "orderbook_delta":
                event = self._normalizer.normalize_orderbook_delta(message)
            elif msg_type == "fill":
                event = self._normalizer.normalize_fill_event(message)
            elif msg_type == "order":
                event = self._normalizer.normalize_order_event(message)

            if event and self._event_handler:
                self._event_handler(event)

        except Exception as e:
            logger.error(f"Error handling WebSocket message: {e}")

    def _handle_ws_connect(self) -> None:
        """Handle WebSocket connect event."""
        logger.info("WebSocket connected")

    def _handle_ws_disconnect(self) -> None:
        """Handle WebSocket disconnect event."""
        logger.warning("WebSocket disconnected")
