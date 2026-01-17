"""Execution module.

Provides execution engines for paper trading and live trading.
"""

from market_maker.execution.paper import PaperExecutionEngine

__all__ = ["PaperExecutionEngine"]
