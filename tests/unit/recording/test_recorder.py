"""Tests for session recorder."""

import tempfile
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path

import pytest

from market_maker.domain.market_data import OrderBook, PriceLevel
from market_maker.domain.orders import Fill, Order, OrderStatus, Quote, QuoteSet
from market_maker.domain.types import OrderSide, Price, Quantity, Side
from market_maker.recording.events import RecordingEvent, RecordingEventType
from market_maker.recording.recorder import SessionPlayer, SessionRecorder


class TestSessionRecorder:
    """Tests for SessionRecorder."""

    @pytest.fixture
    def temp_dir(self) -> Path:
        """Create temporary directory."""
        with tempfile.TemporaryDirectory() as d:
            yield Path(d)

    @pytest.fixture
    def recorder(self, temp_dir: Path) -> SessionRecorder:
        """Create recorder with temp directory."""
        return SessionRecorder(
            output_dir=temp_dir,
            session_id="test-session",
            flush_interval=1,  # Flush every event for testing
        )

    def test_start_stop(self, recorder: SessionRecorder) -> None:
        """Should start and stop recording."""
        recorder.start(config={"test": "config"})

        assert recorder.event_count == 1  # SESSION_START event

        recorder.stop()

        assert recorder.event_count == 2  # SESSION_END event
        assert recorder.file_path.exists()

    def test_record_event(self, recorder: SessionRecorder) -> None:
        """Should record events."""
        recorder.start()

        event = RecordingEvent(
            event_type=RecordingEventType.ERROR,
            timestamp=datetime.now(UTC),
            data={"error": "test error"},
        )
        recorder.record_event(event)

        recorder.stop()

        # Verify by reading back
        player = SessionPlayer(recorder.file_path)
        events = list(player.events())

        assert len(events) == 3  # START + ERROR + END
        assert events[1].event_type == RecordingEventType.ERROR

    def test_record_book_snapshot(self, recorder: SessionRecorder) -> None:
        """Should record order book snapshot."""
        recorder.start()

        book = OrderBook(
            market_id="TEST-MARKET",
            yes_bids=[PriceLevel(Price(Decimal("0.45")), Quantity(100))],
            yes_asks=[PriceLevel(Price(Decimal("0.55")), Quantity(100))],
            timestamp=datetime.now(UTC),
        )
        recorder.record_book_snapshot(book)

        recorder.stop()

        player = SessionPlayer(recorder.file_path)
        events = list(player.events())

        snapshot_event = events[1]
        assert snapshot_event.event_type == RecordingEventType.BOOK_SNAPSHOT
        assert snapshot_event.market_id == "TEST-MARKET"
        assert len(snapshot_event.data["yes_bids"]) == 1

    def test_record_order_placed(self, recorder: SessionRecorder) -> None:
        """Should record order placement."""
        recorder.start()

        order = Order(
            id="order-123",
            client_order_id="client-123",
            market_id="TEST-MARKET",
            side=Side.YES,
            order_side=OrderSide.BUY,
            price=Price(Decimal("0.45")),
            size=Quantity(10),
            filled_size=0,
            status=OrderStatus.OPEN,
            created_at=datetime.now(UTC),
            updated_at=datetime.now(UTC),
        )
        recorder.record_order_placed(order)

        recorder.stop()

        player = SessionPlayer(recorder.file_path)
        events = list(player.events())

        order_event = events[1]
        assert order_event.event_type == RecordingEventType.ORDER_PLACED
        assert order_event.data["order_id"] == "order-123"

    def test_record_fill(self, recorder: SessionRecorder) -> None:
        """Should record fill."""
        recorder.start()

        fill = Fill(
            id="fill-1",
            order_id="order-123",
            market_id="TEST-MARKET",
            side=Side.YES,
            order_side=OrderSide.BUY,
            price=Price(Decimal("0.45")),
            size=Quantity(5),
            timestamp=datetime.now(UTC),
            is_simulated=True,
        )
        recorder.record_fill(fill)

        recorder.stop()

        player = SessionPlayer(recorder.file_path)
        events = list(player.events())

        fill_event = events[1]
        assert fill_event.event_type == RecordingEventType.ORDER_FILLED
        assert fill_event.data["fill_id"] == "fill-1"
        assert fill_event.data["is_simulated"] is True

    def test_record_quotes(self, recorder: SessionRecorder) -> None:
        """Should record quotes."""
        recorder.start()

        quotes = QuoteSet(
            market_id="TEST-MARKET",
            yes_quote=Quote(
                bid_price=Price(Decimal("0.45")),
                bid_size=Quantity(10),
                ask_price=Price(Decimal("0.55")),
                ask_size=Quantity(10),
            ),
            timestamp=datetime.now(UTC),
        )
        recorder.record_quotes(quotes)

        recorder.stop()

        player = SessionPlayer(recorder.file_path)
        events = list(player.events())

        quote_event = events[1]
        assert quote_event.event_type == RecordingEventType.QUOTE_GENERATED
        assert "yes_quote" in quote_event.data

    def test_context_manager(self, temp_dir: Path) -> None:
        """Should work as context manager."""
        with SessionRecorder(
            output_dir=temp_dir,
            session_id="context-test",
        ) as recorder:
            recorder.record_error("test error")

        assert recorder.file_path.exists()


class TestSessionPlayer:
    """Tests for SessionPlayer."""

    @pytest.fixture
    def recording_path(self) -> Path:
        """Create a recording and return its path."""
        with tempfile.TemporaryDirectory() as d:
            recorder = SessionRecorder(
                output_dir=d,
                session_id="replay-test",
                flush_interval=1,
            )
            recorder.start(config={"param": "value"})

            # Add some events
            for i in range(5):
                recorder.record_error(f"Error {i}")

            recorder.stop()
            yield recorder.file_path

    def test_get_metadata(self, recording_path: Path) -> None:
        """Should get session metadata."""
        player = SessionPlayer(recording_path)

        metadata = player.get_metadata()

        assert metadata["session_id"] == "replay-test"
        assert metadata["config"]["param"] == "value"

    def test_get_stats(self, recording_path: Path) -> None:
        """Should get event statistics."""
        player = SessionPlayer(recording_path)

        stats = player.get_stats()

        assert stats["session_start"] == 1
        assert stats["session_end"] == 1
        assert stats["error"] == 5

    def test_iterate_events(self, recording_path: Path) -> None:
        """Should iterate over events."""
        player = SessionPlayer(recording_path)

        events = list(player.events())

        assert len(events) == 7  # START + 5 errors + END
        assert all(isinstance(e, RecordingEvent) for e in events)


class TestRecordingEvent:
    """Tests for RecordingEvent."""

    def test_to_dict_serializes_decimal(self) -> None:
        """Should serialize Decimal values."""
        event = RecordingEvent(
            event_type=RecordingEventType.ORDER_PLACED,
            timestamp=datetime.now(UTC),
            data={"price": Decimal("0.45")},
        )

        d = event.to_dict()

        assert d["data"]["price"] == "0.45"

    def test_from_dict_roundtrip(self) -> None:
        """Should roundtrip through dict."""
        original = RecordingEvent(
            event_type=RecordingEventType.ERROR,
            timestamp=datetime.now(UTC),
            market_id="TEST",
            data={"key": "value"},
        )

        d = original.to_dict()
        restored = RecordingEvent.from_dict(d)

        assert restored.event_type == original.event_type
        assert restored.market_id == original.market_id
        assert restored.data == original.data
