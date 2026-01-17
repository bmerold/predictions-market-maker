"""Exchange adapter factory.

Provides configuration-driven adapter instantiation, allowing the
exchange to be selected via configuration rather than code changes.
"""

from __future__ import annotations

from collections.abc import Callable
from enum import Enum
from typing import Any

from pydantic.dataclasses import dataclass

from market_maker.domain.errors import ConfigurationError
from market_maker.exchange.base import ExchangeAdapter


class ExchangeType(str, Enum):
    """Supported exchange types."""

    KALSHI = "kalshi"
    POLYMARKET = "polymarket"
    MOCK = "mock"


@dataclass
class ExchangeConfig:
    """Configuration for an exchange adapter.

    Contains all settings needed to instantiate an exchange adapter.
    """

    exchange_type: ExchangeType
    api_key: str | None = None
    api_secret: str | None = None
    base_url: str | None = None
    ws_url: str | None = None
    extra_settings: dict[str, Any] | None = None

    def __post_init__(self) -> None:
        if self.extra_settings is None:
            self.extra_settings = {}

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> ExchangeConfig:
        """Create config from a dictionary.

        Args:
            data: Configuration dictionary

        Returns:
            ExchangeConfig instance

        Raises:
            ConfigurationError: If exchange_type is unknown
        """
        exchange_type_str = data.get("exchange_type", "")
        try:
            exchange_type = ExchangeType(exchange_type_str)
        except ValueError as err:
            raise ConfigurationError(
                f"Unknown exchange type: {exchange_type_str}",
                field="exchange_type",
            ) from err

        return cls(
            exchange_type=exchange_type,
            api_key=data.get("api_key"),
            api_secret=data.get("api_secret"),
            base_url=data.get("base_url"),
            ws_url=data.get("ws_url"),
            extra_settings=data.get("extra_settings"),
        )


# Registry of adapter factories
_adapter_factories: dict[ExchangeType, Callable[[ExchangeConfig], ExchangeAdapter]] = {}


def register_adapter(
    exchange_type: ExchangeType,
    factory: Callable[[ExchangeConfig], ExchangeAdapter],
) -> None:
    """Register an adapter factory for an exchange type.

    Args:
        exchange_type: The type of exchange
        factory: Function that creates an adapter from config
    """
    _adapter_factories[exchange_type] = factory


def create_adapter(config: ExchangeConfig) -> ExchangeAdapter:
    """Create an exchange adapter from configuration.

    Args:
        config: Exchange configuration

    Returns:
        Configured exchange adapter

    Raises:
        ConfigurationError: If no adapter registered for exchange type
    """
    factory = _adapter_factories.get(config.exchange_type)
    if factory is None:
        raise ConfigurationError(
            f"No adapter registered for exchange type: {config.exchange_type.value}",
            field="exchange_type",
        )
    return factory(config)


# Import and register mock adapter
from market_maker.exchange.mock import MockExchangeAdapter  # noqa: E402

register_adapter(ExchangeType.MOCK, lambda config: MockExchangeAdapter(config))
