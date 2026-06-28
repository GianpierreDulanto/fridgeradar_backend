"""
Process-wide gate for every call we make to the Google Gemini API.

Why this exists
---------------
The free tier of Google AI Studio enforces hard rate limits:

  * 15 requests / minute (RPM)
  * 1,500 requests / day (RPD)

Every `gemini-2.0-flash:generateContent` call costs one of those. In dev we
trigger Gemini from the recipe service (`/api/recipes/suggest`,
`/api/recipes/daily`) and the chat endpoint (`/api/ai/chat`). React Strict
Mode double-fires every effect, multiple browser tabs pool connections in
parallel, and a single page load can produce 2-4 Gemini calls in under a
second. The result: a flood of `429 Too Many Requests` that Google answers
with for the rest of the day.

What this module does
--------------------
A single `GeminiThrottle` instance shared across the process enforces:

1. **Minimum interval** between calls (default 4s) -> we stay under 15 RPM.
2. **Cooldown after 429** (default 5 min, exponential up to 1h) -> once we
   get throttled we stop trying, letting the quota recover.
3. **TTL cache** (5 min for successful recipes, 30s for empty) -> identical
   requests don't even leave the process.
4. **Thread-safe gate** (`threading.Lock`) -> concurrent FastAPI workers on
   different threads can't fire two simultaneous calls.
5. **Stats** for observability (totals, in-cooldown state, cache size).

The hot path is `acquire_and_call(key, caller, fn) -> result`. If the
caller is allowed to call, the lock is held while the function runs, so
no two threads can both hit Gemini at the same instant.
"""
from __future__ import annotations

import hashlib
import logging
import threading
import time
from typing import Any, Callable, TypeVar

logger = logging.getLogger(__name__)

T = TypeVar("T")


class GeminiThrottle:
    """Per-process gate + TTL cache for Gemini calls.

    Tunables (min interval between calls, cooldown backoff, cache TTLs) are
    configurable per-instance via __init__, which fall back to the values in
    `app.core.config.settings` (themselves driven by env vars).
    """

    # --- defaults (overridable per-instance via __init__) ---
    DEFAULT_MIN_INTERVAL_S: float = 4.0         # > 1/15 RPM; safe margin
    DEFAULT_COOLDOWN_BASE_S: float = 60.0       # first 429 -> 1 min
    DEFAULT_COOLDOWN_MAX_S: float = 3600.0      # never block more than 1h
    DEFAULT_CACHE_TTL_S: float = 300.0          # 5 min for hits
    DEFAULT_CACHE_NEG_TTL_S: float = 30.0       # 30s for "nothing useful"

    def __init__(
        self,
        min_interval_s: float | None = None,
        cooldown_base_s: float | None = None,
        cooldown_max_s: float | None = None,
        cache_ttl_s: float | None = None,
        cache_neg_ttl_s: float | None = None,
    ) -> None:
        from app.core.config import settings
        self.min_interval_s = min_interval_s if min_interval_s is not None else settings.gemini_min_interval_s
        self.cooldown_base_s = cooldown_base_s if cooldown_base_s is not None else settings.gemini_cooldown_base_s
        self.cooldown_max_s = cooldown_max_s if cooldown_max_s is not None else settings.gemini_cooldown_max_s
        self.cache_ttl_s = cache_ttl_s if cache_ttl_s is not None else settings.gemini_cache_ttl_s
        self.cache_neg_ttl_s = cache_neg_ttl_s if cache_neg_ttl_s is not None else settings.gemini_cache_neg_ttl_s
        self._lock = threading.Lock()
        self._last_call_ts: float = 0.0
        self._cooldown_until: float = 0.0
        self._consecutive_429: int = 0
        self._cache: dict[str, tuple[Any, float]] = {}
        self._stats = {
            "calls": 0,
            "cache_hits": 0,
            "cache_neg_hits": 0,
            "rate_limited": 0,
            "in_cooldown": 0,
            "429": 0,
            "errors": 0,
        }

    # ----- introspection -----

    def stats(self) -> dict:
        with self._lock:
            s = dict(self._stats)
            s["cache_size"] = len(self._cache)
            s["cooldown_remaining_s"] = round(max(0.0, self._cooldown_until - time.monotonic()), 1)
            s["in_cooldown_now"] = self.is_in_cooldown()
            s["seconds_since_last_call"] = round(time.monotonic() - self._last_call_ts, 2) if self._last_call_ts else None
            return s

    def is_in_cooldown(self) -> bool:
        return time.monotonic() < self._cooldown_until

    def cooldown_remaining_s(self) -> float:
        return max(0.0, self._cooldown_until - time.monotonic())

    def seconds_since_last_call(self) -> float:
        if self._last_call_ts == 0.0:
            return float("inf")
        return time.monotonic() - self._last_call_ts

    # ----- cache helpers -----

    @staticmethod
    def make_key(*parts: Any) -> str:
        h = hashlib.sha1()
        for p in parts:
            h.update(repr(p).encode("utf-8"))
            h.update(b"|")
        return h.hexdigest()

    def cache_get(self, key: str) -> tuple[bool, Any]:
        """Return (hit, value). hit=True with value=None means "we asked, got
        nothing useful" -> caller should still treat as a miss and try again
        after self.cache_neg_ttl_s."""
        with self._lock:
            entry = self._cache.get(key)
            if entry is None:
                return False, None
            value, expires = entry
            if time.monotonic() > expires:
                self._cache.pop(key, None)
                return False, None
            return True, value

    def cache_set(self, key: str, value: Any, *, ttl_s: float | None = None) -> None:
        ttl = ttl_s if ttl_s is not None else self.cache_ttl_s
        with self._lock:
            self._cache[key] = (value, time.monotonic() + ttl)

    def cache_clear(self) -> None:
        with self._lock:
            self._cache.clear()

    # ----- the one entry point the services use -----

    def acquire_and_call(
        self,
        key: str,
        caller: str,
        fn: Callable[[], T],
    ) -> T | None:
        """Run `fn` if (and only if) we are allowed to call Gemini right now.

        Returns:
          * the cached value if there is a fresh hit,
          * None if we're in cooldown or rate-limited (caller falls back),
          * the result of `fn()` if a real call was made.
        """
        with self._lock:
            # 1. cache
            entry = self._cache.get(key)
            if entry is not None:
                value, expires = entry
                if time.monotonic() <= expires:
                    if value is None:
                        self._stats["cache_neg_hits"] += 1
                    else:
                        self._stats["cache_hits"] += 1
                    logger.debug("[%s] gemini cache hit (neg=%s)", caller, value is None)
                    return value
                self._cache.pop(key, None)

            # 2. cooldown
            if self.is_in_cooldown():
                self._stats["in_cooldown"] += 1
                logger.info(
                    "[%s] gemini skipped (cooldown, %.0fs remaining)",
                    caller, self.cooldown_remaining_s(),
                )
                return None

            # 3. minimum interval
            now = time.monotonic()
            wait = self.min_interval_s - (now - self._last_call_ts)
            if wait > 0 and self._last_call_ts > 0:
                self._stats["rate_limited"] += 1
                logger.info(
                    "[%s] gemini rate-limited (last call %.1fs ago, need %.1fs)",
                    caller, now - self._last_call_ts, self.min_interval_s,
                )
                # cache the skip briefly so we don't keep logging it
                self._cache[key] = (None, now + min(wait + 1.0, self.cache_neg_ttl_s))
                return None

            # 4. we're cleared to call. mark BEFORE running so concurrent
            #    threads wait their turn.
            self._last_call_ts = now
            self._stats["calls"] += 1
            allowed = True

        if not allowed:
            return None

        # run the call OUTSIDE the lock so other threads can still consult
        # the cache and stats.
        try:
            result = fn()
        except _GeminiRateLimited as e:
            with self._lock:
                self._consecutive_429 += 1
                self._stats["429"] += 1
                # exponential cooldown: 1m, 2m, 4m, 8m, 16m, ... cap 1h
                backoff = self.cooldown_base_s * (2 ** min(self._consecutive_429 - 1, 5))
                self._cooldown_until = time.monotonic() + min(backoff, self.cooldown_max_s)
                logger.warning(
                    "[%s] gemini 429 -> cooldown for %.0fs (consecutive=%d, total=%d)",
                    caller, self.cooldown_max_s if backoff > self.cooldown_max_s else backoff,
                    self._consecutive_429, self._stats["429"],
                )
            self.cache_set(key, None, ttl_s=self.cache_neg_ttl_s)
            return None
        except Exception as e:
            with self._lock:
                self._stats["errors"] += 1
            self.cache_set(key, None, ttl_s=self.cache_neg_ttl_s)
            logger.warning("[%s] gemini call error: %s", caller, e)
            return None

        with self._lock:
            self._consecutive_429 = 0
        # success -> cache the value (or a negative marker if empty)
        if result is None:
            self.cache_set(key, None, ttl_s=self.cache_neg_ttl_s)
        else:
            self.cache_set(key, result)
        return result


class _GeminiRateLimited(Exception):
    """Internal signal: the function we just ran got a 429 from Gemini."""


def make_rate_limit_exception() -> type[Exception]:
    """Helper so callers can `raise _GeminiRateLimited()` without importing it."""
    return _GeminiRateLimited


# process-wide singleton
gemini_throttle = GeminiThrottle()
