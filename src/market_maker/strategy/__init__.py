"""Strategy module for market making quote generation.

This package contains:
- StrategyEngine: Composes pluggable components to generate quotes
- Component ABCs and implementations: volatility, reservation, skew, spread, sizer
- Factory functions for building strategies from configuration
"""

from market_maker.strategy.engine import StrategyEngine, StrategyInput
from market_maker.strategy.factory import StrategyConfig, create_strategy_engine

__all__ = [
    "StrategyEngine",
    "StrategyInput",
    "StrategyConfig",
    "create_strategy_engine",
]
