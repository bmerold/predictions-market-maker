"""Pytest configuration and shared fixtures."""

import pytest
from decimal import Decimal


@pytest.fixture
def sample_orderbook_snapshot() -> dict:
    """Sample order book snapshot from Kalshi WebSocket."""
    return {
        "type": "orderbook_snapshot",
        "market_ticker": "KXBTC-25JAN17-100000",
        "yes": [
            [45, 100],  # price in cents, size
            [44, 200],
            [43, 150],
        ],
        "no": [
            [56, 100],
            [57, 200],
            [58, 150],
        ],
    }


@pytest.fixture
def sample_orderbook_delta() -> dict:
    """Sample order book delta from Kalshi WebSocket."""
    return {
        "type": "orderbook_delta",
        "market_ticker": "KXBTC-25JAN17-100000",
        "price": 45,
        "delta": -50,
        "side": "yes",
    }


@pytest.fixture
def sample_trade() -> dict:
    """Sample trade event from Kalshi WebSocket."""
    return {
        "type": "trade",
        "market_ticker": "KXBTC-25JAN17-100000",
        "price": 45,
        "count": 10,
        "side": "yes",
        "ts": 1705500000000,
    }


@pytest.fixture
def default_strategy_params() -> dict:
    """Default parameters for A-S strategy."""
    return {
        "gamma": Decimal("0.1"),
        "sigma_alpha": Decimal("0.1"),
        "base_spread": Decimal("0.02"),
        "quote_size": 100,
        "max_position": 1000,
    }
