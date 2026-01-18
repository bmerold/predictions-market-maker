"""Tests for Kalshi rate limiter."""

import asyncio
import time

import pytest

from market_maker.exchange.kalshi.rate_limiter import (
    RateLimiter,
    create_kalshi_rate_limiters,
)


class TestRateLimiter:
    """Tests for the token bucket rate limiter."""

    def test_initial_tokens(self) -> None:
        """Should start with burst tokens available."""
        limiter = RateLimiter(rate=10.0, burst=5.0)
        assert limiter.available_tokens == 5.0

    def test_initial_tokens_default_burst(self) -> None:
        """Should use rate as default burst."""
        limiter = RateLimiter(rate=10.0)
        assert limiter.available_tokens == 10.0

    def test_try_acquire_success(self) -> None:
        """Should successfully acquire when tokens available."""
        limiter = RateLimiter(rate=10.0, burst=10.0)
        assert limiter.try_acquire(1.0) is True
        # Allow small timing variance from refill
        assert 8.9 <= limiter.available_tokens <= 9.1

    def test_try_acquire_failure(self) -> None:
        """Should fail to acquire when not enough tokens."""
        limiter = RateLimiter(rate=10.0, burst=5.0)
        # Use up all tokens
        for _ in range(5):
            limiter.try_acquire(1.0)
        assert limiter.try_acquire(1.0) is False

    def test_try_acquire_partial(self) -> None:
        """Should handle partial token amounts."""
        limiter = RateLimiter(rate=10.0, burst=10.0)
        assert limiter.try_acquire(0.5) is True
        # Allow small timing variance from refill
        assert 9.4 <= limiter.available_tokens <= 9.6

    def test_tokens_refill_over_time(self) -> None:
        """Should refill tokens based on rate."""
        limiter = RateLimiter(rate=100.0, burst=100.0)  # 100 tokens/sec

        # Drain tokens
        while limiter.try_acquire(1.0):
            pass

        # Wait for refill
        time.sleep(0.1)  # Should refill ~10 tokens

        # Should have some tokens now
        assert limiter.available_tokens > 0

    @pytest.mark.asyncio
    async def test_acquire_waits_when_needed(self) -> None:
        """Should wait when no tokens available."""
        limiter = RateLimiter(rate=100.0, burst=1.0)  # Fast refill for test

        # First acquire should succeed immediately
        await limiter.acquire(1.0)

        # Second acquire should wait
        start = time.monotonic()
        await limiter.acquire(1.0)
        elapsed = time.monotonic() - start

        # Should have waited for refill (at least a small amount)
        assert elapsed > 0

    @pytest.mark.asyncio
    async def test_acquire_respects_rate(self) -> None:
        """Should respect rate limit over multiple acquires."""
        limiter = RateLimiter(rate=10.0, burst=2.0)

        start = time.monotonic()

        # Acquire 4 tokens (2 burst + 2 from rate)
        for _ in range(4):
            await limiter.acquire(1.0)

        elapsed = time.monotonic() - start

        # First 2 should be instant, next 2 should take ~0.2s at 10/sec
        assert elapsed >= 0.15  # Allow some timing slack

    @pytest.mark.asyncio
    async def test_concurrent_acquires(self) -> None:
        """Should handle concurrent acquire requests."""
        limiter = RateLimiter(rate=10.0, burst=5.0)

        # Create concurrent acquire tasks
        async def acquire_one() -> None:
            await limiter.acquire(1.0)

        tasks = [asyncio.create_task(acquire_one()) for _ in range(10)]

        # All should eventually complete
        await asyncio.gather(*tasks)

    def test_burst_caps_tokens(self) -> None:
        """Should not exceed burst limit."""
        limiter = RateLimiter(rate=100.0, burst=5.0)

        # Wait some time
        time.sleep(0.1)

        # Should still be capped at burst
        limiter._refill()
        assert limiter.available_tokens <= 5.0


class TestCreateKalshiRateLimiters:
    """Tests for the factory function."""

    def test_creates_write_limiter(self) -> None:
        """Should create write limiter with correct rate."""
        write_limiter, _ = create_kalshi_rate_limiters()
        assert write_limiter.rate == 10.0

    def test_creates_read_limiter(self) -> None:
        """Should create read limiter with higher rate."""
        _, read_limiter = create_kalshi_rate_limiters()
        assert read_limiter.rate == 30.0

    def test_limiters_independent(self) -> None:
        """Should create independent limiters."""
        write_limiter, read_limiter = create_kalshi_rate_limiters()

        # Exhaust write limiter
        while write_limiter.try_acquire(1.0):
            pass

        # Read limiter should still have tokens
        assert read_limiter.try_acquire(1.0) is True
