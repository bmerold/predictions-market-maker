"""Tests for BacktestEngine."""

import json
import tempfile
from decimal import Decimal
from pathlib import Path

import pytest

from market_maker.backtest.engine import BacktestEngine
from market_maker.domain.types import Side
from market_maker.execution.paper import PaperExecutionEngine
from market_maker.risk.manager import RiskManager
from market_maker.risk.rules.position import MaxInventoryRule
from market_maker.state.store import StateStore
from market_maker.strategy.components.reservation import AvellanedaStoikovReservation
from market_maker.strategy.components.sizer import AsymmetricSizer
from market_maker.strategy.components.skew import LinearSkew
from market_maker.strategy.components.spread import FixedSpread
from market_maker.strategy.engine import StrategyEngine
from market_maker.strategy.volatility.fixed import FixedVolatilityEstimator


def make_sample_recording(
    num_ticks: int = 10,
    best_bid: float = 0.48,
    best_ask: float = 0.52,
) -> dict:
    """Create a sample recording with controllable parameters."""
    ticks = []
    for i in range(num_ticks):
        ticks.append(
            {
                "timestamp": f"2025-12-15T20:19:{i:02d}.000000+00:00",
                "tick_number": i + 1,
                "time_to_close_seconds": 3600.0 - (i * 0.5),  # 1 hour countdown
                "market_ticker": "TEST-MARKET",
                "event_ticker": "TEST",
                "orderbook": {
                    "yes_bids": [
                        {"price": best_bid, "quantity": 1000},
                        {"price": best_bid - 0.01, "quantity": 2000},
                    ],
                    "yes_asks": [
                        {"price": best_ask, "quantity": 1000},
                        {"price": best_ask + 0.01, "quantity": 2000},
                    ],
                    "no_bids": [
                        {"price": 1.0 - best_ask, "quantity": 1000},
                    ],
                    "no_asks": [
                        {"price": 1.0 - best_bid, "quantity": 1000},
                    ],
                    "best_yes_bid": best_bid,
                    "best_yes_ask": best_ask,
                    "best_no_bid": 1.0 - best_ask,
                    "best_no_ask": 1.0 - best_bid,
                },
            }
        )

    return {
        "market_ticker": "TEST-MARKET",
        "event_ticker": "TEST",
        "recording_started": "2025-12-15T20:19:00.000000+00:00",
        "recording_ended": "2025-12-15T21:00:00.000000+00:00",
        "market_close_time": "2025-12-15T21:00:00+00:00",
        "tick_interval_ms": 500,
        "orderbook_depth": 10,
        "ticks": ticks,
    }


def make_strategy() -> StrategyEngine:
    """Create a strategy engine for testing."""
    return StrategyEngine(
        volatility_estimator=FixedVolatilityEstimator(Decimal("0.1")),
        reservation_calculator=AvellanedaStoikovReservation(gamma=Decimal("0.1")),
        skew_calculator=LinearSkew(intensity=Decimal("0.05")),
        spread_calculator=FixedSpread(base_spread=Decimal("0.02")),
        sizer=AsymmetricSizer(),
    )


class TestBacktestEngine:
    """Tests for BacktestEngine."""

    @pytest.fixture
    def strategy(self) -> StrategyEngine:
        """Create a test strategy."""
        return make_strategy()

    @pytest.fixture
    def sample_file(self) -> Path:
        """Create a temporary recording file."""
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".json", delete=False
        ) as f:
            json.dump(make_sample_recording(), f)
            return Path(f.name)

    def test_run_returns_result(
        self, strategy: StrategyEngine, sample_file: Path
    ) -> None:
        """Running backtest returns BacktestResult."""
        engine = BacktestEngine(strategy=strategy)
        result = engine.run(sample_file)

        assert result is not None
        assert result.metadata.market_ticker == "TEST-MARKET"
        assert result.total_ticks == 10

    def test_result_has_statistics(
        self, strategy: StrategyEngine, sample_file: Path
    ) -> None:
        """BacktestResult includes statistics."""
        engine = BacktestEngine(strategy=strategy)
        result = engine.run(sample_file)

        assert result.quotes_generated > 0
        assert isinstance(result.realized_pnl, Decimal)
        assert isinstance(result.max_drawdown, Decimal)

    def test_skip_ticks(self, strategy: StrategyEngine, sample_file: Path) -> None:
        """Can skip initial ticks."""
        engine = BacktestEngine(strategy=strategy)
        result = engine.run(sample_file, skip_ticks=5)

        assert result.total_ticks == 5

    def test_max_ticks(self, strategy: StrategyEngine, sample_file: Path) -> None:
        """Can limit max ticks processed."""
        engine = BacktestEngine(strategy=strategy)
        result = engine.run(sample_file, max_ticks=3)

        assert result.total_ticks == 3

    def test_with_risk_manager(
        self, strategy: StrategyEngine, sample_file: Path
    ) -> None:
        """Backtest integrates with risk manager."""
        risk_manager = RiskManager(rules=[MaxInventoryRule(max_inventory=50)])
        engine = BacktestEngine(strategy=strategy, risk_manager=risk_manager)

        result = engine.run(sample_file)

        # Should still run, risk manager may modify quotes
        assert result.quotes_generated > 0

    def test_settlement_yes(self, strategy: StrategyEngine) -> None:
        """Settlement YES calculates correct PnL."""
        # Create a recording where we'd buy YES
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".json", delete=False
        ) as f:
            json.dump(make_sample_recording(num_ticks=5), f)
            file_path = Path(f.name)

        engine = BacktestEngine(strategy=strategy)
        result = engine.run(file_path, settlement=Side.YES)

        # Result should include settlement PnL
        assert isinstance(result.settlement_pnl, Decimal)
        assert isinstance(result.total_pnl, Decimal)

    def test_settlement_no(self, strategy: StrategyEngine) -> None:
        """Settlement NO calculates correct PnL."""
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".json", delete=False
        ) as f:
            json.dump(make_sample_recording(num_ticks=5), f)
            file_path = Path(f.name)

        engine = BacktestEngine(strategy=strategy)
        result = engine.run(file_path, settlement=Side.NO)

        assert isinstance(result.settlement_pnl, Decimal)

    def test_custom_state_store(
        self, strategy: StrategyEngine, sample_file: Path
    ) -> None:
        """Can provide custom state store."""
        state_store = StateStore(fee_rate=Decimal("0.01"))  # 1% fees
        engine = BacktestEngine(strategy=strategy, state_store=state_store)

        result = engine.run(sample_file)

        # If there were fills, should have fees
        # (may be zero if no fills crossed)
        assert isinstance(result.total_fees, Decimal)

    def test_custom_execution_engine(
        self, strategy: StrategyEngine, sample_file: Path
    ) -> None:
        """Can provide custom execution engine."""
        execution = PaperExecutionEngine()
        engine = BacktestEngine(strategy=strategy, execution_engine=execution)

        result = engine.run(sample_file)

        # Fills from the provided engine should be in result
        assert result.fills == execution.get_fills()

    def test_result_net_position(
        self, strategy: StrategyEngine, sample_file: Path
    ) -> None:
        """Result has net_position property."""
        engine = BacktestEngine(strategy=strategy)
        result = engine.run(sample_file)

        expected = result.final_yes_position - result.final_no_position
        assert result.net_position == expected

    def test_result_fill_rate(
        self, strategy: StrategyEngine, sample_file: Path
    ) -> None:
        """Result has fill_rate property."""
        engine = BacktestEngine(strategy=strategy)
        result = engine.run(sample_file)

        if result.quotes_generated > 0:
            expected = result.total_fills / result.quotes_generated
            assert result.fill_rate == expected
        else:
            assert result.fill_rate == 0.0

    def test_result_block_rate(
        self, strategy: StrategyEngine, sample_file: Path
    ) -> None:
        """Result has block_rate property."""
        engine = BacktestEngine(strategy=strategy)
        result = engine.run(sample_file)

        if result.quotes_generated > 0:
            expected = result.quotes_blocked / result.quotes_generated
            assert result.block_rate == expected
        else:
            assert result.block_rate == 0.0


class TestBacktestEngineIntegration:
    """Integration tests for BacktestEngine."""

    def test_full_backtest_flow(self) -> None:
        """Full integration test with all components."""
        # Create strategy
        strategy = make_strategy()

        # Create risk manager with position limit
        risk_manager = RiskManager(rules=[MaxInventoryRule(max_inventory=500)])

        # Create state store with fees
        state_store = StateStore(fee_rate=Decimal("0.005"))  # 0.5% fees

        # Create execution engine
        execution = PaperExecutionEngine()

        # Create recording
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".json", delete=False
        ) as f:
            json.dump(make_sample_recording(num_ticks=20), f)
            file_path = Path(f.name)

        # Run backtest
        engine = BacktestEngine(
            strategy=strategy,
            risk_manager=risk_manager,
            state_store=state_store,
            execution_engine=execution,
        )

        result = engine.run(file_path, settlement=Side.YES)

        # Verify all components worked together
        assert result.total_ticks == 20
        assert result.quotes_generated > 0
        assert result.metadata.market_ticker == "TEST-MARKET"
        # Total PnL should be sum of realized + unrealized + settlement
        expected_total = (
            result.realized_pnl + result.unrealized_pnl + result.settlement_pnl
        )
        assert result.total_pnl == expected_total
