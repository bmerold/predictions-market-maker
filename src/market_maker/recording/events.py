"""Recording event types.

Defines event types for session recording and replay.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal
from enum import Enum
from typing import Any


class RecordingEventType(str, Enum):
    """Types of events that can be recorded."""

    # Market data events
    BOOK_SNAPSHOT = "book_snapshot"
    BOOK_UPDATE = "book_update"
    TRADE = "trade"

    # Order events
    ORDER_PLACED = "order_placed"
    ORDER_CANCELLED = "order_cancelled"
    ORDER_FILLED = "order_filled"
    ORDER_UPDATED = "order_updated"

    # Strategy events
    QUOTE_GENERATED = "quote_generated"
    QUOTE_EXECUTED = "quote_executed"

    # Risk events
    RISK_CHECK = "risk_check"
    RISK_VIOLATION = "risk_violation"
    KILL_SWITCH = "kill_switch"

    # System events
    SESSION_START = "session_start"
    SESSION_END = "session_end"
    CONFIG_CHANGE = "config_change"
    ERROR = "error"

    # PnL events
    PNL_SNAPSHOT = "pnl_snapshot"


@dataclass(frozen=True)
class RecordingEvent:
    """Event for session recording.

    All trading activity is recorded as events for replay and analysis.
    """

    event_type: RecordingEventType
    timestamp: datetime
    market_id: str | None = None
    data: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            "event_type": self.event_type.value,
            "timestamp": self.timestamp.isoformat(),
            "market_id": self.market_id,
            "data": self._serialize_data(self.data),
        }

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> RecordingEvent:
        """Create from dictionary."""
        return cls(
            event_type=RecordingEventType(d["event_type"]),
            timestamp=datetime.fromisoformat(d["timestamp"]),
            market_id=d.get("market_id"),
            data=d.get("data", {}),
        )

    def _serialize_data(self, data: dict[str, Any]) -> dict[str, Any]:
        """Serialize data values for JSON."""
        result = {}
        for key, value in data.items():
            if isinstance(value, Decimal):
                result[key] = str(value)
            elif isinstance(value, datetime):
                result[key] = value.isoformat()
            elif isinstance(value, dict):
                result[key] = self._serialize_data(value)
            elif isinstance(value, list):
                result[key] = [
                    self._serialize_item(item) for item in value
                ]
            else:
                result[key] = value
        return result

    def _serialize_item(self, item: Any) -> Any:
        """Serialize a single item."""
        if isinstance(item, Decimal):
            return str(item)
        elif isinstance(item, datetime):
            return item.isoformat()
        elif isinstance(item, dict):
            return self._serialize_data(item)
        return item
