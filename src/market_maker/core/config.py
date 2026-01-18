"""Configuration models for the trading application.

Loads and validates configuration from YAML files using pydantic.
"""

from __future__ import annotations

from decimal import Decimal
from enum import Enum
from pathlib import Path
from typing import Any

import yaml
from pydantic import BaseModel, Field


class ExecutionMode(str, Enum):
    """Trading execution mode."""

    PAPER = "paper"
    LIVE = "live"


class ExchangeType(str, Enum):
    """Supported exchanges."""

    KALSHI = "kalshi"
    MOCK = "mock"


class ComponentConfig(BaseModel):
    """Configuration for a strategy component."""

    type: str
    params: dict[str, Any] = Field(default_factory=dict)


class StrategyComponentsConfig(BaseModel):
    """Configuration for all strategy components."""

    volatility: ComponentConfig = Field(
        default_factory=lambda: ComponentConfig(
            type="fixed", params={"value": 0.05}
        )
    )
    reservation_price: ComponentConfig = Field(
        default_factory=lambda: ComponentConfig(
            type="avellaneda_stoikov", params={"gamma": 0.1}
        )
    )
    skew: ComponentConfig = Field(
        default_factory=lambda: ComponentConfig(
            type="linear", params={"intensity": 0.01}
        )
    )
    spread: ComponentConfig = Field(
        default_factory=lambda: ComponentConfig(
            type="fixed", params={"base_spread": 0.02}
        )
    )
    sizer: ComponentConfig = Field(
        default_factory=lambda: ComponentConfig(
            type="asymmetric", params={"base_size": 10}
        )
    )


class PriceBoundsConfig(BaseModel):
    """Price bound configuration."""

    min: Decimal = Decimal("0.01")
    max: Decimal = Decimal("0.99")


class StrategyConfig(BaseModel):
    """Strategy configuration."""

    components: StrategyComponentsConfig = Field(
        default_factory=StrategyComponentsConfig
    )
    max_inventory: int = 100
    min_spread: Decimal = Decimal("0.01")
    price_bounds: PriceBoundsConfig = Field(default_factory=PriceBoundsConfig)
    preset: str | None = None


class RiskRuleConfig(BaseModel):
    """Configuration for a single risk rule."""

    enabled: bool = True
    limit: Decimal | None = None
    action: str = "block"
    max_age_seconds: int | None = None
    cutoff_minutes: int | None = None
    threshold_multiplier: Decimal | None = None
    spread_multiplier: Decimal | None = None


class KillSwitchConfig(BaseModel):
    """Kill switch configuration."""

    enabled: bool = True
    require_manual_reset: bool = True


class RiskConfig(BaseModel):
    """Risk management configuration."""

    rule_order: list[str] = Field(
        default_factory=lambda: [
            "stale_data",
            "settlement_cutoff",
            "daily_loss_limit",
            "hourly_loss_limit",
            "max_inventory",
            "max_order_size",
        ]
    )
    rules: dict[str, RiskRuleConfig] = Field(default_factory=dict)
    kill_switch: KillSwitchConfig = Field(default_factory=KillSwitchConfig)
    custom_rules: list[dict[str, Any]] = Field(default_factory=list)


class RecordingConfig(BaseModel):
    """Session recording configuration."""

    enabled: bool = False
    output_dir: str = "./data/sessions"
    snapshot_interval_seconds: int = 60
    compression: str = "gzip"


class ExchangeConfig(BaseModel):
    """Exchange connection configuration."""

    type: ExchangeType = ExchangeType.MOCK
    demo: bool = False

    # Credentials (loaded from environment or specified directly)
    api_key_env: str = "KALSHI_API_KEY"
    private_key_path_env: str = "KALSHI_PRIVATE_KEY_PATH"

    # Direct credential values (override env vars if set)
    api_key: str | None = None
    private_key_path: str | None = None


class MarketConfig(BaseModel):
    """Market configuration."""

    ticker: str
    settlement_time: str | None = None  # ISO format


class TradingConfig(BaseModel):
    """Root configuration for the trading application."""

    mode: ExecutionMode = ExecutionMode.PAPER
    exchange: ExchangeConfig = Field(default_factory=ExchangeConfig)
    markets: list[MarketConfig] = Field(default_factory=list)
    strategy: StrategyConfig = Field(default_factory=StrategyConfig)
    risk: RiskConfig = Field(default_factory=RiskConfig)
    recording: RecordingConfig = Field(default_factory=RecordingConfig)

    # Timing
    quote_interval_ms: int = 1000  # How often to refresh quotes
    reconciliation_interval_seconds: int = 60  # Position reconciliation

    # API server
    api_port: int | None = 8080  # Set to None to disable

    # Logging
    log_level: str = "INFO"
    log_file: str | None = None

    @classmethod
    def from_yaml(cls, path: str | Path) -> TradingConfig:
        """Load configuration from a YAML file.

        Args:
            path: Path to the YAML configuration file

        Returns:
            Validated TradingConfig

        Raises:
            FileNotFoundError: If the config file doesn't exist
            ValidationError: If the config is invalid
        """
        path = Path(path)
        if not path.exists():
            raise FileNotFoundError(f"Config file not found: {path}")

        with open(path) as f:
            data = yaml.safe_load(f)

        return cls.model_validate(data or {})

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> TradingConfig:
        """Load configuration from a dictionary.

        Args:
            data: Configuration dictionary

        Returns:
            Validated TradingConfig
        """
        return cls.model_validate(data)

    def to_yaml(self, path: str | Path) -> None:
        """Save configuration to a YAML file.

        Args:
            path: Path to write the configuration
        """
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)

        with open(path, "w") as f:
            yaml.dump(self.model_dump(mode="json"), f, default_flow_style=False)


def load_config(path: str | Path | None = None) -> TradingConfig:
    """Load trading configuration.

    Looks for config in the following order:
    1. Provided path argument
    2. ./config/strategy.yaml
    3. Default configuration

    Args:
        path: Optional explicit path to config file

    Returns:
        Validated TradingConfig
    """
    if path:
        return TradingConfig.from_yaml(path)

    # Try default locations
    default_paths = [
        Path("./config/strategy.yaml"),
        Path("./config/config.yaml"),
        Path("./strategy.yaml"),
    ]

    for default_path in default_paths:
        if default_path.exists():
            return TradingConfig.from_yaml(default_path)

    # Return default config
    return TradingConfig()
