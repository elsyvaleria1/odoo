from __future__ import annotations

import logging
import os

from odoo.libs.debug_log import DebugLog
from odoo.libs.memory_watch import read_rss

from ._env import get_env_float, get_env_int
from .settings import INHERIT_FROM_CRON, current

_debug = DebugLog(__name__)

GRACEFUL_STOP_TIMEOUT_S = 60.0
"""How long a stopping server lets in-flight work finish before it escalates.

One bound for both flavours: the prefork master waits this long for SIGINTed
workers before SIGKILL, and the threaded server waits this long for its busy
request threads before closing the listener under them.
"""


def get_graceful_stop_timeout(logger: logging.Logger) -> float:
    return get_env_float(
        "ODOO_GRACEFUL_STOP_TIMEOUT",
        GRACEFUL_STOP_TIMEOUT_S,
        minimum=1.0,
        logger=logger,
    )


BACKOFF_CEILING_S = 60
"""Longest a reconnect back-off will wait.

Its own constant.  It was `SLEEP_INTERVAL`, the cron poll interval, which three
unrelated things had borrowed for the number 60 rather than the meaning: this
ceiling, the cron sweep cadence, and how long `ThreadedServer.run` lets
in-flight requests finish before reloading.  Tuning any one of them moved the
other two.
"""

BACKOFF_BASE_S = 2
"""What a reconnect waits after its first failure, doubling from there.

Stated rather than implied.  The curve came from a second exponential
backoff in this package -- `min(2 ** attempts, ceiling)` over a 0-based
counter, so the base was the offset and neither was written down.
`odoo.libs.backoff` is the one implementation now, 1-based with an explicit
base, and `base=2` is what reproduces this curve exactly.
"""


WEBSOCKET_MAX_CONNECTIONS = 10000

WEBSOCKET_DESCRIPTORS = 1
"""Descriptors one websocket holds: its socket.  The loop that serves every
websocket of the process owns one selector and one socketpair between them."""

WEBSOCKET_MIN_DB_THREADS = 2


def get_websocket_max_connections() -> int:
    return get_env_int(
        "ODOO_WEBSOCKET_MAX_CONNECTIONS",
        WEBSOCKET_MAX_CONNECTIONS,
        minimum=0,
        logger=logging.getLogger("odoo.service.server"),
    )


def get_websocket_db_threads() -> int:
    # What the pool has left once every HTTP thread holds two connections
    # and every listener its session: websocket jobs queue for these threads
    # rather than racing the requests for a connection.
    import odoo

    from .httpd import (
        compute_http_thread_limit,
        count_listener_permits,
        get_http_pool_size,
    )

    settings = current()
    evented = bool(odoo.evented)
    pool = get_http_pool_size(settings, evented=evented)
    http_threads, _ = compute_http_thread_limit(
        settings, listeners_spawned=not evented, evented=evented
    )
    listeners = count_listener_permits(settings, listeners_spawned=not evented)
    return get_env_int(
        "ODOO_WEBSOCKET_DB_THREADS",
        max(WEBSOCKET_MIN_DB_THREADS, pool - 2 * http_threads - listeners),
        minimum=1,
        logger=logging.getLogger("odoo.service.server"),
    )


def get_cron_real_time_budget() -> float:
    return current().cron_real_time_budget


def get_job_real_time_budget() -> float:
    return current().job_real_time_budget


def get_memory_over_soft_limit(soft_limit: int) -> int | None:
    if not soft_limit:
        return None
    memory = read_rss()
    _debug.perf.count(
        "limits.memory_sampled",
        rss=memory,
        soft_limit=soft_limit,
        over=memory > soft_limit,
    )
    return memory if memory > soft_limit else None


def empty_pipe(fd: int) -> None:
    try:
        while os.read(fd, 4096):
            pass
    except BlockingIOError:
        pass


__all__ = (
    "BACKOFF_BASE_S",
    "BACKOFF_CEILING_S",
    "GRACEFUL_STOP_TIMEOUT_S",
    "INHERIT_FROM_CRON",
    "WEBSOCKET_DESCRIPTORS",
    "WEBSOCKET_MAX_CONNECTIONS",
    "WEBSOCKET_MIN_DB_THREADS",
    "empty_pipe",
    "get_cron_real_time_budget",
    "get_graceful_stop_timeout",
    "get_job_real_time_budget",
    "get_memory_over_soft_limit",
    "get_websocket_db_threads",
    "get_websocket_max_connections",
)
