#!/usr/bin/env python3
"""Find the current ATM BTC hourly market on Kalshi.

Usage:
    python scripts/find_market.py

Requires KALSHI_API_KEY and KALSHI_PRIVATE_KEY_PATH environment variables.
"""

import asyncio
import os
import sys
from datetime import UTC, datetime
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from market_maker.exchange.kalshi.auth import KalshiAuth, KalshiCredentials
from market_maker.exchange.kalshi.rest import KalshiRestClient
from market_maker.exchange.kalshi.rate_limiter import create_kalshi_rate_limiters


async def find_btc_hourly_markets() -> None:
    """Find current BTC hourly markets."""
    # Load credentials
    api_key = os.environ.get("KALSHI_API_KEY")
    key_path = os.environ.get("KALSHI_PRIVATE_KEY_PATH")

    if not api_key or not key_path:
        print("Error: Set KALSHI_API_KEY and KALSHI_PRIVATE_KEY_PATH environment variables")
        sys.exit(1)

    credentials = KalshiCredentials(
        api_key=api_key,
        private_key_path=key_path,
        demo=False,
    )

    auth = KalshiAuth(credentials)
    write_limiter, read_limiter = create_kalshi_rate_limiters()
    client = KalshiRestClient(auth, write_limiter, read_limiter)

    await client.start()

    try:
        # Search for BTC hourly markets
        # Series ticker for BTC hourly is KXBTCD
        response = await client.get_markets(
            series_ticker="KXBTCD",
            status="open",
            limit=50,
        )

        markets = response.get("markets", [])

        if not markets:
            print("No open BTC hourly markets found")
            return

        print(f"\nFound {len(markets)} open BTC hourly markets:\n")

        # Group by event (hour)
        events: dict[str, list] = {}
        for market in markets:
            event_ticker = market.get("event_ticker", "unknown")
            if event_ticker not in events:
                events[event_ticker] = []
            events[event_ticker].append(market)

        # Show markets grouped by event
        for event_ticker, event_markets in sorted(events.items()):
            print(f"\n=== {event_ticker} ===")

            # Sort by strike price
            sorted_markets = sorted(
                event_markets,
                key=lambda m: float(m.get("strike_price", 0) or 0)
            )

            for market in sorted_markets:
                ticker = market.get("ticker", "")
                strike = market.get("strike_price")
                yes_bid = market.get("yes_bid", 0)
                yes_ask = market.get("yes_ask", 0)
                volume = market.get("volume", 0)
                close_time = market.get("close_time", "")

                # Calculate mid price
                mid = (yes_bid + yes_ask) / 2 if yes_bid and yes_ask else 0

                # Highlight ATM markets (mid around 50 cents)
                atm_marker = " <-- ATM" if 40 <= mid <= 60 else ""

                print(
                    f"  {ticker}: "
                    f"strike=${strike}, "
                    f"bid={yes_bid}c, "
                    f"ask={yes_ask}c, "
                    f"mid={mid:.0f}c, "
                    f"vol={volume}"
                    f"{atm_marker}"
                )

        # Find the next expiring ATM market
        print("\n\n=== Recommended ATM Market ===")
        atm_markets = []
        for market in markets:
            yes_bid = market.get("yes_bid", 0)
            yes_ask = market.get("yes_ask", 0)
            mid = (yes_bid + yes_ask) / 2 if yes_bid and yes_ask else 0
            if 35 <= mid <= 65:  # Reasonably ATM (in cents)
                atm_markets.append((market, mid))

        if atm_markets:
            # Sort by how close to 50c and then by expiration
            atm_markets.sort(key=lambda x: abs(x[1] - 50))
            best = atm_markets[0][0]
            print(f"\nTicker: {best.get('ticker')}")
            print(f"Strike: ${best.get('strike_price')}")
            print(f"Close time: {best.get('close_time')}")
            print(f"\nTo launch, update config/launch.yaml with this ticker and run:")
            print(f"  python -m market_maker --config config/launch.yaml")
        else:
            print("No ATM markets found")

    finally:
        await client.stop()


if __name__ == "__main__":
    asyncio.run(find_btc_hourly_markets())
