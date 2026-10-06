from __future__ import annotations

import itertools
import threading
from collections import deque
from dataclasses import dataclass
from time import monotonic

from odoo.libs.debug_log import DebugLog

__all__ = ["Attempt", "CircuitBreaker"]

_INITIAL_COOLDOWN = 1.0
_debug = DebugLog(__name__)

_PROBE_ABANDON_AFTER = 60.0

_BREAKER_IDS = itertools.count(1)


@dataclass(frozen=True, slots=True)
class Attempt:
    generation: int
    probe: bool
    breaker: int = 0


class CircuitBreaker:
    __slots__ = (
        "_abandoned_probes",
        "_cooldown",
        "_generation",
        "_id",
        "_lock",
        "_open",
        "_opened_at",
        "_probe_window",
        "_probing_since",
        "_recent_failures",
        "failure_threshold",
        "failure_window",
        "failures",
        "initial_cooldown",
        "max_cooldown",
        "probe_abandon_after",
        "trips",
    )

    def __init__(
        self,
        max_cooldown: float,
        initial_cooldown: float = _INITIAL_COOLDOWN,
        *,
        failure_threshold: int = 1,
        failure_window: float | None = None,
        probe_abandon_after: float = _PROBE_ABANDON_AFTER,
    ) -> None:
        if not initial_cooldown > 0:
            raise ValueError(
                f"initial_cooldown must be positive, got {initial_cooldown}"
            )
        if max_cooldown < initial_cooldown:
            raise ValueError(
                f"max_cooldown ({max_cooldown}) must be >= "
                f"initial_cooldown ({initial_cooldown})"
            )
        if failure_threshold < 1:
            raise ValueError(
                f"failure_threshold must be at least 1, got {failure_threshold}"
            )
        if failure_window is not None and failure_window <= 0:
            raise ValueError(f"failure_window must be positive, got {failure_window}")
        if not probe_abandon_after > 0:
            raise ValueError(
                f"probe_abandon_after must be positive, got {probe_abandon_after}"
            )
        self.initial_cooldown = initial_cooldown
        self.max_cooldown = max_cooldown
        self.failure_threshold = failure_threshold
        self.failure_window = failure_window
        self.probe_abandon_after = probe_abandon_after
        # probes admitted, then given up on so another could go: one still
        # running may yet report the success that closes the breaker, until a
        # newer probe reports a failure
        self._abandoned_probes: set[int] = set()
        self._recent_failures: deque[float] = deque()
        self._lock = threading.Lock()
        self._open = False
        self._cooldown = 0.0
        self._opened_at = 0.0
        self._probing_since = 0.0
        self._probe_window = probe_abandon_after
        self._generation = 0
        # a registry may replace a breaker; an attempt of the old one is stale here
        self._id = next(_BREAKER_IDS)
        self.failures = 0
        self.trips = 0
        _debug.lifecycle(
            "breaker.created",
            initial_cooldown=initial_cooldown,
            max_cooldown=max_cooldown,
            failure_threshold=failure_threshold,
            failure_window=failure_window,
            probe_abandon_after=probe_abandon_after,
        )

    @property
    def closed(self) -> bool:
        return not self._open

    @property
    def cooldown_remaining(self) -> float:
        with self._lock:
            return self._get_cooldown_remaining_locked()

    def _get_cooldown_remaining_locked(self) -> float:
        if not self._open:
            return 0.0
        return max(0.0, self._opened_at + self._cooldown - monotonic())

    def acquire_attempt(self, expected_seconds: float | None = None) -> Attempt | None:
        if expected_seconds is not None and not expected_seconds > 0:
            raise ValueError(
                f"expected_seconds must be positive, got {expected_seconds}"
            )
        with self._lock:
            if not self._open:
                return Attempt(self._generation, probe=False, breaker=self._id)
            now = monotonic()
            if now - self._opened_at < self._cooldown:
                _debug.logic(
                    "breaker.attempt_rejected",
                    reason="cooldown",
                    remaining_s=self._opened_at + self._cooldown - now,
                )
                return None
            if self._probing_since:
                if now - self._probing_since < self._probe_window:
                    _debug.logic(
                        "breaker.attempt_rejected",
                        reason="probe_in_flight",
                        probing_s=now - self._probing_since,
                        window_s=self._probe_window,
                    )
                    return None
                self._abandoned_probes.add(self._generation)
                _debug.logic(
                    "breaker.probe_abandoned",
                    generation=self._generation,
                    probing_s=now - self._probing_since,
                )
            self._probing_since = now
            self._probe_window = (
                self.probe_abandon_after
                if expected_seconds is None
                else expected_seconds
            )
            self._generation += 1
            _debug.logic(
                "breaker.probe",
                cooldown=self._cooldown,
                failures=self.failures,
                window_s=self._probe_window,
            )
            return Attempt(self._generation, probe=True, breaker=self._id)

    def _is_stale_locked(self, attempt: Attempt | None, outcome: str) -> bool:
        if attempt is None or (
            attempt.breaker == self._id and attempt.generation == self._generation
        ):
            return False
        if (
            outcome == "success"
            and attempt.probe
            and attempt.breaker == self._id
            and attempt.generation in self._abandoned_probes
        ):
            _debug.logic(
                "breaker.abandoned_probe_succeeded", generation=attempt.generation
            )
            return False
        _debug.logic(
            "breaker.stale_outcome",
            outcome=outcome,
            probe=attempt.probe,
            attempt_generation=attempt.generation,
            generation=self._generation,
        )
        return True

    def release(self, attempt: Attempt | None) -> None:
        # an admitted call that produced no outcome frees the probe slot, so
        # the next caller probes now instead of after the probe's window
        with self._lock:
            if (
                attempt is not None
                and attempt.probe
                and attempt.breaker == self._id
                and attempt.generation == self._generation
                and self._probing_since
            ):
                self._probing_since = 0.0
                _debug.logic("breaker.probe_released", generation=self._generation)

    def record_success(self, attempt: Attempt | None) -> bool:
        with self._lock:
            if self._is_stale_locked(attempt, "success"):
                return False
            closing = self._open
            if closing:
                # an abandoned probe closing it leaves the newer probe still in
                # flight current: that call was sent later, so its outcome is
                # newer evidence and counts as a closed breaker's outcome
                newer_probe_in_flight = (
                    attempt is not None
                    and attempt.generation != self._generation
                    and self._probing_since
                )
                if not newer_probe_in_flight:
                    self._generation += 1
                _debug.lifecycle(
                    "breaker.closed", failures=self.failures, trips=self.trips
                )
            self._open = False
            self._cooldown = 0.0
            self._opened_at = 0.0
            self._probing_since = 0.0
            self._abandoned_probes.clear()
            self._recent_failures.clear()
            self.failures = 0
            return closing

    def _threshold_reached_locked(self, now: float) -> bool:
        recent = self._recent_failures
        recent.append(now)
        if self.failure_window is not None:
            while recent and now - recent[0] > self.failure_window:
                recent.popleft()
        while len(recent) > self.failure_threshold:
            recent.popleft()
        return len(recent) >= self.failure_threshold

    def record_failure(self, attempt: Attempt | None) -> bool:
        with self._lock:
            self.failures += 1
            if self._is_stale_locked(attempt, "failure"):
                if (
                    attempt is not None
                    and attempt.probe
                    and attempt.breaker == self._id
                    and attempt.generation in self._abandoned_probes
                ):
                    # newer evidence: no older abandoned probe's late success
                    # may close the breaker after it
                    self._abandoned_probes = {
                        g for g in self._abandoned_probes if g > attempt.generation
                    }
                return False
            if not self._open:
                if not self._threshold_reached_locked(monotonic()):
                    _debug.logic(
                        "breaker.failure_below_threshold",
                        recent=len(self._recent_failures),
                        threshold=self.failure_threshold,
                    )
                    return False
                self._recent_failures.clear()
                self._open = True
                self._cooldown = self.initial_cooldown
                self._opened_at = monotonic()
                self._probing_since = 0.0
                self._abandoned_probes.clear()
                self._generation += 1
                self.trips += 1
                _debug.lifecycle(
                    "breaker.opened", cooldown=self._cooldown, trips=self.trips
                )
                return True
            if _debug.logic.enabled and not self._probing_since:
                _debug.logic(
                    "breaker.failure_while_open",
                    failures=self.failures,
                    cooldown=self._cooldown,
                )
            if self._probing_since:
                self._cooldown = min(self._cooldown * 2, self.max_cooldown)
                self._opened_at = monotonic()
                self._probing_since = 0.0
                self._abandoned_probes.clear()
                self._generation += 1
                _debug.logic(
                    "breaker.cooldown_extended",
                    cooldown=self._cooldown,
                    failures=self.failures,
                )
            return False

    def get_snapshot(self) -> dict[str, bool | int | float | None]:
        with self._lock:
            closed = not self._open
            remaining = self._get_cooldown_remaining_locked()
            return {
                "closed": closed,
                "failures": self.failures,
                "trips": self.trips,
                "failure_threshold": self.failure_threshold,
                "failure_window_seconds": self.failure_window,
                "cooldown_seconds": round(self._cooldown, 3),
                "cooldown_remaining_seconds": round(remaining, 3),
            }
