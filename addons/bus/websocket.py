import base64
import bisect
import functools
import hashlib
import logging
import os
import random
import selectors
import socket
import threading
import time
from collections import deque
from contextlib import contextmanager, suppress
from typing import TYPE_CHECKING
from urllib.parse import urlparse

import psycopg
from werkzeug.datastructures import ImmutableMultiDict, MultiDict
from werkzeug.exceptions import BadRequest, HTTPException, ServiceUnavailable
from werkzeug.local import LocalStack

from odoo import api, modules
from odoo.db import PoolError, db_connect
from odoo.exceptions import AccessDenied
from odoo.http import (
    Request,
    Response,
    SessionExpiredException,
    prepare_default_session,
    root,
)
from odoo.libs.debug_log import DebugLog
from odoo.libs.worker_thread import working_on_database
from odoo.modules.registry import Registry
from odoo.service import (
    get_env_float,
    get_websocket_db_threads,
    get_websocket_max_connections,
    metrics,
)
from odoo.service.security import is_session_valid
from odoo.service.server import UPGRADE_ADOPT_KEY, CommonServer
from odoo.service.transaction import retrying
from odoo.tools import config, frozendict

from .models.bus import NOTIFICATION_HOLD_BACK_SECONDS, dispatch
from .tools import orjson
from .tools.websocket_codec import (
    CTRL_OP,
    DATA_OP,
    CloseCode,
    CloseFrame,
    ConnectionState,
    Frame,
    FrameParser,
    InvalidCloseCodeError,
    Opcode,
    PayloadTooLargeError,
    ProtocolError,
    WebsocketError,
    encode_frame,
    parse_close_payload,
)
from .tools.websocket_hub import WebsocketHub

if TYPE_CHECKING:
    from odoo.http.session import Session

_logger = logging.getLogger(__name__)
_debug = DebugLog(__name__)


MAX_TRY_ON_POOL_ERROR = 10
DELAY_ON_POOL_ERROR = 0.15
JITTER_ON_POOL_ERROR = 0.3


@contextmanager
def acquire_cursor(db):
    with _borrow_cursor(db) as cr:
        yield cr


def _borrow_cursor(db):
    delay = DELAY_ON_POOL_ERROR
    for _attempt in range(MAX_TRY_ON_POOL_ERROR - 1):
        try:
            return db_connect(db).cursor()
        except PoolError:
            time.sleep(delay + random.uniform(0, JITTER_ON_POOL_ERROR))
            delay *= 1.5
    try:
        return db_connect(db).cursor()
    except PoolError:
        raise PoolError(
            f"Failed to acquire cursor after {MAX_TRY_ON_POOL_ERROR} retries"
        ) from None


class UpgradeRequired(HTTPException):
    code = 426
    description = "Wrong websocket version was given during the handshake"

    def get_headers(self, environ=None):
        headers = super().get_headers(environ)
        headers.append(
            (
                "Sec-WebSocket-Version",
                ", ".join(sorted(WebsocketConnectionHandler.SUPPORTED_VERSIONS)),
            )
        )
        return headers


class ConnectionClosedError(WebsocketError):
    pass


class InvalidDatabaseError(WebsocketError):
    pass


class InvalidWebsocketRequestError(WebsocketError):
    pass


class RateLimitExceededError(Exception):
    pass


class _ServerClock:
    # freezegun answers time.monotonic() with frozen or real time depending on
    # how deep the caller sits under a threading frame, so the loop and job
    # threads would mix both clocks for one connection; a reference held on a
    # class is one it does not rewrite.
    monotonic = staticmethod(time.monotonic)


_public_session_lock = threading.Lock()
_public_session_sid_by_db = {}
_PUBLIC_SESSION_TOUCH_INTERVAL = 3600


class ConnectionGauge:
    REFUSAL_LOG_INTERVAL = 60.0

    def __init__(self, limit=None, *, clock=time.monotonic) -> None:
        self.limit = get_websocket_max_connections() if limit is None else limit
        self.count = 0
        self.refused = 0
        self._clock = clock
        self._lock = threading.Lock()
        self._refusals_logged_at = None
        self._refusals_unlogged = 0

    def reserve(self) -> bool:
        with self._lock:
            if not self.limit or self.count < self.limit:
                self.count += 1
                return True
            self.refused += 1
            self._refusals_unlogged += 1
            now = self._clock()
            logged_at = self._refusals_logged_at
            if logged_at is not None and now - logged_at < self.REFUSAL_LOG_INTERVAL:
                return False
            self._refusals_logged_at = now
            refusals, self._refusals_unlogged = self._refusals_unlogged, 0
        _logger.warning(
            "Refused %d websocket handshake(s) with 503: %d connections open, "
            "at ODOO_WEBSOCKET_MAX_CONNECTIONS",
            refusals,
            self.limit,
        )
        return False

    def release(self) -> None:
        with self._lock:
            self.count -= 1


_connection_gauge = ConnectionGauge()


def _collect_metrics(add) -> None:
    gauge = _connection_gauge
    add(
        "odoo_websocket_connections",
        gauge.count,
        help="Websocket connections open or being opened in this process.",
    )
    add(
        "odoo_websocket_connections_max",
        gauge.limit,
        help="ODOO_WEBSOCKET_MAX_CONNECTIONS; 0 is unbounded.",
    )
    add(
        "odoo_websocket_refused_total",
        gauge.refused,
        kind="counter",
        help="Websocket handshakes answered 503 at the connection cap.",
    )
    hub = _hub
    executor = hub.executor
    add(
        "odoo_websocket_db_threads",
        executor.size if executor else 0,
        help="Threads running websocket database jobs (ODOO_WEBSOCKET_DB_THREADS).",
    )
    add(
        "odoo_websocket_db_busy",
        executor.busy if executor else 0,
        help="Websocket database threads running a job.",
    )
    add(
        "odoo_websocket_db_queue",
        executor.queued if executor else 0,
        help="Websocket database jobs waiting for a thread.",
    )
    add(
        "odoo_websocket_outbound_bytes",
        hub.outbound,
        help="Bytes written to websockets and not yet taken by the kernel.",
    )
    add(
        "odoo_websocket_write_stalls_total",
        hub.write_stalls,
        kind="counter",
        help="Websockets cut for taking nothing for WRITE_STALL_TIMEOUT.",
    )
    latency = hub.dispatch_latency
    add(
        "odoo_websocket_dispatches_total",
        latency.count,
        kind="counter",
        help="Notification dispatches run.",
    )
    add(
        "odoo_websocket_dispatch_latency_seconds_total",
        latency.total,
        kind="counter",
        help="Seconds from a dispatch's wake to its end, summed.",
    )
    add(
        "odoo_websocket_dispatch_latency_seconds_max",
        latency.recent_max,
        help="Longest dispatch over the last one to two minutes.",
    )
    add(
        "odoo_websocket_loop_lag_seconds_max",
        hub.loop_lag.recent_max,
        help="Longest delay of the websocket loop's 1 s tick over the last one to two minutes.",
    )


metrics.register_collector(_collect_metrics)


class NotificationDispatchState:
    __slots__ = ("_clock", "_history", "_retention_sec", "last_id")

    MAX_HISTORY_LENGTH = 5000

    def __init__(self, retention_sec, clock=None) -> None:
        self._clock = clock if clock is not None else time.monotonic
        self._retention_sec = retention_sec
        self.last_id = 0
        self._history = []

    @property
    def ignore_ids(self) -> list:
        return [nid for nid, _sent_at in self._history]

    def initialize_last_id(self, last) -> None:
        if self.last_id == 0:
            self.last_id = last

    def record_dispatched(self, notif_ids) -> None:
        now = self._clock()
        for nid in notif_ids:
            bisect.insort(self._history, (nid, now), key=lambda entry: entry[0])
        last_index = -1
        for i, (_nid, sent_at) in enumerate(self._history):
            if now - sent_at > self._retention_sec:
                last_index = i
            else:
                break
        if last_index != -1:
            self.last_id = self._history[last_index][0]
            self._history = self._history[last_index + 1 :]
        overflow = len(self._history) - self.MAX_HISTORY_LENGTH
        if overflow > 0:
            self.last_id = self._history[overflow - 1][0]
            del self._history[:overflow]
            _logger.debug(
                "Notification dispatch history capped: dropped %s ids still "
                "within the retention window",
                overflow,
            )


class Websocket:
    MESSAGE_MAX_SIZE = 2**20
    MAX_NOTIFICATION_HISTORY_SEC = NOTIFICATION_HOLD_BACK_SECONDS
    RL_BURST = max(1, int(config["websocket_rate_limit_burst"]))
    RL_DELAY = float(config["websocket_rate_limit_delay"])
    RL_CONTROL_FACTOR = 10
    SESSION_VALIDITY_TTL = 60
    SESSION_VALIDITY_JITTER = 0.5
    FRAME_RECEIVE_TIMEOUT = 15
    RECEIVE_SIZE = 65536
    LANE_DEPTH = 8
    LINGER_SECONDS = 5
    LINGER_READS = 16
    WRITE_STALL_TIMEOUT = 15
    WRITE_BUFFER_LIMIT = 256 * 1024
    SEND_BUFFER = 128 * 1024

    # The dispatch round a batched wake authorised this connection to share an
    # answer in, None otherwise. Declared on the class so a connection that
    # never went through a wake reads None rather than raising.
    _poll_round = None
    _linger_until = None
    _linger_allowed = True
    _hub = None
    _gauge = None
    fd = -1
    events = 0
    timer_at = None

    def __init__(
        self,
        sock,
        session,
        cookies,
        *,
        clock=None,
        httprequest=None,
        outdated=False,
        gauge=None,
    ) -> None:
        self._clock = clock if clock is not None else _ServerClock.monotonic
        self._session = SessionView.of(session)
        self._db = session.db
        self._handshake = (
            HandshakeFacts.of(httprequest, cookies)
            if httprequest is not None
            else HandshakeFacts(cookies, None, None)
        )
        self._outdated = outdated
        self._gauge = gauge
        self.__socket = sock
        self._close_sent = False
        self._close_received = False
        self._timeout_manager = TimeoutManager(clock=self._clock)
        self._data_frames_due = 0.0
        self._control_frames_due = 0.0
        self._parser = FrameParser(self.MESSAGE_MAX_SIZE, self._limit_rate)
        self._fragments = None
        self._fragments_opcode = None
        self._frame_started_at = None
        self._waiting_for_dispatch = False
        self._channels = frozenset()
        self._session_validated_until = 0.0
        self._validated_session_sid = None
        self._dispatch_state = NotificationDispatchState(
            self.MAX_NOTIFICATION_HISTORY_SEC, clock=self._clock
        )
        self._adopted = False
        self._reading = True
        self._lane = deque()
        self._job = None
        self._job_serves_message = False
        self._dispatch_pending = False
        self._dispatch_wanted_at = None
        self._last_job_was_dispatch = False
        self._teardown_pending = False
        self._outbuf = bytearray()
        self._write_progress_at = None
        self._finish_after_flush = False
        self._linger_until = None
        self.state = ConnectionState.OPEN

    @property
    def sock(self):
        return self.__socket

    def close(self, code, reason=None):
        self._on_loop(self._close_if_open, code, reason)

    def subscribe(self, last) -> None:
        self._dispatch_state.initialize_last_id(last)
        self.trigger_notification_dispatching()

    def trigger_notification_dispatching(self, poll_round=None) -> None:
        if self.state is not ConnectionState.OPEN:
            return
        if self._waiting_for_dispatch:
            # Still queued from an earlier wake: it may share this newer
            # round's answer, which was polled after both notifications.
            # Left on the old round, whose answers are gone, a backlog only
            # grows: every late connection polls for itself.
            if poll_round is not None:
                self._poll_round = poll_round
            return
        self._waiting_for_dispatch = True
        # Only a caller that woke a BATCH passes a round, and only that round
        # lets this connection share another's answer. A lone trigger -- a
        # re-arm, a test, anything outside the dispatcher -- shares nothing.
        self._poll_round = poll_round
        self._on_loop(self._dispatch_requested)

    def _adopt(self, sock, buffered, addr) -> None:
        self._adopted = True
        self._hub = _hub
        _hub.adopt(self, buffered)

    def _abandon(self) -> None:
        if not self._adopted:
            self._adopted = True
            self._release_slot()

    def _release_slot(self) -> None:
        gauge, self._gauge = self._gauge, None
        if gauge is not None:
            gauge.release()

    def _on_loop(self, func, *args) -> None:
        hub = self._hub
        if hub is None or hub.in_loop():
            func(*args)
        else:
            hub.call_soon(func, *args)

    def on_attached(self, buffered) -> None:
        # The kernel would otherwise grow the send buffer to megabytes for a
        # client that reads nothing, all of it progress as far as the stall
        # timer can tell, and dispatches for it would go on until it filled.
        with suppress(OSError):
            self.sock.setsockopt(socket.SOL_SOCKET, socket.SO_SNDBUF, self.SEND_BUFFER)
        try:
            if self._hub.stopping:
                self._disconnect(CloseCode.GOING_AWAY)
                return
            if self._outdated:
                self._disconnect(CloseCode.CLEAN, "OUTDATED_VERSION")
            if buffered:
                self._deliver(self._receive(buffered))
        except Exception as exc:
            self.on_loop_error(exc)
        self._reschedule()
        self._pump()

    def on_readable(self) -> None:
        if self._linger_until is not None:
            if self._linger():
                self._close_socket()
            return
        try:
            messages = self._read_messages()
        except BlockingIOError:
            return
        self._deliver(messages)
        self._check_deadlines()
        self._reschedule()

    def on_writable(self) -> None:
        self._flush()

    def on_timer(self) -> None:
        if self._linger_until is not None:
            if self._clock() > self._linger_until:
                self._close_socket()
            else:
                self._reschedule()
            return
        if self.state is ConnectionState.CLOSED:
            if self._write_stalled():
                self._abort()
            else:
                self._reschedule()
            return
        self._check_deadlines()
        if (
            self.state is ConnectionState.OPEN
            and self._reading
            and self._timeout_manager.is_ping_frame_required()
        ):
            self._send_ping_frame()
        self._reschedule()

    def on_loop_error(self, exc) -> None:
        self._handle_transport_error(exc)

    def close_now(self, code) -> None:
        self._close_if_open(code)

    def abort(self) -> None:
        self._abort()

    def _close_if_open(self, code, reason=None) -> None:
        if self.state is ConnectionState.OPEN:
            self._disconnect(code, reason)

    def _dispatch_requested(self) -> None:
        if self.state is not ConnectionState.OPEN:
            return
        self._dispatch_pending = True
        if self._dispatch_wanted_at is None:
            self._dispatch_wanted_at = self._clock()
        self._pump()

    def _read_messages(self) -> list:
        data = self.__socket.recv(self.RECEIVE_SIZE)
        if not data:
            raise ConnectionClosedError
        return self._receive(data)

    def _receive(self, data) -> list:
        # A control frame behind a message waits for that message to be served,
        # in the lane: a client may send a message, then a ping, and read the
        # pong as proof the message was handled.
        items = []
        for frame in self._parser.feed(data):
            self._timeout_manager.acknowledge_frame_receipt(frame)
            if frame.opcode in CTRL_OP and (
                items or self._lane or self._job_serves_message
            ):
                items.append(frame)
                continue
            message = self._on_frame(frame)
            if message is not None:
                items.append(message)
        if not self._parser.mid_frame:
            self._frame_started_at = None
        elif self._frame_started_at is None:
            self._frame_started_at = self._clock()
        return items

    def _check_frame_deadline(self) -> None:
        started = self._frame_started_at
        if started is not None and self._clock() > started + self.FRAME_RECEIVE_TIMEOUT:
            _logger.warning(
                "Websocket peer did not complete a frame within %ss; it will "
                "reconnect. Channels: %.200s",
                self.FRAME_RECEIVE_TIMEOUT,
                self._channels,
            )
            raise ConnectionClosedError(
                f"Peer did not complete the frame within {self.FRAME_RECEIVE_TIMEOUT}s"
            )

    def _on_frame(self, frame):
        if frame.opcode in CTRL_OP:
            self._handle_control_frame(frame)
            return None
        if self.state is not ConnectionState.OPEN:
            return None
        if frame.opcode is Opcode.CONTINUE:
            if self._fragments is None:
                raise ProtocolError("Unexpected continuation frame")
            self._fragments.extend(frame.payload)
            if len(self._fragments) > self.MESSAGE_MAX_SIZE:
                raise PayloadTooLargeError
            if not frame.fin:
                return None
            message, opcode = bytes(self._fragments), self._fragments_opcode
            self._fragments = self._fragments_opcode = None
        elif self._fragments is not None:
            raise ProtocolError("A continuation frame was expected")
        elif not frame.fin:
            self._fragments = bytearray(frame.payload)
            self._fragments_opcode = frame.opcode
            return None
        else:
            message, opcode = frame.payload, frame.opcode
        return message.decode("utf-8") if opcode is Opcode.TEXT else message

    def _deliver(self, items) -> None:
        for item in items:
            if isinstance(item, Frame) or (
                self.state is ConnectionState.OPEN and item != b"\x00"
            ):
                self._lane.append(item)
        if len(self._lane) >= self.LANE_DEPTH and self._reading:
            self._reading = False
            self._update_events()
        self._pump()

    def _pump(self) -> None:
        hub = self._hub
        if hub is None:
            return
        if self._job is None:
            lane = self._lane
            while lane and isinstance(lane[0], Frame):
                self._handle_control_frame(lane.popleft())
            if self.state is ConnectionState.OPEN:
                self._start_next_job(hub)
        if not self._reading and len(self._lane) < self.LANE_DEPTH:
            self._reading = True
            self._timeout_manager.postpone_responses()
            self._update_events()

    def _start_next_job(self, hub) -> None:
        if (
            self._dispatch_pending
            and not (self._lane and self._last_job_was_dispatch)
            and not self._dispatch_held()
        ):
            self._dispatch_pending = False
            self._last_job_was_dispatch = True
            job = self._dispatch_job
        elif self._lane:
            job = functools.partial(self._message_job, self._lane.popleft())
            self._job_serves_message = True
            self._last_job_was_dispatch = False
        else:
            return
        self._job = job
        if not hub.submit(functools.partial(self._run_job, job)):
            self._job = None
            self._job_serves_message = False

    def _drop_messages(self) -> None:
        self._lane = deque(item for item in self._lane if isinstance(item, Frame))
        self._dispatch_pending = False

    def _dispatch_held(self) -> bool:
        # A dispatch only adds to what the peer has not taken yet: a slow
        # reader waits for its own buffer, every reader for the process's.
        if len(self._outbuf) > self.WRITE_BUFFER_LIMIT:
            return True
        hub = self._hub
        if hub.outbound > hub.OUTBOUND_LIMIT:
            hub.deferred.add(self)
            return True
        return False

    def resume(self) -> None:
        self._pump()

    def _run_job(self, job) -> None:
        try:
            # A job thread serves every database's connections: its log lines
            # name the one it works for now.
            with working_on_database(self._db):
                job()
        except Exception as exc:
            self._handle_transport_error(exc)
        finally:
            self._hub.call_soon(self._job_done)

    def _job_done(self) -> None:
        self._job = None
        self._job_serves_message = False
        if self._teardown_pending:
            self._teardown_pending = False
            self._hub.submit(self._teardown)
            return
        self._pump()

    def _message_job(self, message) -> None:
        WebsocketConnectionHandler._serve_message(
            self._db, self._handshake, self, message
        )

    def _dispatch_job(self) -> None:
        wanted_at, self._dispatch_wanted_at = self._dispatch_wanted_at, None
        self._dispatch_bus_notifications()
        if wanted_at is not None:
            self._hub.dispatch_latency.observe(self._clock() - wanted_at)

    def _send(self, message):
        if self.state is not ConnectionState.OPEN:
            return
        opcode = Opcode.BINARY
        if not isinstance(message, (bytes, bytearray)):
            opcode = Opcode.TEXT
        frame = Frame(opcode, message)
        self._on_loop(self._write_data_frame, encode_frame(frame), frame)

    def _write_data_frame(self, data, frame) -> None:
        if self.state is not ConnectionState.OPEN:
            return
        self._write(data)
        self._timeout_manager.acknowledge_frame_sent(frame)

    def _send_frame(self, frame) -> None:
        self._write(encode_frame(frame))
        self._timeout_manager.acknowledge_frame_sent(frame)
        if frame.opcode is Opcode.PING:
            self._reschedule()
        if not isinstance(frame, CloseFrame):
            return
        self.state = ConnectionState.CLOSING
        self._close_sent = True
        _debug.lifecycle(
            "close_sent", code=frame.code, received=self._close_received, db=self._db
        )
        self._drop_messages()
        if (
            frame.code in (CloseCode.ABNORMAL_CLOSURE, CloseCode.KILL_NOW)
            or self._close_received
        ):
            self._terminate()
            return
        self._reschedule()

    def _send_close_frame(self, code, reason=None) -> None:
        self._send_frame(CloseFrame(code, reason))

    def _send_ping_frame(self) -> None:
        self._send_frame(Frame(Opcode.PING))

    def _send_pong_frame(self, payload) -> None:
        self._send_frame(Frame(Opcode.PONG, payload))

    def _write(self, data) -> None:
        if not self._outbuf:
            sent = self._send_some(data)
            if sent == len(data):
                return
            data = data[sent:]
            self._write_progress_at = self._clock()
        self._outbuf += data
        hub = self._hub
        if hub is not None:
            hub.reserve_outbound(len(data))
        self._update_events()
        self._reschedule()

    def _send_some(self, data) -> int:
        try:
            return self.__socket.send(data)
        except BlockingIOError:
            return 0

    def _flush(self) -> None:
        sent = self._send_some(self._outbuf)
        if sent:
            del self._outbuf[:sent]
            if self._hub is not None:
                self._hub.release_outbound(sent)
            self._write_progress_at = self._clock()
        if self._outbuf:
            if self._dispatch_pending and len(self._outbuf) <= self.WRITE_BUFFER_LIMIT:
                self._pump()
            return
        self._write_progress_at = None
        if self._finish_after_flush:
            self._finish_terminate()
            return
        self._update_events()
        self._pump()

    def _write_stalled(self) -> bool:
        return (
            bool(self._outbuf)
            and self._write_progress_at is not None
            and self._clock() - self._write_progress_at > self.WRITE_STALL_TIMEOUT
        )

    def _update_events(self) -> None:
        hub = self._hub
        if hub is None or hub.connections.get(self.fd) is not self:
            return
        events = 0
        if self._linger_until is not None or (
            self._reading and not self._finish_after_flush
        ):
            events |= selectors.EVENT_READ
        if self._outbuf:
            events |= selectors.EVENT_WRITE
        hub.set_events(self, events)

    def _check_deadlines(self) -> None:
        if self._write_stalled():
            self._hub.write_stalls += 1
            _logger.info(
                "Websocket peer read nothing for %ss; closing it. Channels: %.200s",
                self.WRITE_STALL_TIMEOUT,
                self._channels,
            )
            self._abort()
            return
        manager = self._timeout_manager
        if manager.has_keep_alive_timed_out() and self.state is ConnectionState.OPEN:
            self._disconnect(CloseCode.KEEP_ALIVE_TIMEOUT)
            return
        # While the lane holds the socket unread, the answer to a ping waits
        # unread too: that wait is this server's, not the client's.
        if self._reading and manager.has_frame_response_timed_out():
            self._terminate()
            return
        self._check_frame_deadline()

    def _reschedule(self) -> None:
        hub = self._hub
        if hub is None or hub.connections.get(self.fd) is not self:
            return
        deadlines = []
        if self._linger_until is not None:
            deadlines.append(self._linger_until)
        elif self.state is not ConnectionState.CLOSED:
            deadlines.append(
                self._timeout_manager.next_deadline(
                    pinging=self.state is ConnectionState.OPEN
                )
            )
        if self._frame_started_at is not None:
            deadlines.append(self._frame_started_at + self.FRAME_RECEIVE_TIMEOUT)
        if self._outbuf and self._write_progress_at is not None:
            deadlines.append(self._write_progress_at + self.WRITE_STALL_TIMEOUT)
        if not deadlines:
            return
        delay = max(min(deadlines) - self._clock(), 0.0) + 0.01
        when = hub.now() + delay
        if self.timer_at is not None and self.timer_at <= when:
            return
        hub.schedule(self, when)

    def _disconnect(self, code, reason=None) -> None:
        if code in (CloseCode.ABNORMAL_CLOSURE, CloseCode.KILL_NOW):
            self._abort()
        else:
            self._send_close_frame(code, reason)

    @property
    def lingering(self) -> bool:
        return self._linger_until is not None

    def _abort(self) -> None:
        self._linger_allowed = False
        if self._linger_until is not None:
            self._close_socket()
            return
        if self._outbuf:
            if self._hub is not None:
                self._hub.release_outbound(len(self._outbuf))
            self._outbuf.clear()
        if self._finish_after_flush:
            self._finish_terminate()
        else:
            self._terminate()

    def _terminate(self) -> None:
        if self.state == ConnectionState.CLOSED:
            return
        self.state = ConnectionState.CLOSED
        dispatch.unsubscribe(self)
        self._lane.clear()
        self._dispatch_pending = False
        if self._outbuf:
            self._finish_after_flush = True
            self._update_events()
            self._reschedule()
            return
        self._finish_terminate()

    def _finish_terminate(self) -> None:
        self._finish_after_flush = False
        hub = self._hub
        if hub is not None:
            hub.release_outbound(len(self._outbuf))
        self._outbuf.clear()
        # Half-close, then read until the peer closes too: closing a socket
        # with unread input sends a reset, and a reset can make the peer drop
        # the close frame it has not read yet. The loop only reads what is
        # there; the rest of the wait is the linger timer's.
        self._linger_until = self._clock() + self.LINGER_SECONDS
        with suppress(OSError):
            self.__socket.shutdown(socket.SHUT_WR)
        if hub is None or not self._linger_allowed or self._linger():
            self._close_socket()
        else:
            self._update_events()
            self._reschedule()
        if hub is None:
            return
        if self._job is not None:
            self._teardown_pending = True
        else:
            hub.submit(self._teardown)

    def _linger(self) -> bool:
        try:
            for _ in range(self.LINGER_READS):
                if not self.__socket.recv(4096) or self._clock() > self._linger_until:
                    return True
        except BlockingIOError:
            return self._clock() > self._linger_until
        except OSError:
            return True
        return self._clock() > self._linger_until

    def _close_socket(self) -> None:
        self._linger_until = None
        hub = self._hub
        if hub is not None:
            hub.detach(self)
        with suppress(OSError):
            self.__socket.close()
        self._release_slot()

    def _teardown(self) -> None:
        if self._hub is not None and self._hub.stopping:
            return
        try:
            with working_on_database(self._db), acquire_cursor(self._db) as cr:
                env = self.new_env(cr, self._session)
                retrying(
                    functools.partial(
                        env["ir.websocket"]._on_websocket_closed,
                        self._handshake.cookies,
                    ),
                    env,
                )
        except Exception:
            _logger.warning("Error during websocket teardown cleanup", exc_info=True)

    def _handle_control_frame(self, frame) -> None:
        if frame.opcode is Opcode.PING:
            self._send_pong_frame(frame.payload)
        elif frame.opcode is Opcode.CLOSE:
            self.state = ConnectionState.CLOSING
            self._close_received = True
            code, reason = parse_close_payload(frame.payload)
            if not self._close_sent:
                self._send_close_frame(code, reason)
            else:
                self._terminate()

    def _handle_transport_error(self, exc) -> None:
        code, reason = CloseCode.SERVER_ERROR, str(exc)
        if isinstance(exc, (ConnectionClosedError, OSError)):
            code = CloseCode.ABNORMAL_CLOSURE
        elif isinstance(exc, (ProtocolError, InvalidCloseCodeError)):
            code = CloseCode.PROTOCOL_ERROR
        elif isinstance(exc, UnicodeDecodeError):
            code = CloseCode.INCONSISTENT_DATA
        elif isinstance(exc, PayloadTooLargeError):
            code = CloseCode.MESSAGE_TOO_BIG
        elif isinstance(exc, (PoolError, RateLimitExceededError)):
            code = CloseCode.TRY_LATER
        elif isinstance(exc, SessionExpiredException):
            code = CloseCode.SESSION_EXPIRED
        if code is CloseCode.SERVER_ERROR:
            reason = None
            if self._registry_reloaded():
                _logger.warning("Bus operation aborted; registry has been reloaded")
            else:
                _logger.error("Unhandled exception in websocket handler", exc_info=exc)
        self._on_loop(self._close_after_error, code, reason)

    def _registry_reloaded(self) -> bool:
        # The check queries the database, or loads the registry: never on the
        # loop thread, which every connection of the process waits on.
        hub = self._hub
        if hub is not None and hub.in_loop():
            return False
        try:
            registry = Registry(self._db)
            sequence = registry.registry_sequence
            return sequence != registry.check_signaling().registry_sequence
        except Exception:
            _logger.debug(
                "Registry signaling check failed for %s", self._db, exc_info=True
            )
            return False

    def _close_after_error(self, code, reason) -> None:
        if self.state is ConnectionState.OPEN:
            try:
                self._disconnect(code, reason)
            except Exception:
                _logger.debug("Failed to emit close frame, terminating", exc_info=True)
                self._abort()
        elif code is CloseCode.ABNORMAL_CLOSURE:
            self._abort()
        else:
            self._terminate()

    def _limit_rate(self, opcode) -> None:
        # GCRA: each frame is due one interval after the one before; a burst of
        # RL_BURST may come early, and one more is refused. Two floats per
        # connection where the last RL_BURST timestamps took two deques. Unlike
        # that window, the bucket refills continuously: a window of T admits
        # up to RL_BURST + T / interval frames, the same rate over time. The
        # bound sits half an interval past the burst so that the sum of float
        # intervals cannot refuse the burst's last frame; after a full burst
        # the next frame is admitted half an interval later.
        now = self._clock()
        if opcode in DATA_OP:
            interval = self.RL_DELAY
            due = max(self._data_frames_due, now)
            if due - now > (self.RL_BURST - 0.5) * interval:
                raise RateLimitExceededError
            self._data_frames_due = due + interval
        else:
            interval = self.RL_DELAY / self.RL_CONTROL_FACTOR
            due = max(self._control_frames_due, now)
            if due - now > (self.RL_BURST * self.RL_CONTROL_FACTOR - 0.5) * interval:
                raise RateLimitExceededError
            self._control_frames_due = due + interval

    def _session_check_due(self, now) -> bool:
        return (
            now >= self._session_validated_until
            or self._session.sid != self._validated_session_sid
        )

    def _revalidate_session(self, cr, now) -> bool:
        """Follow the session to its live successor and ask whether it is still
        valid, on the caller's cursor; a valid one is trusted again for up to
        SESSION_VALIDITY_TTL. A session logged out or revoked since is gone
        from the store, and as invalid as an expired one."""
        try:
            session = _follow_session_chain(self._session)
        except SessionExpiredException:
            _debug.logic("session_gone", uid=self._session.uid)
            return False
        self._session = SessionView.of(session)
        if session.uid is not None and not is_session_valid(
            session, self.new_env(cr, session), fresh_primary_cr=cr
        ):
            return False
        self._trust_session(session.sid, now)
        return True

    def _trust_session(self, sid, now) -> None:
        # Up to SESSION_VALIDITY_TTL, never past it: connections that
        # subscribed together must not all come due together.
        self._session_validated_until = now + self.SESSION_VALIDITY_TTL * (
            1 - self.SESSION_VALIDITY_JITTER * random.random()
        )
        self._validated_session_sid = sid

    def _dispatch_bus_notifications(self) -> None:
        now = self._clock()
        self._waiting_for_dispatch = False
        # Subscribers to a busy channel converge on one cursor, so a dispatch
        # round asks the same question once per connection. Each wake
        # authorises at most one shared answer, in the newest round that woke
        # the connection while it waited: a dispatch nobody woke, or a second
        # dispatch inside one round, queries for itself. That keeps a hit to
        # rows committed before the notification that opened the round;
        # anything later wakes the connection again, because
        # _waiting_for_dispatch is cleared above.
        # The result is read-only downstream -- _send only serialises it.
        poll_round, self._poll_round = self._poll_round, None
        notifications, truncated, expired = _answer_round(
            [self], self._dispatch_key(), poll_round, now
        )
        if expired:
            raise SessionExpiredException
        if not notifications:
            return
        self._dispatch_state.record_dispatched([notif["id"] for notif in notifications])
        self._send(notifications)
        if truncated:
            self.trigger_notification_dispatching()

    def _dispatch_key(self) -> tuple:
        return (
            self._db,
            self._channels,
            self._dispatch_state.last_id,
            tuple(self._dispatch_state.ignore_ids),
        )

    def _can_join_batch(self) -> bool:
        return (
            self.state is ConnectionState.OPEN
            and self._job is None
            and not self._waiting_for_dispatch
            and not self._lane
            and not self._dispatch_held()
        )

    def new_env(self, cr, session, *, set_lang=False):
        ctx = dict(session.context, lang=None)
        env = api.Environment(cr, session.uid, ctx)
        if set_lang:
            lang = env["res.lang"]._get_code(session.context.get("lang"))
            env = env(context=dict(ctx, lang=lang))
        if not env.transaction.default_env:
            env.transaction.default_env = env
        return env


class TimeoutManager:
    TIMEOUT = 15
    KEEP_ALIVE_TIMEOUT = int(config["websocket_keep_alive_timeout"])
    CONNECTION_TIMEOUT = 60
    INACTIVITY_TIMEOUT = CONNECTION_TIMEOUT - 20
    PING_JITTER = 0.1

    def __init__(self, clock=None) -> None:
        super().__init__()
        self._clock = clock if clock is not None else time.monotonic
        self._expiration_time_by_opcode = {}
        self._keep_alive_timeout = self.KEEP_ALIVE_TIMEOUT + random.uniform(
            0, self.KEEP_ALIVE_TIMEOUT / 2
        )
        now = self._clock()
        self._keep_alive_expiration_time = now + self._keep_alive_timeout
        self._next_ping_time = now + self._inactivity_timeout()

    def _inactivity_timeout(self) -> float:
        # Connections opened together would otherwise ping together, forever.
        jitter = self.PING_JITTER
        return self.INACTIVITY_TIMEOUT * random.uniform(1 - jitter, 1 + jitter)

    def acknowledge_frame_receipt(self, frame) -> None:
        self._next_ping_time = self._clock() + self._inactivity_timeout()
        self._expiration_time_by_opcode.pop(frame.opcode, None)

    def acknowledge_frame_sent(self, frame) -> None:
        now = self._clock()
        self._next_ping_time = now + self._inactivity_timeout()
        if frame.opcode in (Opcode.PING, Opcode.CLOSE):
            self._expiration_time_by_opcode[
                Opcode.PONG if frame.opcode is Opcode.PING else Opcode.CLOSE
            ] = now + self.TIMEOUT

    def postpone_responses(self) -> None:
        horizon = self._clock() + self.TIMEOUT
        for opcode, expiration in self._expiration_time_by_opcode.items():
            self._expiration_time_by_opcode[opcode] = max(expiration, horizon)

    def has_keep_alive_timed_out(self) -> bool:
        return self._clock() >= self._keep_alive_expiration_time

    def has_frame_response_timed_out(self) -> bool:
        now = self._clock()
        return any(
            now >= expiration for expiration in self._expiration_time_by_opcode.values()
        )

    def is_ping_frame_required(self) -> bool:
        return (
            not self.has_frame_response_timed_out()
            and not self.has_keep_alive_timed_out()
            and self._clock() >= self._next_ping_time
        )

    def next_deadline(self, *, pinging: bool) -> float:
        deadlines = list(self._expiration_time_by_opcode.values())
        if pinging:
            deadlines += (self._keep_alive_expiration_time, self._next_ping_time)
        return min(deadlines, default=float("inf"))


class HandshakeUserAgent:
    __slots__ = ("browser", "platform", "string")

    def __init__(self, string, platform, browser) -> None:
        self.string = string
        self.platform = platform
        self.browser = browser


class HandshakeFacts:
    """What a connection keeps of its handshake request, read while the request
    is alive: serving a message reads the cookies, and the session's device
    trace the address and the user agent. A handler wanting another field of
    the handshake adds it here."""

    __slots__ = ("cookies", "remote_addr", "user_agent")

    def __init__(self, cookies, remote_addr, user_agent) -> None:
        self.cookies = cookies
        self.remote_addr = remote_addr
        self.user_agent = user_agent

    @classmethod
    def of(cls, httprequest, cookies=None) -> HandshakeFacts:
        agent = httprequest.user_agent
        return cls(
            cookies if cookies is not None else ImmutableMultiDict(httprequest.cookies),
            httprequest.remote_addr,
            HandshakeUserAgent(agent.string, agent.platform, agent.browser),
        )


class SessionView:
    """What a connection keeps of its session between two loads of it: the
    session itself -- its data and the serialized baseline it diffs against --
    is loaded by sid where it is needed, when a message is served and when the
    session is checked again."""

    __slots__ = ("context", "sid", "uid")

    def __init__(self, sid, uid, context) -> None:
        self.sid = sid
        self.uid = uid
        self.context = context

    @classmethod
    def of(cls, session) -> SessionView:
        if isinstance(session, SessionView):
            return session
        return cls(session.sid, session.uid, frozendict(session.context or {}))


def _follow_session_chain(initial_session: SessionView) -> Session:
    return root.session_store.get_live(initial_session.sid)


_wsrequest_stack = LocalStack()
wsrequest = _wsrequest_stack()


class WebsocketRequest:
    def __init__(self, db, httprequest, websocket) -> None:
        self.db = db
        self.httprequest = httprequest
        self.session = None
        self.ws = websocket
        self.app = root
        self.registry = None

    def __enter__(self):
        _wsrequest_stack.push(self)
        return self

    def __exit__(self, *args):
        _wsrequest_stack.pop()

    def serve_websocket_message(self, message) -> None:
        try:
            jsonrequest = orjson.loads(message)
            if not isinstance(jsonrequest, dict):
                raise InvalidWebsocketRequestError(
                    "Websocket request must be a JSON object"
                )
            event_name = jsonrequest["event_name"]
        except KeyError as exc:
            raise InvalidWebsocketRequestError(
                f"Key {exc.args[0]!r} is missing from request"
            ) from exc
        except ValueError as exc:
            raise InvalidWebsocketRequestError(
                f"Invalid JSON data, {exc.args[0]}"
            ) from exc
        data = jsonrequest.get("data")
        self.session = self._acquire_session()

        try:
            self.registry = Registry(self.db).check_signaling()
            threading.current_thread().dbname = self.registry.db_name
        except (
            AttributeError,
            psycopg.OperationalError,
            psycopg.ProgrammingError,
        ) as exc:
            raise InvalidDatabaseError from exc

        with (
            acquire_cursor(self.db) as cr,
            _debug.perf(
                "message_served", cr=cr, event_name=event_name, uid=self.session.uid
            ),
        ):
            self.env = self.ws.new_env(cr, self.session, set_lang=True)
            retrying(
                functools.partial(self._serve_ir_websocket, event_name, data),
                self.env,
            )

    def _serve_ir_websocket(self, event_name, data):
        self.env["ir.websocket"]._authenticate()
        # The message has just checked the session its dispatches would
        # check again.
        self.ws._trust_session(self.session.sid, self.ws._clock())
        if event_name == "subscribe":
            self.env["ir.websocket"]._subscribe(data)
        self.env["ir.websocket"]._serve_ir_websocket(event_name, data)

    def _acquire_session(self) -> Session:
        session = _follow_session_chain(self.ws._session)
        self.ws._session = SessionView.of(session)
        return session

    def update_env(self, user=None, context=None, su=None) -> None:
        Request.update_env(self, user, context, su)

    def update_context(self, **overrides) -> None:
        self.update_env(context=dict(self.env.context, **overrides))

    @functools.cached_property
    def cookies(self):
        cookies = MultiDict(self.httprequest.cookies)
        if self.registry:
            self.registry["ir.http"]._update_cookies(cookies)
        return ImmutableMultiDict(cookies)


class WebsocketConnectionHandler:
    SUPPORTED_VERSIONS = {"13"}
    _HANDSHAKE_GUID = "258EAFA5-E914-47DA-95CA-C5AB0DC85B11"
    _REQUIRED_HANDSHAKE_HEADERS = {
        "connection",
        "host",
        "sec-websocket-key",
        "sec-websocket-version",
        "upgrade",
    }
    _VERSION = "19.0-11"
    RETRY_AFTER_AT_CAPACITY = 5

    @classmethod
    def websocket_allowed(cls, request) -> bool:
        return not modules.module.current_test

    @classmethod
    def open_connection(cls, request, version):
        if not cls.websocket_allowed(request):
            raise ServiceUnavailable("Websocket is disabled in test mode")
        try:
            response = cls._get_handshake_response(request.httprequest.headers)
            request.httprequest.raw_environ["odoo.socket"]
        except KeyError as err:
            raise ServiceUnavailable(
                "Websocket unavailable on this port. Use the evented service port."
            ) from err
        except HTTPException as exc:
            _logger.warning("Websocket handshake refused: %s", exc)
            raise
        if _hub.stopping:
            raise ServiceUnavailable(
                "The server is stopping.", retry_after=cls.RETRY_AFTER_AT_CAPACITY
            )
        gauge = _connection_gauge
        if not gauge.reserve():
            raise ServiceUnavailable(
                "Too many websocket connections on this process.",
                retry_after=cls.RETRY_AFTER_AT_CAPACITY,
            )
        try:
            public_session = cls._handle_public_configuration(request)
            if public_session is None and request.session.is_new:
                # Nothing is stored for an anonymous visitor until it writes,
                # and its cookie is never written under: the socket serves it
                # as the public user, as an untrusted origin is served.
                public_session = cls._get_shared_public_session(request.db)
            httprequest = request.httprequest
            websocket = Websocket(
                httprequest.raw_environ["odoo.socket"],
                public_session or request.session,
                httprequest.cookies,
                httprequest=httprequest,
                outdated=bool(httprequest.user_agent) and version != cls._VERSION,
                gauge=gauge,
            )
            httprequest.raw_environ[UPGRADE_ADOPT_KEY] = websocket._adopt
            _debug.lifecycle(
                "opened",
                db=websocket._db,
                uid=websocket._session.uid,
                public=public_session is not None,
                outdated=websocket._outdated,
                connections=gauge.count,
            )
            response.call_on_close(websocket._abandon)
            if public_session is None and request.session.can_save:
                # The websocket authenticates from the stored session; marking
                # it dirty instead would resend its session_id cookie, which a
                # handshake answered between a login and the next request uses
                # to put the pre-login session back in the browser.
                root.session_store.save(request.session)
        except BaseException:
            gauge.release()
            raise
        return response

    @classmethod
    def _get_handshake_response(cls, headers):
        cls._assert_handshake_validity(headers)
        accept_header = hashlib.sha1(
            (headers["sec-websocket-key"] + cls._HANDSHAKE_GUID).encode()
        ).digest()
        accept_header = base64.b64encode(accept_header)
        return Response(
            status=101,
            headers={
                "Upgrade": "websocket",
                "Connection": "Upgrade",
                "Sec-WebSocket-Accept": accept_header.decode(),
            },
        )

    @classmethod
    def _handle_public_configuration(cls, request):
        origin = request.httprequest.headers.get("origin", "")
        if cls._is_trusted_origin(origin, request):
            return None
        # Every handshake of a page embedded on another site (a live chat)
        # comes here: the downgrade is the defence, the event no incident.
        _debug.logic(
            "session_downgraded",
            host=request.httprequest.host,
            origin=origin,
            scheme=request.httprequest.scheme,
        )
        return cls._get_shared_public_session(request.session.db)

    @staticmethod
    def _get_shared_public_session(db):
        with _public_session_lock:
            sid = _public_session_sid_by_db.get(db)
            session = root.session_store.get(sid) if sid else None
            if (
                session
                and time.time() - (session.mtime or 0) > _PUBLIC_SESSION_TOUCH_INTERVAL
            ):
                # Every anonymous socket of the database rides this session:
                # reaped as idle, it would close them all at once.
                try:
                    root.session_store.keep_alive(session)
                except SessionExpiredException:
                    session = None
            if not session:
                session = root.session_store.new()
                session.update(prepare_default_session(), db=db)
                root.session_store.save(session)
                _public_session_sid_by_db[db] = session.sid
            return session

    @staticmethod
    def _normalize_origin(origin) -> str:
        url = urlparse(origin.strip())
        scheme = url.scheme.lower()
        netloc = url.netloc.lower()
        default_port = {"http": ":80", "https": ":443", "ws": ":80", "wss": ":443"}
        suffix = default_port.get(scheme)
        if suffix and netloc.endswith(suffix):
            netloc = netloc.removesuffix(suffix)
        return f"{scheme}://{netloc}"

    @classmethod
    def _is_trusted_origin(cls, origin, request) -> bool:
        origin = cls._normalize_origin(origin)
        expected = cls._normalize_origin(
            f"{request.httprequest.scheme}://{request.httprequest.host}"
        )
        if origin == expected:
            return True
        trusted_origins = os.getenv("ODOO_BUS_TRUSTED_ORIGINS", "")
        return origin in {
            cls._normalize_origin(trusted)
            for trusted in trusted_origins.split(",")
            if trusted.strip()
        }

    @classmethod
    def _assert_handshake_validity(cls, headers) -> None:
        missing_or_empty_headers = {
            header
            for header in cls._REQUIRED_HANDSHAKE_HEADERS
            if not headers.get(header)
        }
        if missing_or_empty_headers:
            raise BadRequest(
                f"""Empty or missing header(s): {", ".join(missing_or_empty_headers)}"""
            )

        if headers["upgrade"].lower() != "websocket":
            raise BadRequest("Invalid upgrade header")
        if "upgrade" not in headers["connection"].lower():
            raise BadRequest("Invalid connection header")
        if headers["sec-websocket-version"] not in cls.SUPPORTED_VERSIONS:
            raise UpgradeRequired

        key = headers["sec-websocket-key"]
        try:
            decoded_key = base64.b64decode(key, validate=True)
        except ValueError as err:
            raise BadRequest("Sec-WebSocket-Key should be b64 encoded") from err
        if len(decoded_key) != 16:
            raise BadRequest("Sec-WebSocket-Key should be of length 16 once decoded")

    @classmethod
    def _serve_message(cls, db, httprequest, websocket, message) -> None:
        with WebsocketRequest(db, httprequest, websocket) as req:
            try:
                req.serve_websocket_message(message)
            except SessionExpiredException:
                websocket.close(CloseCode.SESSION_EXPIRED)
            except PoolError:
                websocket.close(CloseCode.TRY_LATER)
            except InvalidDatabaseError:
                _logger.warning(
                    "Closing websocket: database %r is unavailable or "
                    "incompatible with this server",
                    db,
                )
                websocket.close(CloseCode.TRY_LATER)
            except (
                InvalidWebsocketRequestError,
                ValueError,
                AccessDenied,
            ) as exc:
                _logger.warning("Invalid websocket request: %s", exc)
            except Exception:
                _logger.exception(
                    "Exception occurred during websocket request handling"
                )


def _open_websockets() -> list:
    return list(_hub.connections.values())


_BATCH_JOB = object()


def _trigger_dispatch(websockets, poll_round) -> None:
    # The idle subscribers of one round that would ask the same question are
    # asked once, on one database thread, and handed the same encoded frame;
    # those due a session check are checked on that thread's cursor first. The
    # busy ones dispatch one by one.
    batches = {}
    for websocket in websockets:
        if poll_round is not None and websocket._can_join_batch():
            batches.setdefault(websocket._dispatch_key(), []).append(websocket)
        else:
            websocket.trigger_notification_dispatching(poll_round)
    for key, members in batches.items():
        hub = members[0]._hub
        for websocket in members:
            websocket._job = _BATCH_JOB
        job = functools.partial(_run_batch, hub, key, members, poll_round, hub.now())
        if not hub.submit(job):
            for websocket in members:
                websocket._job = None


def _answer_round(members, key, poll_round, now) -> tuple:
    due = [websocket for websocket in members if websocket._session_check_due(now)]
    answer = dispatch.poll_memo_get(poll_round, key)
    shared = answer is not None
    expired = set()
    if due or answer is None:
        db, channels, last_id, ignore_ids = key
        with acquire_cursor(db) as cr:
            expired = {
                websocket
                for websocket in due
                if not websocket._revalidate_session(cr, now)
            }
            valid = [websocket for websocket in members if websocket not in expired]
            if answer is None and valid:
                env = valid[0].new_env(cr, valid[0]._session)
                answer = env["bus.bus"]._poll(channels, last_id, list(ignore_ids))
                dispatch.poll_memo_set(poll_round, key, answer)
    notifications, truncated = answer or ([], False)
    _debug.perf.count(
        "dispatched",
        members=len(members),
        due=len(due),
        expired=len(expired),
        rows=len(notifications),
        truncated=truncated,
        shared=shared,
    )
    return notifications, truncated, expired


def _run_batch(hub, key, members, poll_round, woken_at) -> None:
    try:
        with working_on_database(key[0]):
            notifications, truncated, expired = _answer_round(
                members, key, poll_round, members[0]._clock()
            )
        frame = Frame(Opcode.TEXT, notifications)
        data = encode_frame(frame) if notifications else None
    except Exception:
        _logger.warning("Batched websocket dispatch failed", exc_info=True)
        hub.call_soon(_retry_batch_one_by_one, members, poll_round)
        return
    hub.call_soon(
        _deliver_batch,
        hub,
        key,
        members,
        notifications,
        truncated,
        data,
        frame,
        woken_at,
        expired,
    )


def _deliver_batch(
    hub, key, members, notifications, truncated, data, frame, woken_at, expired
) -> None:
    ids = [notification["id"] for notification in notifications]
    latency = hub.now() - woken_at
    for websocket in members:
        websocket._job = None
        try:
            rearm = False
            if websocket in expired:
                websocket.on_loop_error(SessionExpiredException())
            elif websocket.state is not ConnectionState.OPEN:
                pass
            elif websocket._dispatch_key() != key:
                rearm = True
            elif data is not None:
                websocket._dispatch_state.record_dispatched(ids)
                websocket._write_data_frame(data, frame)
                rearm = truncated
            hub.dispatch_latency.observe(latency)
            _finish_batch_member(websocket, rearm)
        except Exception as exc:
            websocket.on_loop_error(exc)


def _retry_batch_one_by_one(members, poll_round) -> None:
    for websocket in members:
        websocket._job = None
        _finish_batch_member(websocket, rearm=True, poll_round=poll_round)


def _finish_batch_member(websocket, rearm, poll_round=None) -> None:
    if websocket._teardown_pending:
        websocket._job_done()
        return
    if rearm:
        websocket.trigger_notification_dispatching(poll_round)
    websocket._pump()


def _wake_websockets(websockets, poll_round) -> None:
    if _hub.running:
        _hub.call_soon(_trigger_dispatch, list(websockets), poll_round)
    else:
        _trigger_dispatch(websockets, poll_round)


def _kick_all(code=CloseCode.GOING_AWAY) -> None:
    _hub.close_all(code)


DRAIN_TIMEOUT = 3.0


def get_drain_timeout() -> float:
    return get_env_float(
        "ODOO_WEBSOCKET_DRAIN_TIMEOUT", DRAIN_TIMEOUT, minimum=0.0, logger=_logger
    )


def _drain_on_stop() -> None:
    # A stop is not every user leaving: the close hooks (presence going
    # offline, a row per connection) are skipped, the clients reconnect to the
    # next server and carry on.
    open_count = len(_hub.connections)
    started = time.monotonic()
    cut = _hub.stop(get_drain_timeout(), CloseCode.GOING_AWAY)
    if open_count:
        _logger.info(
            "Stopping: asked %d websocket(s) to reconnect elsewhere (1001), "
            "cut %d unanswered after %.1fs",
            open_count,
            cut,
            time.monotonic() - started,
        )


_hub = WebsocketHub(db_threads=get_websocket_db_threads)
dispatch.set_waker(_wake_websockets)
CommonServer.register_on_stop_hook(_drain_on_stop)
