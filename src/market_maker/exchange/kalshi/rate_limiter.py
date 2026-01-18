"""Rate limiter for Kalshi API requests.

Implements a token bucket algorithm to respect Kalshi's rate limits.
"""

from __future__ import annotations

import asyncio
import logging
import time
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)


@dataclass
class RateLimiter:
    """Token bucket rate limiter.

    Kalshi rate limits:
    - Writes (orders, cancels): 10/second
    - Reads (positions, balance): Higher limit

    This implementation uses a token bucket that refills at
    a constant rate. Requests consume tokens; if no tokens
    are available, the request waits.

    Attributes:
        rate: Number of operations allowed per second
        burst: Maximum burst size (defaults to rate)
    """

    rate: float
    burst: float = 0.0  # 0 means "use rate as default"
    _tokens: float = field(init=False)
    _last_update: float = field(init=False)
    _lock: asyncio.Lock = field(init=False, default_factory=asyncio.Lock)
    _effective_burst: float = field(init=False)

    def __post_init__(self) -> None:
        """Initialize token bucket."""
        self._effective_burst = self.burst if self.burst > 0 else self.rate
        self._tokens = self._effective_burst
        self._last_update = time.monotonic()

    def _refill(self) -> None:
        """Refill tokens based on elapsed time."""
        now = time.monotonic()
        elapsed = now - self._last_update
        self._tokens = min(self._effective_burst, self._tokens + elapsed * self.rate)
        self._last_update = now

    async def acquire(self, tokens: float = 1.0) -> None:
        """Acquire tokens, waiting if necessary.

        Args:
            tokens: Number of tokens to acquire (default 1)

        This method blocks until enough tokens are available.
        """
        async with self._lock:
            self._refill()

            if self._tokens >= tokens:
                self._tokens -= tokens
                return

            # Calculate wait time
            deficit = tokens - self._tokens
            wait_time = deficit / self.rate

            logger.debug(f"Rate limited, waiting {wait_time:.3f}s")
            await asyncio.sleep(wait_time)

            # After waiting, we should have enough tokens
            self._refill()
            self._tokens -= tokens

    def try_acquire(self, tokens: float = 1.0) -> bool:
        """Try to acquire tokens without waiting.

        Args:
            tokens: Number of tokens to acquire

        Returns:
            True if tokens were acquired, False otherwise
        """
        self._refill()

        if self._tokens >= tokens:
            self._tokens -= tokens
            return True
        return False

    @property
    def available_tokens(self) -> float:
        """Return the current number of available tokens."""
        self._refill()
        return self._tokens


def create_kalshi_rate_limiters() -> tuple[RateLimiter, RateLimiter]:
    """Create rate limiters for Kalshi API.

    Returns:
        Tuple of (write_limiter, read_limiter)
    """
    # Kalshi limits: 10 writes/sec, more lenient reads
    write_limiter = RateLimiter(rate=10.0, burst=10.0)
    read_limiter = RateLimiter(rate=30.0, burst=30.0)
    return write_limiter, read_limiter
