from __future__ import annotations

import faulthandler
import logging
import os
import sys
import threading
import traceback
from collections.abc import Callable

from .worker_thread import describe_thread_work

__all__ = ["MemoryWatch", "read_rss", "start_from_environ"]

_logger = logging.getLogger(__name__)

STEP_VAR = "ODOO_MEMORY_WATCH"
LIMIT_VAR = "ODOO_MEMORY_LIMIT"
_MIB = 1024 * 1024
_STATM = b"/proc/self/statm"
_PAGE = os.sysconf("SC_PAGE_SIZE") if hasattr(os, "sysconf") else 4096


def read_rss() -> int:
    try:
        fd = os.open(_STATM, os.O_RDONLY | os.O_CLOEXEC)
    except OSError:
        import psutil

        return psutil.Process().memory_info().rss
    try:
        return int(os.read(fd, 256).split()[1]) * _PAGE
    finally:
        os.close(fd)


def _thread_stacks(skip: int | None) -> str:
    frames = sys._current_frames()
    threads = {thread.ident: thread for thread in threading.enumerate()}
    main = threading.main_thread().ident
    blocks = []
    for ident in sorted(frames, key=lambda ident: ident != main):
        if ident == skip:
            continue
        thread = threads.get(ident)
        label = thread.name if thread is not None else f"thread {ident}"
        if thread is not None and (work := describe_thread_work(thread)):
            label = f"{label}, {work}"
        stack = "".join(traceback.format_stack(frames[ident]))
        blocks.append(f"{label}:\n{stack}")
    return "\n".join(blocks) or "<no thread has a frame>"


class MemoryWatch:
    """Reports where the process is each time its RSS grows by `step` bytes,
    and aborts it with every thread's stack once it passes `limit`. A runaway
    allocation logs nothing on its own, and the OOM killer leaves no stack."""

    def __init__(
        self,
        step: int,
        limit: int = 0,
        *,
        interval: float = 0.5,
        rss: Callable[[], int] = read_rss,
        abort: Callable[[], None] | None = None,
    ) -> None:
        if step <= 0 or limit < 0:
            raise ValueError(
                f"a memory watch needs a positive step and a non-negative "
                f"limit, got step={step} limit={limit}"
            )
        self.step = step
        self.limit = limit
        self.interval = interval
        self._rss = rss
        self._abort = abort or self._abort_process
        self._next = 0
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None

    def check(self) -> bool:
        rss = self._rss()
        if self.limit and rss >= self.limit:
            _logger.critical(
                "memory watch: rss %d MiB passed the limit of %d MiB; aborting "
                "with every thread's stack:\n%s",
                rss // _MIB,
                self.limit // _MIB,
                _thread_stacks(self._watch_ident()),
            )
            self._abort()
            return True
        if rss < self._next:
            return False
        self._next = (rss // self.step + 1) * self.step
        _logger.warning(
            "memory watch: rss %d MiB (next report at %d MiB), threads at:\n%s",
            rss // _MIB,
            self._next // _MIB,
            _thread_stacks(self._watch_ident()),
        )
        return True

    def _watch_ident(self) -> int | None:
        return self._thread.ident if self._thread is not None else None

    def _run(self) -> None:
        while not self._stop.wait(self.interval):
            self.check()

    def start(self) -> None:
        self._next = 0
        self._stop.clear()
        self._thread = threading.Thread(
            target=self._run, name="odoo.memory_watch", daemon=True
        )
        self._thread.start()
        _logger.info(
            "memory watch: reporting every %d MiB, limit %s",
            self.step // _MIB,
            f"{self.limit // _MIB} MiB" if self.limit else "none",
        )

    def stop(self) -> None:
        self._stop.set()
        if self._thread is not None:
            self._thread.join()

    @staticmethod
    def _abort_process() -> None:
        for handler in logging.getLogger().handlers:
            handler.flush()
        faulthandler.dump_traceback(all_threads=True)
        os._exit(137)


def _mib_from_environ(name: str) -> int:
    value = os.environ.get(name, "").strip()
    if not value:
        return 0
    try:
        mib = int(value)
    except ValueError:
        mib = -1
    if mib < 0:
        _logger.error("%s=%r is not a whole number of MiB; ignored", name, value)
        return 0
    return mib * _MIB


_started: list[MemoryWatch] = []


def _restart_in_child() -> None:
    for watch in _started:
        watch._thread = None
        watch.start()


def start_from_environ() -> MemoryWatch | None:
    if _started:
        return _started[0]
    step = _mib_from_environ(STEP_VAR)
    limit = _mib_from_environ(LIMIT_VAR)
    if not step and not limit:
        return None
    watch = MemoryWatch(step or limit, limit)
    watch.start()
    if not _started and hasattr(os, "register_at_fork"):
        os.register_at_fork(after_in_child=_restart_in_child)
    _started.append(watch)
    return watch
