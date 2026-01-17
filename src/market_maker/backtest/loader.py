"""Loader for recorded market data."""

from __future__ import annotations

import json
from collections.abc import Iterator
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path
from typing import Any

from market_maker.backtest.types import RecordingMetadata, Tick
from market_maker.domain.market_data import OrderBook, PriceLevel
from market_maker.domain.types import Price, Quantity, Side


class RecordingLoader:
    """Loads recorded market data from JSON files.

    Supports the Kalshi recording format with:
    - Metadata (market_ticker, event_ticker, timestamps, etc.)
    - Ticks with order book snapshots
    """

    def load_index(self, index_path: str | Path) -> list[dict[str, Any]]:
        """Load a recording index file.

        The index file is a JSON array of objects with:
        - hour: Hour identifier
        - file: Path to recording file
        - ticker: Market ticker
        - settlement: YES or NO

        Args:
            index_path: Path to the index JSON file

        Returns:
            List of index entries
        """
        with open(index_path) as f:
            data: list[dict[str, Any]] = json.load(f)
            return data

    def load_metadata(
        self,
        file_path: str | Path,
        settlement: Side | None = None,
    ) -> RecordingMetadata:
        """Load just the metadata from a recording file.

        Args:
            file_path: Path to the recording JSON file
            settlement: Known settlement outcome (YES or NO)

        Returns:
            RecordingMetadata object
        """
        with open(file_path) as f:
            data = json.load(f)

        return RecordingMetadata(
            market_ticker=data["market_ticker"],
            event_ticker=data["event_ticker"],
            recording_started=self._parse_timestamp(data["recording_started"]),
            recording_ended=self._parse_timestamp(data["recording_ended"]),
            market_close_time=self._parse_timestamp(data["market_close_time"]),
            tick_interval_ms=data["tick_interval_ms"],
            orderbook_depth=data["orderbook_depth"],
            settlement=settlement,
            file_path=str(file_path),
        )

    def load_ticks(
        self,
        file_path: str | Path,
        start_tick: int = 0,
        end_tick: int | None = None,
    ) -> Iterator[Tick]:
        """Load ticks from a recording file.

        Uses an iterator to avoid loading entire file into memory.

        Args:
            file_path: Path to the recording JSON file
            start_tick: First tick to return (0-indexed)
            end_tick: Last tick to return (exclusive), None for all

        Yields:
            Tick objects
        """
        with open(file_path) as f:
            data = json.load(f)

        market_id = data["market_ticker"]
        ticks = data.get("ticks", [])

        for i, tick_data in enumerate(ticks):
            if i < start_tick:
                continue
            if end_tick is not None and i >= end_tick:
                break

            yield self._parse_tick(tick_data, market_id)

    def load_recording(
        self,
        file_path: str | Path,
        settlement: Side | None = None,
    ) -> tuple[RecordingMetadata, list[Tick]]:
        """Load a complete recording file.

        Args:
            file_path: Path to the recording JSON file
            settlement: Known settlement outcome

        Returns:
            Tuple of (metadata, list of ticks)
        """
        with open(file_path) as f:
            data = json.load(f)

        metadata = RecordingMetadata(
            market_ticker=data["market_ticker"],
            event_ticker=data["event_ticker"],
            recording_started=self._parse_timestamp(data["recording_started"]),
            recording_ended=self._parse_timestamp(data["recording_ended"]),
            market_close_time=self._parse_timestamp(data["market_close_time"]),
            tick_interval_ms=data["tick_interval_ms"],
            orderbook_depth=data["orderbook_depth"],
            settlement=settlement,
            file_path=str(file_path),
        )

        market_id = data["market_ticker"]
        ticks = [self._parse_tick(t, market_id) for t in data.get("ticks", [])]

        return metadata, ticks

    def _parse_tick(self, tick_data: dict[str, Any], market_id: str) -> Tick:
        """Parse a tick from JSON data.

        Args:
            tick_data: Raw tick dictionary
            market_id: Market identifier

        Returns:
            Tick object
        """
        orderbook_data = tick_data["orderbook"]

        # Parse order book levels
        yes_bids = self._parse_levels(orderbook_data.get("yes_bids", []))
        yes_asks = self._parse_levels(orderbook_data.get("yes_asks", []))

        # Sort bids descending, asks ascending
        yes_bids.sort(key=lambda x: x.price.value, reverse=True)
        yes_asks.sort(key=lambda x: x.price.value)

        order_book = OrderBook(
            market_id=market_id,
            yes_bids=yes_bids,
            yes_asks=yes_asks,
            timestamp=self._parse_timestamp(tick_data["timestamp"]),
        )

        return Tick(
            timestamp=self._parse_timestamp(tick_data["timestamp"]),
            tick_number=tick_data["tick_number"],
            time_to_close_seconds=tick_data["time_to_close_seconds"],
            order_book=order_book,
        )

    def _parse_levels(self, levels: list[dict[str, Any]]) -> list[PriceLevel]:
        """Parse price levels from JSON.

        Args:
            levels: List of {price, quantity} dicts

        Returns:
            List of PriceLevel objects
        """
        result = []
        for level in levels:
            price = Decimal(str(level["price"]))
            quantity = int(level["quantity"])
            result.append(PriceLevel(Price(price), Quantity(quantity)))
        return result

    def _parse_timestamp(self, timestamp_str: str) -> datetime:
        """Parse ISO format timestamp.

        Args:
            timestamp_str: ISO format timestamp string

        Returns:
            datetime object (UTC)
        """
        # Handle various ISO formats
        timestamp_str = timestamp_str.replace("Z", "+00:00")
        dt = datetime.fromisoformat(timestamp_str)

        # Ensure UTC
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=UTC)

        return dt
