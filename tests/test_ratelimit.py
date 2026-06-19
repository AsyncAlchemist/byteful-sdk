"""Tests for the sliding-window ``RateLimiter``."""

from __future__ import annotations

import threading
import time

import pytest

from byteful import RateLimiter
from byteful.ratelimit import DEFAULT_RATE_LIMITER


def test_default_is_ten_per_second() -> None:
    assert DEFAULT_RATE_LIMITER.max_requests == 10
    assert DEFAULT_RATE_LIMITER.period == 1.0


def test_rejects_bad_parameters() -> None:
    with pytest.raises(ValueError):
        RateLimiter(max_requests=0)
    with pytest.raises(ValueError):
        RateLimiter(period=0)


def test_under_limit_does_not_block() -> None:
    rl = RateLimiter(max_requests=5, period=1.0)
    t0 = time.monotonic()
    for _ in range(5):
        rl.acquire()
    elapsed = time.monotonic() - t0
    assert elapsed < 0.1


def test_over_limit_blocks_until_window_clears() -> None:
    rl = RateLimiter(max_requests=2, period=0.3)
    rl.acquire()
    rl.acquire()
    t0 = time.monotonic()
    rl.acquire()  # 3rd call must wait for one slot to fall out of the window
    elapsed = time.monotonic() - t0
    assert elapsed >= 0.2  # some slack to absorb timing noise


def test_thread_safety() -> None:
    rl = RateLimiter(max_requests=4, period=0.5)
    counts = []

    def worker() -> None:
        rl.acquire()
        counts.append(time.monotonic())

    threads = [threading.Thread(target=worker) for _ in range(8)]
    t0 = time.monotonic()
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    elapsed = time.monotonic() - t0
    # 8 acquires at 4/0.5s rate: first 4 immediate, next 4 must wait ~0.5s
    assert elapsed >= 0.4
    assert len(counts) == 8
