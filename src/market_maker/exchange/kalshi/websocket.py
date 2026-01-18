"""Kalshi WebSocket client for real-time market data.

Handles connection management, subscriptions, and message parsing.
"""

from __future__ import annotations

import asyncio
import json
import logging
from collections.abc import Callable
from typing import Any

import websockets
from websockets.asyncio.client import ClientConnection

from market_maker.exchange.kalshi.auth import KalshiAuth

logger = logging.getLogger(__name__)

# WebSocket endpoints
KALSHI_WS_URL = "wss://api.elections.kalshi.com/trade-api/ws/v2"
KALSHI_DEMO_WS_URL = "wss://demo-api.kalshi.co/trade-api/ws/v2"


class KalshiWebSocketClient:
    """WebSocket client for Kalshi market data.

    Features:
    - Automatic reconnection with exponential backoff
    - Subscription management
    - Message parsing and routing
    - Heartbeat handling
    """

    def __init__(
        self,
        auth: KalshiAuth,
        on_message: Callable[[dict[str, Any]], None] | None = None,
        on_connect: Callable[[], None] | None = None,
        on_disconnect: Callable[[], None] | None = None,
    ) -> None:
        """Initialize the WebSocket client.

        Args:
            auth: Authentication manager
            on_message: Callback for incoming messages
            on_connect: Callback when connected
            on_disconnect: Callback when disconnected
        """
        self._auth = auth
        self._on_message = on_message
        self._on_connect = on_connect
        self._on_disconnect = on_disconnect

        self._ws: ClientConnection | None = None
        self._connected = False
        self._subscriptions: set[str] = set()
        self._reconnect_task: asyncio.Task[None] | None = None
        self._receive_task: asyncio.Task[None] | None = None
        self._should_run = False

        # Reconnection settings
        self._reconnect_delay = 1.0
        self._max_reconnect_delay = 60.0
        self._reconnect_attempts = 0

    @property
    def ws_url(self) -> str:
        """Return the appropriate WebSocket URL."""
        return KALSHI_DEMO_WS_URL if self._auth.is_demo else KALSHI_WS_URL

    def is_connected(self) -> bool:
        """Return True if connected."""
        return self._connected and self._ws is not None

    async def connect(self) -> None:
        """Connect to Kalshi WebSocket.

        Establishes connection and starts message processing.
        """
        self._should_run = True
        await self._connect()

    async def _connect(self) -> None:
        """Internal connect implementation."""
        await self._auth.ensure_authenticated()

        # Get auth headers for WebSocket connection
        # Sign with GET /trade-api/ws/v2 as per Kalshi docs
        auth_headers = self._auth.get_auth_headers("GET", "/trade-api/ws/v2")

        try:
            self._ws = await websockets.connect(
                self.ws_url,
                additional_headers=auth_headers,
                ping_interval=30,
                ping_timeout=10,
            )
            self._connected = True
            self._reconnect_attempts = 0
            self._reconnect_delay = 1.0

            logger.info("Kalshi WebSocket connected")

            if self._on_connect:
                self._on_connect()

            # Resubscribe to any previous subscriptions
            if self._subscriptions:
                await self._resubscribe()

            # Start message processing
            self._receive_task = asyncio.create_task(self._receive_loop())

        except Exception as e:
            logger.error(f"WebSocket connection failed: {e}")
            self._connected = False
            if self._should_run:
                await self._schedule_reconnect()

    async def disconnect(self) -> None:
        """Disconnect from WebSocket."""
        self._should_run = False

        if self._reconnect_task:
            self._reconnect_task.cancel()
            self._reconnect_task = None

        if self._receive_task:
            self._receive_task.cancel()
            self._receive_task = None

        if self._ws:
            await self._ws.close()
            self._ws = None

        self._connected = False
        logger.info("Kalshi WebSocket disconnected")

        if self._on_disconnect:
            self._on_disconnect()

    async def subscribe(self, channels: list[str]) -> None:
        """Subscribe to channels.

        Args:
            channels: List of channel identifiers
                     Format: "orderbook_delta:{ticker}" or "ticker:{ticker}"
        """
        if not self._ws:
            # Store subscriptions for when we connect
            self._subscriptions.update(channels)
            return

        for channel in channels:
            if channel in self._subscriptions:
                continue

            msg = self._build_subscribe_message(channel)
            await self._send(msg)
            self._subscriptions.add(channel)

            logger.debug(f"Subscribed to {channel}")

    async def unsubscribe(self, channels: list[str]) -> None:
        """Unsubscribe from channels.

        Args:
            channels: List of channel identifiers
        """
        if not self._ws:
            self._subscriptions.difference_update(channels)
            return

        for channel in channels:
            if channel not in self._subscriptions:
                continue

            msg = self._build_unsubscribe_message(channel)
            await self._send(msg)
            self._subscriptions.discard(channel)

            logger.debug(f"Unsubscribed from {channel}")

    async def subscribe_orderbook(self, ticker: str) -> None:
        """Subscribe to order book updates for a ticker.

        Args:
            ticker: Market ticker
        """
        await self.subscribe([f"orderbook_delta:{ticker}"])

    async def unsubscribe_orderbook(self, ticker: str) -> None:
        """Unsubscribe from order book updates.

        Args:
            ticker: Market ticker
        """
        await self.unsubscribe([f"orderbook_delta:{ticker}"])

    async def subscribe_fills(self) -> None:
        """Subscribe to fill notifications."""
        await self.subscribe(["fill"])

    async def subscribe_orders(self) -> None:
        """Subscribe to order updates."""
        await self.subscribe(["order"])

    def _build_subscribe_message(self, channel: str) -> dict[str, Any]:
        """Build a subscription message.

        Args:
            channel: Channel to subscribe to

        Returns:
            Message dict
        """
        parts = channel.split(":", 1)
        cmd = parts[0]
        params: dict[str, Any] = {"channels": [cmd]}

        # Channel has a parameter (e.g., market_ticker)
        if len(parts) > 1 and cmd in ("orderbook_delta", "ticker"):
            params["market_ticker"] = parts[1]

        return {
            "id": 1,
            "cmd": "subscribe",
            "params": params,
        }

    def _build_unsubscribe_message(self, channel: str) -> dict[str, Any]:
        """Build an unsubscription message."""
        parts = channel.split(":", 1)
        cmd = parts[0]
        params: dict[str, Any] = {"channels": [cmd]}

        if len(parts) > 1 and cmd in ("orderbook_delta", "ticker"):
            params["market_ticker"] = parts[1]

        return {
            "id": 1,
            "cmd": "unsubscribe",
            "params": params,
        }

    async def _send(self, message: dict[str, Any]) -> None:
        """Send a message.

        Args:
            message: Message dict to send
        """
        if not self._ws:
            raise ConnectionError("WebSocket not connected")

        msg_str = json.dumps(message)
        logger.debug(f"Sending WebSocket message: {msg_str}")
        await self._ws.send(msg_str)

    async def _receive_loop(self) -> None:
        """Process incoming messages."""
        if not self._ws:
            return

        try:
            async for raw_message in self._ws:
                try:
                    message = json.loads(raw_message)
                    await self._handle_message(message)
                except json.JSONDecodeError as e:
                    logger.warning(f"Failed to parse message: {e}")

        except websockets.ConnectionClosed as e:
            logger.warning(f"WebSocket connection closed: {e}")
            self._connected = False
            if self._on_disconnect:
                self._on_disconnect()
            if self._should_run:
                await self._schedule_reconnect()

        except Exception as e:
            logger.error(f"WebSocket receive error: {e}")
            self._connected = False
            if self._should_run:
                await self._schedule_reconnect()

    async def _handle_message(self, message: dict[str, Any]) -> None:
        """Handle an incoming message.

        Args:
            message: Parsed message dict
        """
        msg_type = message.get("type")

        if msg_type == "subscribed":
            logger.debug(f"Subscription confirmed: {message}")
            return

        if msg_type == "error":
            logger.error(f"WebSocket error: {message}")
            return

        # Forward to handler
        if self._on_message:
            self._on_message(message)

    async def _schedule_reconnect(self) -> None:
        """Schedule a reconnection attempt."""
        self._reconnect_attempts += 1
        delay = min(
            self._reconnect_delay * (2 ** (self._reconnect_attempts - 1)),
            self._max_reconnect_delay,
        )

        logger.info(
            f"Scheduling reconnect in {delay:.1f}s "
            f"(attempt {self._reconnect_attempts})"
        )

        await asyncio.sleep(delay)

        if self._should_run:
            await self._connect()

    async def _resubscribe(self) -> None:
        """Resubscribe to all channels after reconnect."""
        channels = list(self._subscriptions)
        self._subscriptions.clear()
        await self.subscribe(channels)

    def set_message_handler(
        self, handler: Callable[[dict[str, Any]], None]
    ) -> None:
        """Set the message handler callback.

        Args:
            handler: Callback for incoming messages
        """
        self._on_message = handler
