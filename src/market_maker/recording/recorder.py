"""Session recorder for trading activity.

Records all trading events to compressed JSONL files for replay and analysis.
"""

from __future__ import annotations

import gzip
import json
import logging
from datetime import UTC, datetime
from pathlib import Path
from typing import TYPE_CHECKING, Any, Iterator

from market_maker.recording.events import RecordingEvent, RecordingEventType

if TYPE_CHECKING:
    from market_maker.domain.events import BookUpdate, FillEvent
    from market_maker.domain.market_data import OrderBook
    from market_maker.domain.orders import Fill, Order, QuoteSet

logger = logging.getLogger(__name__)


class SessionRecorder:
    """Records trading sessions to JSONL.gz files.

    Features:
    - Compressed output (gzip)
    - Append-mode writes for crash recovery
    - Event counting and statistics
    - Flush control for performance
    """

    def __init__(
        self,
        output_dir: str | Path = "recordings",
        session_id: str | None = None,
        flush_interval: int = 100,
    ) -> None:
        """Initialize recorder.

        Args:
            output_dir: Directory for recording files
            session_id: Session identifier (auto-generated if not provided)
            flush_interval: Flush to disk every N events
        """
        self._output_dir = Path(output_dir)
        self._output_dir.mkdir(parents=True, exist_ok=True)

        self._session_id = session_id or datetime.now(UTC).strftime("%Y%m%d_%H%M%S")
        self._file_path = self._output_dir / f"session_{self._session_id}.jsonl.gz"

        self._file: gzip.GzipFile | None = None
        self._event_count = 0
        self._flush_interval = flush_interval
        self._started = False

    @property
    def session_id(self) -> str:
        """Get session ID."""
        return self._session_id

    @property
    def file_path(self) -> Path:
        """Get recording file path."""
        return self._file_path

    @property
    def event_count(self) -> int:
        """Get number of events recorded."""
        return self._event_count

    def start(self, config: dict[str, Any] | None = None) -> None:
        """Start recording session.

        Args:
            config: Optional configuration to record
        """
        if self._started:
            return

        self._file = gzip.open(self._file_path, "at", encoding="utf-8")
        self._started = True

        # Record session start
        self.record_event(
            RecordingEvent(
                event_type=RecordingEventType.SESSION_START,
                timestamp=datetime.now(UTC),
                data={"session_id": self._session_id, "config": config or {}},
            )
        )

        logger.info(f"Recording started: {self._file_path}")

    def stop(self) -> None:
        """Stop recording session."""
        if not self._started:
            return

        # Record session end
        self.record_event(
            RecordingEvent(
                event_type=RecordingEventType.SESSION_END,
                timestamp=datetime.now(UTC),
                data={
                    "session_id": self._session_id,
                    "event_count": self._event_count,
                },
            )
        )

        if self._file:
            self._file.close()
            self._file = None

        self._started = False
        logger.info(f"Recording stopped: {self._event_count} events")

    def record_event(self, event: RecordingEvent) -> None:
        """Record a single event.

        Args:
            event: Event to record
        """
        if not self._file:
            return

        line = json.dumps(event.to_dict()) + "\n"
        self._file.write(line)
        self._event_count += 1

        if self._event_count % self._flush_interval == 0:
            self._file.flush()

    # --- Convenience Methods ---

    def record_book_snapshot(self, book: OrderBook) -> None:
        """Record order book snapshot.

        Args:
            book: Order book to record
        """
        self.record_event(
            RecordingEvent(
                event_type=RecordingEventType.BOOK_SNAPSHOT,
                timestamp=book.timestamp,
                market_id=book.market_id,
                data={
                    "yes_bids": [
                        {"price": str(l.price.value), "size": l.size.value}
                        for l in book.yes_bids
                    ],
                    "yes_asks": [
                        {"price": str(l.price.value), "size": l.size.value}
                        for l in book.yes_asks
                    ],
                },
            )
        )

    def record_book_update(self, update: BookUpdate) -> None:
        """Record order book update.

        Args:
            update: Book update to record
        """
        self.record_event(
            RecordingEvent(
                event_type=RecordingEventType.BOOK_UPDATE,
                timestamp=update.timestamp,
                market_id=update.market_id,
                data={
                    "update_type": update.update_type.value,
                    "yes_bids": [
                        {"price": str(l.price.value), "size": l.size.value}
                        for l in update.yes_bids
                    ],
                    "yes_asks": [
                        {"price": str(l.price.value), "size": l.size.value}
                        for l in update.yes_asks
                    ],
                },
            )
        )

    def record_order_placed(self, order: Order) -> None:
        """Record order placement.

        Args:
            order: Placed order
        """
        self.record_event(
            RecordingEvent(
                event_type=RecordingEventType.ORDER_PLACED,
                timestamp=order.created_at,
                market_id=order.market_id,
                data={
                    "order_id": order.id,
                    "client_order_id": order.client_order_id,
                    "side": order.side.value,
                    "order_side": order.order_side.value,
                    "price": str(order.price.value),
                    "size": order.size.value,
                },
            )
        )

    def record_order_cancelled(self, order_id: str, market_id: str) -> None:
        """Record order cancellation.

        Args:
            order_id: Cancelled order ID
            market_id: Market ID
        """
        self.record_event(
            RecordingEvent(
                event_type=RecordingEventType.ORDER_CANCELLED,
                timestamp=datetime.now(UTC),
                market_id=market_id,
                data={"order_id": order_id},
            )
        )

    def record_fill(self, fill: Fill) -> None:
        """Record fill.

        Args:
            fill: Fill to record
        """
        self.record_event(
            RecordingEvent(
                event_type=RecordingEventType.ORDER_FILLED,
                timestamp=fill.timestamp,
                market_id=fill.market_id,
                data={
                    "fill_id": fill.id,
                    "order_id": fill.order_id,
                    "side": fill.side.value,
                    "order_side": fill.order_side.value,
                    "price": str(fill.price.value),
                    "size": fill.size.value,
                    "is_simulated": fill.is_simulated,
                },
            )
        )

    def record_quotes(self, quotes: QuoteSet) -> None:
        """Record generated quotes.

        Args:
            quotes: Generated quote set
        """
        data: dict[str, Any] = {"market_id": quotes.market_id}
        if quotes.yes_quote:
            data["yes_quote"] = {
                "bid_price": str(quotes.yes_quote.bid_price.value),
                "bid_size": quotes.yes_quote.bid_size.value,
                "ask_price": str(quotes.yes_quote.ask_price.value),
                "ask_size": quotes.yes_quote.ask_size.value,
            }
            # no_quote is a method that derives NO quote from YES quote
            no_q = quotes.no_quote()
            data["no_quote"] = {
                "bid_price": str(no_q.bid_price.value),
                "bid_size": no_q.bid_size.value,
                "ask_price": str(no_q.ask_price.value),
                "ask_size": no_q.ask_size.value,
            }

        self.record_event(
            RecordingEvent(
                event_type=RecordingEventType.QUOTE_GENERATED,
                timestamp=quotes.timestamp,
                market_id=quotes.market_id,
                data=data,
            )
        )

    def record_error(self, error: str, context: dict[str, Any] | None = None) -> None:
        """Record error.

        Args:
            error: Error message
            context: Optional context
        """
        self.record_event(
            RecordingEvent(
                event_type=RecordingEventType.ERROR,
                timestamp=datetime.now(UTC),
                data={"error": error, "context": context or {}},
            )
        )

    def __enter__(self) -> SessionRecorder:
        """Context manager entry."""
        self.start()
        return self

    def __exit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> None:
        """Context manager exit."""
        self.stop()


class SessionPlayer:
    """Plays back recorded sessions.

    Reads JSONL.gz files and yields events for replay.
    """

    def __init__(self, file_path: str | Path) -> None:
        """Initialize player.

        Args:
            file_path: Path to recording file
        """
        self._file_path = Path(file_path)

    def events(self) -> Iterator[RecordingEvent]:
        """Yield events from recording.

        Yields:
            Recording events in order
        """
        with gzip.open(self._file_path, "rt", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line:
                    data = json.loads(line)
                    yield RecordingEvent.from_dict(data)

    def get_metadata(self) -> dict[str, Any]:
        """Get session metadata from first event.

        Returns:
            Session metadata dict
        """
        for event in self.events():
            if event.event_type == RecordingEventType.SESSION_START:
                return event.data
        return {}

    def get_stats(self) -> dict[str, int]:
        """Get event statistics.

        Returns:
            Dict of event type counts
        """
        stats: dict[str, int] = {}
        for event in self.events():
            event_type = event.event_type.value
            stats[event_type] = stats.get(event_type, 0) + 1
        return stats
