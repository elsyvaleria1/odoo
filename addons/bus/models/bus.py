import contextlib
import datetime
import logging
import os
import selectors
import threading
import time

import psycopg
import psycopg.sql
from psycopg import InterfaceError

import odoo
from odoo import api, fields, models
from odoo.libs import backoff
from odoo.libs.json import dumps as json_dumps
from odoo.libs.json import loads as json_loads
from odoo.service.server import CommonServer
from odoo.tools import SQL
from odoo.tools.json import json_default

from ..tools.websocket_codec import ConnectionState

_logger = logging.getLogger(__name__)

POLL_LOOKBACK_SECONDS = 50
DISPATCHER_SELECT_TIMEOUT = 50
MAX_DISPATCHER_RETRY_DELAY = 50
DEFAULT_GC_RETENTION_SECONDS = 60 * 60 * 24
GC_MESSAGES_BATCH_SIZE = 10000
NOTIFICATION_HOLD_BACK_SECONDS = 10

ODOO_NOTIFY_FUNCTION = os.getenv("ODOO_NOTIFY_FUNCTION", "pg_notify")


def get_notify_payload_max_length(default=8000):
    try:
        length = int(os.environ.get("ODOO_NOTIFY_PAYLOAD_MAX_LENGTH", default))
    except ValueError:
        _logger.warning(
            "ODOO_NOTIFY_PAYLOAD_MAX_LENGTH has to be an integer, "
            "defaulting to %d bytes",
            default,
        )
        length = default
    return length


NOTIFY_PAYLOAD_MAX_LENGTH = get_notify_payload_max_length()

DISPATCH_CATCHUP_CHUNK_SIZE = 50
DISPATCH_CATCHUP_CHUNK_DELAY = 0.1

MAX_NOTIFICATIONS_PER_POLL = 500
MAX_NOTIFICATION_BYTES_PER_POLL = 256 * 1024


_notify_conn: psycopg.Connection | None = None
_notify_lock = threading.Lock()
_notify_conns_inherited_from_parent = []


def _reset_notify_state_in_child() -> None:
    global _notify_conn, _notify_lock  # noqa: PLW0603  one NOTIFY connection per process, reset after fork
    if _notify_conn is not None:
        _notify_conns_inherited_from_parent.append(_notify_conn)
        _notify_conn = None
    _notify_lock = threading.Lock()


os.register_at_fork(after_in_child=_reset_notify_state_in_child)


def _get_notify_conn_locked():
    global _notify_conn  # noqa: PLW0603  one NOTIFY connection per process
    if _notify_conn is None or _notify_conn.closed:
        _dbname, params = odoo.db.get_connection_info_for_database("postgres")
        _notify_conn = psycopg.connect(autocommit=True, **params)
    return _notify_conn


def _close_notify_conn_locked() -> None:
    global _notify_conn  # noqa: PLW0603  one NOTIFY connection per process
    if _notify_conn is not None:
        with contextlib.suppress(psycopg.Error, OSError):
            _notify_conn.close()
        _notify_conn = None


def _close_notify_conn() -> None:
    with _notify_lock:
        _close_notify_conn_locked()


def _send_pg_notify(payloads) -> None:
    _query = psycopg.sql.SQL("SELECT {}('imbus', %s)").format(
        psycopg.sql.Identifier(ODOO_NOTIFY_FUNCTION)
    )
    payloads = list(payloads)
    sent = 0
    with _notify_lock:
        for attempt in range(2):
            try:
                conn = _get_notify_conn_locked()
                while sent < len(payloads):
                    try:
                        conn.execute(_query, (payloads[sent],))
                    except InterfaceError, psycopg.OperationalError:
                        raise
                    except Exception:
                        if conn.closed:
                            raise
                        _logger.warning(
                            "Skipping imbus NOTIFY payload rejected by "
                            "PostgreSQL: %.200s",
                            payloads[sent],
                            exc_info=True,
                        )
                    sent += 1
                return
            except Exception:
                _close_notify_conn_locked()
                if attempt == 1:
                    raise


def json_dump(v):
    return json_dumps(v, default=json_default)


def hashable(key):
    if isinstance(key, list):
        return tuple(hashable(item) for item in key)
    return key


def channel_with_db(dbname, channel):
    if isinstance(channel, models.Model):
        return (dbname, channel._name, channel.id)
    if (
        isinstance(channel, tuple)
        and len(channel) == 2
        and isinstance(channel[0], models.Model)
    ):
        return (dbname, channel[0]._name, channel[0].id, channel[1])
    if isinstance(channel, str):
        return (dbname, channel)
    return channel


def get_notify_payloads(channels):
    payloads = []
    items = []
    items_len = 0
    for item in channels:
        item_len = len(item.encode())
        if item_len + 2 >= NOTIFY_PAYLOAD_MAX_LENGTH:
            _logger.error(
                "Dropping imbus channel whose %d-byte NOTIFY payload exceeds "
                "the %d-byte limit: %.200s",
                item_len + 2,
                NOTIFY_PAYLOAD_MAX_LENGTH,
                item,
            )
            continue
        if items and items_len + len(items) + item_len + 2 >= NOTIFY_PAYLOAD_MAX_LENGTH:
            payloads.append(f"[{','.join(items)}]")
            items = []
            items_len = 0
        items.append(item)
        items_len += item_len
    if items:
        payloads.append(f"[{','.join(items)}]")
    return payloads


class BusBus(models.Model):
    _name = "bus.bus"

    _description = "Communication Bus"

    channel = fields.Char()
    message = fields.Char()

    _channel_id_idx = models.Index("(channel, id)")
    _create_date_idx = models.Index("(create_date)")

    @api.autovacuum
    def _gc_messages(self) -> tuple:
        param_value = self.env.registry.settings.get(
            self.env, "bus.gc_retention_seconds", DEFAULT_GC_RETENTION_SECONDS
        )
        try:
            gc_retention_seconds = int(param_value)
        except ValueError, TypeError:
            _logger.warning(
                "bus.gc_retention_seconds is %r (must be an integer); using default %d seconds.",
                param_value,
                DEFAULT_GC_RETENTION_SECONDS,
            )
            gc_retention_seconds = DEFAULT_GC_RETENTION_SECONDS
        if gc_retention_seconds <= 0:
            _logger.warning(
                "bus.gc_retention_seconds is %d (must be > 0); using default %d seconds.",
                gc_retention_seconds,
                DEFAULT_GC_RETENTION_SECONDS,
            )
            gc_retention_seconds = DEFAULT_GC_RETENTION_SECONDS
        timeout_ago = fields.Datetime.now() - datetime.timedelta(
            seconds=gc_retention_seconds
        )
        # the newest row stays: _bus_last_id is MAX(id), the watermark a client
        # reconciles an absolute value against, and it must never go back to 0
        self.env.cr.execute(
            "DELETE FROM bus_bus WHERE id IN "
            "(SELECT id FROM bus_bus WHERE create_date < %s"
            " AND id < (SELECT MAX(id) FROM bus_bus) LIMIT %s)",
            (timeout_ago, GC_MESSAGES_BATCH_SIZE),
        )
        deleted = self.env.cr.rowcount
        return deleted, deleted == GC_MESSAGES_BATCH_SIZE

    @api.model
    def _sendone(self, target, notification_type, message) -> None:
        self._add_commit_hooks()
        channel = json_dump(channel_with_db(self.env.cr.dbname, target))
        self.env.cr.precommit.data["bus.bus.values"].append(
            {
                "channel": channel,
                "message": json_dump(
                    {
                        "type": notification_type,
                        "payload": message,
                    }
                ),
            }
        )
        self.env.cr.postcommit.data["bus.bus.channels"].add(channel)

    def _add_commit_hooks(self) -> None:
        cr = self.env.cr
        if "bus.bus.values" not in cr.precommit.data:
            cr.precommit.data.setdefault_list("bus.bus.values")

            @cr.precommit.add
            def create_bus():
                # A row's id is drawn here, and a flush (a savepoint) can run
                # this long before the commit that makes the row visible.
                cr.postcommit.data.setdefault("bus.bus.first_insert", time.monotonic())
                self.sudo().create(cr.precommit.data.pop("bus.bus.values"))

        if "bus.bus.channels" not in cr.postcommit.data:
            cr.postcommit.data.setdefault_set("bus.bus.channels")

            @cr.postcommit.add
            def notify():
                channels = list(cr.postcommit.data.pop("bus.bus.channels"))
                inserted_at = cr.postcommit.data.pop("bus.bus.first_insert", None)
                held_for = (
                    0.0 if inserted_at is None else time.monotonic() - inserted_at
                )
                if held_for > NOTIFICATION_HOLD_BACK_SECONDS:
                    _logger.warning(
                        "Bus notification inserted %.1fs before its commit, "
                        "beyond the %ds hold-back window: it may never be "
                        "dispatched to clients that received other "
                        "notifications meanwhile. A savepoint flushes pending "
                        "bus notifications; send them after the transaction's "
                        "long-running part. Channels: %.300s",
                        held_for,
                        NOTIFICATION_HOLD_BACK_SECONDS,
                        channels,
                    )
                payloads = get_notify_payloads(channels)
                if len(payloads) > 1:
                    _logger.info(
                        "The imbus notification payload was too large, it's been split into %d payloads.",
                        len(payloads),
                    )
                try:
                    _send_pg_notify(payloads)
                except Exception:
                    _logger.exception(
                        "Failed to send imbus NOTIFY; delivery of the committed "
                        "bus notifications will be delayed."
                    )

    @api.model
    def _poll(
        self, channels, last=0, ignore_ids=None, limit=MAX_NOTIFICATIONS_PER_POLL
    ):
        return self._poll_batch(channels, last, ignore_ids, limit)[0]

    @api.model
    def _poll_batch(
        self,
        channels,
        last=0,
        ignore_ids=None,
        limit=MAX_NOTIFICATIONS_PER_POLL,
        max_bytes=MAX_NOTIFICATION_BYTES_PER_POLL,
    ) -> tuple:
        if last == 0:
            timeout_ago = fields.Datetime.now() - datetime.timedelta(
                seconds=POLL_LOOKBACK_SECONDS
            )
            where = SQL("create_date > %s", timeout_ago)
        else:
            where = SQL("id > %s", last)
        if ignore_ids:
            where = SQL("%s AND NOT (id = ANY(%s))", where, ignore_ids)
        channels = [json_dump(channel_with_db(self.env.cr.dbname, c)) for c in channels]
        self.env.cr.execute(
            SQL(
                "SELECT id, message FROM bus_bus WHERE %s AND channel = ANY(%s)"
                " ORDER BY id LIMIT %s",
                where,
                channels,
                limit + 1,
            )
        )
        rows = self.env.cr.fetchall()
        truncated = len(rows) > limit
        del rows[limit:]
        notifications = []
        payload_bytes = 0
        for row in rows:
            payload_bytes += len(row[1])
            notifications.append({"id": row[0], "message": json_loads(row[1])})
            if payload_bytes >= max_bytes:
                truncated = truncated or len(notifications) < len(rows)
                break
        return notifications, truncated

    def _bus_last_id(self):
        self.env.cr.execute("SELECT COALESCE(MAX(id), 0) FROM bus_bus")
        return self.env.cr.fetchone()[0]


def _keep_session_alive_while_idle(conn) -> None:
    try:
        conn.execute("SET idle_session_timeout = 0")
    except psycopg.Error as exc:
        _logger.info(
            "Bus.loop could not clear idle_session_timeout, the LISTEN "
            "connection may be reaped while idle: %s",
            exc,
        )


class ImDispatch(threading.Thread):
    MAX_POLL_MEMO_KEYS = 512

    def __init__(self) -> None:
        super().__init__(daemon=True, name=f"{__name__}.Bus")
        self._channels_to_ws = {}
        self._lock = threading.Lock()
        self._first_listen = True
        self._ever_started = False
        self._poll_round = 0
        self._poll_memo = {}
        self._poll_memo_lock = threading.Lock()
        self._start_lock = threading.Lock()
        self._waker = None

    def set_waker(self, waker) -> None:
        # One call per wake for a whole set of websockets, rather than one
        # cross-thread hand-off per websocket.
        self._waker = waker

    def _wake(self, websockets, poll_round) -> None:
        if self._waker is not None:
            self._waker(websockets, poll_round)
            return
        for websocket in websockets:
            websocket.trigger_notification_dispatching(poll_round)

    def open_poll_round(self):
        with self._poll_memo_lock:
            self._poll_round += 1
            self._poll_memo.clear()
            return self._poll_round

    def poll_memo_get(self, round_id, key):
        with self._poll_memo_lock:
            if round_id != self._poll_round:
                return None
            return self._poll_memo.get(key)

    def poll_memo_set(self, round_id, key, value) -> None:
        with self._poll_memo_lock:
            if round_id != self._poll_round:
                return
            if len(self._poll_memo) < self.MAX_POLL_MEMO_KEYS:
                self._poll_memo[key] = value

    @property
    def is_healthy(self) -> bool:
        return bool(
            not stop_event.is_set() and (not self._ever_started or self.is_alive())
        )

    def _start_if_stopped(self) -> None:
        # Subscriptions arrive on several threads at once, and two that both
        # find the thread not alive would both start it.
        with self._start_lock:
            with contextlib.suppress(RuntimeError):
                if not self.is_alive():
                    self.start()
            self._ever_started = True

    def subscribe(self, channels, last, db, websocket) -> None:
        channels = frozenset(hashable(channel_with_db(db, c)) for c in channels)
        # A connection closes on the loop thread while its subscribe runs on a
        # job thread: checked and recorded under the lock its unsubscribe
        # takes, a closed one is never registered again, and an unsubscribe
        # always sees the channels it has to remove.
        with self._lock:
            if websocket.state is not ConnectionState.OPEN:
                return
            self._discard(websocket, websocket._channels - channels)
            for channel in channels:
                self._channels_to_ws.setdefault(channel, set()).add(websocket)
            websocket._channels = channels
        websocket.subscribe(last)
        self._start_if_stopped()

    def unsubscribe(self, websocket) -> None:
        with self._lock:
            self._discard(websocket, websocket._channels)

    def _discard(self, websocket, channels) -> None:
        for channel in channels:
            ws_set = self._channels_to_ws.get(channel)
            if ws_set is not None:
                ws_set.discard(websocket)
                if not ws_set:
                    del self._channels_to_ws[channel]

    def loop(self) -> None:
        _logger.info("Bus.loop listen imbus on db postgres")
        _dbname, params = odoo.db.get_connection_info_for_database("postgres")
        with (
            psycopg.connect(autocommit=True, **params) as conn,
            selectors.DefaultSelector() as sel,
        ):
            _keep_session_alive_while_idle(conn)
            conn.execute("LISTEN imbus")
            sel.register(conn, selectors.EVENT_READ)
            if self._first_listen:
                self._first_listen = False
            else:
                self._dispatch_to_all()
            while not stop_event.is_set():
                if sel.select(DISPATCHER_SELECT_TIMEOUT):
                    channels = []
                    for notif in conn.notifies(timeout=0):
                        channels.extend(self._parse_imbus_payload(notif.payload))
                    poll_round = self.open_poll_round()
                    self._wake(self._collect_websockets(channels), poll_round)

    @staticmethod
    def _parse_imbus_payload(payload):
        try:
            channels = json_loads(payload)
        except ValueError:
            _logger.warning("Bus.loop ignoring malformed imbus payload: %r", payload)
            return []
        if not isinstance(channels, list):
            _logger.warning("Bus.loop ignoring non-list imbus payload: %r", payload)
            return []
        return channels

    def _collect_websockets(self, channels):
        websockets = set()
        with self._lock:
            for channel in channels:
                try:
                    websockets.update(self._channels_to_ws.get(hashable(channel), ()))
                except TypeError:
                    _logger.warning("Bus.loop ignoring unhashable channel: %r", channel)
        return websockets

    def _dispatch_to_all(self) -> None:
        poll_round = self.open_poll_round()
        with self._lock:
            websockets = list(set().union(*self._channels_to_ws.values()))
        for start in range(0, len(websockets), DISPATCH_CATCHUP_CHUNK_SIZE):
            if start and stop_event.wait(DISPATCH_CATCHUP_CHUNK_DELAY):
                return
            self._wake(
                websockets[start : start + DISPATCH_CATCHUP_CHUNK_SIZE], poll_round
            )

    def run(self):
        attempt = 0
        while not stop_event.is_set():
            started_at = time.monotonic()
            try:
                self.loop()
            except Exception as exc:
                if (
                    isinstance(exc, (InterfaceError, psycopg.OperationalError))
                    and stop_event.is_set()
                ):
                    continue
                if time.monotonic() - started_at > MAX_DISPATCHER_RETRY_DELAY:
                    attempt = 0
                attempt += 1
                retry_delay = backoff.get_bound(
                    attempt, base=1, cap=MAX_DISPATCHER_RETRY_DELAY
                )
                _logger.exception("Bus.loop error, retry in %d seconds", retry_delay)
                stop_event.wait(retry_delay)


dispatch = ImDispatch()
stop_event = threading.Event()
CommonServer.register_on_stop_hook(stop_event.set)
CommonServer.register_on_stop_hook(_close_notify_conn)
