"""SQLAlchemy models for trading data persistence.

Stores orders, fills, and PnL snapshots in SQLite.
"""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal

from sqlalchemy import DateTime, Integer, Numeric, String
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    """Base class for all models."""

    pass


class OrderRecord(Base):
    """Persisted order record."""

    __tablename__ = "orders"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    client_order_id: Mapped[str] = mapped_column(String(64), index=True)
    market_id: Mapped[str] = mapped_column(String(128), index=True)
    side: Mapped[str] = mapped_column(String(8))  # "yes" or "no"
    order_side: Mapped[str] = mapped_column(String(8))  # "buy" or "sell"
    price: Mapped[Decimal] = mapped_column(Numeric(10, 4))
    size: Mapped[int] = mapped_column(Integer)
    filled_size: Mapped[int] = mapped_column(Integer, default=0)
    status: Mapped[str] = mapped_column(String(32), index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    session_id: Mapped[str] = mapped_column(String(64), index=True)

    def __repr__(self) -> str:
        return (
            f"OrderRecord(id={self.id!r}, market={self.market_id!r}, "
            f"{self.order_side} {self.size} {self.side} @ {self.price}, "
            f"status={self.status!r})"
        )


class FillRecord(Base):
    """Persisted fill record."""

    __tablename__ = "fills"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    order_id: Mapped[str] = mapped_column(String(64), index=True)
    market_id: Mapped[str] = mapped_column(String(128), index=True)
    side: Mapped[str] = mapped_column(String(8))  # "yes" or "no"
    order_side: Mapped[str] = mapped_column(String(8))  # "buy" or "sell"
    price: Mapped[Decimal] = mapped_column(Numeric(10, 4))
    size: Mapped[int] = mapped_column(Integer)
    timestamp: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    is_simulated: Mapped[bool] = mapped_column(default=False)
    session_id: Mapped[str] = mapped_column(String(64), index=True)

    def __repr__(self) -> str:
        return (
            f"FillRecord(id={self.id!r}, order={self.order_id!r}, "
            f"{self.size} @ {self.price})"
        )


class PnLRecord(Base):
    """Persisted PnL snapshot record."""

    __tablename__ = "pnl_snapshots"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    market_id: Mapped[str] = mapped_column(String(128), index=True)
    timestamp: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    realized_pnl: Mapped[Decimal] = mapped_column(Numeric(16, 4))
    unrealized_pnl: Mapped[Decimal] = mapped_column(Numeric(16, 4))
    total_pnl: Mapped[Decimal] = mapped_column(Numeric(16, 4))
    yes_position: Mapped[int] = mapped_column(Integer)
    no_position: Mapped[int] = mapped_column(Integer)
    yes_avg_price: Mapped[Decimal] = mapped_column(Numeric(10, 4), nullable=True)
    no_avg_price: Mapped[Decimal] = mapped_column(Numeric(10, 4), nullable=True)
    session_id: Mapped[str] = mapped_column(String(64), index=True)

    def __repr__(self) -> str:
        return (
            f"PnLRecord(market={self.market_id!r}, "
            f"total_pnl={self.total_pnl}, timestamp={self.timestamp})"
        )
