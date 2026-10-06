from __future__ import annotations

import threading
from contextlib import contextmanager
from typing import TYPE_CHECKING, Protocol, cast

if TYPE_CHECKING:
    from collections.abc import Iterator

__all__ = [
    "REQUEST_SCOPED_ATTRIBUTES",
    "WorkerThread",
    "as_worker_thread",
    "current_worker_thread",
    "describe_thread_work",
    "forget_request",
    "working_on_database",
]


class WorkerThread(Protocol):
    dbname: str | None
    uid: int | None
    url: str
    request_id: str
    query_count: int
    query_time: float
    perf_t0: float
    cursor_mode: str | None
    rpc_model_method: str

    # Not request-scoped: these describe the thread's role and the unit of
    # work it is on, and outlive any one request. `forget_request` drops
    # everything above and resets `rpc_model_method`; a new attribute here
    # has to be one or the other, which is what
    # `test_every_declared_attribute_is_accounted_for` asks.
    type: str

    start_time: float | None

    exec_context: object


REQUEST_SCOPED_ATTRIBUTES: tuple[str, ...] = (
    "query_count",
    "query_time",
    "perf_t0",
    "cursor_mode",
    "dbname",
    "uid",
    "url",
    "request_id",
)
"""What describes the request a thread is serving, and must not outlive it.

`query_count` is the one the readers gate on -- the perf log filter and the
pool's query accumulator both ask whether it is there and then read
`query_time`, `perf_t0` and `cursor_mode` without asking again -- so these
go together or not at all.  Two places answer "that request is over": the
transport, when a malformed head means no application will run, and the
application, before it dispatches.  Each kept its own list by hand, and the
shorter one left the previous request's database and user on the thread for
the error line it was about to log.
"""


def forget_request() -> None:
    worker = as_worker_thread(threading.current_thread())
    worker.rpc_model_method = ""
    for attr in REQUEST_SCOPED_ATTRIBUTES:
        if hasattr(worker, attr):
            delattr(worker, attr)


def as_worker_thread(thread: threading.Thread) -> WorkerThread:
    return cast("WorkerThread", thread)


def current_worker_thread() -> WorkerThread:
    return as_worker_thread(threading.current_thread())


@contextmanager
def working_on_database(db_name: str) -> Iterator[None]:
    worker = as_worker_thread(threading.current_thread())
    was_set = hasattr(worker, "dbname")
    previous = worker.dbname if was_set else None
    worker.dbname = db_name
    try:
        yield
    finally:
        if was_set:
            worker.dbname = previous
        elif hasattr(worker, "dbname"):
            del worker.dbname


def describe_thread_work(thread: threading.Thread) -> str:
    # What the operator will want beside the thread name or pid: the request
    # it is serving (the http layer stamps `url` and `request_id`, the RPC
    # dispatcher `rpc_model_method`) or the database a cron/job pass is
    # sweeping.  The verdicts naming it are logged from a monitor thread, so
    # the request id has to travel in the message to join the request's lines.
    kind = getattr(thread, "type", None)
    if kind == "http":
        url = getattr(thread, "url", "")
        if not url:
            return ""
        method = getattr(thread, "rpc_model_method", "")
        text = f"serving {url} ({method})" if method else f"serving {url}"
        if request_id := getattr(thread, "request_id", ""):
            text += f", request {request_id}"
        return text
    db_name = getattr(thread, "dbname", None)
    return f"sweeping {db_name}" if db_name else ""
