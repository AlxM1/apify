"""Rate limiting utility for scraper requests."""

import asyncio
import time
import logging

logger = logging.getLogger(__name__)


class RateLimiter:
    """Token bucket rate limiter for controlling request frequency.

    Args:
        requests_per_second: Maximum requests per second.
        burst: Maximum burst size (tokens that can accumulate).
    """

    def __init__(self, requests_per_second: float = 1.0, burst: int = 1):
        self.rate = requests_per_second
        self.burst = burst
        self._tokens = float(burst)
        self._last_refill = time.monotonic()
        self._lock = asyncio.Lock()

    async def acquire(self):
        """Wait until a request token is available."""
        async with self._lock:
            while True:
                now = time.monotonic()
                elapsed = now - self._last_refill
                self._tokens = min(
                    self.burst, self._tokens + elapsed * self.rate
                )
                self._last_refill = now

                if self._tokens >= 1.0:
                    self._tokens -= 1.0
                    return

                wait = (1.0 - self._tokens) / self.rate
                logger.debug(f"Rate limited, waiting {wait:.2f}s")
                await asyncio.sleep(wait)

    async def __aenter__(self):
        await self.acquire()
        return self

    async def __aexit__(self, *args):
        pass
