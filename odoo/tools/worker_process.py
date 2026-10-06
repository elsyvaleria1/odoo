import atexit
import contextlib
import logging
import subprocess
from collections.abc import Callable

__all__ = ["close_at_shutdown", "close_pipes", "stop"]

_logger = logging.getLogger(__name__)

_closers: set[Callable[[], None]] = set()


def close_at_shutdown(close: Callable[[], None]) -> None:
    if close in _closers:
        return
    _closers.add(close)
    atexit.register(close)
    try:
        from odoo.service.server import CommonServer

        CommonServer.register_on_stop_hook(close)
    except Exception:
        _logger.debug(
            "could not register %s on server stop", close.__qualname__, exc_info=True
        )


def close_pipes(proc: subprocess.Popen, *, flush: bool = True) -> None:
    # a forked child holds a copy of the parent's write buffer: flushing it
    # would send the parent's half-written request a second time
    for pipe in (proc.stdin, proc.stdout):
        if pipe is not None:
            with contextlib.suppress(OSError):
                (pipe if flush else getattr(pipe, "raw", pipe)).close()


def stop(proc: subprocess.Popen, *, grace_s: float = 0) -> bool:
    if grace_s:
        close_pipes(proc)
        try:
            proc.wait(timeout=grace_s)
        except subprocess.TimeoutExpired:
            pass
        else:
            return False
    with contextlib.suppress(OSError):
        proc.kill()
    with contextlib.suppress(subprocess.TimeoutExpired, OSError):
        proc.wait(timeout=5)
    close_pipes(proc)
    return True
