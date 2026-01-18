"""Checkpointing and crash recovery support.

Provides:
- State checkpointing for crash recovery
- Graceful shutdown with order draining
- Position reconciliation with exchange
"""

from __future__ import annotations

import asyncio
import json
import logging
import signal
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path
from typing import TYPE_CHECKING, Any, Callable

if TYPE_CHECKING:
    from market_maker.execution.base import ExecutionEngine
    from market_maker.state.store import StateStore

logger = logging.getLogger(__name__)


@dataclass
class Checkpoint:
    """Checkpoint of trading state.

    Captures enough state to recover after a crash.
    """

    session_id: str
    timestamp: str
    market_id: str

    # Position state
    yes_position: int
    no_position: int
    avg_yes_price: str | None
    avg_no_price: str | None

    # PnL state
    realized_pnl: str
    unrealized_pnl: str

    # Open orders
    open_order_ids: list[str]

    # Config snapshot
    config_hash: str | None = None

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Checkpoint:
        """Create from dictionary."""
        return cls(**data)


class CheckpointManager:
    """Manages checkpoints for crash recovery.

    Features:
    - Periodic checkpointing
    - Checkpoint storage (file-based)
    - Recovery from latest checkpoint
    """

    def __init__(
        self,
        checkpoint_dir: str | Path = "checkpoints",
        checkpoint_interval: float = 60.0,
    ) -> None:
        """Initialize checkpoint manager.

        Args:
            checkpoint_dir: Directory for checkpoint files
            checkpoint_interval: Seconds between checkpoints
        """
        self._checkpoint_dir = Path(checkpoint_dir)
        self._checkpoint_dir.mkdir(parents=True, exist_ok=True)
        self._checkpoint_interval = checkpoint_interval

        self._session_id: str | None = None
        self._running = False
        self._task: asyncio.Task | None = None

        # Callbacks to get current state
        self._get_state: Callable[[], list[Checkpoint]] | None = None

    def set_state_provider(
        self,
        provider: Callable[[], list[Checkpoint]],
    ) -> None:
        """Set callback to get current state.

        Args:
            provider: Function that returns list of checkpoints
        """
        self._get_state = provider

    def _get_checkpoint_path(self, market_id: str) -> Path:
        """Get checkpoint file path for a market."""
        safe_id = market_id.replace("/", "_").replace(":", "_")
        return self._checkpoint_dir / f"checkpoint_{safe_id}.json"

    def save_checkpoint(self, checkpoint: Checkpoint) -> None:
        """Save a checkpoint.

        Args:
            checkpoint: Checkpoint to save
        """
        path = self._get_checkpoint_path(checkpoint.market_id)

        # Write atomically
        tmp_path = path.with_suffix(".tmp")
        with open(tmp_path, "w") as f:
            json.dump(checkpoint.to_dict(), f, indent=2)
        tmp_path.rename(path)

        logger.debug(f"Checkpoint saved for {checkpoint.market_id}")

    def load_checkpoint(self, market_id: str) -> Checkpoint | None:
        """Load checkpoint for a market.

        Args:
            market_id: Market ID

        Returns:
            Checkpoint or None if not found
        """
        path = self._get_checkpoint_path(market_id)
        if not path.exists():
            return None

        try:
            with open(path) as f:
                data = json.load(f)
            return Checkpoint.from_dict(data)
        except (json.JSONDecodeError, KeyError) as e:
            logger.error(f"Failed to load checkpoint: {e}")
            return None

    def list_checkpoints(self) -> list[str]:
        """List all available checkpoint market IDs.

        Returns:
            List of market IDs with checkpoints
        """
        market_ids = []
        for path in self._checkpoint_dir.glob("checkpoint_*.json"):
            # Extract market ID from filename
            name = path.stem.replace("checkpoint_", "")
            market_ids.append(name)
        return market_ids

    def delete_checkpoint(self, market_id: str) -> bool:
        """Delete checkpoint for a market.

        Args:
            market_id: Market ID

        Returns:
            True if deleted
        """
        path = self._get_checkpoint_path(market_id)
        if path.exists():
            path.unlink()
            return True
        return False

    async def _checkpoint_loop(self) -> None:
        """Background loop for periodic checkpointing."""
        while self._running:
            try:
                if self._get_state:
                    checkpoints = self._get_state()
                    for checkpoint in checkpoints:
                        self.save_checkpoint(checkpoint)
            except Exception as e:
                logger.error(f"Error during checkpointing: {e}")

            await asyncio.sleep(self._checkpoint_interval)

    def start(self, session_id: str) -> None:
        """Start periodic checkpointing.

        Args:
            session_id: Trading session ID
        """
        if self._running:
            return

        self._session_id = session_id
        self._running = True
        self._task = asyncio.create_task(self._checkpoint_loop())
        logger.info("Checkpoint manager started")

    def stop(self) -> None:
        """Stop periodic checkpointing."""
        self._running = False
        if self._task:
            self._task.cancel()
            self._task = None

        # Save final checkpoint
        if self._get_state:
            try:
                checkpoints = self._get_state()
                for checkpoint in checkpoints:
                    self.save_checkpoint(checkpoint)
                logger.info("Final checkpoints saved")
            except Exception as e:
                logger.error(f"Error saving final checkpoint: {e}")

        logger.info("Checkpoint manager stopped")


class GracefulShutdown:
    """Manages graceful shutdown of the trading system.

    Features:
    - Signal handling (SIGINT, SIGTERM)
    - Order draining before exit
    - Position closing (optional)
    - Checkpoint saving
    """

    def __init__(
        self,
        drain_timeout: float = 30.0,
        cancel_orders: bool = True,
        close_positions: bool = False,
    ) -> None:
        """Initialize graceful shutdown handler.

        Args:
            drain_timeout: Max seconds to wait for drain
            cancel_orders: Cancel open orders on shutdown
            close_positions: Close positions on shutdown (dangerous)
        """
        self._drain_timeout = drain_timeout
        self._cancel_orders = cancel_orders
        self._close_positions = close_positions

        self._shutting_down = False
        self._shutdown_event = asyncio.Event()

        # Components to shutdown
        self._execution_engine: ExecutionEngine | None = None
        self._checkpoint_manager: CheckpointManager | None = None
        self._on_shutdown: Callable[[], Any] | None = None

    @property
    def is_shutting_down(self) -> bool:
        """Check if shutdown is in progress."""
        return self._shutting_down

    def set_execution_engine(self, engine: ExecutionEngine) -> None:
        """Set execution engine for order cancellation."""
        self._execution_engine = engine

    def set_checkpoint_manager(self, manager: CheckpointManager) -> None:
        """Set checkpoint manager for final save."""
        self._checkpoint_manager = manager

    def set_shutdown_callback(self, callback: Callable[[], Any]) -> None:
        """Set callback to run during shutdown."""
        self._on_shutdown = callback

    def setup_signal_handlers(self) -> None:
        """Setup signal handlers for graceful shutdown."""
        loop = asyncio.get_running_loop()

        for sig in (signal.SIGINT, signal.SIGTERM):
            loop.add_signal_handler(
                sig,
                lambda: asyncio.create_task(self.initiate_shutdown()),
            )

        logger.info("Signal handlers configured")

    async def initiate_shutdown(self) -> None:
        """Initiate graceful shutdown."""
        if self._shutting_down:
            logger.warning("Shutdown already in progress")
            return

        self._shutting_down = True
        logger.info("Initiating graceful shutdown...")

        try:
            # Cancel open orders
            if self._cancel_orders and self._execution_engine:
                await self._cancel_all_orders()

            # Run custom shutdown callback
            if self._on_shutdown:
                try:
                    result = self._on_shutdown()
                    if asyncio.iscoroutine(result):
                        await result
                except Exception as e:
                    logger.error(f"Error in shutdown callback: {e}")

            # Save final checkpoint
            if self._checkpoint_manager:
                self._checkpoint_manager.stop()

        except Exception as e:
            logger.error(f"Error during shutdown: {e}")
        finally:
            self._shutdown_event.set()
            logger.info("Shutdown complete")

    async def _cancel_all_orders(self) -> None:
        """Cancel all open orders."""
        if not self._execution_engine:
            return

        logger.info("Cancelling open orders...")

        # Get all markets with open orders
        # Note: This would need to track which markets are active
        # For now, this is a placeholder
        pass

    async def wait_for_shutdown(self) -> None:
        """Wait for shutdown to complete."""
        await self._shutdown_event.wait()


class PositionReconciler:
    """Reconciles local position state with exchange.

    Used during startup and periodically to ensure consistency.
    """

    def __init__(
        self,
        state_store: StateStore,
        max_divergence: int = 5,
    ) -> None:
        """Initialize reconciler.

        Args:
            state_store: Local state store
            max_divergence: Max position divergence before alert
        """
        self._state_store = state_store
        self._max_divergence = max_divergence

    async def reconcile(
        self,
        market_id: str,
        exchange_yes_position: int,
        exchange_no_position: int,
    ) -> dict[str, Any]:
        """Reconcile local position with exchange.

        Args:
            market_id: Market ID
            exchange_yes_position: Position from exchange
            exchange_no_position: Position from exchange

        Returns:
            Reconciliation result
        """
        local = self._state_store.get_position(market_id)

        local_yes = local.yes_quantity if local else 0
        local_no = local.no_quantity if local else 0

        yes_diff = exchange_yes_position - local_yes
        no_diff = exchange_no_position - local_no

        result = {
            "market_id": market_id,
            "timestamp": datetime.now(UTC).isoformat(),
            "local_yes": local_yes,
            "local_no": local_no,
            "exchange_yes": exchange_yes_position,
            "exchange_no": exchange_no_position,
            "yes_divergence": yes_diff,
            "no_divergence": no_diff,
            "synced": yes_diff == 0 and no_diff == 0,
        }

        # Check for significant divergence
        if abs(yes_diff) > self._max_divergence:
            logger.warning(
                f"YES position divergence for {market_id}: "
                f"local={local_yes}, exchange={exchange_yes_position}"
            )
            result["warning"] = "yes_position_divergence"

        if abs(no_diff) > self._max_divergence:
            logger.warning(
                f"NO position divergence for {market_id}: "
                f"local={local_no}, exchange={exchange_no_position}"
            )
            result["warning"] = "no_position_divergence"

        return result

    async def sync_from_exchange(
        self,
        market_id: str,
        exchange_yes_position: int,
        exchange_no_position: int,
    ) -> None:
        """Sync local position from exchange (trust exchange).

        Args:
            market_id: Market ID
            exchange_yes_position: Position from exchange
            exchange_no_position: Position from exchange
        """
        # Update local state to match exchange
        # Note: This would need StateStore to support position updates
        logger.info(
            f"Syncing position for {market_id} from exchange: "
            f"YES={exchange_yes_position}, NO={exchange_no_position}"
        )
