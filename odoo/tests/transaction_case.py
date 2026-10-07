import contextlib
import difflib
import functools
import inspect
import ipaddress
import logging
import pathlib
import pprint
import re
import socket
import sys
import threading
import traceback
import types
import warnings
from contextlib import ExitStack, contextmanager
from datetime import date, datetime
from itertools import zip_longest
from typing import TYPE_CHECKING, Any, ClassVar, cast
from unittest import TestResult, mock
from unittest.mock import Mock, _patch, patch
from urllib.parse import urlsplit

import psutil
import requests
from lxml import etree, html
from requests import PreparedRequest, Session
from werkzeug.exceptions import BadRequest
from werkzeug.routing import Map

import odoo.cli
import odoo.http
import odoo.models
import odoo.orm.runtime
from odoo import api
from odoo.db import Cursor, observing_statements
from odoo.db.utils import update_planner_stats
from odoo.exceptions import AccessError
from odoo.http import Controller
from odoo.libs.collections import DotDict
from odoo.libs.debug_log import DebugLog
from odoo.libs.logging import lower_logging, mute_logger
from odoo.libs.password import CryptContext
from odoo.libs.sql import SQL
from odoo.libs.worker_thread import describe_thread_work
from odoo.logutils import RUNBOT
from odoo.modules.registry import DummyRLock, Registry
from odoo.tools import config, profiler
from odoo.tools.constants import CACHES_BY_KEY, ROLLBACK_SAFE_CACHES
from odoo.tools.subprocess import dumpstacks

from . import clock
from .case import TestCase
from .cursor import TestCursor, _release_foreign_acquisition, cannot_release
from .matchers import Approx, _normalize_arch_for_assert
from .utils import HOST, env_int, get_db_name

if TYPE_CHECKING:
    from collections.abc import Callable, Generator, Iterable, Iterator

    from .result import OdooTestResult


_logger = logging.getLogger(__name__)
_debug = DebugLog(__name__)


TEST_CURSOR_COOKIE_NAME = "test_request_key"


class RegistryRLock(threading._RLock):  # type: ignore[misc]  # only the private class is subclassable
    _owner: int | None

    @property
    def count(self) -> int:
        return self._count

    @property
    def held_by_this_thread(self) -> bool:
        return self._owner == threading.get_ident()

    @property
    def owner_ident(self) -> int | None:
        return self._owner


class RegistryTestLockLost(RuntimeError):
    pass


class RegistryTestLockRevoked(RuntimeError):
    pass


_registry_test_lock = RegistryRLock()


def current_test_tag() -> str:
    return getattr(odoo.modules.module.current_test, "canonical_tag", "<no test>")


@contextmanager
def release_test_lock() -> Generator[None]:
    if not _registry_test_lock.held_by_this_thread:
        _debug.logic(
            "test.lock.not_held",
            test=current_test_tag(),
            held=_registry_test_lock.count,
        )
        _logger.warning(
            "The registry test lock was not held on entering %s, so this "
            "hand-over releases nothing and re-acquires nothing. An earlier "
            "test lost it -- look for the first 'Halting the test run' above.",
            current_test_tag(),
        )
        yield
        return

    _registry_test_lock.release()
    _debug.lifecycle(
        "test.lock.released", test=current_test_tag(), held=_registry_test_lock.count
    )
    try:
        yield
    finally:
        _take_back_test_lock()


# How long the hand-back waits before it names the thread still holding the
# lock -- a request that outlived its client -- and dumps that thread's stack.
_TAKE_BACK_REPORT_S = 5.0

# How long a revocation waits for the statement a late request is running on
# the test connection to return; past it the run halts instead.
_REVOKE_STATEMENT_WAIT_S = 30.0


def _request_time_ceiling() -> float | None:
    limit = config["limit_time_real"]
    return float(limit) if limit and limit > 0 else None


def _take_back_test_lock() -> None:
    # The lock was lent to this test's requests. A request that outlives its
    # client still holds it through its TestCursor and still runs statements
    # on the test's connection, so the test waits for that thread to return
    # it -- however long it takes, up to the time a server allows a request
    # (limit_time_real). Past that a server would cancel the request and roll
    # its transaction back; the test does the same to the request's cursors,
    # between two of its statements, and fails, and the run goes on.
    ceiling = _request_time_ceiling()
    started = clock.monotonic()
    reported_ident: int | None = None
    revoked: list[str] = []
    with _debug.perf("test.lock.reacquire", test=current_test_tag()) as span:
        while True:
            ident = _registry_test_lock.owner_ident
            holder = TestCursor.holder_of(ident)
            if (
                ident is not None
                and cannot_release(holder)
                and _recover_stranded_acquisitions(ident)
            ):
                continue
            waited = clock.monotonic() - started
            if (
                holder is not None
                and reported_ident != ident
                and waited >= _TAKE_BACK_REPORT_S
            ):
                reported_ident = ident
                _report_lock_holder(holder, waited)
            if ceiling is not None and waited >= ceiling and ident is not None:
                holder_name = holder.name if holder else "another thread"
                reason = (
                    f"{holder_name} still held the registry test lock "
                    f"{ceiling:.0f}s (limit_time_real) after {current_test_tag()} "
                    f"took it back"
                )
                if _revoke_late_request(ident, reason):
                    revoked.append(reason)
                    continue
                span.set(acquired=False, waited_s=waited)
                reason = (
                    f"the registry test lock did not come back to "
                    f"{current_test_tag()}: {reason}, and a statement it ran "
                    f"on the test connection did not return within "
                    f"{_REVOKE_STATEMENT_WAIT_S:.0f}s, so every later test "
                    f"would share that connection with it"
                )
                _halt_run(reason)
                raise RegistryTestLockLost(reason)
            wait_s = _TAKE_BACK_REPORT_S
            if ceiling is not None and waited < ceiling:
                wait_s = min(wait_s, ceiling - waited)
            if _registry_test_lock.acquire(timeout=wait_s):
                waited = clock.monotonic() - started
                span.set(acquired=True, waited_s=waited, revoked=len(revoked))
                if revoked:
                    raise RegistryTestLockRevoked(
                        f"{revoked[0]}: its cursors were revoked and its work "
                        f"rolled back, as a server past limit_time_real would"
                    )
                if reported_ident is not None:
                    _logger.warning(
                        "The registry test lock came back to %s after %.1fs",
                        current_test_tag(),
                        waited,
                    )
                return


def _revoke_late_request(ident: int, reason: str) -> bool:
    revoked = TestCursor.revoke_held_by(
        ident, _registry_test_lock, reason, _REVOKE_STATEMENT_WAIT_S
    )
    _debug.logic(
        "test.lock.late_request_revoked",
        test=current_test_tag(),
        cursors=revoked,
    )
    if revoked is None:
        return False
    _logger.error(
        "%s: revoked its %d cursor(s) and rolled back what it wrote; its next "
        "statement fails",
        reason,
        revoked,
    )
    return True


def _recover_stranded_acquisitions(ident: int) -> bool:
    released = TestCursor.release_stranded_by(ident, current_test_tag())
    if _registry_test_lock.owner_ident == ident:
        # acquisitions with no cursor left to return them: adopt them all, and
        # let the hand-back take its own one
        _release_foreign_acquisition(_registry_test_lock)
        while _registry_test_lock.held_by_this_thread:
            _registry_test_lock.release()
    recovered = _registry_test_lock.owner_ident != ident
    _debug.logic(
        "test.lock.stranded_recovered",
        test=current_test_tag(),
        cursors=released,
        recovered=recovered,
    )
    return recovered


def _report_lock_holder(holder: threading.Thread, waited: float) -> None:
    _debug.logic(
        "test.lock.held_by_request",
        test=current_test_tag(),
        holder=holder.name,
        waited_s=waited,
    )
    _logger.warning(
        "%s is waiting for the registry test lock, still held after %.1fs by "
        "%s %s -- a request that outlived its client. Its stack:",
        current_test_tag(),
        waited,
        holder.name,
        describe_thread_work(holder) or "",
    )
    if holder.ident is not None:
        dumpstacks(thread_idents={holder.ident}, log_level=logging.WARNING)


def _halt_run(reason: str) -> None:
    outcome = getattr(odoo.modules.module.current_test, "_outcome", None)
    result = getattr(outcome, "result", None)
    if result is not None:
        result.halt(reason)
    _logger.error("Halting the test run: %s", reason)


def _has_child_processes() -> bool:
    try:
        return any(
            (task / "children").read_text().strip()
            for task in pathlib.Path("/proc/self/task").iterdir()
        )
    except OSError:
        return True


def gc_test_filestore() -> None:
    try:
        with (
            Registry(get_db_name()).cursor() as cr,
            _debug.perf("test.filestore.gc", cr=cr, db=cr.dbname),
        ):
            gc_env = api.Environment(cr, api.SUPERUSER_ID, {})
            gc_env["ir.attachment"]._gc_file_store_unsafe()
    except Exception:
        _logger.warning("Could not sweep the filestore after the suite", exc_info=True)


def release_stranded_test_cursors(owner: str = "") -> int:
    return TestCursor.release_stranded(owner)


def _patch_target_name(obj: Any) -> str:
    if isinstance(obj, type):
        return f"{obj.__module__}.{obj.__qualname__}"
    name = getattr(obj, "__name__", None)
    if isinstance(name, str):
        return name
    return type(obj).__qualname__


def _patcher_name(patcher: Any) -> str:
    target = getattr(patcher, "target", None)
    attribute = getattr(patcher, "attribute", None)
    if target is not None and attribute:
        return f"{_patch_target_name(target)}.{attribute}"
    return type(patcher).__qualname__


def _enter_context(cm: Any, addcleanup: Callable) -> Any:
    cls = type(cm)
    try:
        enter = cls.__enter__
        exit = cls.__exit__
    except AttributeError:
        raise TypeError(
            f"'{cls.__module__}.{cls.__qualname__}' object does not support the context manager protocol"
        ) from None
    result = enter(cm)
    addcleanup(exit, cm, None, None, None)
    return result


def _query_text(query: Any) -> str:
    if isinstance(query, SQL):
        return query.code
    if isinstance(query, str):
        return query
    if isinstance(query, bytes):
        return query.decode()
    return str(query)


def _copy_from_text(table, columns, *args, **kwargs) -> str:
    columns_sql = ", ".join(f'"{column}"' for column in columns)
    return f'COPY "{table}" ({columns_sql}) FROM STDIN'


_STATEMENT_RECORDERS = {
    "execute": lambda query, *args, **kwargs: _query_text(query),
    "executemany": lambda query, *args, **kwargs: _query_text(query),
    "copy": lambda statement, *args, **kwargs: _query_text(statement),
    "copy_from": _copy_from_text,
}


_DELEGATING_STATEMENTS = {"execute_values"}


class BlockedRequest(requests.exceptions.ConnectionError):
    pass


_super_send = requests.Session.send
_super_getaddrinfo = socket.getaddrinfo


# names public DNS never answers: RFC 6761's .invalid and .test, and the
# private-use .internal (ICANN, 2024) and .home.arpa (RFC 8375), which only a
# private resolver answers, never with a public address; every other external
# name gets a public address, so the egress guard lets it through to the
# request block (BlockedRequest) as it would with a working resolver, without
# a DNS lookup
_UNRESOLVABLE_SUFFIXES = (".invalid", ".test", ".internal", ".home.arpa")
_EXTERNAL_TEST_ADDRESS = "93.184.216.34"


@functools.cache
def _hosts_file_names(path: str = "/etc/hosts") -> frozenset[str]:
    try:
        lines = pathlib.Path(path).read_text(encoding="utf-8").splitlines()
    except OSError:
        return frozenset()
    return frozenset(
        name.lower() for line in lines for name in line.split("#", 1)[0].split()[1:]
    )


def _resolves_for_real(name: str) -> bool:
    if name in (HOST, "localhost") or name.endswith(".localhost"):
        return True
    # the hosts file answers without a network, so it answers as in production
    # (ip6-localhost is ::1 there, and the egress guard must see that)
    if name.lower() in _hosts_file_names():
        return True
    try:
        ipaddress.ip_address(name)
    except ValueError:
        return False
    return True


def _offline_getaddrinfo(host, port=None, *args, **kwargs):
    name = (host.decode() if isinstance(host, bytes) else str(host or "")).strip("[]")
    if not name or _resolves_for_real(name):
        return _super_getaddrinfo(host, port, *args, **kwargs)
    if name.rstrip(".").endswith(_UNRESOLVABLE_SUFFIXES):
        raise socket.gaierror(socket.EAI_NONAME, f"{name} does not exist")
    _debug.logic("test.dns.answered", host=name)
    return _super_getaddrinfo(_EXTERNAL_TEST_ADDRESS, port, *args, **kwargs)


def _raise_test_timeout(timeout):
    """At least ten seconds for each part of a `requests` timeout.

    `requests` takes a number or a (connect, read) pair, where either part may
    be None for no limit.
    """
    if isinstance(timeout, tuple):
        return tuple(_raise_test_timeout(part) for part in timeout)
    if timeout and timeout < 10:
        return 10
    return timeout


def _normalise_expected(
    records: odoo.models.BaseModel,
    expected_values: list[dict],
    field_names: Iterable[str],
) -> list[dict]:
    rows = []
    for vs in expected_values:
        row: dict[str, Any] = {}
        for name in field_names:
            field_type = records._fields[name].type
            if vs[name] is None:
                row[name] = False
            elif field_type in ("one2many", "many2many"):
                row[name] = sorted(vs[name]) if vs[name] else []
            elif field_type == "float":
                row[name] = float(vs[name])
            elif field_type == "integer":
                row[name] = int(vs[name])
            else:
                row[name] = vs[name]
        rows.append(row)
    return rows


def _normalise_records(
    records: odoo.models.BaseModel, field_names: Iterable[str]
) -> list[dict]:
    rows = []
    for record in records:
        row: dict[str, Any] = {}
        for field_name in field_names:
            record_value = record[field_name]
            match record._fields[field_name]:
                case odoo.fields.Many2one():
                    record_value = record_value.id
                case odoo.fields.One2many() | odoo.fields.Many2many():
                    record_value = sorted(record_value.ids)
                case odoo.fields.Float() as field if isinstance(
                    digits := field.get_digits(record.env), tuple
                ):
                    record_value = Approx(record_value, digits[1], decorate=False)
                case odoo.fields.Monetary() as field if (
                    currency_field_name := field.get_currency_field(record)
                ):
                    if c := record[currency_field_name]:
                        record_value = Approx(record_value, c, decorate=False)

            row[field_name] = record_value
        rows.append(row)
    return rows


class BaseCase(TestCase):
    registry: Registry = None  # type: ignore[assignment]
    env: api.Environment = None  # type: ignore[assignment]
    cr: Cursor = None  # type: ignore[assignment]
    registry_patches: ClassVar[list]

    test_tags: set[str] | None = None
    freeze_time: ClassVar[Any] = None
    _starts_freeze_time_itself = False

    test_module: str = ""

    def __init_subclass__(cls) -> None:
        super().__init_subclass__()
        if cls.__module__.startswith("odoo.addons."):
            defaulted = cls.test_tags is None
            if defaulted:
                cls.test_tags = {"standard", "at_install"}
            cls.test_module = cls.__module__.split(".")[2]
            if _debug.lifecycle.enabled:
                _debug.lifecycle(
                    "test.case.subclass",
                    cls=cls.__qualname__,
                    module=cls.test_module,
                    tags=sorted(cls.test_tags or ()),
                    defaulted=defaulted,
                )

    longMessage = True
    warm = True

    _tests_run_count = env_int("ODOO_TEST_FAILURE_RETRIES", 0) + 1

    registry_test_mode: ClassVar[bool] = True
    _registry_patched = False
    _registry_readonly_enabled = True
    test_cursor_lock_timeout: int = 20

    def __init__(self, methodName: str = "runTest") -> None:
        super().__init__(methodName)
        self.addTypeEqualityFunc(etree._Element, self.assertTreesEqual)
        self.addTypeEqualityFunc(html.HtmlElement, self.assertTreesEqual)
        if methodName != "runTest":
            test_method = getattr(self, methodName)
            additional = self.get_method_additional_tags(test_method)
            test_tags = (self.test_tags or set()) | set(additional)
            test_tags |= getattr(test_method, "test_tags", set())
            test_tags -= getattr(test_method, "test_tags_exclude", set())
            if _debug.logic.enabled and test_tags != (type(self).test_tags or set()):
                _debug.logic(
                    "test.case.method_tags",
                    test=self.canonical_tag,
                    source=additional,
                    added=sorted(getattr(test_method, "test_tags", ())),
                    removed=sorted(getattr(test_method, "test_tags_exclude", ())),
                    tags=sorted(test_tags),
                )
            self.test_tags = test_tags

    @classmethod
    def _request_handler(cls, s: Session, r: PreparedRequest, /, **kw):
        url = urlsplit(r.url)
        timeout = kw.get("timeout")
        if (raised := _raise_test_timeout(timeout)) != timeout:
            _debug.logic(
                "test.http.timeout_raised",
                host=url.hostname,
                given=timeout,
                raised=raised,
            )
            _logger.getChild("requests").info(
                "request %s with timeout %s increased to %s during tests",
                url,
                timeout,
                raised,
            )
            kw["timeout"] = raised
        if url.hostname in (HOST, "localhost"):
            _debug.logic("test.http.send", decision="local", method=r.method, url=r.url)
            return _super_send(s, r, **kw)
        if url.scheme == "file":
            _debug.logic("test.http.send", decision="file", method=r.method, url=r.url)
            return _super_send(s, r, **kw)

        _debug.logic("test.http.send", decision="blocked", method=r.method, url=r.url)
        _logger.getChild("requests").info(
            "Blocking un-mocked external HTTP request %s %s", r.method, r.url
        )
        raise BlockedRequest(f"External requests verboten (was {r.method} {r.url})")

    def run(self, result: OdooTestResult) -> None:  # type: ignore[override]  # a result is mandatory here
        testMethod = getattr(self, self._testMethodName)

        if getattr(testMethod, "_retry", True) and getattr(self, "_retry", True):
            tests_run_count = self._tests_run_count
        else:
            tests_run_count = 1
            _debug.lifecycle("test.case.retry_disabled", test=self.canonical_tag)
            _logger.info("Auto retry disabled for %s", self)

        for retry in range(tests_run_count):
            result.had_failure = False
            if retry:
                _logger.log(RUNBOT, "Retrying a failed test: %s", self)
            final = retry == tests_run_count - 1
            _debug.pipeline(
                "test.case.attempt",
                test=self.canonical_tag,
                attempt=retry + 1,
                of=tests_run_count,
                final=final,
            )
            with ExitStack() as attempt:
                if retry:
                    attempt.enter_context(result.retry())

                if final:
                    super().run(cast("TestResult", result))
                    if not result.wasSuccessful() and type(self)._tests_run_count != 1:
                        _debug.lifecycle(
                            "test.case.retries_disabled_globally",
                            test=self.canonical_tag,
                            was=type(self)._tests_run_count,
                        )
                        _logger.log(RUNBOT, "Disabling auto-retry after a failed test")
                        type(self)._tests_run_count = 1
                    break

                attempt.enter_context(warnings.catch_warnings())
                attempt.enter_context(result.soft_fail())
                quiet_log = attempt.enter_context(lower_logging(25, logging.INFO))
                super().run(cast("TestResult", result))
                _debug.logic(
                    "test.case.soft_attempt",
                    test=self.canonical_tag,
                    attempt=retry + 1,
                    had_failure=result.had_failure,
                    had_error_log=quiet_log.had_error_log,
                )
                if not (result.had_failure or quiet_log.had_error_log):
                    break

    @classmethod
    def setUpClass(cls) -> None:
        def check_remaining_processes() -> None:
            if not _has_child_processes():
                return
            current_process = psutil.Process()
            children = current_process.children(recursive=True)
            _debug.logic(
                "test.case.child_processes", cls=cls.__qualname__, count=len(children)
            )
            for child in children:
                _logger.warning("A child process was found, terminating it: %s", child)
                child.terminate()
            _, alive = psutil.wait_procs(children, timeout=10)
            if alive:
                _logger.warning(
                    "Killing %d child process(es) that survived terminate(): %s",
                    len(alive),
                    ", ".join(str(p) for p in alive),
                )
                for child in alive:
                    child.kill()
                psutil.wait_procs(alive, timeout=5)

        cls.addClassCleanup(check_remaining_processes)

        def check_remaining_patchers():
            for patcher in list(_patch._active_patches):  # type: ignore[attr-defined]  # mock keeps the registry private
                if hasattr(patcher, "target"):
                    description = f"{patcher.target}.{patcher.attribute}"
                else:
                    description = f"dict {getattr(patcher, 'in_dict', patcher)!r}"
                _debug.logic(
                    "test.case.patcher_leaked",
                    cls=cls.__qualname__,
                    target=description,
                )
                _logger.warning(
                    "A patcher (targeting %s) was remaining active at the end of %s, disabling it...",
                    description,
                    cls.__name__,
                )
                patcher.stop()

        cls.addClassCleanup(check_remaining_patchers)

        def close_sass():
            try:
                from odoo.tools.sass_embedded import close_sass_compiler

                close_sass_compiler()
            except ImportError:
                pass

        cls.addClassCleanup(close_sass)

        def close_esm_lexer():
            try:
                from odoo.tools.assets.esm_lexer import close_lexer_worker

                close_lexer_worker()
            except ImportError:
                pass

        cls.addClassCleanup(close_esm_lexer)
        super().setUpClass()
        if cls.freeze_time and not cls._starts_freeze_time_itself:
            cls.startClassPatcher(cls.freeze_time)
        class_tags = cls.test_tags or set()
        requests_patched = "standard" in class_tags or "click_all" in class_tags
        if requests_patched:
            patcher = patch.object(
                requests.sessions.Session,
                "send",
                lambda s, r, **kw: cls._request_handler(s, r, **kw),  # noqa: PLW0108  classmethod would bind and shift (s, r)
            )
            patcher.start()
            cls.addClassCleanup(patcher.stop)
            # the egress guard resolves a name before `requests` sends: without
            # this, an external name waits on a DNS lookup the test may not need
            dns_patcher = patch.object(socket, "getaddrinfo", _offline_getaddrinfo)
            dns_patcher.start()
            cls.addClassCleanup(dns_patcher.stop)
        _debug.lifecycle(
            "test.case.setup_class",
            cls=cls.__qualname__,
            freeze_time=cls.freeze_time is not None,
            requests_patched=requests_patched,
            retries=cls._tests_run_count - 1,
        )

    def setUp(self) -> None:
        super().setUp()
        self.http_request_key: str = ""
        self.http_request_allow_all: bool = False
        self._test_thread = threading.current_thread()
        self.addCleanup(
            setattr,
            type(self),
            "_registry_readonly_enabled",
            self._registry_readonly_enabled,
        )
        _debug.lifecycle(
            "test.case.setup",
            test=self.canonical_tag,
            thread=self._test_thread.name,
            readonly_enabled=self._registry_readonly_enabled,
        )

    def cursor(self) -> Cursor:
        _debug.lifecycle("test.case.extra_cursor", test=self.canonical_tag)
        return cast("Cursor", self.registry.cursor())

    @classmethod
    def _open_class_cursor(cls) -> None:
        cls.cr = cast("Cursor", cls.registry.cursor())
        cls.addClassCleanup(cls.cr.close)
        # the class holds one transaction for all its tests, which may wait on
        # a browser or compute for minutes: the server's idle timeout is not
        # for them (transaction-local, gone with the class's rollback)
        cls.cr.execute(
            "SELECT set_config('idle_in_transaction_session_timeout', '0', true)"
        )
        _debug.lifecycle(
            "test.case.class_cursor", cls=cls.__qualname__, db=cls.cr.dbname
        )
        with _debug.perf("test.case.planner_stats", cr=cls.cr, cls=cls.__qualname__):
            update_planner_stats(cls.cr)

    @property
    def uid(self):
        return self.env.uid

    @uid.setter
    def uid(self, user):
        _debug.lifecycle(
            "test.env.uid",
            test=self.canonical_tag,
            uid=getattr(user, "id", user),
            was=self.env.uid,
        )
        self.env = self.env(user=user)
        self.env.transaction.default_env = self.env

    def ref(self, xid: str) -> int:
        return self.browse_ref(xid).id

    def browse_ref(self, xid: str) -> Any:
        assert "." in xid, (
            "this method requires a fully qualified parameter, in the following form: 'module.identifier'"
        )
        return self.env.ref(xid)

    def _distrust_test_caches(self, *groups: str) -> None:
        # for code that knows a value it caches now will not hold for the next
        # test, though no write of the test cleared its cache
        for scope in _cache_scope:
            scope.distrust(groups)

    def patch(self, obj: Any, key: str, val: Any) -> None:
        patcher = patch.object(obj, key, val)
        patcher.start()
        self.addCleanup(patcher.stop)
        _debug.lifecycle(
            "test.case.patch",
            scope="test",
            target=_patch_target_name(obj),
            key=key,
        )

    @classmethod
    def classPatch(cls, obj: Any, key: str, val: Any) -> None:
        patcher = patch.object(obj, key, val)
        patcher.start()
        cls.addClassCleanup(patcher.stop)
        _debug.lifecycle(
            "test.case.patch",
            scope="class",
            target=_patch_target_name(obj),
            key=key,
        )

    def startPatcher(self, patcher: Any) -> Any:
        mock = patcher.start()
        self.addCleanup(patcher.stop)
        _debug.lifecycle(
            "test.case.patcher", scope="test", patcher=_patcher_name(patcher)
        )
        return mock

    @classmethod
    def startClassPatcher(cls, patcher: Any) -> Any:
        mock = patcher.start()
        cls.addClassCleanup(patcher.stop)
        _debug.lifecycle(
            "test.case.patcher", scope="class", patcher=_patcher_name(patcher)
        )
        return mock

    def enterContext(self, cm: Any) -> Any:
        return _enter_context(cm, self.addCleanup)

    @classmethod
    def enterClassContext(cls, cm: Any) -> Any:
        return _enter_context(cm, cls.addClassCleanup)

    @contextmanager
    def with_user(self, login: str) -> Generator[None]:
        old_uid = self.uid
        old_env = self.env
        try:
            user = self.env["res.users"].sudo().search([("login", "=", login)])
            assert user, f"Login {login} not found"
            self.uid = user.id
            _debug.lifecycle(
                "test.env.with_user", test=self.canonical_tag, login=login, uid=user.id
            )
            yield
        finally:
            self.uid = old_uid
            self.env = old_env

    @contextmanager
    def debug_mode(self) -> Generator[None]:
        request = Mock(
            httprequest=Mock(host="localhost"),
            db=self.env.cr.dbname,
            env=self.env,
            session=DotDict(odoo.http.prepare_default_session(), debug="1"),
        )
        try:
            self.env.flush_all()
            self.env.invalidate_all()
            odoo.http._request_stack.push(request)
            _debug.lifecycle("test.env.debug_mode", test=self.canonical_tag)
            yield
            self.env.flush_all()
            self.env.invalidate_all()
        finally:
            popped_request = odoo.http._request_stack.pop()
            if popped_request is not request:
                _debug.logic(
                    "test.env.request_stack_mismatch",
                    test=self.canonical_tag,
                    failing=sys.exc_info()[0] is not None,
                )
            if popped_request is not request and sys.exc_info()[0] is None:
                raise Exception("Wrong request stack cleanup.")

    @contextmanager
    def _assertRaises(
        self,
        exception: type[BaseException] | tuple[type[BaseException], ...],
        *,
        msg: str | None = None,
    ) -> Generator[Any]:
        with ExitStack() as init:
            if self.env:
                init.enter_context(self.env.cr.savepoint())
                if isinstance(exception, tuple):
                    clear_cache = any(issubclass(exc, AccessError) for exc in exception)
                else:
                    clear_cache = issubclass(exception, AccessError)
                _debug.logic(
                    "test.assert.raises",
                    test=self.canonical_tag,
                    exception=getattr(exception, "__name__", None),
                    clear_cache=clear_cache,
                )
                if clear_cache:
                    self.env.cr.clear()

            with ExitStack() as inner:
                cm = inner.enter_context(super().assertRaises(exception, msg=msg))
                inner.push(init.pop_all())

                yield cm

    def assertRaises(  # type: ignore[override]  # narrowed to one exception type
        self,
        exception: type[BaseException],
        func: Callable | None = None,
        *args: Any,
        **kwargs: Any,
    ) -> Any:
        if func:
            with self._assertRaises(exception):
                func(*args, **kwargs)
        else:
            return self._assertRaises(exception, **kwargs)
        return None

    def _patchExecute(self, actual_queries, flush=True):

        def recorded(name, describe):
            original = getattr(Cursor, name)

            def wrapper(cr, *args, **kwargs):
                actual_queries.append(describe(*args, **kwargs))
                return original(cr, *args, **kwargs)

            return patch.object(Cursor, name, wrapper)

        if flush:
            self.env.flush_all()
            self.env.cr.flush()

        _debug.pipeline(
            "test.assert.queries_recording", test=self.canonical_tag, flush=flush
        )
        with ExitStack() as patches:
            patches.enter_context(observing_statements())
            for name, describe in _STATEMENT_RECORDERS.items():
                patches.enter_context(recorded(name, describe))
            patches.enter_context(
                patch.object(self.env.registry, "unaccent", lambda x: x)
            )
            yield actual_queries
            if flush:
                self.env.flush_all()
                self.env.cr.flush()
        _debug.perf.count(
            "test.assert.queries_recorded",
            test=self.canonical_tag,
            count=len(actual_queries),
        )

    @staticmethod
    def _normalize_query(query: str) -> str:
        normalized = "".join(query.lower().split())
        normalized = re.sub(
            r"\((?:%s|default)(?:,(?:%s|default))*\)", "(%s)", normalized
        )
        normalized = normalized.replace("=any(%s)", "in(%s)")
        return normalized.replace("!=all(%s)", "notin(%s)")

    def _assert_queries(
        self,
        expected: list[str],
        actual_queries: list[str],
        compare: Callable[[str, str], None],
    ) -> None:
        if not self.warm:
            _debug.logic("test.assert.queries_cold_skipped", test=self.canonical_tag)
            return

        _debug.logic(
            "test.assert.queries_compare",
            test=self.canonical_tag,
            expected=len(expected),
            actual=len(actual_queries),
            compare=compare.__name__,
        )
        self.assertEqual(
            len(actual_queries),
            len(expected),
            "\n---- actual queries:\n%s\n---- expected queries:\n%s"
            % (
                "\n".join(actual_queries),
                "\n".join(expected),
            ),
        )
        for actual_query, expect_query in zip(actual_queries, expected, strict=False):
            compare(actual_query, expect_query)

    @contextmanager
    def assertQueries(
        self, expected: list[str], flush: bool = True
    ) -> Generator[list[str]]:
        actual_queries: list[str] = []

        yield from self._patchExecute(actual_queries, flush)

        def equals(actual_query: str, expect_query: str) -> None:
            self.assertEqual(
                self._normalize_query(actual_query),
                self._normalize_query(expect_query),
                "\n---- actual query:\n%s\n---- not like:\n%s"
                % (actual_query, expect_query),
            )

        self._assert_queries(expected, actual_queries, equals)

    @contextmanager
    def assertQueriesContain(
        self, expected: list[str], flush: bool = True
    ) -> Generator[list[str]]:
        actual_queries: list[str] = []

        yield from self._patchExecute(actual_queries, flush)

        def contains(actual_query: str, expect_query: str) -> None:
            self.assertIn(
                self._normalize_query(expect_query),
                self._normalize_query(actual_query),
                "\n---- actual query:\n%s\n---- doesn't contain:\n%s"
                % (actual_query, expect_query),
            )

        self._assert_queries(expected, actual_queries, contains)

    @contextmanager
    def capturedQueries(self, flush: bool = True) -> Generator[list[str]]:
        yield from self._patchExecute([], flush)

    def _counts_no_statements(self) -> bool:
        # a backend that issues no SQL has no statement budget to grade: the
        # body of the assertion still runs, so a class hosted on the DB-free
        # tier gets everything the test says about behaviour and leaves the
        # budget to the database-backed run of the same test
        return not hasattr(self.cr, "sql_statement_count")

    @contextmanager
    def assertQueryCount(
        self, default: int = 0, flush: bool = True, **counters: int
    ) -> Generator[None]:
        if self.warm and not self._counts_no_statements():
            with patch("random.random", lambda: 1), observing_statements():
                login = self.env.user.login  # type: ignore[attr-defined]  # res.users is an addon model
                expected = counters.get(login, default)
                if flush:
                    self.env.flush_all()
                    self.env.cr.flush()
                count0 = self.cr.sql_statement_count
                yield
                if flush:
                    self.env.flush_all()
                    self.env.cr.flush()
                count = self.cr.sql_statement_count - count0
                _debug.logic(
                    "test.assert.query_count",
                    test=self.canonical_tag,
                    login=login,
                    expected=expected,
                    count=count,
                    flush=flush,
                )
                if count != expected:
                    caller = inspect.stack(0)[2]
                    filename, linenum, funcname = (
                        caller.filename,
                        caller.lineno,
                        caller.function,
                    )
                    filename = filename.replace("\\", "/")
                    if "/odoo/addons/" in filename:
                        filename = filename.rsplit("/odoo/addons/", 1)[1]
                    if count > expected:
                        with self.subTest():
                            self.fail(
                                "Query count more than expected for user %s: %d > %d in %s at %s:%s"
                                % (
                                    login,
                                    count,
                                    expected,
                                    funcname,
                                    filename,
                                    linenum,
                                )
                            )
                    else:
                        logger = logging.getLogger(type(self).__module__)
                        msg = "Query count less than expected for user %s: %d < %d in %s at %s:%s"
                        logger.info(
                            msg,
                            login,
                            count,
                            expected,
                            funcname,
                            filename,
                            linenum,
                        )
        else:
            _debug.logic(
                "test.assert.query_count_cold",
                test=self.canonical_tag,
                graded=not self._counts_no_statements(),
            )
            if flush:
                self.env.flush_all()
                self.env.cr.flush()
            yield
            if flush:
                self.env.flush_all()
                self.env.cr.flush()

    def assertQueriesConstant(
        self, run: Callable[[int], object], small: int = 2, large: int = 10
    ) -> None:
        # the query count of run(n) does not depend on n: an N+1 fails here
        # whatever the pinned number, and a constant-cost change passes here
        # whatever the pinned number. Each run gets a savepoint and a cold
        # record cache; the first run is a warm-up that pays the one-off
        # costs (rules, users, ormcaches) neither measured run then meets
        if self._counts_no_statements():
            # same rule as assertQueryCount: run the work, grade the shape
            # where the statements are
            _debug.logic(
                "test.assert.queries_constant_ungraded", test=self.canonical_tag
            )
            run(small)
            return
        counts = {}
        for index, size in enumerate((small, small, large)):
            with (
                contextlib.closing(self.cr.savepoint(flush=True)),
                patch("random.random", lambda: 1),
                observing_statements(),
            ):
                self.env.flush_all()
                self.env.invalidate_all()
                count0 = self.cr.sql_statement_count
                run(size)
                self.env.flush_all()
                self.env.cr.flush()
                if index:
                    counts[size] = self.cr.sql_statement_count - count0
        _debug.logic(
            "test.assert.queries_constant",
            test=self.canonical_tag,
            small=small,
            large=large,
            counts=counts,
        )
        self.assertEqual(
            counts[small],
            counts[large],
            f"the query count grows with the batch: {counts[small]} at {small} "
            f"records, {counts[large]} at {large}",
        )

    def assertRecordValues(
        self,
        records: odoo.models.BaseModel,
        expected_values: list[dict],
        *,
        field_names: Iterable[str] | None = None,
    ) -> None:
        if not field_names:
            if not expected_values:
                self.assertFalse(
                    records,
                    f"expected no record, got {len(records)}: {records}",
                )
                return
            field_names = expected_values[0].keys()
            for i, v in enumerate(expected_values):
                self.assertEqual(
                    v.keys(),
                    field_names,
                    f"All expected values must have the same keys, found differences between records 0 and {i}",
                )

        expected_reformatted = _normalise_expected(
            records, expected_values, field_names
        )
        with _debug.perf(
            "test.assert.record_values",
            cr=records.env.cr,
            model=records._name,
            records=len(records),
            expected=len(expected_values),
            fields=len(list(field_names)),
        ):
            record_reformatted = _normalise_records(records, field_names)

        try:
            self.assertSequenceEqual(
                expected_reformatted, record_reformatted, seq_type=list
            )
            return
        except AssertionError as e:
            _debug.logic("test.assert.record_values_mismatch", model=records._name)
            standardMsg, _, diffMsg = str(e).rpartition("\n")
            if "self.maxDiff" not in diffMsg:
                raise

        diffMsg = "".join(
            difflib.unified_diff(
                pprint.pformat(expected_reformatted).splitlines(keepends=True),
                pprint.pformat(record_reformatted).splitlines(keepends=True),
                fromfile="expected",
                tofile="records",
            )
        )
        self.fail(self._formatMessage(None, standardMsg + "\n" + diffMsg))

    def assertItemsEqual(self, a: Any, b: Any, msg: str | None = None) -> None:
        self.assertCountEqual(a, b, msg=msg)

    _DEPENDS_PROBE_VALUES: ClassVar[dict[str, list[Any]]] = {
        "char": ["zzz-probe"],
        "text": ["zzz-probe"],
        "html": ["<p>zzz-probe</p>"],
        "boolean": [True, False],
        "integer": [7],
        "float": [3.5],
        "monetary": [3.5],
        "date": [date(2021, 3, 4)],
        "datetime": [datetime(2021, 3, 4, 5, 6, 7)],
    }

    _DEPENDS_PROBE_EXTRA_TYPES = frozenset({"selection", "many2one"})
    _DEPENDS_PROBE_DYNAMIC = frozenset({"selection"})

    def assertDependsComplete(
        self,
        records: odoo.models.BaseModel,
        *,
        probe_fields: Iterable[str] | None = None,
        computed_fields: Iterable[str] | None = None,
        known_incomplete: Iterable[str] | None = None,
        msg: str | None = None,
    ) -> None:
        self.assertTrue(records, msg or "assertDependsComplete needs records")
        model = records.browse(records.ids)
        exempt = set(known_incomplete or ())
        if unknown := exempt - set(
            self._depends_computed_names(model, computed_fields)
        ):
            self.fail(
                f"known_incomplete names {sorted(unknown)}, which are not "
                f"computed fields of {model._name}"
            )
        stale = self.findStaleComputedFields(
            records, probe_fields=probe_fields, computed_fields=computed_fields
        )
        _debug.logic(
            "test.assert.depends_complete",
            model=model._name,
            stale=len(stale),
            exempt=sorted(exempt),
        )
        if unproven := exempt - {entry[1] for entry in stale}:
            self.fail(
                f"known_incomplete names {sorted(unproven)} on {model._name}, "
                f"but nothing made them stale. Either the dependency is now "
                f"expressible and should be declared, or drop them from the list."
            )
        if reportable := [entry for entry in stale if entry[1] not in exempt]:
            self.fail(msg or self._depends_failure_message(model, reportable))

    @staticmethod
    def _depends_computed_names(
        model: odoo.models.BaseModel, computed_fields: Iterable[str] | None
    ) -> list[str]:
        if computed_fields is not None:
            return list(computed_fields)
        return [
            name
            for name, f in model._fields.items()
            if f.compute and not f.related and name != "id"
        ]

    def _depends_probe_names(
        self, model: odoo.models.BaseModel, probe_fields: Iterable[str] | None
    ) -> list[str]:
        if probe_fields is not None:
            return list(probe_fields)
        fields = model._fields
        probes = [
            name
            for name, f in fields.items()
            if f.store
            and not (f.readonly or f.compute or f.related)
            and (
                f.type in self._DEPENDS_PROBE_VALUES
                or f.type in self._DEPENDS_PROBE_EXTRA_TYPES
            )
        ]
        probes.sort(key=lambda name: fields[name].type == "many2one")
        return probes

    def findStaleComputedFields(
        self,
        records: odoo.models.BaseModel,
        *,
        probe_fields: Iterable[str] | None = None,
        computed_fields: Iterable[str] | None = None,
    ) -> list[tuple[str, str, Any, Any, Any]]:
        model = records.browse(records.ids)
        fields = model._fields
        computed = self._depends_computed_names(model, computed_fields)
        probes = self._depends_probe_names(model, probe_fields)  # debuglog
        with _debug.perf(
            "test.assert.depends_probe_sweep",
            cr=model.env.cr,
            model=model._name,
            records=len(model),
            probes=len(probes),
            computed=len(computed),
        ) as span:
            stale = [
                entry
                for name in probes
                for value in self._depends_probe_values(model, fields[name])
                for target in model
                for entry in self._depends_probe(model, computed, name, value, target)
            ]
            span.set(stale=len(stale))
        return stale

    def _depends_probe_values(
        self, records: odoo.models.BaseModel, field: Any
    ) -> list[Any]:
        if field.type == "many2one":
            return self._depends_probe_comodel_ids(records, field)
        if field.type in self._DEPENDS_PROBE_DYNAMIC:
            with contextlib.suppress(Exception):
                return list(field.get_values(records.env))[:2]
            return []
        return self._DEPENDS_PROBE_VALUES.get(field.type, [])

    @staticmethod
    def _depends_probe_comodel_ids(
        records: odoo.models.BaseModel, field: Any
    ) -> list[Any]:
        try:
            comodel = records.env[field.comodel_name].sudo()
            held = {record[field.name].id for record in records} - {False}
            candidate = comodel.with_context(active_test=False).search(
                [("id", "not in", list(held))], limit=1
            )
        except Exception as exc:
            _debug.logic(
                "test.assert.depends_comodel_failed",
                field=field.name,
                comodel=field.comodel_name,
                error=type(exc).__name__,
            )
            return []
        return candidate.ids

    def _depends_probe(
        self,
        records: odoo.models.BaseModel,
        computed: list[str],
        probe_name: str,
        value: Any,
        target: odoo.models.BaseModel,
    ) -> list[tuple[str, str, Any, Any, Any]]:
        env = records.env
        savepoint = env.cr.savepoint(flush=False)
        skipped = None  # debuglog
        try:
            env.flush_all()
            env.invalidate_all()
            current = target[probe_name]
            if isinstance(current, odoo.models.BaseModel):
                if current.id == value:
                    skipped = "same_value"  # debuglog
                    return []
            elif current == value:
                skipped = "same_value"  # debuglog
                return []
            if self._depends_forced_recompute(records, computed) is None:
                skipped = "recompute_failed"  # debuglog
                return []
            env.invalidate_all()
            before = self._depends_read(records, computed)
            target.write({probe_name: value})
            cached = self._depends_read(records, computed)
            env.flush_all()
            env.invalidate_all()
            fresh = self._depends_read(records.browse(records.ids), computed)
            if before is None or cached is None or fresh is None:
                skipped = "read_failed"  # debuglog
                return []
            recomputed = self._depends_forced_recompute(records, computed)
            if recomputed is None:
                skipped = "recompute_failed"  # debuglog
                return []
            fresh = {**fresh, **recomputed}
        except Exception as exc:
            skipped = type(exc).__name__  # debuglog
            return []
        finally:
            savepoint.rollback()
            savepoint.close(rollback=False)
            env.clear()
            if _debug.logic.enabled and skipped:
                _debug.logic(
                    "test.assert.depends_probe_skipped",
                    model=records._name,
                    probe=probe_name,
                    target=target.id,
                    reason=skipped,
                )
        stale = []
        for key in before:
            if key not in cached or key not in fresh:
                continue
            if cached[key] != fresh[key]:
                _debug.logic(
                    "test.assert.depends_stale",
                    model=records._name,
                    probe=probe_name,
                    field=key[1],
                    record=key[0],
                )
                stale.append((probe_name, key[1], value, cached[key], fresh[key]))
        return stale

    def _depends_forced_recompute(
        self, records: odoo.models.BaseModel, field_names: list[str]
    ) -> dict[tuple[Any, str], Any] | None:
        stored = [
            name
            for name in field_names
            if (field := records._fields.get(name)) is not None
            and field.store
            and field.compute
            and field.readonly
        ]
        if not stored:
            return {}
        env = records.env
        try:
            for name in stored:
                env.add_to_compute(records._fields[name], records)
            env.flush_all()
            env.invalidate_all()
            return self._depends_read(records.browse(records.ids), stored)
        except Exception:
            return None

    @staticmethod
    def _depends_read(
        records: odoo.models.BaseModel, field_names: list[str]
    ) -> dict[tuple[Any, str], Any] | None:
        values: dict[tuple[Any, str], Any] = {}
        for record in records:
            for name in field_names:
                try:
                    value = record[name]
                except Exception:
                    return None
                values[record.id, name] = (
                    tuple(value._ids)
                    if isinstance(value, odoo.models.BaseModel)
                    else value
                )
        return values

    @staticmethod
    def _depends_failure_message(
        records: odoo.models.BaseModel, stale: list[tuple[str, str, Any, Any, Any]]
    ) -> str:
        depends = records.env.registry.field_depends
        lines = [
            (
                f"{len(stale)} computed field(s) on {records._name} went stale "
                f"after a write to a field they do not depend on:"
            )
        ]
        seen: set[tuple[str, str]] = set()
        for probe_name, name, value, cached, fresh in stale:
            if (probe_name, name) in seen:
                continue
            seen.add((probe_name, name))
            declared = sorted(set(depends.get(records._fields[name], ())))
            lines.append(
                f"  {records._name}.{name} after writing {probe_name}={value!r}\n"
                f"      cached  {cached!r}\n"
                f"      fresh   {fresh!r}\n"
                f"      depends {declared}"
            )
        return "\n".join(lines)

    def assertSweep(self, candidates: Any, msg: str | None = None) -> list:
        found = list(candidates)
        _debug.logic("test.assert.sweep", test=self.canonical_tag, found=len(found))
        self.assertTrue(
            found,
            msg or "the sweep found nothing to check, so it proves nothing",
        )
        return found

    def assertTreesEqual(self, n1: Any, n2: Any, msg: str | None = None) -> None:
        self.assertIsNotNone(n1, msg)
        self.assertIsNotNone(n2, msg)
        self.assertEqual(n1.tag, n2.tag, msg)
        self.assertEqual(dict(n1.attrib), dict(n2.attrib), msg)
        self.assertEqual((n1.text or "").strip(), (n2.text or "").strip(), msg)
        self.assertEqual((n1.tail or "").strip(), (n2.tail or "").strip(), msg)

        for c1, c2 in zip_longest(n1, n2):
            self.assertTreesEqual(c1, c2, msg)

    def _assertXMLEqual(
        self, original: str, expected: str, parser: str = "xml"
    ) -> None:
        self.maxDiff = 10000
        _debug.perf.count(
            "test.assert.xml_equal",
            test=self.canonical_tag,
            parser=parser,
            original=len(original or ""),
            expected=len(expected or ""),
        )
        if original:
            original = _normalize_arch_for_assert(original, parser)
        if expected:
            expected = _normalize_arch_for_assert(expected, parser)
        self.assertEqual(original, expected)

    def assertXMLEqual(self, original: str, expected: str) -> None:
        return self._assertXMLEqual(original, expected)

    def assertHTMLEqual(self, original: str, expected: str) -> None:
        return self._assertXMLEqual(original, expected, "html")

    def profile(self, description: str = "", **kwargs: Any) -> Any:
        test_method = getattr(self, "_testMethodName", "Unknown test method")
        if not hasattr(self, "profile_session"):
            self.profile_session = profiler.get_session_name(test_method)
        if "db" not in kwargs:
            kwargs["db"] = self.env.cr.dbname
        _debug.lifecycle(
            "test.profile.start",
            test=self.canonical_tag,
            session=self.profile_session,
            warm=self.warm,
            options=sorted(kwargs),
        )
        return profiler.Profiler(
            description="%s uid:%s %s %s"
            % (
                test_method,
                self.env.user.id,
                "warm" if self.warm else "cold",
                description,
            ),
            profile_session=self.profile_session,
            **kwargs,
        )

    @classmethod
    def _registry_test_mode_patches(cls, *, cr: Cursor, registry: Registry):

        def _patched_cursor(
            readonly: bool = False, *, pin_key: object = None, primary: bool = False
        ):
            return TestCursor(
                cr,
                cast("Any", _registry_test_lock),
                readonly and cls._registry_readonly_enabled,
            )

        patches = [
            patch.object(registry, "cursor", _patched_cursor),
            patch.object(Registry, "_lock", DummyRLock()),
            patch.object(registry, "setup_signaling", return_value=None),
            patch.object(registry, "check_signaling", return_value=registry),
        ]

        try:
            from odoo.addons.bus import websocket as bus_websocket
        except ImportError:
            _debug.logic("test.registry.bus_patch", present=False)
        else:
            og_db_connect = bus_websocket.db_connect

            def _patched_ws_db_connect(to, allow_uri=False, readonly=False):
                if to == cr.dbname:
                    _debug.logic("test.registry.ws_db_connect", db=to, patched=True)

                    class _TestConnection:
                        def cursor(self):
                            return _patched_cursor(readonly)

                    return _TestConnection()
                _debug.logic("test.registry.ws_db_connect", db=to, patched=False)
                return og_db_connect(to, allow_uri=allow_uri, readonly=readonly)

            patches.append(
                patch.object(bus_websocket, "db_connect", _patched_ws_db_connect)
            )
            _debug.logic("test.registry.bus_patch", present=True)

        return patches

    @classmethod
    def _registry_enter_test_mode(cls, *, cr: Cursor) -> None:
        assert not cls._registry_patched, "Can only patch registry once"
        assert cr, "No cursor"
        assert cls.registry, "No registry"

        cls.registry_patches = cls._registry_test_mode_patches(
            cr=cr,
            registry=cls.registry,
        )
        for p in cls.registry_patches:
            p.start()
        cls._registry_patched = True
        _debug.lifecycle(
            "test.registry.test_mode_entered",
            cls=cls.__qualname__,
            patches=len(cls.registry_patches),
            readonly_enabled=cls._registry_readonly_enabled,
        )

    @classmethod
    def registry_enter_test_mode_cls(cls) -> None:
        cls._registry_enter_test_mode(cr=cls.cr)
        cls.addClassCleanup(cls.registry_leave_test_mode)

    def registry_enter_test_mode(self) -> None:
        type(self)._registry_enter_test_mode(cr=self.cr)
        self.addCleanup(self.registry_leave_test_mode)

    @classmethod
    def registry_leave_test_mode(cls) -> None:
        assert cls._registry_patched, "Registry is not patched"

        for p in cls.registry_patches:
            p.stop()
        cls.registry_patches.clear()
        cls._registry_patched = False
        _debug.lifecycle("test.registry.test_mode_left", cls=cls.__qualname__)

    @classmethod
    def set_registry_readonly_mode(cls, enabled: bool) -> None:
        assert cls._registry_patched, "Registry is not patched"

        _debug.lifecycle(
            "test.registry.readonly_mode",
            cls=cls.__qualname__,
            enabled=enabled,
            was=cls._registry_readonly_enabled,
        )
        cls._registry_readonly_enabled = enabled

    def assertCanOpenTestCursor(self) -> None:
        if odoo.modules.module.current_test is not self:
            _debug.logic(
                "test.cursor.foreign_test",
                test=self.canonical_tag,
                current=current_test_tag(),
            )
            message = f"Trying to open a test cursor for {self.canonical_tag} while already in a test {current_test_tag()}"
            _logger.log(RUNBOT, message)
            raise BadRequest(message)
        request = odoo.http.request
        if not request:
            _debug.logic("test.cursor.allowed", reason="no_request")
            return
        if self.http_request_allow_all:
            _debug.logic("test.cursor.allowed", reason="allow_all")
            return
        # The cookie is how a request served on a SERVER thread proves it is
        # this test's. Code running on the test's own thread under a request it
        # mocked -- a login that reads its durable cooldown row through
        # `registry.cursor()`, say -- needs no ticket, and has none to show.
        if threading.current_thread() is self._test_thread:
            _debug.logic("test.cursor.allowed", reason="test_thread")
            return
        http_request_required_key = self.http_request_key
        http_request_key = request.cookies.get(TEST_CURSOR_COOKIE_NAME)
        if http_request_key != http_request_required_key:
            expected = http_request_required_key
            _debug.logic(
                "test.cursor.cookie_rejected",
                test=self.canonical_tag,
                path=request.httprequest.path,
                expected=expected or None,
                got=http_request_key,
            )
            if not expected:
                expected = "None (request are not enabled)"
            _logger.log(
                RUNBOT,
                "Request with path %s has been ignored during test as it "
                "does not contain the test_cursor cookie or it is expired."
                ' (required "%s", got "%s")',
                request.httprequest.path,
                expected,
                http_request_key,
            )
            raise BadRequest(
                "Request ignored during test as it does not contain the required cookie."
            )
        _debug.logic("test.cursor.allowed", reason="cookie", key=http_request_key)

    _SOURCE_TAGS: dict[str, str] = {"is_query_count": "self.assertQueryCount"}
    """Tags derived by grepping a test's own source: {tag: needle}.

    Subclasses extend the mapping rather than overriding the method, so the
    source is read once however many of these tags are being selected.
    """

    def get_method_additional_tags(self, test_method: Callable | None) -> list[str]:
        selected = odoo.tools.config["test_tags"] or ""
        wanted = {
            tag: needle for tag, needle in self._SOURCE_TAGS.items() if tag in selected
        }
        if not wanted or test_method is None:
            return []
        try:
            method_source = inspect.getsource(test_method)
        except OSError, TypeError:
            _debug.logic(
                "test.tags.source_unavailable",
                method=getattr(test_method, "__qualname__", None),
            )
            return []
        found = [tag for tag, needle in wanted.items() if needle in method_source]
        _debug.logic(
            "test.tags.source_tags",
            method=getattr(test_method, "__qualname__", None),
            wanted=sorted(wanted),
            found=found,
        )
        return found


_muted_registry_logger = mute_logger(odoo.orm.runtime.registry._logger.name)


class _RegistryGuard:
    __slots__ = (
        "cache_sequences",
        "label",
        "models_touched",
        "registry",
        "start_invalidated",
        "start_sequence",
    )

    def __init__(self, registry: Registry, label: str) -> None:
        self.registry = registry
        self.label = label
        self.start_invalidated = registry.registry_invalidated
        self.start_sequence = registry.registry_sequence
        self.cache_sequences = dict(registry.cache_sequences)
        registry.registry_invalidated = False
        self.models_touched: set[str] | None = set()
        _debug.lifecycle(
            "test.registry.bound",
            cls=label,
            db=registry.db_name,
            sequence=self.start_sequence,
            invalidated=self.start_invalidated,
            ready=registry.ready,
            loaded=registry.loaded,
        )

    def note_touched_models(self) -> None:
        registry = self.registry
        if registry.registry_invalidated:
            touched = self.models_touched
            now = registry.invalidated_model_names
            self.models_touched = (
                None if touched is None or now is None else touched | now
            )

    def signal_changes(self) -> None:
        registry = self.registry
        if not registry.ready:
            _debug.logic("test.registry.signal_changes", ready=False)
            _logger.info("Skipping signal changes during tests")
            return
        if registry.registry_invalidated or registry.cache_invalidated:
            _logger.info("Simulating signal changes during tests")
        _debug.logic(
            "test.registry.signal_changes",
            ready=True,
            registry_invalidated=registry.registry_invalidated,
            caches=sorted(registry.cache_invalidated or ()),
        )
        if registry.registry_invalidated:
            self.note_touched_models()
            registry.registry_sequence += 1
        for cache_name in registry.cache_invalidated or ():
            registry.cache_sequences[cache_name] += 1
        registry.registry_invalidated = False
        registry.cache_invalidated.clear()

    def reset_changes(self) -> None:
        registry = self.registry
        rebuild = (
            self.start_sequence != registry.registry_sequence
        ) or registry.registry_invalidated
        self.note_touched_models()
        touched = self.models_touched
        with _debug.perf(
            "test.registry.reset_changes",
            cls=self.label,
            rebuild=rebuild,
            scope="all" if touched is None else len(touched),
            sequence=registry.registry_sequence,
            started_at=self.start_sequence,
        ):
            if rebuild:
                with registry.cursor() as cr:
                    if touched is None:
                        registry.setup_models(cr)
                    else:
                        registry.setup_models(cr, touched)
            registry.registry_invalidated = self.start_invalidated
            registry.registry_sequence = self.start_sequence
            with _muted_registry_logger:
                registry.clear_all_caches()
            registry.cache_invalidated.clear()
            registry.cache_sequences = self.cache_sequences


_ROUTING_LRUS = ("routing", "routing.rewrites")

_routing_controllers_fingerprints: dict[int, int] = {}


def _iter_controller_classes(cls: type = Controller) -> Iterator[type]:
    subclass: type
    for subclass in cls.__subclasses__():
        yield subclass
        yield from _iter_controller_classes(subclass)


def _get_controllers_fingerprint() -> int:
    # a set: __subclasses__() reorders as transient subclasses come and go
    return hash(
        frozenset(
            (id(cls), name, id(value))
            for cls in _iter_controller_classes()
            for name, value in vars(cls).items()
            if callable(value)
        )
    )


def sync_routing_with_controllers(registry: Any) -> None:
    # a routing map holds the controller methods it was built from: a test
    # that patches or adds one between two requests must not be served the
    # map an earlier test left warm
    fingerprint = _get_controllers_fingerprint()
    if _routing_controllers_fingerprints.get(id(registry)) == fingerprint:
        return
    _routing_controllers_fingerprints[id(registry)] = fingerprint
    if any(registry.ormcache_lrus[name] for name in _ROUTING_LRUS):
        _debug.logic("test.registry.routing_outdated", by="controllers_changed")
        registry.clear_cache("routing")


def _iter_cached_endpoints(value: Any) -> Iterator[Any]:
    if isinstance(value, Map):
        for rule in value.iter_rules():
            yield rule.endpoint
    elif isinstance(value, tuple):
        yield from (item for item in value if callable(item))


def _is_routed_by_current_code(endpoint: Any, resolved: dict[type, set[int]]) -> bool:
    while isinstance(endpoint, functools.partial):
        endpoint = endpoint.func
    owner = getattr(endpoint, "__self__", None)
    if not isinstance(owner, Controller):
        return True
    cls = type(owner)
    ids = resolved.get(cls)
    if ids is None:
        ids = resolved[cls] = {id(getattr(cls, name, None)) for name in dir(cls)}
    return id(endpoint.__func__) in ids


def _is_routing_built_from_replaced_code(
    registry: Any, marks: dict[str, tuple[int, int]]
) -> bool:
    # a map stored while a test patched a controller keeps the patched method
    # once the patch is undone; nothing invalidates a cache for a code change
    resolved: dict[type, set[int]] = {}
    for name in _ROUTING_LRUS:
        lru = registry.ormcache_lrus[name]
        if (mark := marks.get(name)) is not None and lru.stores == mark[1]:
            continue
        for value in lru.values():
            for endpoint in _iter_cached_endpoints(value):
                if not _is_routed_by_current_code(endpoint, resolved):
                    return True
    return False


# what the trusted caches are computed from besides rows: code, the registry's
# own attributes, the server options. A test that patches one of them with
# unittest.mock gets those caches cleared when the patch starts and again when
# it stops, as a test whose every cache started cold used to
_CACHE_FEEDING_MODULES = (
    "odoo.http",
    "odoo.modules",
    "odoo.tools.assets",
    "odoo.addons.base.models.assetsbundle",
    "odoo.addons.base.models.ir_asset",
    "odoo.addons.base.models.ir_http",
    "odoo.addons.base.models.ir_qweb",
    "odoo.addons.base.models.ir_ui_view",
    "odoo.addons.http_routing.",
    "odoo.addons.web.controllers.",
    "odoo.addons.website.models.",
)

_cache_owning_models: dict[int, frozenset[str]] = {}


def _get_cache_owning_models(registry: Any) -> frozenset[str]:
    owners = _cache_owning_models.get(id(registry))
    if owners is None:
        # what every model inherits from `base` (the view caches) is no reason
        # to call every model a source of those caches
        shared = set(registry["base"].__mro__) if "base" in registry else set()
        owners = _cache_owning_models[id(registry)] = frozenset(
            name
            for name, model_cls in registry.models.items()
            if any(
                getattr(getattr(value, "__cache__", None), "cache_name", None)
                in ROLLBACK_SAFE_CACHES
                for klass in model_cls.__mro__
                if klass not in shared
                for value in vars(klass).values()
            )
        )
    return owners


_ALL_TRUSTED_GROUPS = ("assets", "templates", "routing")

# a model's view archs are cached per model in "templates", whatever the model
_MODEL_GROUPS = ("templates",)

_PATCH_PLUMBING = frozenset(
    {
        "_is_patched_by_the_framework",
        "note_patch",
        "_note_patch",
        "watched_enter",
        "watched_patch_dict",
        "patch",
        "classPatch",
        "startPatcher",
        "startClassPatcher",
        "enterContext",
        "enterClassContext",
        "_enter_context",
    }
)


def _get_groups_fed_by(
    target: Any, attribute: str | None, registry: Any
) -> tuple[str, ...]:
    if isinstance(target, Registry):
        # its state, not the methods the framework itself patches in a test
        if callable(getattr(Registry, attribute or "", None)):
            return ()
        return _ALL_TRUSTED_GROUPS
    if target is config:
        return _ALL_TRUSTED_GROUPS
    if isinstance(target, dict) and any(target is d for d in vars(config).values()):
        return _ALL_TRUSTED_GROUPS
    if isinstance(target, types.ModuleType):
        module = target.__name__
    elif isinstance(target, type):
        if issubclass(target, Controller):
            return _ALL_TRUSTED_GROUPS
        if getattr(target, "_name", None) in _get_cache_owning_models(registry):
            return _ALL_TRUSTED_GROUPS
        module = target.__module__
        if issubclass(target, odoo.models.BaseModel):
            return (
                _ALL_TRUSTED_GROUPS
                if module.startswith(_CACHE_FEEDING_MODULES)
                else _MODEL_GROUPS
            )
    elif isinstance(target, odoo.models.BaseModel):
        return _MODEL_GROUPS
    else:
        module = type(target).__module__
    return _ALL_TRUSTED_GROUPS if module.startswith(_CACHE_FEEDING_MODULES) else ()


def _is_patched_by_the_framework() -> bool:
    # the patches this package applies around a request or a tour (the bus,
    # the tour flag, the test credentials) feed none of these caches, and
    # would otherwise make every browser test start cold
    frame: types.FrameType | None = sys._getframe()
    while frame is not None:
        module = frame.f_globals.get("__name__", "")
        if module in ("unittest.mock", "contextlib") or (
            module == __name__ and frame.f_code.co_name in _PATCH_PLUMBING
        ):
            frame = frame.f_back
            continue
        return module in (__name__, "odoo.tests.http")
    return False


class _TestCacheScope:
    __slots__ = ("carried", "marks", "registry", "untrusted")

    def __init__(self, registry: Any) -> None:
        self.registry = registry
        self.marks = _get_ormcache_marks(registry)
        self.carried = {
            name: set(registry.ormcache_lrus[name].keys())
            for name in ROLLBACK_SAFE_CACHES
        }
        self.untrusted: set[str] = set()

    @property
    def trusted(self) -> frozenset[str]:
        return ROLLBACK_SAFE_CACHES - self.untrusted

    def note_patch(self, target: Any, attribute: str | None) -> None:
        # a test used to start with every cache cold: what earlier tests left
        # in the trusted caches must not answer for the code it patches, and
        # what it stores under its patch is not trusted at its end
        lrus = {
            lru
            for group in _get_groups_fed_by(target, attribute, self.registry)
            for lru in CACHES_BY_KEY[group]
            if lru in ROLLBACK_SAFE_CACHES and lru not in self.untrusted
        }
        if not lrus or _is_patched_by_the_framework():
            return
        self.untrusted |= lrus
        _debug.logic(
            "test.registry.caches_patched",
            target=_patch_target_name(target),
            caches=sorted(lrus),
        )
        self.registry.discard_ormcache_entries({lru: self.carried[lru] for lru in lrus})

    def distrust(self, groups: Iterable[str]) -> None:
        # what the test stores in these from here on is not kept past its end
        lrus = {
            lru
            for group in groups
            for lru in CACHES_BY_KEY[group]
            if lru in ROLLBACK_SAFE_CACHES
        } - self.untrusted
        if not lrus:
            return
        self.untrusted |= lrus
        _debug.logic("test.registry.caches_distrusted", caches=sorted(lrus))


_cache_scope: list[_TestCacheScope] = []


def _note_patch(target: Any, attribute: str | None = None) -> None:
    for scope in _cache_scope:
        scope.note_patch(target, attribute)


def _watch_cache_feeding_patches() -> None:
    if getattr(mock._patch, "_clears_caches_it_feeds", False):
        return
    enter = mock._patch.__enter__
    patch_dict = mock._patch_dict._patch_dict  # type: ignore[attr-defined]

    def watched_enter(self: Any) -> Any:
        result = enter(self)
        _note_patch(self.target, self.attribute)
        return result

    def watched_patch_dict(self: Any) -> Any:
        result = patch_dict(self)
        _note_patch(self.in_dict)
        return result

    mock._patch.__enter__ = watched_enter  # type: ignore[method-assign]
    mock._patch_dict._patch_dict = watched_patch_dict  # type: ignore[attr-defined]
    mock._patch._clears_caches_it_feeds = True  # type: ignore[attr-defined]


def _get_ormcache_marks(registry: Any) -> dict[str, tuple[int, int]]:
    return {
        name: (lru.generation, lru.stores)
        for name, lru in registry.ormcache_lrus.items()
    }


def _get_ormcaches_touched(
    registry: Any, marks: dict[str, tuple[int, int]], trusted: frozenset[str]
) -> list[str]:
    stale = []
    for name, lru in registry.ormcache_lrus.items():
        mark = marks.get(name)
        if (
            mark is None
            or lru.generation != mark[0]
            or (lru.stores != mark[1] and name not in trusted)
        ):
            stale.append(name)
    return stale


class TransactionCase(BaseCase):
    muted_registry_logger = _muted_registry_logger
    _registry_guard: ClassVar[_RegistryGuard]
    _signal_changes_patcher: ClassVar[Any]
    commit_patcher: ClassVar[Any]
    rollback_patcher: ClassVar[Any]
    close_patcher: ClassVar[Any]
    _crypt_context_patcher: ClassVar[Any]
    _starts_freeze_time_itself = True

    @classmethod
    def _open_class_transaction(cls) -> None:
        # the whole of what binds the class to a database: a case that runs on
        # another backend (odoo/tests/in_memory_case.py) replaces this method
        # and inherits everything else, so a hosted class's own setUpClass
        # builds its fixtures in the environment the case actually uses
        cls.registry = Registry(get_db_name())
        cls._registry_guard = guard = _RegistryGuard(cls.registry, cls.__qualname__)
        cls.addClassCleanup(guard.reset_changes)

        cls._signal_changes_patcher = patch.object(
            cls.registry, "signal_changes", guard.signal_changes
        )
        cls.startClassPatcher(cls._signal_changes_patcher)

        cls._open_class_cursor()

        cls.addClassCleanup(release_stranded_test_cursors, cls.__name__)

        cls.env = api.Environment(cls.cr, api.SUPERUSER_ID, {})
        cls.env.transaction.default_env = cls.env

    @classmethod
    def setUpClass(cls) -> None:
        super().setUpClass()
        cls._open_class_transaction()
        _watch_cache_feeding_patches()

        if cls.freeze_time:
            cls.startClassPatcher(cls.freeze_time)

        def forbid(operation):
            def forbidden(*args, **kwargs):
                _debug.logic(
                    "test.cursor.forbidden_call",
                    test=current_test_tag(),
                    operation=operation,
                )
                traceback.print_stack()
                raise AssertionError(
                    f"Cannot {operation}() a cursor from inside a test: it would "
                    "leave a broken cursor for the test's own rollback. Roll back "
                    "to a specific savepoint instead, or open another cursor if "
                    "one is really necessary."
                )

            return forbidden

        cls.commit_patcher = patch.object(cls.cr, "commit", forbid("commit"))
        cls.startClassPatcher(cls.commit_patcher)
        cls.rollback_patcher = patch.object(cls.cr, "rollback", forbid("rollback"))
        cls.startClassPatcher(cls.rollback_patcher)
        cls.close_patcher = patch.object(cls.cr, "close", forbid("close"))
        cls.startClassPatcher(cls.close_patcher)

        def _get_crypt_context(self):
            return CryptContext(
                ["pbkdf2_sha512", "plaintext"],
                pbkdf2_sha512__rounds=1,
            )

        cls._crypt_context_patcher = patch(
            "odoo.addons.base.models.res_users.ResUsersPatchedInTest._get_crypt_context",
            _get_crypt_context,
        )
        cls.startClassPatcher(cls._crypt_context_patcher)
        if cls.registry_test_mode:
            cls.registry_enter_test_mode_cls()
        _debug.lifecycle(
            "test.case.transaction_ready",
            cls=cls.__qualname__,
            db=cls.cr.dbname,
            uid=cls.env.uid,
        )

    def setUp(self) -> None:
        super().setUp()

        def _check_registry_lock() -> None:
            _debug.logic(
                "test.lock.count_at_end",
                test=self.canonical_tag,
                held=_registry_test_lock.count,
            )
            if _registry_test_lock.count == 0:
                _logger.warning(
                    "The registry test lock is still released at the end of %s",
                    self.canonical_tag,
                )
            elif _registry_test_lock.count > 1:
                _logger.warning(
                    "The registry test lock was acquired more than once (%s) at the end of %s",
                    _registry_test_lock.count,
                    self.canonical_tag,
                )

        self.addCleanup(_check_registry_lock)
        if type(self)._registry_patched:
            self._redo_registry_resets_after_rollback()
        envs = self.env.transaction.envs
        for env in list(envs):
            self.addCleanup(env.clear)
        self.addCleanup(envs.update, list(envs))
        self.addCleanup(envs.clear)

        scope = _TestCacheScope(self.registry)
        _cache_scope[:] = [scope]
        self.addCleanup(self._clear_registry_caches, scope)

        cr = self.env.cr
        for callbacks in (
            cr.precommit,
            cr.postcommit,
            cr.prerollback,
            cr.postrollback,
        ):
            mark = callbacks.checkpoint(strict=True)
            self.addCleanup(callbacks.release, mark)
            self.addCleanup(callbacks.rollback_to, mark)

        with _debug.perf(
            "test.case.transaction_setup",
            cr=cr,
            test=self.canonical_tag,
            envs=len(envs),
            cleanups=len(self._cleanups),
        ):
            self.env.flush_all()

            # the cursor's own factory, so a class hosted on the DB-free tier
            # (odoo/tests/in_memory_case.py) takes its storage snapshot here
            savepoint = self.cr.savepoint(flush=False)
        self.addCleanup(savepoint.close)

    def _clear_registry_caches(self, scope: _TestCacheScope) -> None:
        # what a rolled-back transaction leaves in a cache is what it cleared or
        # stored there: a cache it cleared may hold values computed from its
        # writes, and so may one it filled unless every write that cache
        # depends on would have cleared it. The others keep entries the test
        # could not have influenced, which spares the next test their rebuild
        registry = self.registry
        _cache_scope.clear()
        marks = scope.marks
        if _is_routing_built_from_replaced_code(registry, marks):
            _debug.logic("test.registry.routing_outdated", by="patched_controllers")
            registry.clear_cache("routing")
        stale = _get_ormcaches_touched(registry, marks, scope.trusted)
        _debug.logic(
            "test.registry.caches_cleared",
            test=self.canonical_tag,
            caches=stale,
            kept=len(registry.ormcache_lrus) - len(stale),
        )
        registry.clear_ormcache_lrus(stale)
        # nothing signals in a test: the groups the test invalidated would
        # reach the next test's reset_changes() as its own
        registry.cache_invalidated.clear()

    def _redo_registry_resets_after_rollback(self) -> None:
        # in test mode `reset_changes` rebuilds from a test cursor, which still
        # sees what this test wrote: rebuilt from the test's own cleanup, the
        # models keep what the rollback then undoes, so the reset is redone
        # once the rollback and the environments' clearing are both done
        registry = self.registry
        reset_changes = registry.reset_changes
        resets: list[bool] = []

        def recording_reset_changes() -> None:
            if registry.registry_invalidated:
                resets.append(True)
            reset_changes()

        def redo() -> None:
            if not resets:
                return
            _debug.lifecycle(
                "test.registry.reset_after_rollback",
                test=self.canonical_tag,
                resets=len(resets),
            )
            registry.setup_models(self.cr)

        self.startPatcher(
            patch.object(registry, "reset_changes", recording_reset_changes)
        )
        self.addCleanup(redo)

    @contextmanager
    def sync_env_with_side_cursors(self) -> Generator[None]:
        # a side cursor shares this transaction but not this env: it reads
        # only what was flushed, and what it writes this cache cannot see
        env = self.env
        env.flush_all()
        _debug.lifecycle("test.registry.side_cursor_sync", test=self.canonical_tag)
        try:
            yield
        finally:
            env.invalidate_all()

    @contextmanager
    def leave_registry_test_mode(self) -> Generator[None]:
        # for what only a second connection shows: another transaction's
        # snapshot, its locks, or a cursor that outlives this one's failure
        cls = type(self)
        left = cls._registry_patched
        if left:
            cls.registry_leave_test_mode()
        _debug.lifecycle(
            "test.registry.real_cursor_scope", test=self.canonical_tag, left=left
        )
        try:
            yield
        finally:
            if left:
                cls._registry_enter_test_mode(cr=cls.cr)


class SingleTransactionCase(BaseCase):
    _registry_guard: ClassVar[_RegistryGuard]
    _signal_changes_patcher: ClassVar[Any]
    _starts_freeze_time_itself = True

    @classmethod
    def __init_subclass__(cls) -> None:
        super().__init_subclass__()
        if issubclass(cls, TransactionCase):
            _debug.logic("test.case.double_inheritance", cls=cls.__qualname__)
            _logger.warning(
                "%s inherits from both TransactionCase and SingleTransactionCase",
                cls.__name__,
            )

    @classmethod
    def setUpClass(cls) -> None:
        super().setUpClass()
        cls.registry = Registry(get_db_name())
        cls._registry_guard = guard = _RegistryGuard(cls.registry, cls.__qualname__)
        cls.addClassCleanup(guard.reset_changes)
        cls._signal_changes_patcher = patch.object(
            cls.registry, "signal_changes", guard.signal_changes
        )
        cls.startClassPatcher(cls._signal_changes_patcher)

        cls._open_class_cursor()

        if cls.freeze_time:
            cls.startClassPatcher(cls.freeze_time)

        cls.env = api.Environment(cls.cr, api.SUPERUSER_ID, {})
        cls.env.transaction.default_env = cls.env
        if cls.registry_test_mode:
            cls.registry_enter_test_mode_cls()
        _debug.lifecycle(
            "test.case.single_transaction_ready",
            cls=cls.__qualname__,
            db=cls.cr.dbname,
        )

    def setUp(self) -> None:
        super().setUp()
        with _debug.perf(
            "test.case.single_transaction_setup", cr=self.cr, test=self.canonical_tag
        ):
            self.env.flush_all()
