import contextlib
import contextvars
import dataclasses
import logging
from collections.abc import Callable, Sequence
from typing import Any

import odoo.service.common
import odoo.service.db
import odoo.service.model
from odoo.libs.debug_log import DebugLog
from odoo.libs.worker_thread import current_worker_thread

from .core import borrow_request

_logger = logging.getLogger(__name__)
_debug = DebugLog(__name__)


@dataclasses.dataclass(slots=True)
class RpcClient:
    address: str
    after_release: list[Callable[[], object]] = dataclasses.field(default_factory=list)

    def call_after_release(self, func: Callable[[], object]) -> None:
        self.after_release.append(func)

    def release(self) -> None:
        pending, self.after_release = self.after_release, []
        for func in pending:
            try:
                func()
            except Exception:
                _logger.warning(
                    "A write deferred past the RPC call's cursors failed",
                    exc_info=True,
                )


_RPC_CLIENT: contextvars.ContextVar[RpcClient | None] = contextvars.ContextVar(
    "rpc_client", default=None
)


def rpc_client() -> RpcClient | None:
    return _RPC_CLIENT.get()


def _get_rpc_dispatcher(service_name: str) -> Callable:
    match service_name:
        case "common":
            return odoo.service.common.dispatch
        case "db":
            return odoo.service.db.dispatch
        case "object":
            return odoo.service.model.dispatch
        case _:
            _debug.logic("http.dispatch_rpc.unknown_service", service=service_name)
            raise KeyError(service_name)


def _restore_thread_attr(thread: Any, attr: str, prev: Any, sentinel: Any) -> None:
    if prev is sentinel:
        with contextlib.suppress(AttributeError):
            delattr(thread, attr)
    else:
        setattr(thread, attr, prev)


def dispatch_rpc(service_name: str, method: str, params: Sequence[Any]) -> Any:
    thread = current_worker_thread()
    sentinel = object()
    prev_uid = getattr(thread, "uid", sentinel)
    prev_dbname = getattr(thread, "dbname", sentinel)
    with borrow_request() as req:
        client = (
            RpcClient(req.httprequest.remote_addr or "n/a") if req is not None else None
        )
        client_token = _RPC_CLIENT.set(client)
        thread.uid = None
        thread.dbname = None
        _debug.pipeline(
            "http.dispatch_rpc.begin",
            service=service_name,
            method=method,
            params=len(params),
        )
        try:
            dispatch = _get_rpc_dispatcher(service_name)
            with _debug.perf("http.dispatch_rpc", service=service_name, method=method):
                return dispatch(method, params)
        finally:
            _RPC_CLIENT.reset(client_token)
            _restore_thread_attr(thread, "uid", prev_uid, sentinel)
            _restore_thread_attr(thread, "dbname", prev_dbname, sentinel)
            if client is not None:
                client.release()
