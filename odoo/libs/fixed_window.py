from __future__ import annotations

import heapq
import threading
from time import monotonic

from odoo.libs.debug_log import DebugLog

__all__ = ["FixedWindowLimiter"]

_debug = DebugLog(__name__)


class FixedWindowLimiter:
    """At most ``limit`` hits per key in each ``window`` seconds.

    Per process: under prefork each worker counts on its own, so it bounds
    abuse, not an exact rate. Past ``max_keys`` keys, windows that ended are
    dropped first, then the oldest, down to nine tenths of the bound.
    """

    __slots__ = ("_lock", "_state", "limit", "max_keys", "window")

    def __init__(self, window: float, limit: int, max_keys: int = 10_000) -> None:
        self.window = window
        self.limit = limit
        self.max_keys = max_keys
        self._lock = threading.Lock()
        self._state: dict[str, list[float]] = {}

    def is_limited(self, key: str) -> bool:
        now = monotonic()
        with self._lock:
            if len(self._state) > self.max_keys:
                self._sweep(now)
            state = self._state.get(key)
            if state is None or now - state[0] >= self.window:
                if state is not None:
                    _debug.logic("rate_window_expired", key=key, hits=state[1])
                self._state[key] = [now, 1]
                return False
            if state[1] >= self.limit:
                _debug.logic("rate_limited", key=key, hits=state[1])
                return True
            state[1] += 1
            return False

    def clear(self) -> None:
        with self._lock:
            self._state.clear()

    def _sweep(self, now: float) -> None:
        cutoff = now - self.window
        before = len(self._state)
        for stale in [k for k, v in self._state.items() if v[0] < cutoff]:
            del self._state[stale]
        _debug.perf.count(
            "rate_sweep_stale_evicted", keys_before=before, keys_after=len(self._state)
        )
        if len(self._state) > self.max_keys:
            evict = len(self._state) - self.max_keys * 9 // 10
            _debug.logic("rate_sweep_evict_oldest", keys=len(self._state), evict=evict)
            for key in heapq.nsmallest(
                evict, self._state, key=lambda k: self._state[k][0]
            ):
                del self._state[key]
