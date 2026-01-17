"""Tests for RecordingLoader."""

import json
import tempfile
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path

import pytest

from market_maker.backtest.loader import RecordingLoader
from market_maker.domain.types import Side


def make_sample_recording() -> dict:
    """Create a sample recording for testing."""
    return {
        "market_ticker": "KXBTCD-25DEC1516-T86249.99",
        "event_ticker": "KXBTCD-25DEC1516",
        "recording_started": "2025-12-15T20:19:10.124768+00:00",
        "recording_ended": "2025-12-15T21:30:33.186181+00:00",
        "market_close_time": "2025-12-15T21:00:00+00:00",
        "tick_interval_ms": 500,
        "orderbook_depth": 10,
        "ticks": [
            {
                "timestamp": "2025-12-15T20:19:10.125941+00:00",
                "tick_number": 1,
                "time_to_close_seconds": 2449.874059,
                "market_ticker": "KXBTCD-25DEC1516-T86249.99",
                "event_ticker": "KXBTCD-25DEC1516",
                "orderbook": {
                    "yes_bids": [
                        {"price": 0.18, "quantity": 1548},
                        {"price": 0.17, "quantity": 15000},
                        {"price": 0.16, "quantity": 18100},
                    ],
                    "yes_asks": [
                        {"price": 0.20, "quantity": 2},
                        {"price": 0.21, "quantity": 2050},
                        {"price": 0.22, "quantity": 19100},
                    ],
                    "no_bids": [
                        {"price": 0.80, "quantity": 2},
                        {"price": 0.79, "quantity": 2050},
                    ],
                    "no_asks": [
                        {"price": 0.82, "quantity": 1548},
                        {"price": 0.83, "quantity": 15000},
                    ],
                    "best_yes_bid": 0.18,
                    "best_yes_ask": 0.20,
                    "best_no_bid": 0.80,
                    "best_no_ask": 0.82,
                },
            },
            {
                "timestamp": "2025-12-15T20:19:10.625941+00:00",
                "tick_number": 2,
                "time_to_close_seconds": 2449.374059,
                "market_ticker": "KXBTCD-25DEC1516-T86249.99",
                "event_ticker": "KXBTCD-25DEC1516",
                "orderbook": {
                    "yes_bids": [
                        {"price": 0.19, "quantity": 1000},
                        {"price": 0.18, "quantity": 1500},
                    ],
                    "yes_asks": [
                        {"price": 0.21, "quantity": 500},
                        {"price": 0.22, "quantity": 2000},
                    ],
                    "no_bids": [
                        {"price": 0.79, "quantity": 500},
                        {"price": 0.78, "quantity": 2000},
                    ],
                    "no_asks": [
                        {"price": 0.81, "quantity": 1000},
                        {"price": 0.82, "quantity": 1500},
                    ],
                    "best_yes_bid": 0.19,
                    "best_yes_ask": 0.21,
                    "best_no_bid": 0.79,
                    "best_no_ask": 0.81,
                },
            },
        ],
    }


def make_sample_index() -> list:
    """Create a sample index for testing."""
    return [
        {
            "hour": "KXBTCD-25DEC1516",
            "file": "/path/to/recording1.json",
            "ticker": "KXBTCD-25DEC1516-T86249.99",
            "settlement": "NO",
        },
        {
            "hour": "KXBTCD-25DEC2409",
            "file": "/path/to/recording2.json",
            "ticker": "KXBTCD-25DEC2409-T87249.99",
            "settlement": "YES",
        },
    ]


class TestRecordingLoader:
    """Tests for RecordingLoader."""

    @pytest.fixture
    def loader(self) -> RecordingLoader:
        """Create a loader instance."""
        return RecordingLoader()

    @pytest.fixture
    def sample_file(self) -> Path:
        """Create a temporary recording file."""
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".json", delete=False
        ) as f:
            json.dump(make_sample_recording(), f)
            return Path(f.name)

    @pytest.fixture
    def index_file(self) -> Path:
        """Create a temporary index file."""
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".json", delete=False
        ) as f:
            json.dump(make_sample_index(), f)
            return Path(f.name)

    def test_load_index(self, loader: RecordingLoader, index_file: Path) -> None:
        """Loading index returns list of entries."""
        entries = loader.load_index(index_file)

        assert len(entries) == 2
        assert entries[0]["hour"] == "KXBTCD-25DEC1516"
        assert entries[0]["settlement"] == "NO"
        assert entries[1]["settlement"] == "YES"

    def test_load_metadata(self, loader: RecordingLoader, sample_file: Path) -> None:
        """Loading metadata returns RecordingMetadata."""
        metadata = loader.load_metadata(sample_file, settlement=Side.NO)

        assert metadata.market_ticker == "KXBTCD-25DEC1516-T86249.99"
        assert metadata.event_ticker == "KXBTCD-25DEC1516"
        assert metadata.tick_interval_ms == 500
        assert metadata.orderbook_depth == 10
        assert metadata.settlement == Side.NO
        assert metadata.file_path == str(sample_file)

    def test_load_metadata_parses_timestamps(
        self, loader: RecordingLoader, sample_file: Path
    ) -> None:
        """Metadata timestamps are parsed correctly."""
        metadata = loader.load_metadata(sample_file)

        assert metadata.recording_started.year == 2025
        assert metadata.recording_started.month == 12
        assert metadata.recording_started.day == 15
        assert metadata.recording_started.tzinfo == timezone.utc

    def test_load_ticks(self, loader: RecordingLoader, sample_file: Path) -> None:
        """Loading ticks returns iterator of Tick objects."""
        ticks = list(loader.load_ticks(sample_file))

        assert len(ticks) == 2
        assert ticks[0].tick_number == 1
        assert ticks[1].tick_number == 2

    def test_load_ticks_with_range(
        self, loader: RecordingLoader, sample_file: Path
    ) -> None:
        """Can load a subset of ticks."""
        ticks = list(loader.load_ticks(sample_file, start_tick=1, end_tick=2))

        assert len(ticks) == 1
        assert ticks[0].tick_number == 2

    def test_tick_has_order_book(
        self, loader: RecordingLoader, sample_file: Path
    ) -> None:
        """Tick contains properly parsed order book."""
        ticks = list(loader.load_ticks(sample_file))
        tick = ticks[0]

        assert tick.order_book is not None
        assert tick.order_book.market_id == "KXBTCD-25DEC1516-T86249.99"

        # Check bids are sorted descending
        bids = tick.order_book.yes_bids
        assert len(bids) == 3
        assert bids[0].price.value == Decimal("0.18")  # Best bid first
        assert bids[1].price.value == Decimal("0.17")

        # Check asks are sorted ascending
        asks = tick.order_book.yes_asks
        assert len(asks) == 3
        assert asks[0].price.value == Decimal("0.20")  # Best ask first
        assert asks[1].price.value == Decimal("0.21")

    def test_tick_has_time_to_close(
        self, loader: RecordingLoader, sample_file: Path
    ) -> None:
        """Tick has time_to_close_seconds field."""
        ticks = list(loader.load_ticks(sample_file))

        assert ticks[0].time_to_close_seconds == pytest.approx(2449.874059)
        assert ticks[1].time_to_close_seconds == pytest.approx(2449.374059)

    def test_load_recording(self, loader: RecordingLoader, sample_file: Path) -> None:
        """load_recording returns both metadata and ticks."""
        metadata, ticks = loader.load_recording(sample_file, settlement=Side.YES)

        assert metadata.market_ticker == "KXBTCD-25DEC1516-T86249.99"
        assert metadata.settlement == Side.YES
        assert len(ticks) == 2

    def test_order_book_best_bid_ask(
        self, loader: RecordingLoader, sample_file: Path
    ) -> None:
        """Order book best_bid/best_ask return correct values."""
        ticks = list(loader.load_ticks(sample_file))
        book = ticks[0].order_book

        best_bid = book.best_bid()
        best_ask = book.best_ask()

        assert best_bid is not None
        assert best_bid.price.value == Decimal("0.18")
        assert best_bid.size.value == 1548

        assert best_ask is not None
        assert best_ask.price.value == Decimal("0.20")
        assert best_ask.size.value == 2
