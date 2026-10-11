from __future__ import annotations

import base64
import contextlib
import copy
import os
import re
import socket
import ssl
import threading
import time
import typing
import xmlrpc.client
from collections.abc import Buffer, Mapping
from urllib.parse import unquote

import requests
from requests.adapters import HTTPAdapter
from requests.auth import HTTPBasicAuth, HTTPDigestAuth
from requests.structures import CaseInsensitiveDict
from requests.utils import stream_decode_response_unicode
from urllib3 import HTTPConnectionPool, HTTPSConnectionPool, ProxyManager
from urllib3.exceptions import (
    ConnectTimeoutError,
    LocationParseError,
    MaxRetryError,
    NewConnectionError,
    ReadTimeoutError,
)
from urllib3.util import Timeout, parse_url
from urllib3.util.retry import RequestHistory, Retry

from odoo.libs import netguard, redact
from odoo.libs.debug_log import DebugLog
from odoo.libs.secret import MASK, Secret, SecretRenderedError

if typing.TYPE_CHECKING:
    from collections.abc import Callable, Iterator

    from requests.models import PreparedRequest, Response

    from odoo.libs.netguard import IPAddress, Policy, Resolver

__all__ = [
    "CALL_BUDGET",
    "DEFAULT_MAX_BYTES",
    "DEFAULT_MAX_REDIRECTS",
    "DEFAULT_TIMEOUT",
    "ENVIRONMENT_PROXY_VARIABLES",
    "SCHEMES",
    "CallBudget",
    "GuardedAdapter",
    "GuardedSession",
    "RefusedDestination",
    "ResponseTooLarge",
    "ResponseTooSlow",
    "configure_egress_proxy",
    "egress_proxy",
    "guarded_session",
]

DEFAULT_TIMEOUT = (10.0, 30.0)
DEFAULT_MAX_BYTES = 32 * 1024 * 1024
DEFAULT_MAX_REDIRECTS = 5
SCHEMES = ("http", "https")

_CONTENT_LENGTH = re.compile(r"[0-9]{1,19}")

ENVIRONMENT_PROXY_VARIABLES = (
    "HTTP_PROXY",
    "HTTPS_PROXY",
    "ALL_PROXY",
    "http_proxy",
    "https_proxy",
    "all_proxy",
)

_egress_proxy: str | None = None

_debug = DebugLog(__name__)


def configure_egress_proxy(url: str | None) -> None:
    global _egress_proxy  # noqa: PLW0603 - the process-wide proxy is configured at server startup
    if url:
        parts = parse_url(url)
        if parts.scheme not in SCHEMES or not parts.host:
            raise ValueError(
                f"the egress proxy must be an http:// or https:// URL, got {url!r}"
            )
    _egress_proxy = url or None


def egress_proxy() -> str | None:
    return _egress_proxy


class _Configured:
    pass


_CONFIGURED = _Configured()


class CallBudget:
    def __repr__(self) -> str:
        return "CALL_BUDGET"


CALL_BUDGET = CallBudget()

_UNWIND_SECONDS = 1.0


_FAILED_TRY = RequestHistory(None, None, None, None, None)


def _get_timeout_pair(timeout: typing.Any) -> tuple[float, float] | None:
    pair = timeout if isinstance(timeout, tuple) else (timeout, timeout)
    if len(pair) == 2 and all(
        isinstance(part, (int, float)) and part > 0 for part in pair
    ):
        return float(pair[0]), float(pair[1])
    return None


def _get_retry_after_max(retry: Retry, read: float) -> float:
    if not retry.respect_retry_after_header:
        return 0
    if retry.retry_after_max == Retry.DEFAULT_RETRY_AFTER_MAX:
        return read
    return retry.retry_after_max


def _get_retry_backoffs(retry: Retry) -> list[float] | None:
    if retry.total is None:
        return None
    without_jitter = retry.new(backoff_jitter=0.0)
    backoffs = []
    for failed in range(1, int(retry.total) + 1):
        backoff = without_jitter.new(history=(_FAILED_TRY,) * failed).get_backoff_time()
        if backoff:
            backoff = min(retry.backoff_max, backoff + retry.backoff_jitter)
        backoffs.append(float(backoff))
    return backoffs


class RefusedDestination(requests.exceptions.InvalidURL, netguard.DestinationRefused):
    def __init__(
        self,
        *args: object,
        request: PreparedRequest | None = None,
        kind: netguard.RefusalKind | None = None,
    ) -> None:
        requests.exceptions.RequestException.__init__(self, *args, request=request)
        if kind is not None:
            self.kind = kind


class ResponseTooLarge(requests.exceptions.RequestException):
    pass


class ResponseTooSlow(requests.exceptions.Timeout):
    pass


def _connect_failure(error: requests.exceptions.ConnectionError) -> str | None:
    cause = error.args[0] if error.args else None
    if not isinstance(cause, MaxRetryError):
        return None
    if isinstance(cause.reason, NewConnectionError):
        return "refused"
    if isinstance(cause.reason, ConnectTimeoutError):
        return "timeout"
    return None


class GuardedAdapter(HTTPAdapter):
    def __init__(
        self,
        policy: Policy,
        *,
        resolver: Resolver | None = None,
        timeout: float | tuple[float, float] = DEFAULT_TIMEOUT,
        max_bytes: int | None = DEFAULT_MAX_BYTES,
        max_seconds: float | CallBudget | None = None,
        proxy: str | _Configured | None = _CONFIGURED,
        ssl_context: ssl.SSLContext | None = None,
        **kwargs: typing.Any,
    ) -> None:
        self.policy = policy
        self.resolver = resolver
        self.timeout = timeout
        self.max_bytes = max_bytes
        self.max_seconds = max_seconds
        self._proxy = proxy
        self._ssl_context = ssl_context
        super().__init__(**kwargs)

    @property
    def proxy(self) -> str | None:
        if isinstance(self._proxy, _Configured):
            return _egress_proxy
        return self._proxy

    def get_call_budget(self, timeout: typing.Any = None) -> float | None:
        backoffs = _get_retry_backoffs(self.max_retries)
        pair = _get_timeout_pair(self.timeout if timeout is None else timeout)
        if backoffs is None or pair is None:
            return None
        retry = self.max_retries
        connect, read = pair
        retry_after = _get_retry_after_max(retry, read)
        tries = len(backoffs) + 1
        return (
            tries * (connect + read)
            + sum(max(retry_after, backoff) for backoff in backoffs)
            + netguard.TIMEOUTS_PASSED_OVER * connect
        )

    def get_max_seconds(self, timeout: typing.Any = None) -> float | None:
        if isinstance(self.max_seconds, CallBudget):
            return self.get_call_budget(timeout)
        return self.max_seconds

    def get_worst_case_seconds(self, timeout: typing.Any = None) -> float | None:
        limit = self.get_max_seconds(timeout)
        return None if limit is None else limit + _UNWIND_SECONDS

    @typing.override
    def init_poolmanager(self, *args: typing.Any, **kwargs: typing.Any) -> None:
        if self._ssl_context is not None:
            kwargs["ssl_context"] = self._ssl_context
        super().init_poolmanager(*args, **kwargs)
        self.poolmanager.pool_classes_by_scheme = _WATCHED_POOLS

    @typing.override
    def proxy_manager_for(self, proxy: str, **proxy_kwargs: typing.Any) -> typing.Any:
        if self._ssl_context is not None:
            proxy_kwargs["ssl_context"] = self._ssl_context
        manager = super().proxy_manager_for(proxy, **proxy_kwargs)
        if isinstance(manager, ProxyManager):
            manager.pool_classes_by_scheme = _WATCHED_POOLS
        return manager

    @typing.override
    def send(
        self,
        request: PreparedRequest,
        stream: bool = False,
        timeout: typing.Any = None,
        verify: typing.Any = True,
        cert: typing.Any = None,
        proxies: dict[str, str] | None = None,
        chain_started: float | None = None,
    ) -> Response:
        started = time.monotonic() if chain_started is None else chain_started
        if timeout is None:
            timeout = self.timeout
        limit = self.get_max_seconds(timeout)
        deadline = None if limit is None else started + limit
        addresses = request.__dict__.pop("netguard_addresses", None)
        if addresses is None:
            addresses = self._check(request, deadline)
        del proxies
        request.headers.pop("Proxy-Authorization", None)
        if deadline is not None:
            timeout = _Deadline.of(timeout, deadline)
        options = {
            "stream": stream,
            "timeout": timeout,
            "verify": verify,
            "cert": cert,
            "proxies": {},
        }
        try:
            response = self._send_pinned(request, addresses, options)
        except requests.exceptions.RequestException as error:
            if isinstance(timeout, _Deadline) and timeout.passed():
                raise _too_slow(timeout.deadline - started, request=request) from error
            raise
        return self._capped(response, limit, deadline)

    def _check(
        self, request: PreparedRequest, deadline: float | None = None
    ) -> tuple[IPAddress, ...]:
        if deadline is None:
            return self._check_now(request)
        resolved: dict[str, typing.Any] = {}

        def resolve() -> None:
            try:
                resolved["addresses"] = self._check_now(request)
            except BaseException as error:
                resolved["error"] = error

        resolver = threading.Thread(
            target=resolve, name="guarded_http-resolve", daemon=True
        )
        started = time.monotonic()
        resolver.start()
        resolver.join(max(deadline - started, 0.0))
        if resolver.is_alive():
            raise ResponseTooSlow(
                "the name was not resolved before the response deadline",
                request=request,
            )
        if "error" in resolved:
            raise resolved["error"]
        return resolved["addresses"]

    def _check_now(self, request: PreparedRequest) -> tuple[IPAddress, ...]:
        try:
            return netguard.check_url(
                request.url or "",
                policy=self.policy,
                resolver=self.resolver,
                schemes=SCHEMES,
            ).addresses
        except netguard.DestinationRefused as error:
            raise RefusedDestination(
                str(error), request=request, kind=error.kind
            ) from None

    def _send_pinned(
        self,
        request: PreparedRequest,
        addresses: tuple[IPAddress, ...],
        options: dict[str, typing.Any],
    ) -> Response:
        added_host = "Host" not in request.headers
        if added_host:
            request.headers["Host"] = parse_url(request.url or "").netloc or ""
        timeouts = 0
        try:
            for position, address in enumerate(addresses, start=1):
                request.netguard_address = str(address)
                _passing_over.active = position < len(addresses)
                try:
                    return super().send(request, **options)
                except requests.exceptions.ConnectionError as error:
                    failure = _connect_failure(error)
                    timeouts += failure == "timeout"
                    if (
                        position == len(addresses)
                        or failure is None
                        or timeouts > netguard.TIMEOUTS_PASSED_OVER
                    ):
                        raise
            raise AssertionError("check_host returns at least one address")
        finally:
            _passing_over.active = False
            del request.netguard_address
            if added_host:
                del request.headers["Host"]

    @typing.override
    def get_connection_with_tls_context(
        self,
        request: PreparedRequest,
        verify: typing.Any,
        proxies: dict[str, str] | None = None,
        cert: typing.Any = None,
    ) -> typing.Any:
        del proxies
        address = getattr(request, "netguard_address", None)
        if address is None:
            return super().get_connection_with_tls_context(
                request, verify, proxies={}, cert=cert
            )
        host_params, pool_kwargs = self.build_connection_pool_key_attributes(
            request, verify, cert
        )
        name = host_params["host"]
        host_params["host"] = address
        if host_params.get("scheme") == "https":
            pool_kwargs["assert_hostname"] = name
            pool_kwargs["server_hostname"] = name
        manager = self.proxy_manager_for(self.proxy) if self.proxy else self.poolmanager
        return manager.connection_from_host(**host_params, pool_kwargs=pool_kwargs)

    def request_url(self, request: PreparedRequest, proxies: typing.Any) -> str:
        del proxies
        address = getattr(request, "netguard_address", None)
        parts = parse_url(request.url or "")
        if address is None or not self.proxy or parts.scheme != "http":
            return super().request_url(request, {})
        host = f"[{address}]" if ":" in str(address) else str(address)
        port = 80 if parts.port is None else parts.port
        return f"http://{host}:{port}{request.path_url}"

    def _capped(
        self, response: Response, max_seconds: float | None, deadline: float | None
    ) -> Response:
        limit = self.max_bytes
        announced = response.headers.get("Content-Length", "")
        if (
            limit is not None
            and response.request.method != "HEAD"
            and _CONTENT_LENGTH.fullmatch(announced)
            and int(announced) > limit
        ):
            response.close()
            raise ResponseTooLarge(
                f"the response announces {announced} bytes, over the {limit} cap",
                response=response,
            )
        iter_content: Callable[..., Iterator[bytes]] = response.iter_content

        def too_slow() -> ResponseTooSlow:
            return _too_slow(max_seconds or 0.0, response=response)

        def capped_bytes(chunk_size: int | None) -> Iterator[bytes]:
            received = 0
            watchdog = _start_watchdog(lambda: _socket_of(response.raw), deadline)
            try:
                for chunk in iter_content(chunk_size, decode_unicode=False):
                    received += len(chunk)
                    if limit is not None and received > limit:
                        response.close()
                        raise ResponseTooLarge(
                            f"the response exceeds the {limit} byte cap",
                            response=response,
                        )
                    if watchdog is not None and watchdog.fired.is_set():
                        raise too_slow()
                    yield chunk
            except requests.exceptions.RequestException:
                if watchdog is not None and watchdog.fired.is_set():
                    raise too_slow() from None
                raise
            finally:
                if watchdog is not None:
                    watchdog.cancel()
            if watchdog is not None and watchdog.fired.is_set():
                raise too_slow()

        def capped(
            chunk_size: int | None = 1, decode_unicode: bool = False
        ) -> Iterator[typing.Any]:
            chunks = capped_bytes(chunk_size)
            if decode_unicode:
                return stream_decode_response_unicode(chunks, response)
            return chunks

        response.iter_content = capped
        return response


def _too_slow(max_seconds: float, **kwargs: typing.Any) -> ResponseTooSlow:
    return ResponseTooSlow(f"the response took longer than {max_seconds:g}s", **kwargs)


def _socket_of(raw: typing.Any) -> socket.socket | None:
    sock = getattr(getattr(raw, "connection", None), "sock", None)
    if sock is not None:
        return sock
    reader = getattr(getattr(raw, "_fp", None), "fp", None)
    return getattr(getattr(reader, "raw", None), "_sock", None)


class _Watchdog(threading.Timer):
    fired: threading.Event


def _start_watchdog(
    find_socket: Callable[[], socket.socket | None],
    deadline: float | None,
    fired: threading.Event | None = None,
) -> _Watchdog | None:
    if deadline is None:
        return None
    fired = fired or threading.Event()

    def expire() -> None:
        fired.set()
        sock = find_socket()
        if sock is not None:
            with contextlib.suppress(OSError):
                sock.shutdown(socket.SHUT_RDWR)

    watchdog = _Watchdog(max(deadline - time.monotonic(), 0.0), expire)
    watchdog.fired = fired
    watchdog.daemon = True
    watchdog.start()
    return watchdog


class _Deadline(Timeout):
    def __init__(
        self,
        connect: typing.Any,
        read: typing.Any,
        total: typing.Any = None,
        *,
        deadline: float,
        fired: threading.Event | None = None,
    ) -> None:
        super().__init__(total=total, connect=connect, read=read)
        self.deadline = deadline
        self.fired = fired or threading.Event()

    @classmethod
    def of(cls, timeout: typing.Any, deadline: float) -> _Deadline:
        if isinstance(timeout, Timeout):
            return cls(
                timeout._connect, timeout._read, timeout.total, deadline=deadline
            )
        connect, read = timeout if isinstance(timeout, tuple) else (timeout, timeout)
        return cls(connect, read, deadline=deadline)

    @typing.override
    def clone(self) -> _Deadline:
        return _Deadline(
            self._connect,
            self._read,
            self.total,
            deadline=self.deadline,
            fired=self.fired,
        )

    def passed(self) -> bool:
        return self.fired.is_set() or time.monotonic() >= self.deadline

    def _within(self, value: typing.Any) -> float:
        remaining = max(self.deadline - time.monotonic(), 0.001)
        value = Timeout.resolve_default_timeout(value)
        return remaining if value is None else min(value, remaining)

    @property
    @typing.override
    def connect_timeout(self) -> float:
        return self._within(super().connect_timeout)

    @property
    @typing.override
    def read_timeout(self) -> float:
        return self._within(super().read_timeout)


class _RetryWithinDeadline(Retry):
    deadline: float

    @typing.override
    def new(self, **kw: typing.Any) -> typing.Self:
        retry = super().new(**kw)
        retry.deadline = self.deadline
        return retry

    def _remaining(self) -> float:
        return max(self.deadline - time.monotonic(), 0.0)

    @typing.override
    def get_backoff_time(self) -> float:
        return min(super().get_backoff_time(), self._remaining())

    @typing.override
    def get_retry_after(self, response: typing.Any) -> float | None:
        seconds = super().get_retry_after(response)
        return None if seconds is None else min(seconds, self._remaining())


_RETRY_CLASSES_WITHIN_DEADLINE: dict[type, type] = {}


def _retry_within(retry: Retry, deadline: float) -> Retry:
    retry_class = type(retry)
    bounded_class = _RETRY_CLASSES_WITHIN_DEADLINE.get(retry_class)
    if bounded_class is None:
        bounded_class = _RETRY_CLASSES_WITHIN_DEADLINE.setdefault(
            retry_class,
            type(retry_class.__name__, (_RetryWithinDeadline, retry_class), {}),
        )
    bounded = copy.copy(retry)
    bounded.__class__ = bounded_class
    bounded.deadline = deadline
    return bounded


_passing_over = threading.local()


class _WatchedPool(HTTPConnectionPool):
    @typing.override
    def urlopen(
        self,
        method: str,
        url: str,
        body: typing.Any = None,
        headers: typing.Any = None,
        retries: typing.Any = None,
        *args: typing.Any,
        **kwargs: typing.Any,
    ) -> typing.Any:
        if (
            getattr(_passing_over, "active", False)
            and isinstance(retries, Retry)
            and retries.connect != 0
        ):
            retries = retries.new(connect=0)
        timeout = kwargs.get("timeout")
        if isinstance(timeout, _Deadline):
            if timeout.passed():
                timeout.fired.set()
                raise MaxRetryError(
                    self,
                    url,
                    ReadTimeoutError(self, url, "the response deadline passed"),
                )
            if isinstance(retries, Retry) and not isinstance(
                retries, _RetryWithinDeadline
            ):
                retries = _retry_within(retries, timeout.deadline)
        return super().urlopen(method, url, body, headers, retries, *args, **kwargs)

    @typing.override
    def _make_request(
        self,
        conn: typing.Any,
        method: str,
        url: str,
        *args: typing.Any,
        **kwargs: typing.Any,
    ) -> typing.Any:
        timeout = kwargs.get("timeout")
        make_request = super()._make_request
        if not isinstance(timeout, _Deadline):
            return make_request(conn, method, url, *args, **kwargs)

        watchdog = _start_watchdog(
            lambda: getattr(conn, "sock", None), timeout.deadline, timeout.fired
        )
        try:
            response = make_request(conn, method, url, *args, **kwargs)
        finally:
            if watchdog is not None:
                watchdog.cancel()
        drain_conn = response.drain_conn

        def drain_within_deadline() -> None:
            watchdog = _start_watchdog(
                lambda: _socket_of(response), timeout.deadline, timeout.fired
            )
            try:
                drain_conn()
            finally:
                if watchdog is not None:
                    watchdog.cancel()

        response.drain_conn = drain_within_deadline
        return response


class _WatchedHTTPConnectionPool(_WatchedPool, HTTPConnectionPool):
    pass


class _WatchedHTTPSConnectionPool(_WatchedPool, HTTPSConnectionPool):
    pass


_WATCHED_POOLS = {
    "http": _WatchedHTTPConnectionPool,
    "https": _WatchedHTTPSConnectionPool,
}


def _holds_secret(value: typing.Any) -> bool:
    if isinstance(value, Secret):
        return True
    if isinstance(value, Mapping):
        return any(_holds_secret(item) for item in value.values())
    if isinstance(value, (list, tuple)):
        return any(_holds_secret(item) for item in value)
    return False


def _revealed(value: typing.Any) -> typing.Any:
    if not _holds_secret(value):
        return value
    if isinstance(value, Secret):
        return value.reveal()
    if isinstance(value, Mapping):
        return {key: _revealed(item) for key, item in value.items()}
    revealed = [_revealed(item) for item in value]
    return revealed if isinstance(value, list) else tuple(revealed)


def _revealed_auth(auth: typing.Any) -> typing.Any:
    if isinstance(auth, (HTTPBasicAuth, HTTPDigestAuth)):
        pair = (auth.username, auth.password)
        revealed = _revealed(pair)
        return auth if revealed is pair else type(auth)(*revealed)
    if isinstance(auth, (tuple, list)) and len(auth) == 2:
        return _revealed(auth)
    return auth


def _is_rendered(value: typing.Any) -> bool:
    if isinstance(value, bytes):
        value = value.decode("latin-1")
    if not isinstance(value, str):
        return False
    if MASK in value:
        return True
    scheme, _, credentials = value.partition(" ")
    if scheme.lower() != "basic":
        return False
    try:
        decoded = base64.b64decode(credentials.strip(), validate=True)
    except ValueError:
        return False
    return MASK.encode() in decoded


def _refuse_rendered(prepared: PreparedRequest) -> None:
    url = prepared.url or ""
    if MASK in url or MASK in unquote(url):
        _debug.logic("guarded_http.secret_rendered", where="url")
        raise SecretRenderedError(
            "the URL carries a Secret rendered as text: pass the Secret itself, "
            "or build the URL with Secret.map()"
        )
    for name, value in prepared.headers.items():
        if _is_rendered(value):
            _debug.logic("guarded_http.secret_rendered", where="header", header=name)
            raise SecretRenderedError(
                f"the {name} header carries a Secret rendered as text: build it "
                "with Secret.prefixed() or Secret.map(), never str() or an f-string"
            )


class GuardedSession(requests.Session):  # noqa: E8518 -- the guard itself: it mounts GuardedAdapter for both schemes
    def __init__(self) -> None:
        super().__init__()
        self.trust_env = False

    @typing.override
    def merge_environment_settings(
        self,
        url: str | None,
        proxies: typing.Any,
        stream: typing.Any,
        verify: typing.Any,
        cert: typing.Any,
    ) -> dict[str, typing.Any]:
        if verify is True or verify is None:
            verify = (
                os.environ.get("REQUESTS_CA_BUNDLE")
                or os.environ.get("CURL_CA_BUNDLE")
                or verify
            )
        settings = super().merge_environment_settings(
            url, proxies, stream, verify, cert
        )
        settings["proxies"] = {}
        return settings

    @typing.override
    def prepare_request(self, request: requests.Request) -> PreparedRequest:
        given_url = request.url
        request = self._reveal_secrets(request)
        try:
            port = parse_url(request.url or "").port
        except LocationParseError:
            port = None
        if port == 0:
            raise RefusedDestination(
                f"{redact.mask_url(str(given_url))!r} names port 0, "
                "which no connection reaches",
                kind="syntax",
            )
        prepared = super().prepare_request(request)
        _refuse_rendered(prepared)
        return prepared

    def _reveal_secrets(self, request: requests.Request) -> requests.Request:
        revealed: dict[str, typing.Any] = {}
        if isinstance(request.url, Secret):
            revealed["url"] = request.url.reveal()
        auth = request.auth if request.auth is not None else self.auth
        if (auth_revealed := _revealed_auth(auth)) is not auth:
            revealed["auth"] = auth_revealed
        headers = request.headers or {}
        if (headers_revealed := _revealed(headers)) is not headers:
            revealed["headers"] = headers_revealed
        session_secrets = {
            name: value.reveal()
            for name, value in self.headers.items()
            if isinstance(value, Secret)
        }
        if session_secrets:
            merged = CaseInsensitiveDict(session_secrets)
            merged.update(revealed.get("headers", headers))
            revealed["headers"] = merged
        for name in ("params", "data", "json"):
            value = getattr(request, name)
            if (value_revealed := _revealed(value)) is not value:
                revealed[name] = value_revealed
        if not revealed:
            return request
        _debug.logic("guarded_http.secret_revealed", parts=sorted(revealed))
        request = copy.copy(request)
        for name, value in revealed.items():
            setattr(request, name, value)
        return request

    def get_worst_case_seconds(
        self, url: str, timeout: typing.Any = None
    ) -> float | None:
        if not isinstance(url, str):
            return None
        try:
            adapter = self.get_adapter(url)
        except requests.exceptions.InvalidSchema:
            return None
        if not isinstance(adapter, GuardedAdapter):
            return None
        return adapter.get_worst_case_seconds(timeout)

    @typing.override
    def rebuild_proxies(
        self, prepared_request: PreparedRequest, proxies: typing.Any
    ) -> dict[str, str]:
        prepared_request.headers.pop("Proxy-Authorization", None)
        return {}

    @typing.override
    def send(
        self,
        request: PreparedRequest,
        *,
        chain_started: float | None = None,
        **kwargs: typing.Any,
    ) -> Response:
        adapter = self.get_adapter(url=request.url or "")
        if isinstance(adapter, GuardedAdapter):
            started = time.monotonic() if chain_started is None else chain_started
            limit = adapter.get_max_seconds(kwargs.get("timeout"))
            request.netguard_addresses = adapter._check(
                request, None if limit is None else started + limit
            )
            kwargs["chain_started"] = started
        return super().send(request, **kwargs)


def guarded_session(
    policy: Policy,
    *,
    resolver: Resolver | None = None,
    timeout: float | tuple[float, float] = DEFAULT_TIMEOUT,
    max_bytes: int | None = DEFAULT_MAX_BYTES,
    max_seconds: float | CallBudget | None = None,
    max_redirects: int = DEFAULT_MAX_REDIRECTS,
    session_class: type[GuardedSession] = GuardedSession,
    **adapter_options: typing.Any,
) -> GuardedSession:
    adapter = GuardedAdapter(
        policy,
        resolver=resolver,
        timeout=timeout,
        max_bytes=max_bytes,
        max_seconds=max_seconds,
        **adapter_options,
    )
    session = session_class()
    for scheme in SCHEMES:
        session.mount(f"{scheme}://", adapter)
    session.max_redirects = max_redirects
    return session


class GuardedXmlRpcTransport(xmlrpc.client.Transport):
    def __init__(
        self,
        session: requests.Session,
        base_url: str,
        *,
        timeout: float | tuple[float, float] = DEFAULT_TIMEOUT,
    ) -> None:
        super().__init__()
        self._session = session
        self._base_url = base_url.rstrip("/")
        self._timeout = timeout

    @typing.override
    def request(
        self,
        host: str | tuple[str, dict[str, str]],
        handler: str,
        request_body: Buffer,
        verbose: bool = False,
    ) -> tuple[typing.Any, ...]:
        _, auth_headers, _ = self.get_host_info(host)
        url = f"{self._base_url}{handler}"
        response = self._session.post(
            url,
            # Requests measures len(memoryview) in elements and does not
            # recognize every PEP 688 buffer object as an HTTP body.
            data=request_body
            if isinstance(request_body, bytes)
            else memoryview(request_body).tobytes(),
            headers={"Content-Type": "text/xml", **dict(auth_headers or ())},
            timeout=self._timeout,
            allow_redirects=False,
        )
        if response.status_code != 200:
            raise xmlrpc.client.ProtocolError(
                url, response.status_code, response.reason, dict(response.headers)
            )
        del verbose
        parser, unmarshaller = self.getparser()
        parser.feed(response.content)
        parser.close()
        return unmarshaller.close()


def xmlrpc_proxy(
    session: requests.Session,
    url: str,
    *,
    timeout: float | tuple[float, float] = DEFAULT_TIMEOUT,
) -> xmlrpc.client.ServerProxy:
    parts = parse_url(url)
    base_url = f"{parts.scheme}://{parts.netloc}"
    return xmlrpc.client.ServerProxy(
        url,
        transport=GuardedXmlRpcTransport(session, base_url, timeout=timeout),
        allow_none=True,
    )
