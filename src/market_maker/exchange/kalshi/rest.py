"""Kalshi REST API client.

Handles order management, positions, and account operations.
"""

from __future__ import annotations

import logging
from typing import Any

import httpx

from market_maker.exchange.kalshi.auth import KalshiAuth
from market_maker.exchange.kalshi.rate_limiter import RateLimiter

logger = logging.getLogger(__name__)


class KalshiRestClient:
    """REST client for Kalshi trading API.

    Handles:
    - Order placement and cancellation
    - Position queries
    - Balance queries
    - Market information

    All methods are async and respect rate limits.
    """

    def __init__(
        self,
        auth: KalshiAuth,
        write_limiter: RateLimiter,
        read_limiter: RateLimiter,
    ) -> None:
        """Initialize the REST client.

        Args:
            auth: Authentication manager
            write_limiter: Rate limiter for write operations
            read_limiter: Rate limiter for read operations
        """
        self._auth = auth
        self._write_limiter = write_limiter
        self._read_limiter = read_limiter
        self._client: httpx.AsyncClient | None = None

    async def start(self) -> None:
        """Start the REST client."""
        self._client = httpx.AsyncClient(timeout=30.0)
        await self._auth.ensure_authenticated()

    async def stop(self) -> None:
        """Stop the REST client."""
        if self._client:
            await self._client.aclose()
            self._client = None

    async def _request(
        self,
        method: str,
        endpoint: str,
        is_write: bool = False,
        **kwargs: Any,
    ) -> dict[str, Any]:
        """Make an authenticated request.

        Args:
            method: HTTP method
            endpoint: API endpoint (relative to base URL)
            is_write: Whether this is a write operation
            **kwargs: Additional request arguments

        Returns:
            JSON response data

        Raises:
            KalshiAPIError: If the request fails
        """
        if not self._client:
            raise KalshiAPIError("Client not started")

        # Apply rate limiting
        limiter = self._write_limiter if is_write else self._read_limiter
        await limiter.acquire()

        # Ensure authenticated
        await self._auth.ensure_authenticated()

        url = f"{self._auth.base_url}{endpoint}"
        # Full path for signing includes /trade-api/v2
        full_path = f"/trade-api/v2{endpoint}"
        headers = self._auth.get_auth_headers(method, full_path)

        try:
            response = await self._client.request(
                method, url, headers=headers, **kwargs
            )
            response.raise_for_status()
            result: dict[str, Any] = response.json()
            return result

        except httpx.HTTPStatusError as e:
            error_body = e.response.text
            logger.error(
                f"Kalshi API error: {e.response.status_code} - {error_body}"
            )
            raise KalshiAPIError(
                f"API error {e.response.status_code}: {error_body}"
            ) from e

        except httpx.RequestError as e:
            logger.error(f"Kalshi request failed: {e}")
            raise KalshiAPIError(f"Request failed: {e}") from e

    # Order operations

    async def place_order(
        self,
        ticker: str,
        side: str,  # "yes" or "no"
        action: str,  # "buy" or "sell"
        count: int,
        price: int,  # Price in cents (1-99)
        client_order_id: str | None = None,
        order_type: str = "limit",
    ) -> dict[str, Any]:
        """Place an order.

        Args:
            ticker: Market ticker (e.g., "KXBTCD-25DEC1516-T86249.99")
            side: "yes" or "no"
            action: "buy" or "sell"
            count: Number of contracts
            price: Price in cents (1-99)
            client_order_id: Optional client-side order ID
            order_type: "limit" or "market"

        Returns:
            Order response from Kalshi
        """
        payload: dict[str, Any] = {
            "ticker": ticker,
            "side": side,
            "action": action,
            "count": count,
            "type": order_type,
        }

        if order_type == "limit":
            payload["yes_price"] = price if side == "yes" else 100 - price

        if client_order_id:
            payload["client_order_id"] = client_order_id

        logger.info(
            f"Placing order: {action} {count} {side} @ {price}c on {ticker}"
        )

        return await self._request(
            "POST", "/portfolio/orders", is_write=True, json=payload
        )

    async def cancel_order(self, order_id: str) -> dict[str, Any]:
        """Cancel an order.

        Args:
            order_id: The Kalshi order ID

        Returns:
            Cancellation response
        """
        logger.info(f"Cancelling order: {order_id}")
        return await self._request(
            "DELETE", f"/portfolio/orders/{order_id}", is_write=True
        )

    async def batch_cancel_orders(
        self, order_ids: list[str]
    ) -> dict[str, Any]:
        """Cancel multiple orders.

        Args:
            order_ids: List of order IDs to cancel

        Returns:
            Batch cancellation response
        """
        logger.info(f"Batch cancelling {len(order_ids)} orders")
        return await self._request(
            "DELETE",
            "/portfolio/orders",
            is_write=True,
            json={"order_ids": order_ids},
        )

    async def get_order(self, order_id: str) -> dict[str, Any]:
        """Get order details.

        Args:
            order_id: The Kalshi order ID

        Returns:
            Order details
        """
        return await self._request("GET", f"/portfolio/orders/{order_id}")

    async def get_orders(
        self,
        ticker: str | None = None,
        status: str | None = None,
        limit: int = 100,
    ) -> dict[str, Any]:
        """Get orders.

        Args:
            ticker: Optional ticker filter
            status: Optional status filter ("resting", "pending", etc.)
            limit: Maximum number of orders to return

        Returns:
            Orders response
        """
        params: dict[str, Any] = {"limit": limit}
        if ticker:
            params["ticker"] = ticker
        if status:
            params["status"] = status

        return await self._request("GET", "/portfolio/orders", params=params)

    # Position operations

    async def get_positions(
        self, ticker: str | None = None
    ) -> dict[str, Any]:
        """Get positions.

        Args:
            ticker: Optional ticker filter

        Returns:
            Positions response
        """
        params = {}
        if ticker:
            params["ticker"] = ticker

        return await self._request(
            "GET", "/portfolio/positions", params=params if params else None
        )

    async def get_balance(self) -> dict[str, Any]:
        """Get account balance.

        Returns:
            Balance response with available_balance, etc.
        """
        return await self._request("GET", "/portfolio/balance")

    # Market operations

    async def get_market(self, ticker: str) -> dict[str, Any]:
        """Get market details.

        Args:
            ticker: Market ticker

        Returns:
            Market details
        """
        return await self._request("GET", f"/markets/{ticker}")

    async def get_markets(
        self,
        event_ticker: str | None = None,
        series_ticker: str | None = None,
        status: str = "open",
        limit: int = 100,
    ) -> dict[str, Any]:
        """Get markets.

        Args:
            event_ticker: Optional event filter
            series_ticker: Optional series filter
            status: Market status filter
            limit: Maximum number of markets

        Returns:
            Markets response
        """
        params: dict[str, Any] = {"status": status, "limit": limit}
        if event_ticker:
            params["event_ticker"] = event_ticker
        if series_ticker:
            params["series_ticker"] = series_ticker

        return await self._request("GET", "/markets", params=params)

    async def get_orderbook(self, ticker: str, depth: int = 10) -> dict[str, Any]:
        """Get order book for a market.

        Args:
            ticker: Market ticker
            depth: Number of price levels

        Returns:
            Order book data
        """
        return await self._request(
            "GET", f"/markets/{ticker}/orderbook", params={"depth": depth}
        )


class KalshiAPIError(Exception):
    """Raised when a Kalshi API request fails."""

    pass
