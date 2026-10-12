import traceback
from collections.abc import Mapping
from typing import Any

import psycopg

from odoo.libs.debug_log import DebugLog
from odoo.models import BaseModel
from odoo.tools.translate import LazyGettext

from .core import request
from .settings import current as current_settings

_debug = DebugLog(__name__)

_TRACEBACK_HIDDEN = "Traceback hidden; enable dev_mode or read the server log."


def _is_exception_detail_hidden() -> bool:
    return bool(request) and not current_settings().dev_mode


def _get_exception_debug_text(exception: BaseException) -> str:
    if _is_exception_detail_hidden():
        return _TRACEBACK_HIDDEN
    return "".join(traceback.format_exception(exception))


def _client_context(context: Mapping[str, Any]) -> dict[str, Any]:
    return {
        key: (
            {"model": value._name, "ids": value.ids}
            if isinstance(value, BaseModel)
            else value
        )
        for key, value in context.items()
    }


def _qualified_name(cls: type) -> str:
    return f"{cls.__module__}.{cls.__name__}" if cls.__module__ else cls.__name__


def _exception_lineage(exception: BaseException) -> list[str]:
    # The client picks a dialog by exact class name; the ancestors let an
    # unregistered subclass of a known exception borrow its parent's dialog.
    return [
        _qualified_name(base)
        for base in type(exception).__mro__[1:]
        if issubclass(base, BaseException) and base not in (Exception, BaseException)
    ]


_OPAQUE_EXCEPTION_TYPES = (psycopg.Error, OSError)
_MASKED_EXCEPTION_MESSAGE = "Internal Server Error"


def serialize_exception(
    exception: BaseException,
    *,
    message: str | None = None,
    arguments: tuple[Any, ...] | None = None,
) -> dict[str, Any]:
    name = type(exception).__name__
    opaque = (
        isinstance(exception, _OPAQUE_EXCEPTION_TYPES) and _is_exception_detail_hidden()
    )

    if message is None:
        message = _MASKED_EXCEPTION_MESSAGE if opaque else str(exception)
    if arguments is None:
        arguments = (
            ()
            if opaque
            else tuple(
                str(arg) if isinstance(arg, LazyGettext) else arg
                for arg in exception.args
            )
        )

    _debug.logic(
        "http.exception.serialized",
        name=name,
        opaque=opaque,
        arguments=len(arguments),
        traceback_hidden=_is_exception_detail_hidden(),
    )
    return {
        "name": _qualified_name(type(exception)),
        "lineage": _exception_lineage(exception),
        "message": message,
        "arguments": arguments,
        "context": _client_context(getattr(exception, "context", {})),
        "debug": _get_exception_debug_text(exception),
    }
