import contextlib
import heapq
import itertools
import logging
import os
import selectors
import socket
import threading
import time
import weakref
from collections import deque

from odoo.libs.worker_thread import as_worker_thread
from odoo.service.server import REQUEST_THREAD_PREFIX

_logger = logging.getLogger(__name__)

JOB_THREAD_TYPE = "websocket_job"
IDLE_THREAD_PREFIX = "odoo.addons.bus.websocket.idle."

LOOP_TICK = 1.0
STAT_WINDOW = 60.0


class LatencyStat:
    __slots__ = (
        "_clock",
        "_current",
        "_lock",
        "_previous",
        "_window_start",
        "count",
        "total",
    )

    def __init__(self, clock=time.monotonic) -> None:
        self._clock = clock
        self._lock = threading.Lock()
        self.count = 0
        self.total = 0.0
        self._window_start = clock()
        self._current = self._previous = 0.0

    def _rotate(self, now: float) -> None:
        elapsed = now - self._window_start
        if elapsed >= STAT_WINDOW:
            self._previous = self._current if elapsed < 2 * STAT_WINDOW else 0.0
            self._current = 0.0
            self._window_start = now

    def observe(self, seconds: float) -> None:
        with self._lock:
            self._rotate(self._clock())
            self.count += 1
            self.total += seconds
            self._current = max(self._current, seconds)

    @property
    def recent_max(self) -> float:
        with self._lock:
            self._rotate(self._clock())
            return max(self._current, self._previous)


class DbExecutor:
    def __init__(self, size: int, clock=time.monotonic) -> None:
        self.size = size
        self.busy = 0
        self._clock = clock
        self._jobs = deque()
        lock = threading.Lock()
        self._cond = threading.Condition(lock)
        # Its own condition: a wait_idle() woken by submit()'s notify() would
        # take the wake-up a sleeping job thread needs, and the job would sit.
        self._drained = threading.Condition(lock)
        self._threads = 0
        self._idle = 0
        self._closed = False

    @property
    def queued(self) -> int:
        return len(self._jobs)

    def submit(self, job) -> bool:
        with self._cond:
            if self._closed:
                return False
            self._jobs.append(job)
            if self._idle >= len(self._jobs):
                self._cond.notify()
                return True
            if self._threads >= self.size:
                return True
            self._threads += 1
        try:
            threading.Thread(target=self._run, daemon=True).start()
        except RuntimeError:
            with self._cond:
                self._threads -= 1
            _logger.warning(
                "Could not start a websocket job thread; %d running", self._threads
            )
        return True

    def close(self) -> int:
        with self._cond:
            self._closed = True
            dropped = len(self._jobs)
            self._jobs.clear()
            self._cond.notify_all()
            self._drained.notify_all()
        return dropped

    def wait_idle(self, deadline: float) -> bool:
        with self._cond:
            while self.busy or self._jobs:
                remaining = deadline - self._clock()
                if remaining <= 0:
                    return False
                self._drained.wait(remaining)
            return True

    def _next(self):
        with self._cond:
            while not self._jobs:
                if self._closed:
                    self._threads -= 1
                    return None
                self._idle += 1
                self._cond.wait()
                self._idle -= 1
            self.busy += 1
            return self._jobs.popleft()

    def _run(self) -> None:
        me = threading.current_thread()
        idle_name = f"{IDLE_THREAD_PREFIX}{me.ident}"
        # A job holds a cursor, in a test the shared test cursor: named like a
        # request thread while busy, the HTTP test harness waits for it before
        # the next test takes the registry lock.
        busy_name = f"{REQUEST_THREAD_PREFIX}{me.ident}"
        me.name = idle_name
        worker = as_worker_thread(me)
        worker.type = JOB_THREAD_TYPE
        worker.start_time = None
        while (job := self._next()) is not None:
            me.name = busy_name
            worker.start_time = self._clock()
            try:
                job()
            except Exception:
                _logger.exception("Unhandled error in a websocket job")
            finally:
                # The idle wait for the next job must not keep this one, and
                # the connection it closes over, alive.
                job = None
                worker.start_time = None
                me.name = idle_name
                with self._cond:
                    self.busy -= 1
                    if not self.busy and not self._jobs:
                        self._drained.notify_all()


class WebsocketHub:
    OUTBOUND_LIMIT = 256 * 1024 * 1024

    def __init__(self, *, db_threads, clock=time.monotonic) -> None:
        self._db_threads = db_threads
        self._clock = clock
        self._reset()
        os.register_at_fork(after_in_child=self._reset)

    def _reset(self) -> None:
        self._lock = threading.Lock()
        self._thread = None
        self._selector = None
        self._wake_r = self._wake_w = None
        self._wake_pending = False
        self._posted = deque()
        self._timers = []
        self._seq = itertools.count()
        self._exit = False
        self._next_tick = 0.0
        self.executor = None
        self.connections = {}
        self.stopping = False
        self.outbound = 0
        self.deferred = set()
        self.loop_lag = LatencyStat(self._clock)
        self.dispatch_latency = LatencyStat(self._clock)
        self.write_stalls = 0

    @property
    def running(self) -> bool:
        return self._thread is not None and self._thread.is_alive()

    def now(self) -> float:
        return self._clock()

    def in_loop(self) -> bool:
        return self._thread is threading.current_thread()

    def start(self) -> None:
        with self._lock:
            if self.running:
                return
            self._selector = selectors.DefaultSelector()
            self._wake_r, self._wake_w = socket.socketpair()
            self._wake_r.setblocking(False)
            self._wake_w.setblocking(False)
            self._selector.register(self._wake_r, selectors.EVENT_READ, None)
            self.executor = DbExecutor(self._db_threads(), clock=self._clock)
            self._exit = False
            self._thread = threading.Thread(
                target=self._run, name="odoo.addons.bus.websocket.hub", daemon=True
            )
            self._thread.start()

    def call_soon(self, func, *args) -> None:
        with self._lock:
            self._posted.append((func, args))
            if self._wake_pending or self._wake_w is None:
                return
            self._wake_pending = True
            wake = self._wake_w
        with contextlib.suppress(OSError):
            wake.send(b"\0")

    def call_and_wait(self, func, *args, timeout: float = 5.0) -> bool:
        if not self.running:
            return False
        if self.in_loop():
            func(*args)
            return True
        done = threading.Event()

        def run():
            try:
                func(*args)
            finally:
                done.set()

        self.call_soon(run)
        return done.wait(timeout)

    def adopt(self, conn, buffered=b"") -> None:
        self.start()
        self.call_soon(self._attach, conn, buffered)

    def _attach(self, conn, buffered) -> None:
        try:
            conn.sock.setblocking(False)
            conn.fd = conn.sock.fileno()
            self.connections[conn.fd] = conn
            conn.events = 0
            self.set_events(conn, selectors.EVENT_READ)
        except Exception:
            # A client gone between its 101 and here: its socket and its slot
            # are given back, not left to a hub that never registered them.
            _logger.info("Websocket could not be attached; closing it", exc_info=True)
            conn.abort()
            return
        conn.on_attached(buffered)

    def detach(self, conn) -> None:
        self.set_events(conn, 0)
        self.connections.pop(conn.fd, None)
        self.deferred.discard(conn)

    def set_events(self, conn, events) -> None:
        current = conn.events
        if events == current:
            return
        if not current:
            self._selector.register(conn.fd, events, conn)
        elif not events:
            self._selector.unregister(conn.fd)
        else:
            self._selector.modify(conn.fd, events, conn)
        conn.events = events

    def reserve_outbound(self, size: int) -> None:
        self.outbound += size

    def release_outbound(self, size: int) -> None:
        self.outbound -= size
        if self.deferred and self.outbound <= self.OUTBOUND_LIMIT:
            deferred, self.deferred = self.deferred, set()
            for conn in deferred:
                conn.resume()

    def schedule(self, conn, when: float) -> None:
        conn.timer_at = when
        heapq.heappush(self._timers, (when, next(self._seq), weakref.ref(conn)))

    def submit(self, job) -> bool:
        executor = self.executor
        return executor is not None and executor.submit(job)

    def _run(self) -> None:
        self._next_tick = self._clock() + LOOP_TICK
        while not self._exit:
            try:
                self._run_once()
            except Exception:
                _logger.exception("Websocket hub loop iteration failed")

    def _run_once(self) -> None:
        now = self._clock()
        timeout = min(LOOP_TICK, max(self._next_tick - now, 0.0))
        if self._timers:
            timeout = min(timeout, max(self._timers[0][0] - now, 0.0))
        if self._posted:
            timeout = 0
        for key, mask in self._selector.select(timeout):
            conn = key.data
            if conn is None:
                self._drain_wake()
                continue
            try:
                if mask & conn.events & selectors.EVENT_WRITE:
                    conn.on_writable()
                if mask & conn.events & selectors.EVENT_READ:
                    conn.on_readable()
            except Exception as exc:
                conn.on_loop_error(exc)
        self._run_posted()
        self._run_timers()

    def _drain_wake(self) -> None:
        with contextlib.suppress(OSError):
            while self._wake_r.recv(4096):
                pass

    def _run_posted(self) -> None:
        with self._lock:
            posted, self._posted = self._posted, deque()
            self._wake_pending = False
        for func, args in posted:
            try:
                func(*args)
            except Exception as exc:
                owner = getattr(func, "__self__", None)
                if hasattr(owner, "on_loop_error"):
                    owner.on_loop_error(exc)
                else:
                    _logger.exception("Websocket hub callback failed")

    def _run_timers(self) -> None:
        now = self._clock()
        if now >= self._next_tick:
            self.loop_lag.observe(now - self._next_tick)
            self._next_tick = now + LOOP_TICK
        timers = self._timers
        while timers and timers[0][0] <= now:
            when, _, ref = heapq.heappop(timers)
            conn = ref()
            if conn is None or conn.timer_at != when:
                continue
            conn.timer_at = None
            try:
                conn.on_timer()
            except Exception as exc:
                conn.on_loop_error(exc)

    def _for_each_connection(self, action) -> None:
        for conn in list(self.connections.values()):
            try:
                action(conn)
            except Exception as exc:
                conn.on_loop_error(exc)

    def close_all(self, code, *, timeout: float = 5.0) -> bool:
        def close():
            self._for_each_connection(lambda conn: conn.close_now(code))

        return self.call_and_wait(close, timeout=timeout)

    def stop(self, drain_timeout: float, code) -> int:
        if not self.running:
            self.stopping = True
            return 0
        deadline = self._clock() + drain_timeout

        def begin():
            self.stopping = True
            self._for_each_connection(lambda conn: conn.close_now(code))

        def answering():
            return [c for c in list(self.connections.values()) if not c.lingering]

        self.call_and_wait(begin, timeout=drain_timeout)
        while answering() and self._clock() < deadline:
            time.sleep(0.02)
        remaining = len(answering())

        def finish():
            self._for_each_connection(lambda conn: conn.abort())
            self._exit = True

        self.call_and_wait(finish, timeout=1.0)
        # finish may never have run on a blocked loop: the flag is what makes
        # it end, not the callback.
        self._exit = True
        self.executor.wait_idle(max(deadline, self._clock() + 0.1))
        self.executor.close()
        self._thread.join(1.0)
        if self._thread.is_alive():
            # Closing its selector under it would make every iteration fail
            # and the loop spin; the process is going away anyway.
            _logger.warning("Websocket hub loop did not stop; leaving it to exit")
            return remaining
        for resource in (self._selector, self._wake_r, self._wake_w):
            with contextlib.suppress(OSError):
                resource.close()
        return remaining
