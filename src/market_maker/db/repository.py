"""Repository for trading data access.

Provides a clean interface for persisting and querying trading data.
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime
from decimal import Decimal
from typing import TYPE_CHECKING

from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session, sessionmaker

from market_maker.db.models import Base, FillRecord, OrderRecord, PnLRecord
from market_maker.domain.orders import Fill, Order, OrderStatus
from market_maker.domain.positions import PnLSnapshot
from market_maker.domain.types import OrderSide, Price, Quantity, Side

if TYPE_CHECKING:
    from sqlalchemy.engine import Engine

logger = logging.getLogger(__name__)


class TradingRepository:
    """Repository for persisting trading data.

    Handles CRUD operations for orders, fills, and PnL snapshots.
    Thread-safe with session-per-operation pattern.
    """

    def __init__(
        self,
        db_url: str = "sqlite:///trading.db",
        session_id: str | None = None,
    ) -> None:
        """Initialize repository.

        Args:
            db_url: SQLAlchemy database URL
            session_id: Trading session identifier
        """
        self._engine: Engine = create_engine(db_url, echo=False)
        self._session_factory = sessionmaker(bind=self._engine)
        self._session_id = session_id or datetime.now(UTC).strftime("%Y%m%d_%H%M%S")

        # Create tables if they don't exist
        Base.metadata.create_all(self._engine)
        logger.info(f"Repository initialized with session {self._session_id}")

    @property
    def session_id(self) -> str:
        """Get current session ID."""
        return self._session_id

    def _get_session(self) -> Session:
        """Create a new database session."""
        return self._session_factory()

    # --- Order Operations ---

    def save_order(self, order: Order) -> None:
        """Save or update an order.

        Args:
            order: Order to persist
        """
        with self._get_session() as session:
            record = session.get(OrderRecord, order.id)
            if record:
                # Update existing
                record.filled_size = order.filled_size
                record.status = order.status.value
                record.updated_at = order.updated_at
            else:
                # Insert new
                record = OrderRecord(
                    id=order.id,
                    client_order_id=order.client_order_id,
                    market_id=order.market_id,
                    side=order.side.value,
                    order_side=order.order_side.value,
                    price=order.price.value,
                    size=order.size.value,
                    filled_size=order.filled_size,
                    status=order.status.value,
                    created_at=order.created_at,
                    updated_at=order.updated_at,
                    session_id=self._session_id,
                )
                session.add(record)
            session.commit()

    def get_order(self, order_id: str) -> Order | None:
        """Get an order by ID.

        Args:
            order_id: Order ID

        Returns:
            Order or None if not found
        """
        with self._get_session() as session:
            record = session.get(OrderRecord, order_id)
            if not record:
                return None
            return self._order_from_record(record)

    def get_orders_by_market(
        self,
        market_id: str,
        status: OrderStatus | None = None,
    ) -> list[Order]:
        """Get orders for a market.

        Args:
            market_id: Market ID
            status: Optional filter by status

        Returns:
            List of orders
        """
        with self._get_session() as session:
            stmt = select(OrderRecord).where(
                OrderRecord.market_id == market_id,
                OrderRecord.session_id == self._session_id,
            )
            if status:
                stmt = stmt.where(OrderRecord.status == status.value)

            records = session.execute(stmt).scalars().all()
            return [self._order_from_record(r) for r in records]

    def get_orders_by_session(self) -> list[Order]:
        """Get all orders for current session.

        Returns:
            List of orders
        """
        with self._get_session() as session:
            stmt = select(OrderRecord).where(
                OrderRecord.session_id == self._session_id
            )
            records = session.execute(stmt).scalars().all()
            return [self._order_from_record(r) for r in records]

    def _order_from_record(self, record: OrderRecord) -> Order:
        """Convert database record to domain Order."""
        return Order(
            id=record.id,
            client_order_id=record.client_order_id,
            market_id=record.market_id,
            side=Side(record.side),
            order_side=OrderSide(record.order_side),
            price=Price(record.price),
            size=Quantity(int(record.size)),
            filled_size=int(record.filled_size),
            status=OrderStatus(record.status),
            created_at=record.created_at,
            updated_at=record.updated_at,
        )

    # --- Fill Operations ---

    def save_fill(self, fill: Fill) -> None:
        """Save a fill.

        Args:
            fill: Fill to persist
        """
        with self._get_session() as session:
            record = FillRecord(
                id=fill.id,
                order_id=fill.order_id,
                market_id=fill.market_id,
                side=fill.side.value,
                order_side=fill.order_side.value,
                price=fill.price.value,
                size=fill.size.value,
                timestamp=fill.timestamp,
                is_simulated=fill.is_simulated,
                session_id=self._session_id,
            )
            session.merge(record)  # Use merge to handle duplicates
            session.commit()

    def get_fills_by_order(self, order_id: str) -> list[Fill]:
        """Get fills for an order.

        Args:
            order_id: Order ID

        Returns:
            List of fills
        """
        with self._get_session() as session:
            stmt = select(FillRecord).where(FillRecord.order_id == order_id)
            records = session.execute(stmt).scalars().all()
            return [self._fill_from_record(r) for r in records]

    def get_fills_by_market(
        self,
        market_id: str,
        since: datetime | None = None,
    ) -> list[Fill]:
        """Get fills for a market.

        Args:
            market_id: Market ID
            since: Optional start timestamp

        Returns:
            List of fills
        """
        with self._get_session() as session:
            stmt = select(FillRecord).where(
                FillRecord.market_id == market_id,
                FillRecord.session_id == self._session_id,
            )
            if since:
                stmt = stmt.where(FillRecord.timestamp >= since)
            stmt = stmt.order_by(FillRecord.timestamp)

            records = session.execute(stmt).scalars().all()
            return [self._fill_from_record(r) for r in records]

    def get_fills_by_session(self) -> list[Fill]:
        """Get all fills for current session.

        Returns:
            List of fills
        """
        with self._get_session() as session:
            stmt = (
                select(FillRecord)
                .where(FillRecord.session_id == self._session_id)
                .order_by(FillRecord.timestamp)
            )
            records = session.execute(stmt).scalars().all()
            return [self._fill_from_record(r) for r in records]

    def _fill_from_record(self, record: FillRecord) -> Fill:
        """Convert database record to domain Fill."""
        return Fill(
            id=record.id,
            order_id=record.order_id,
            market_id=record.market_id,
            side=Side(record.side),
            order_side=OrderSide(record.order_side),
            price=Price(record.price),
            size=Quantity(int(record.size)),
            timestamp=record.timestamp,
            is_simulated=record.is_simulated,
        )

    # --- PnL Operations ---

    def save_pnl_snapshot(
        self,
        market_id: str,
        snapshot: PnLSnapshot,
    ) -> None:
        """Save a PnL snapshot.

        Args:
            market_id: Market ID
            snapshot: PnL snapshot to persist
        """
        position = snapshot.positions.get(market_id)
        with self._get_session() as session:
            record = PnLRecord(
                market_id=market_id,
                timestamp=snapshot.timestamp,
                realized_pnl=snapshot.realized_pnl,
                unrealized_pnl=snapshot.unrealized_pnl,
                total_pnl=snapshot.total_pnl,
                yes_position=position.yes_quantity if position else 0,
                no_position=position.no_quantity if position else 0,
                yes_avg_price=(
                    position.avg_yes_price.value
                    if position and position.avg_yes_price
                    else None
                ),
                no_avg_price=(
                    position.avg_no_price.value
                    if position and position.avg_no_price
                    else None
                ),
                session_id=self._session_id,
            )
            session.add(record)
            session.commit()

    def get_pnl_history(
        self,
        market_id: str,
        since: datetime | None = None,
    ) -> list[dict]:
        """Get PnL history for a market.

        Args:
            market_id: Market ID
            since: Optional start timestamp

        Returns:
            List of PnL snapshot dicts
        """
        with self._get_session() as session:
            stmt = select(PnLRecord).where(
                PnLRecord.market_id == market_id,
                PnLRecord.session_id == self._session_id,
            )
            if since:
                stmt = stmt.where(PnLRecord.timestamp >= since)
            stmt = stmt.order_by(PnLRecord.timestamp)

            records = session.execute(stmt).scalars().all()
            return [
                {
                    "timestamp": r.timestamp,
                    "realized_pnl": float(r.realized_pnl),
                    "unrealized_pnl": float(r.unrealized_pnl),
                    "total_pnl": float(r.total_pnl),
                    "yes_position": r.yes_position,
                    "no_position": r.no_position,
                }
                for r in records
            ]

    def get_latest_pnl(self, market_id: str) -> dict | None:
        """Get latest PnL snapshot for a market.

        Args:
            market_id: Market ID

        Returns:
            Latest PnL snapshot dict or None
        """
        with self._get_session() as session:
            stmt = (
                select(PnLRecord)
                .where(
                    PnLRecord.market_id == market_id,
                    PnLRecord.session_id == self._session_id,
                )
                .order_by(PnLRecord.timestamp.desc())
                .limit(1)
            )
            record = session.execute(stmt).scalar_one_or_none()
            if not record:
                return None
            return {
                "timestamp": record.timestamp,
                "realized_pnl": float(record.realized_pnl),
                "unrealized_pnl": float(record.unrealized_pnl),
                "total_pnl": float(record.total_pnl),
                "yes_position": record.yes_position,
                "no_position": record.no_position,
            }

    # --- Utility Methods ---

    def close(self) -> None:
        """Close database connection."""
        self._engine.dispose()
        logger.info("Repository closed")
