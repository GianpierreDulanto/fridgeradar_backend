"""Tests for the process-wide Gemini throttler.

These exercise the state machine directly (no real Gemini call).
"""
from __future__ import annotations

import time

import pytest

from app.services.gemini_throttle import (
    GeminiThrottle,
    _GeminiRateLimited,
)


@pytest.fixture
def throttle(monkeypatch) -> GeminiThrottle:
    """Fresh instance per test so state doesn't leak between cases.

    Tunables are class-level constants, so we override them via monkeypatch
    before each test and reset automatically.
    """
    monkeypatch.setattr(GeminiThrottle, "MIN_INTERVAL_S", 0.1)
    monkeypatch.setattr(GeminiThrottle, "COOLDOWN_BASE_S", 0.3)
    monkeypatch.setattr(GeminiThrottle, "COOLDOWN_MAX_S", 2.0)
    monkeypatch.setattr(GeminiThrottle, "CACHE_TTL_S", 0.5)
    monkeypatch.setattr(GeminiThrottle, "CACHE_NEG_TTL_S", 0.2)
    return GeminiThrottle()


def test_initial_stats_are_zero(throttle: GeminiThrottle):
    s = throttle.stats()
    assert s["calls"] == 0
    assert s["429"] == 0
    assert s["cache_hits"] == 0
    assert s["cache_size"] == 0
    assert s["in_cooldown_now"] is False


def test_first_call_runs_and_caches_result(throttle: GeminiThrottle):
    calls = {"n": 0}

    def fn():
        calls["n"] += 1
        return ["recipe-a", "recipe-b"]

    out1 = throttle.acquire_and_call("k1", "test", fn)
    assert out1 == ["recipe-a", "recipe-b"]
    assert calls["n"] == 1
    assert throttle.stats()["calls"] == 1

    out2 = throttle.acquire_and_call("k1", "test", fn)
    assert out2 == ["recipe-a", "recipe-b"]
    assert calls["n"] == 1  # cache hit, fn not called again
    assert throttle.stats()["cache_hits"] == 1


def test_minimum_interval_blocks_second_call(throttle: GeminiThrottle):
    def fn():
        return "ok"

    throttle.acquire_and_call("k1", "test", fn)
    # immediate second call should be skipped (rate-limited)
    out = throttle.acquire_and_call("k2", "test", fn)
    assert out is None
    assert throttle.stats()["rate_limited"] >= 1


def test_429_triggers_cooldown(throttle: GeminiThrottle):
    def boom():
        raise _GeminiRateLimited("simulated 429")

    out = throttle.acquire_and_call("k1", "test", boom)
    assert out is None
    assert throttle.is_in_cooldown() is True
    assert throttle.stats()["429"] == 1
    assert throttle.cooldown_remaining_s() > 0


def test_during_cooldown_no_calls_attempted(throttle: GeminiThrottle):
    calls = {"n": 0}

    def boom():
        calls["n"] += 1
        raise _GeminiRateLimited("simulated 429")

    throttle.acquire_and_call("k1", "test", boom)
    assert calls["n"] == 1
    assert throttle.is_in_cooldown()

    # even after the min interval, cooldown blocks us
    time.sleep(0.15)
    out = throttle.acquire_and_call("k2", "test", lambda: "ok")
    assert out is None
    assert calls["n"] == 1  # still only the first one ran


def test_429_cooldown_is_exponential(throttle: GeminiThrottle):
    def boom():
        raise _GeminiRateLimited("simulated 429")

    for i in range(3):
        # wait for both the min interval AND the current cooldown to expire
        # so the next call actually reaches Gemini
        while throttle.is_in_cooldown() or throttle.seconds_since_last_call() < 0.1:
            time.sleep(0.05)
        out = throttle.acquire_and_call(f"k{i}", "test", boom)
        assert out is None  # Gemini was called and raised

    # 1st 429 -> base * 2^0 = 0.3s
    # 2nd 429 -> base * 2^1 = 0.6s
    # 3rd 429 -> base * 2^2 = 1.2s
    assert throttle.cooldown_remaining_s() > 0.4
    assert throttle.stats()["429"] == 3


def test_consecutive_success_resets_429_counter(throttle: GeminiThrottle):
    # one 429 -> enters cooldown
    def boom():
        raise _GeminiRateLimited("simulated 429")
    throttle.acquire_and_call("k1", "test", boom)
    consecutive = throttle._consecutive_429  # type: ignore[attr-defined]
    assert consecutive == 1

    # wait for cooldown + min interval
    time.sleep(0.35)

    # a successful call after the cooldown resets the counter
    throttle.acquire_and_call("k2", "test", lambda: "ok")
    assert throttle._consecutive_429 == 0  # type: ignore[attr-defined]


def test_negative_caching_avoids_repeat_calls(throttle: GeminiThrottle):
    calls = {"n": 0}

    def returns_none():
        calls["n"] += 1
        return None

    throttle.acquire_and_call("k1", "test", returns_none)
    # negative cache hit before TTL expires
    time.sleep(0.05)
    out = throttle.acquire_and_call("k1", "test", returns_none)
    assert out is None
    assert calls["n"] == 1
    assert throttle.stats()["cache_neg_hits"] == 1


def test_cache_ttl_expires(throttle: GeminiThrottle):
    calls = {"n": 0}

    def fn():
        calls["n"] += 1
        return f"result-{calls['n']}"

    throttle.acquire_and_call("k1", "test", fn)
    time.sleep(0.6)  # > CACHE_TTL_S (0.5)
    # but also need to wait for min interval (0.1)
    out = throttle.acquire_and_call("k1", "test", fn)
    assert out == "result-2"
    assert calls["n"] == 2


def test_generic_exception_is_handled(throttle: GeminiThrottle):
    def boom():
        raise RuntimeError("network down")

    out = throttle.acquire_and_call("k1", "test", boom)
    assert out is None
    assert throttle.stats()["errors"] == 1
    # NOT in cooldown for generic errors
    assert throttle.is_in_cooldown() is False


def test_concurrent_threads_only_make_one_call(throttle: GeminiThrottle):
    """Simulate the 3-tab problem: multiple threads call simultaneously.
    Only one should actually call the function; the others should hit the
    min-interval gate or the cache."""
    import threading
    calls = {"n": 0}
    barrier = threading.Barrier(5)

    def slow_fn():
        calls["n"] += 1
        time.sleep(0.05)
        return "ok"

    results: list = []

    def worker():
        barrier.wait()
        r = throttle.acquire_and_call("k1", "test", slow_fn)
        results.append(r)

    threads = [threading.Thread(target=worker) for _ in range(5)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    # at least one call returned "ok" (the winner); the rest either got
    # the cached value or None. We just want to assert we didn't slam
    # Gemini 5 times.
    assert calls["n"] <= 2  # worst case: first one + maybe one slip-through
    assert sum(1 for r in results if r == "ok") >= 1


def test_make_key_is_stable():
    assert GeminiThrottle.make_key("a", 1, [1, 2]) == GeminiThrottle.make_key("a", 1, [1, 2])
    assert GeminiThrottle.make_key("a", 1) != GeminiThrottle.make_key("a", 2)
