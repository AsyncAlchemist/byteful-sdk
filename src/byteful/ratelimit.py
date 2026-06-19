"""Process-wide rate limiting.

The byteful API documents a default of **10 requests per second per customer**;
anything over returns HTTP 429. ``RateLimiter`` is a thread-safe sliding-window
limiter. By default, :class:`~byteful.client.BytefulClient` instances share a
single module-level limiter so that multiple clients in the same process
throttle as one.
"""

from __future__ import annotations

import threading
import time
from collections import deque


class RateLimiter:
    """Sliding-window rate limiter.

    ``max_requests`` are allowed in any rolling ``period`` seconds. Callers
    invoke :meth:`acquire` immediately before a request; it blocks just long
    enough to keep the caller under the limit and is safe to share across
    threads.
    """

    __slots__ = ("max_requests", "period", "_timestamps", "_lock")

    def __init__(self, max_requests: int = 10, period: float = 1.0) -> None:
        if max_requests < 1:
            raise ValueError("max_requests must be >= 1")
        if period <= 0:
            raise ValueError("period must be > 0")
        self.max_requests = max_requests
        self.period = period
        self._timestamps: deque[float] = deque()
        self._lock = threading.Lock()

    def acquire(self) -> None:
        with self._lock:
            now = time.monotonic()
            self._prune(now)
            if len(self._timestamps) >= self.max_requests:
                wait = self.period - (now - self._timestamps[0])
                if wait > 0:
                    time.sleep(wait)
                    now = time.monotonic()
                    self._prune(now)
            self._timestamps.append(now)

    def _prune(self, now: float) -> None:
        cutoff = now - self.period
        while self._timestamps and self._timestamps[0] <= cutoff:
            self._timestamps.popleft()


# Shared limiter used by BytefulClient instances unless they're given another
# one. The 10 req/s figure comes from the API docs.
DEFAULT_RATE_LIMITER = RateLimiter(max_requests=10, period=1.0)
