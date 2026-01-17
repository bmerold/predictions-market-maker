"""Tests for strategy factory."""

from decimal import Decimal
from typing import Any

import pytest

from market_maker.strategy.components.reservation import AvellanedaStoikovReservation
from market_maker.strategy.components.sizer import AsymmetricSizer
from market_maker.strategy.components.skew import LinearSkew
from market_maker.strategy.components.spread import FixedSpread
from market_maker.strategy.engine import StrategyEngine
from market_maker.strategy.factory import (
    StrategyConfig,
    create_strategy_engine,
)
from market_maker.strategy.volatility.ewma import EWMAVolatilityEstimator
from market_maker.strategy.volatility.fixed import FixedVolatilityEstimator


class TestStrategyConfig:
    """Tests for StrategyConfig."""

    def test_create_default_config(self) -> None:
        """StrategyConfig can be created with defaults."""
        config = StrategyConfig()
        assert config.volatility_type == "fixed"
        assert config.reservation_type == "avellaneda_stoikov"
        assert config.skew_type == "linear"
        assert config.spread_type == "fixed"
        assert config.sizer_type == "asymmetric"

    def test_create_custom_config(self) -> None:
        """StrategyConfig accepts custom values."""
        config = StrategyConfig(
            volatility_type="ewma",
            volatility_params={"alpha": "0.94", "initial_volatility": "0.10"},
            reservation_type="avellaneda_stoikov",
            reservation_params={"gamma": "0.05"},
        )
        assert config.volatility_type == "ewma"
        assert config.volatility_params["alpha"] == "0.94"

    def test_from_dict(self) -> None:
        """StrategyConfig can be created from dict."""
        data: dict[str, Any] = {
            "volatility": {
                "type": "ewma",
                "params": {"alpha": "0.94"},
            },
            "reservation_price": {
                "type": "avellaneda_stoikov",
                "params": {"gamma": "0.1"},
            },
        }
        config = StrategyConfig.from_dict(data)
        assert config.volatility_type == "ewma"
        assert config.reservation_type == "avellaneda_stoikov"


class TestCreateStrategyEngine:
    """Tests for create_strategy_engine factory function."""

    def test_creates_engine(self) -> None:
        """Factory creates a valid StrategyEngine."""
        config = StrategyConfig()
        engine = create_strategy_engine(config)
        assert isinstance(engine, StrategyEngine)

    def test_creates_with_fixed_volatility(self) -> None:
        """Factory creates engine with fixed volatility."""
        config = StrategyConfig(
            volatility_type="fixed",
            volatility_params={"volatility": "0.15"},
        )
        engine = create_strategy_engine(config)
        assert isinstance(engine._volatility, FixedVolatilityEstimator)

    def test_creates_with_ewma_volatility(self) -> None:
        """Factory creates engine with EWMA volatility."""
        config = StrategyConfig(
            volatility_type="ewma",
            volatility_params={
                "alpha": "0.1",
                "initial_volatility": "0.10",
                "min_samples": "2",
            },
        )
        engine = create_strategy_engine(config)
        assert isinstance(engine._volatility, EWMAVolatilityEstimator)

    def test_creates_with_avellaneda_stoikov(self) -> None:
        """Factory creates engine with A-S reservation price."""
        config = StrategyConfig(
            reservation_type="avellaneda_stoikov",
            reservation_params={"gamma": "0.05"},
        )
        engine = create_strategy_engine(config)
        assert isinstance(engine._reservation, AvellanedaStoikovReservation)
        assert engine._reservation.gamma == Decimal("0.05")

    def test_creates_with_linear_skew(self) -> None:
        """Factory creates engine with linear skew."""
        config = StrategyConfig(
            skew_type="linear",
            skew_params={"intensity": "0.02"},
        )
        engine = create_strategy_engine(config)
        assert isinstance(engine._skew, LinearSkew)
        assert engine._skew.intensity == Decimal("0.02")

    def test_creates_with_fixed_spread(self) -> None:
        """Factory creates engine with fixed spread."""
        config = StrategyConfig(
            spread_type="fixed",
            spread_params={"base_spread": "0.04"},
        )
        engine = create_strategy_engine(config)
        assert isinstance(engine._spread, FixedSpread)
        assert engine._spread.base_spread == Decimal("0.04")

    def test_creates_with_asymmetric_sizer(self) -> None:
        """Factory creates engine with asymmetric sizer."""
        config = StrategyConfig(
            sizer_type="asymmetric",
        )
        engine = create_strategy_engine(config)
        assert isinstance(engine._sizer, AsymmetricSizer)

    def test_unknown_volatility_type_raises(self) -> None:
        """Unknown volatility type raises error."""
        config = StrategyConfig(volatility_type="unknown")
        with pytest.raises(ValueError, match="Unknown volatility type"):
            create_strategy_engine(config)

    def test_unknown_reservation_type_raises(self) -> None:
        """Unknown reservation type raises error."""
        config = StrategyConfig(reservation_type="unknown")
        with pytest.raises(ValueError, match="Unknown reservation type"):
            create_strategy_engine(config)

    def test_unknown_skew_type_raises(self) -> None:
        """Unknown skew type raises error."""
        config = StrategyConfig(skew_type="unknown")
        with pytest.raises(ValueError, match="Unknown skew type"):
            create_strategy_engine(config)

    def test_unknown_spread_type_raises(self) -> None:
        """Unknown spread type raises error."""
        config = StrategyConfig(spread_type="unknown")
        with pytest.raises(ValueError, match="Unknown spread type"):
            create_strategy_engine(config)

    def test_unknown_sizer_type_raises(self) -> None:
        """Unknown sizer type raises error."""
        config = StrategyConfig(sizer_type="unknown")
        with pytest.raises(ValueError, match="Unknown sizer type"):
            create_strategy_engine(config)
