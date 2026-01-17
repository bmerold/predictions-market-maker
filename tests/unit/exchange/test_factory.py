"""Tests for exchange adapter factory."""


import pytest

from market_maker.domain.errors import ConfigurationError
from market_maker.exchange.base import ExchangeAdapter
from market_maker.exchange.factory import (
    ExchangeConfig,
    ExchangeType,
    create_adapter,
)


class TestExchangeType:
    """Tests for ExchangeType enum."""

    def test_kalshi_type(self) -> None:
        """ExchangeType has KALSHI."""
        assert ExchangeType.KALSHI.value == "kalshi"

    def test_polymarket_type(self) -> None:
        """ExchangeType has POLYMARKET."""
        assert ExchangeType.POLYMARKET.value == "polymarket"

    def test_mock_type(self) -> None:
        """ExchangeType has MOCK for testing."""
        assert ExchangeType.MOCK.value == "mock"


class TestExchangeConfig:
    """Tests for ExchangeConfig."""

    def test_create_config(self) -> None:
        """ExchangeConfig stores exchange settings."""
        config = ExchangeConfig(
            exchange_type=ExchangeType.KALSHI,
            api_key="test_key",
            api_secret="test_secret",
            base_url="https://api.kalshi.com",
            ws_url="wss://api.kalshi.com",
            extra_settings={"rate_limit": 10},
        )
        assert config.exchange_type == ExchangeType.KALSHI
        assert config.api_key == "test_key"
        assert config.extra_settings["rate_limit"] == 10

    def test_config_minimal(self) -> None:
        """ExchangeConfig works with minimal settings."""
        config = ExchangeConfig(
            exchange_type=ExchangeType.MOCK,
        )
        assert config.exchange_type == ExchangeType.MOCK
        assert config.api_key is None
        assert config.api_secret is None

    def test_config_from_dict(self) -> None:
        """ExchangeConfig can be created from dict."""
        data = {
            "exchange_type": "kalshi",
            "api_key": "key",
            "api_secret": "secret",
            "base_url": "https://api.kalshi.com",
        }
        config = ExchangeConfig.from_dict(data)
        assert config.exchange_type == ExchangeType.KALSHI
        assert config.api_key == "key"

    def test_config_from_dict_unknown_exchange(self) -> None:
        """ExchangeConfig.from_dict raises for unknown exchange."""
        data = {"exchange_type": "unknown_exchange"}
        with pytest.raises(ConfigurationError, match="Unknown exchange type"):
            ExchangeConfig.from_dict(data)


class TestAdapterRegistry:
    """Tests for adapter registration."""

    def test_register_and_create_mock_adapter(self) -> None:
        """Can register and create a mock adapter."""
        # Mock adapter should be pre-registered
        config = ExchangeConfig(exchange_type=ExchangeType.MOCK)
        adapter = create_adapter(config)
        assert adapter is not None

    def test_create_unregistered_raises(self) -> None:
        """Creating unregistered adapter type raises."""
        # Create a config with a fake/unregistered type
        config = ExchangeConfig(exchange_type=ExchangeType.POLYMARKET)
        # Polymarket is not implemented yet, should raise
        with pytest.raises(ConfigurationError, match="No adapter registered"):
            create_adapter(config)


class TestCreateAdapter:
    """Tests for create_adapter factory function."""

    def test_create_mock_adapter(self) -> None:
        """create_adapter returns mock adapter."""
        config = ExchangeConfig(exchange_type=ExchangeType.MOCK)
        adapter = create_adapter(config)
        assert isinstance(adapter, ExchangeAdapter)

    def test_adapter_receives_config(self) -> None:
        """Adapter factory receives config."""
        config = ExchangeConfig(
            exchange_type=ExchangeType.MOCK,
            extra_settings={"test_setting": "test_value"},
        )
        adapter = create_adapter(config)
        # Mock adapter should store config for testing
        assert hasattr(adapter, "config")
        assert adapter.config.extra_settings.get("test_setting") == "test_value"
