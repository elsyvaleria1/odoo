import itertools
import logging
import time

__all__ = ["PhaseTimer"]


class PhaseTimer:
    __slots__ = ("_final", "_marks", "debug", "timed")

    def __init__(self, logger: logging.Logger, *, timed: bool = False) -> None:
        self.debug = logger.isEnabledFor(logging.DEBUG)
        self.timed = timed
        self._marks: dict[str, float] = {}
        self._final = "end"
        if self.debug or timed:
            self._marks["start"] = time.perf_counter()

    def mark(self, name: str) -> None:
        if self.debug:
            self._marks[name] = time.perf_counter()

    def stop(self, final: str = "end") -> None:
        if self.debug or self.timed:
            self._final = final
            self._marks[final] = time.perf_counter()

    def get_elapsed_ms(self, start: str, end: str) -> float:
        return (self._marks[end] - self._marks[start]) * 1000.0

    @property
    def elapsed(self) -> float:
        return self._marks[self._final] - self._marks["start"]

    def report(self, logger: logging.Logger, message: str, *args: object) -> None:
        if not self.debug:
            return
        times = list(self._marks.values())
        if len(times) > 2:
            names = list(self._marks)[1:]
            phases = " | " + " ".join(f"{name}=%.1f" for name in names)
            args = (
                *args,
                *((b - a) * 1000.0 for a, b in itertools.pairwise(times)),
            )
        else:
            phases = ""
        fmt = "[%.3f ms] " + message + phases
        logger.debug(fmt, self.elapsed * 1000.0, *args)
