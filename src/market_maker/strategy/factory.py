"""Strategy factory for building strategy engines from configuration.

Provides factory functions to instantiate strategy components and
compose them into a StrategyEngine.
"""

from __future__ import annotations

from decimal import Decimal
from typing import Any

from pydantic.dataclasses import dataclass

from market_maker.strategy.components.base import (
    QuoteSizer,
    ReservationPriceCalculator,
    SkewCalculator,
    SpreadCalculator,
)
from market_maker.strategy.components.reservation import AvellanedaStoikovReservation
from market_maker.strategy.components.sizer import AsymmetricSizer
from market_maker.strategy.components.skew import LinearSkew
from market_maker.strategy.components.spread import FixedSpread
from market_maker.strategy.engine import StrategyEngine
from market_maker.strategy.volatility.base import VolatilityEstimator
from market_maker.strategy.volatility.ewma import EWMAVolatilityEstimator
from market_maker.strategy.volatility.fixed import FixedVolatilityEstimator


@dataclass
class StrategyConfig:
    """Configuration for building a StrategyEngine.

    Specifies which component implementations to use and their parameters.
    """

    # Volatility estimator
    volatility_type: str = "fixed"
    volatility_params: dict[str, str] | None = None

    # Reservation price calculator
    reservation_type: str = "avellaneda_stoikov"
    reservation_params: dict[str, str] | None = None

    # Skew calculator
    skew_type: str = "linear"
    skew_params: dict[str, str] | None = None

    # Spread calculator
    spread_type: str = "fixed"
    spread_params: dict[str, str] | None = None

    # Quote sizer
    sizer_type: str = "asymmetric"
    sizer_params: dict[str, str] | None = None

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> StrategyConfig:
        """Create config from a dictionary (e.g., parsed YAML).

        Expected format:
        {
            "volatility": {"type": "ewma", "params": {...}},
            "reservation_price": {"type": "avellaneda_stoikov", "params": {...}},
            "skew": {"type": "linear", "params": {...}},
            "spread": {"type": "fixed", "params": {...}},
            "sizer": {"type": "asymmetric", "params": {...}},
        }

        Args:
            data: Dictionary with component configurations

        Returns:
            StrategyConfig instance
        """
        volatility = data.get("volatility", {})
        reservation = data.get("reservation_price", {})
        skew = data.get("skew", {})
        spread = data.get("spread", {})
        sizer = data.get("sizer", {})

        return cls(
            volatility_type=volatility.get("type", "fixed"),
            volatility_params=volatility.get("params"),
            reservation_type=reservation.get("type", "avellaneda_stoikov"),
            reservation_params=reservation.get("params"),
            skew_type=skew.get("type", "linear"),
            skew_params=skew.get("params"),
            spread_type=spread.get("type", "fixed"),
            spread_params=spread.get("params"),
            sizer_type=sizer.get("type", "asymmetric"),
            sizer_params=sizer.get("params"),
        )


def create_strategy_engine(config: StrategyConfig) -> StrategyEngine:
    """Create a StrategyEngine from configuration.

    Args:
        config: Strategy configuration

    Returns:
        Configured StrategyEngine

    Raises:
        ValueError: If unknown component type specified
    """
    volatility = _create_volatility_estimator(
        config.volatility_type,
        config.volatility_params or {},
    )
    reservation = _create_reservation_calculator(
        config.reservation_type,
        config.reservation_params or {},
    )
    skew = _create_skew_calculator(
        config.skew_type,
        config.skew_params or {},
    )
    spread = _create_spread_calculator(
        config.spread_type,
        config.spread_params or {},
    )
    sizer = _create_sizer(
        config.sizer_type,
        config.sizer_params or {},
    )

    return StrategyEngine(
        volatility_estimator=volatility,
        reservation_calculator=reservation,
        skew_calculator=skew,
        spread_calculator=spread,
        sizer=sizer,
    )


def _create_volatility_estimator(
    estimator_type: str,
    params: dict[str, str],
) -> VolatilityEstimator:
    """Create a volatility estimator from config.

    Args:
        estimator_type: Type of estimator (fixed, ewma)
        params: Estimator-specific parameters

    Returns:
        Configured VolatilityEstimator

    Raises:
        ValueError: If unknown type
    """
    if estimator_type == "fixed":
        volatility = Decimal(params.get("volatility", "0.10"))
        return FixedVolatilityEstimator(volatility=volatility)

    elif estimator_type == "ewma":
        alpha = Decimal(params.get("alpha", "0.1"))
        initial_volatility = Decimal(params.get("initial_volatility", "0.10"))
        min_samples = int(params.get("min_samples", "2"))
        return EWMAVolatilityEstimator(
            alpha=alpha,
            initial_volatility=initial_volatility,
            min_samples=min_samples,
        )

    else:
        raise ValueError(f"Unknown volatility type: {estimator_type}")


def _create_reservation_calculator(
    calc_type: str,
    params: dict[str, str],
) -> ReservationPriceCalculator:
    """Create a reservation price calculator from config.

    Args:
        calc_type: Type of calculator (avellaneda_stoikov)
        params: Calculator-specific parameters

    Returns:
        Configured ReservationPriceCalculator

    Raises:
        ValueError: If unknown type
    """
    if calc_type == "avellaneda_stoikov":
        gamma = Decimal(params.get("gamma", "0.1"))
        return AvellanedaStoikovReservation(gamma=gamma)

    else:
        raise ValueError(f"Unknown reservation type: {calc_type}")


def _create_skew_calculator(
    calc_type: str,
    params: dict[str, str],
) -> SkewCalculator:
    """Create a skew calculator from config.

    Args:
        calc_type: Type of calculator (linear)
        params: Calculator-specific parameters

    Returns:
        Configured SkewCalculator

    Raises:
        ValueError: If unknown type
    """
    if calc_type == "linear":
        intensity = Decimal(params.get("intensity", "0.01"))
        return LinearSkew(intensity=intensity)

    else:
        raise ValueError(f"Unknown skew type: {calc_type}")


def _create_spread_calculator(
    calc_type: str,
    params: dict[str, str],
) -> SpreadCalculator:
    """Create a spread calculator from config.

    Args:
        calc_type: Type of calculator (fixed)
        params: Calculator-specific parameters

    Returns:
        Configured SpreadCalculator

    Raises:
        ValueError: If unknown type
    """
    if calc_type == "fixed":
        base_spread = Decimal(params.get("base_spread", "0.02"))
        min_spread = Decimal(params.get("min_spread", "0"))
        return FixedSpread(base_spread=base_spread, min_spread=min_spread)

    else:
        raise ValueError(f"Unknown spread type: {calc_type}")


def _create_sizer(
    sizer_type: str,
    params: dict[str, str],  # noqa: ARG001
) -> QuoteSizer:
    """Create a quote sizer from config.

    Args:
        sizer_type: Type of sizer (asymmetric)
        params: Sizer-specific parameters (currently unused)

    Returns:
        Configured QuoteSizer

    Raises:
        ValueError: If unknown type
    """
    if sizer_type == "asymmetric":
        return AsymmetricSizer()

    else:
        raise ValueError(f"Unknown sizer type: {sizer_type}")
