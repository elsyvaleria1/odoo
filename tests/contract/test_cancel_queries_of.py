import contextlib
import threading
import time

import psycopg
import pytest

from .conftest import requires_pg

HOLD_S = 30.0


@pytest.fixture
def pool(scratch_db):
    from odoo.db import ConnectionPool
    from odoo.db.utils import get_connection_info_for_database

    _, info = get_connection_info_for_database(scratch_db)
    pool = ConnectionPool(maxconn=4)
    try:
        yield pool, info
    finally:
        pool.close_all()


class _Holder(threading.Thread):
    def __init__(self, pool, name, sql=None):
        super().__init__(name=name, daemon=True)
        self._pool, self._info = pool
        self._sql = sql
        self.borrowed = threading.Event()
        self.done = threading.Event()
        self.backend_pid = None
        self.error = None

    def run(self):
        conn = self._pool.borrow(self._info)
        try:
            self.backend_pid = conn.info.backend_pid
            self.borrowed.set()
            if self._sql:
                try:
                    conn.execute(self._sql)
                except psycopg.Error as exc:
                    self.error = exc
            self.done.wait(HOLD_S)
        finally:
            with contextlib.suppress(psycopg.Error):
                conn.rollback()
            self._pool.give_back(conn)

    def __enter__(self):
        self.start()
        assert self.borrowed.wait(10)
        return self

    def __exit__(self, *exc):
        self.done.set()
        if self.is_alive() and self._sql:
            with psycopg.connect(dbname=self._info["dbname"], autocommit=True) as admin:
                admin.execute("SELECT pg_cancel_backend(%s)", (self.backend_pid,))
        self.join(10)


def _state_of(info, pid):
    with psycopg.connect(dbname=info["dbname"], autocommit=True) as admin:
        row = admin.execute(
            "SELECT state FROM pg_stat_activity WHERE pid = %s", (pid,)
        ).fetchone()
    return row[0] if row else None


def _wait_running(info, holder):
    deadline = time.monotonic() + 10
    while _state_of(info, holder.backend_pid) != "active":
        assert time.monotonic() < deadline, "the probe query never started"
        time.sleep(0.05)


@requires_pg
class TestCancelQueriesOf:
    def test_only_the_named_threads_running_query_is_cancelled(self, pool):
        _, info = pool
        sleep = f"SELECT pg_sleep({HOLD_S})"
        with (
            _Holder(pool, "probe.overrun", sleep) as overrun,
            _Holder(pool, "probe.bystander", sleep) as bystander,
        ):
            _wait_running(info, overrun)
            _wait_running(info, bystander)

            assert pool[0].cancel_queries_of("probe.overrun") == 1

            deadline = time.monotonic() + 10
            while overrun.error is None and time.monotonic() < deadline:
                time.sleep(0.05)
            assert isinstance(overrun.error, psycopg.errors.QueryCanceled)
            assert _state_of(info, bystander.backend_pid) == "active", (
                "a cancel aimed at one thread reached another thread's query"
            )
            assert bystander.error is None

    def test_a_held_idle_connection_is_not_counted_as_a_running_query(self, pool):
        with _Holder(pool, "probe.idle"):
            cancelled = pool[0].cancel_queries_of("probe.idle")
        assert cancelled == 0, (
            "the watchdog logged a cancelled running query for a connection that "
            "ran none -- a listener's LISTEN or a stream lease idles checked out "
            "for the thread's whole life"
        )
